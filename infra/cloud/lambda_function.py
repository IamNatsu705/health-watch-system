"""Read-only AWS Lambda API for telemetry stored by the AWS IoT DynamoDBv2 rule."""

import json
import os
import base64
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError


TABLE_NAME = os.environ.get("TABLE_NAME", "HealthWatchTelemetry")
ACTIVITY_TABLE_NAME = os.environ.get(
    "ACTIVITY_TABLE_NAME",
    "HealthWatchActivity",
)
DEVICE_IDS = [
    value.strip()
    for value in os.environ.get("DEVICE_IDS", "pi-watch-001").split(",")
    if value.strip()
]
LOCAL_TIMEZONE = os.environ.get("LOCAL_TIMEZONE", "Asia/Ho_Chi_Minh")
FRESH_DATA_S = int(os.environ.get("FRESH_DATA_S", "30"))
IOT_DATA_ENDPOINT = os.environ.get(
    "IOT_DATA_ENDPOINT",
    "https://ae9vwl9rpojp0-ats.iot.ap-southeast-2.amazonaws.com",
)

table = boto3.resource("dynamodb").Table(TABLE_NAME)
activity_table = boto3.resource("dynamodb").Table(ACTIVITY_TABLE_NAME)
iot_data = boto3.client("iot-data", endpoint_url=IOT_DATA_ENDPOINT)


def json_default(value):
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, default=json_default),
    }


def epoch_ms(value):
    return int(value) if value is not None else None


def iso_from_ms(value):
    value = epoch_ms(value)
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat().replace("+00:00", "Z")


def latest_item(device_id):
    result = table.query(
        KeyConditionExpression=Key("device_id").eq(device_id),
        ScanIndexForward=False,
        Limit=1,
    )
    items = result.get("Items", [])
    return items[0] if items else None


def utc_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def empty_alert_state():
    return {
        "known": False,
        "buzzer_active": False,
        "red_led_active": False,
        "source": "unknown",
        "expires_at": None,
        "reported_at": None,
        "pending": False,
        "pending_active": None,
        "pending_command_id": None,
    }


def alert_state_view(device_id):
    topic = f"health/v1/devices/{device_id}/alert-state"
    try:
        result = iot_data.get_retained_message(topic=topic)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {
            "ResourceNotFoundException",
            "ResourceNotFound",
        }:
            return empty_alert_state()
        raise

    payload = result.get("payload", b"")
    if hasattr(payload, "read"):
        payload = payload.read()
    if isinstance(payload, str):
        try:
            payload = base64.b64decode(payload)
        except ValueError:
            payload = payload.encode("utf-8")

    try:
        document = json.loads(bytes(payload).decode("utf-8"))
    except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return empty_alert_state()

    if document.get("device_id") != device_id:
        return empty_alert_state()
    return {
        "known": True,
        "buzzer_active": bool(document.get("buzzer_active")),
        "red_led_active": bool(document.get("red_led_active")),
        "source": document.get("source", "unknown"),
        "expires_at": document.get("expires_at"),
        "reported_at": document.get("reported_at"),
        "pending": False,
        "pending_active": None,
        "pending_command_id": None,
    }


def telemetry_view(item):
    metrics = item.get("metrics") or {}
    received_ms = epoch_ms(item.get("timestamp"))
    age_s = None if received_ms is None else max(0, (datetime.now(timezone.utc).timestamp() * 1000 - received_ms) / 1000)
    ai_steps = metrics.get("steps_ai_session")
    algorithm_steps = metrics.get("steps_algorithm_session")
    primary_source = "ai" if ai_steps is not None else "algorithm"
    distance_basis = item.get("distance_basis") or {}

    return {
        "device_id": item.get("device_id"),
        "boot_id": item.get("boot_id"),
        "sequence": item.get("sequence"),
        "schema_version": item.get("schema_version"),
        "legacy": (item.get("schema_version") or 1) < 2,
        "measured_at": item.get("measured_at"),
        "received_at": iso_from_ms(received_ms),
        "age_s": None if age_s is None else round(age_s, 1),
        "fresh": age_s is not None and age_s < FRESH_DATA_S,
        "clock_synced": item.get("clock_synced"),
        "clock_skew_s": None,
        "session_started_at": item.get("session_started_at"),
        "uptime_s": item.get("uptime_s"),
        "firmware_version": item.get("firmware_version"),
        "heart_rate_bpm": metrics.get("heart_rate_bpm"),
        "finger_present": metrics.get("finger_present"),
        "imu_status": metrics.get("imu_status"),
        "step_algorithm": item.get("step_algorithm"),
        "steps_algorithm_session": algorithm_steps,
        "steps_ai_session": ai_steps,
        "step_model": item.get("step_model"),
        "steps_primary_session": ai_steps if primary_source == "ai" else algorithm_steps,
        "steps_primary_source": primary_source,
        "walking": metrics.get("walking"),
        "walking_probability": metrics.get("walking_probability"),
        "cadence_spm": metrics.get("cadence_spm"),
        "distance_m_session": metrics.get("distance_m_session"),
        "calories_kcal_session": metrics.get("calories_kcal_session"),
        "step_length_m": distance_basis.get("step_length_m") if isinstance(distance_basis, dict) else None,
        "distance_method": distance_basis.get("method") if isinstance(distance_basis, dict) else None,
    }


def device_view(device_id, item):
    if item is None:
        return {
            "id": device_id,
            "name": device_id,
            "online": False,
            "last_seen_at": None,
            "last_seen_age_s": None,
            "firmware_version": None,
            "has_profile": False,
        }

    received_ms = epoch_ms(item.get("timestamp"))
    age_s = max(0, (datetime.now(timezone.utc).timestamp() * 1000 - received_ms) / 1000)
    return {
        "id": device_id,
        "name": device_id,
        "online": age_s < FRESH_DATA_S,
        "last_seen_at": iso_from_ms(received_ms),
        "last_seen_age_s": round(age_s, 1),
        "firmware_version": item.get("firmware_version"),
        "has_profile": False,
    }


def devices_view():
    result = [device_view(device_id, latest_item(device_id)) for device_id in DEVICE_IDS]
    result.sort(key=lambda item: (not item["online"], item["last_seen_age_s"] is None, item["last_seen_age_s"] or 0))
    return result


def latest_view(device_id):
    item = latest_item(device_id)
    if item is None:
        return None
    return {
        "device": device_view(device_id, item),
        "telemetry": telemetry_view(item),
        "remote_alert": alert_state_view(device_id),
    }


def remote_alert_view(device_id, body):
    item = latest_item(device_id)
    if item is None:
        return 404, {"detail": "Telemetry not found"}

    device = device_view(device_id, item)
    if not device["online"]:
        return 409, {"detail": "Device is offline or telemetry is stale"}

    active = body.get("active")
    duration_s = body.get("duration_s", 10)
    if not isinstance(active, bool):
        return 400, {"detail": "active must be boolean"}
    if isinstance(duration_s, bool) or not isinstance(duration_s, int) or not 1 <= duration_s <= 60:
        return 400, {"detail": "duration_s must be an integer from 1 to 60"}

    state = alert_state_view(device_id)
    if active and not state["known"]:
        return 409, {"detail": "No retained alert state has been received from the device"}
    if active and state["buzzer_active"]:
        return 409, {"detail": "The buzzer is already active"}
    if not active and state["buzzer_active"] and state["source"] in {"fall", "sos"}:
        return 409, {"detail": "A fall or SOS alarm must be stopped on the device"}

    command_id = str(uuid4())
    issued_at = utc_iso()
    document = {
        "schema_version": 1,
        "command_id": command_id,
        "device_id": device_id,
        "command_type": "remote_alert",
        "active": active,
        "duration_s": duration_s,
        "issued_at": issued_at,
    }
    iot_data.publish(
        topic=f"health/v1/devices/{device_id}/commands",
        qos=1,
        retain=False,
        payload=json.dumps(document, separators=(",", ":")).encode("utf-8"),
    )
    state.update(
        {
            "pending": True,
            "pending_active": active,
            "pending_command_id": command_id,
        }
    )
    return 202, {
        "accepted": True,
        "command_id": command_id,
        "device_id": device_id,
        "active": active,
        "duration_s": duration_s,
        "issued_at": issued_at,
        "state": state,
    }


def history_view(device_id, limit):
    result = table.query(
        KeyConditionExpression=Key("device_id").eq(device_id),
        ScanIndexForward=False,
        Limit=max(1, min(limit, 500)),
    )
    return [telemetry_view(item) for item in reversed(result.get("Items", []))]


def samples_since(device_id, start_ms):
    items = []
    kwargs = {
        "KeyConditionExpression": Key("device_id").eq(device_id) & Key("timestamp").gte(start_ms),
        "ScanIndexForward": True,
    }
    while True:
        result = table.query(**kwargs)
        items.extend(result.get("Items", []))
        key = result.get("LastEvaluatedKey")
        if not key:
            return items
        kwargs["ExclusiveStartKey"] = key


def daily_steps_view(device_id, days):
    days = max(1, min(days, 31))
    zone = ZoneInfo(LOCAL_TIMEZONE)
    today = datetime.now(zone).date()
    first_day = today - timedelta(days=days - 1)
    query_start = datetime.combine(first_day - timedelta(days=1), time.min, zone).astimezone(timezone.utc)
    items = samples_since(device_id, int(query_start.timestamp() * 1000))

    result = {}
    for offset in range(days):
        day = first_day + timedelta(days=offset)
        result[day.isoformat()] = {
            "date": day.isoformat(),
            "steps": 0,
            "source": None,
            "steps_ai": 0,
            "steps_algorithm": 0,
            "distance_m": 0.0,
            "calories_kcal": 0.0,
            "sessions": 0,
            "_sources": set(),
            "_sessions": set(),
        }

    previous = {}
    for item in items:
        metrics = item.get("metrics") or {}
        boot_id = str(item.get("boot_id") or "unknown")
        sample_day = datetime.fromtimestamp(epoch_ms(item.get("timestamp")) / 1000, zone).date().isoformat()
        values = {
            "algorithm": metrics.get("steps_algorithm_session"),
            "ai": metrics.get("steps_ai_session"),
            "distance_m": metrics.get("distance_m_session"),
            "calories_kcal": metrics.get("calories_kcal_session"),
        }

        deltas = {}
        for name, current in values.items():
            key = (boot_id, name)
            old = previous.get(key)
            if current is None:
                deltas[name] = None
            else:
                current = float(current)
                deltas[name] = current if old is None else max(0.0, current - old)
                previous[key] = current

        if sample_day not in result:
            continue
        row = result[sample_day]
        row["_sessions"].add(boot_id)
        row["steps_algorithm"] += int(deltas["algorithm"] or 0)
        if deltas["ai"] is not None:
            row["steps_ai"] += int(deltas["ai"])
            row["steps"] += int(deltas["ai"])
            row["_sources"].add("ai")
        else:
            row["steps"] += int(deltas["algorithm"] or 0)
            row["_sources"].add("algorithm")
        row["distance_m"] += float(deltas["distance_m"] or 0)
        row["calories_kcal"] += float(deltas["calories_kcal"] or 0)

    output = []
    for row in result.values():
        sources = row.pop("_sources")
        sessions = row.pop("_sessions")
        row["source"] = None if not sources else (next(iter(sources)) if len(sources) == 1 else "mixed")
        row["sessions"] = len(sessions)
        row["steps_ai"] = row["steps_ai"] if "ai" in sources else None
        row["distance_m"] = round(row["distance_m"], 1)
        row["calories_kcal"] = round(row["calories_kcal"], 1)
        output.append(row)
    return {"timezone": LOCAL_TIMEZONE, "days": output}


def integer_parameter(event, name, default):
    params = event.get("queryStringParameters") or {}
    try:
        return int(params.get(name, default))
    except (TypeError, ValueError):
        return default


def request_body(event):
    body = event.get("body")
    if body is None:
        return {}
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    if isinstance(body, dict):
        return body
    try:
        value = json.loads(body)
    except (TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def activity_view(body):
    session_id = body.get("session_id")
    action = body.get("action")
    device_id = body.get("device_id")

    if not isinstance(session_id, str) or not session_id.strip():
        return 400, {"detail": "session_id is required"}

    allowed_actions = {
        "dashboard_view",
        "device_select",
        "profile_update",
        "profile_clear",
        "remote_alert_start",
        "remote_alert_stop",
    }
    if action not in allowed_actions:
        return 400, {"detail": "Unsupported activity action"}

    timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    item = {
        "session_id": session_id.strip(),
        "timestamp": timestamp_ms,
        "event_id": str(uuid4()),
        "action": action,
        "created_at": iso_from_ms(timestamp_ms),
    }
    if isinstance(device_id, str) and device_id.strip():
        item["device_id"] = device_id.strip()

    activity_table.put_item(Item=item)
    return 201, {
        "accepted": True,
        "event_id": item["event_id"],
        "timestamp": timestamp_ms,
    }


def lambda_handler(event, context):
    request = (event.get("requestContext") or {}).get("http") or {}
    method = request.get("method", "GET")
    path = event.get("rawPath") or request.get("path") or ""
    path_parameters = event.get("pathParameters") or {}
    device_id = path_parameters.get("device_id") or event.get("device_id")

    if method == "GET" and path == "/api/v1/devices":
        return response(200, devices_view())

    # Keep the simple Lambda console test event working.
    if method == "GET" and not path and device_id:
        data = latest_view(device_id)
        return response(200, data) if data else response(404, {"detail": "Telemetry not found"})

    if method == "POST" and path == "/api/v1/activity":
        body = request_body(event)
        if body is None:
            return response(400, {"detail": "Request body must be a JSON object"})
        status_code, data = activity_view(body)
        return response(status_code, data)

    if not device_id or device_id not in DEVICE_IDS:
        return response(404, {"detail": "Device not found"})

    if method == "POST" and path.endswith("/commands/remote-alert"):
        body = request_body(event)
        if body is None:
            return response(400, {"detail": "Request body must be a JSON object"})
        status_code, data = remote_alert_view(device_id, body)
        return response(status_code, data)

    if method != "GET":
        return response(405, {"detail": "Method not allowed"})

    if path.endswith("/latest"):
        data = latest_view(device_id)
        return response(200, data) if data else response(404, {"detail": "Telemetry not found"})
    if path.endswith("/history"):
        return response(200, history_view(device_id, integer_parameter(event, "limit", 60)))
    if path.endswith("/steps/daily"):
        return response(200, daily_steps_view(device_id, integer_parameter(event, "days", 7)))
    if path.endswith("/events"):
        return response(200, [])
    if path.endswith("/profile"):
        return response(200, {"profile": None})

    return response(404, {"detail": "Route not found"})
