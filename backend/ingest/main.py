"""Subscribe to device topics and persist validated messages."""

import logging
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from sqlalchemy.dialects.postgresql import insert

from backend.common.config import MQTT_HOST, MQTT_PASSWORD, MQTT_PORT, MQTT_USERNAME
from backend.common.contracts import parse_message
from backend.common.database import SessionLocal
from backend.common.models import Device, DeviceEvent, TelemetrySample


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("health_watch.ingest")


def save_message(kind: str, document: dict) -> None:
    received_at = datetime.now(timezone.utc)
    device_id = document["device_id"]
    with SessionLocal.begin() as db:
        db.execute(
            insert(Device)
            .values(id=device_id, name=device_id, online=kind != "status" or document["state"] == "online", last_seen_at=received_at)
            .on_conflict_do_nothing(index_elements=["id"])
        )
        device = db.get(Device, device_id)
        device.last_seen_at = received_at
        device.online = (document["state"] == "online") if kind == "status" else True

        if kind == "telemetry":
            metrics = document["metrics"]
            statement = insert(TelemetrySample).values(
                device_id=device_id,
                boot_id=document["boot_id"],
                sequence=document["sequence"],
                measured_at=datetime.fromisoformat(document["measured_at"].replace("Z", "+00:00")),
                received_at=received_at,
                **metrics,
            ).on_conflict_do_nothing(constraint="uq_telemetry_identity")
            db.execute(statement)
        elif kind == "events":
            statement = insert(DeviceEvent).values(
                event_id=document["event_id"],
                device_id=device_id,
                boot_id=document["boot_id"],
                sequence=document["sequence"],
                event_type=document["event_type"],
                occurred_at=datetime.fromisoformat(document["occurred_at"].replace("Z", "+00:00")),
                received_at=received_at,
            ).on_conflict_do_nothing(index_elements=["event_id"])
            db.execute(statement)


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        log.error("MQTT connection failed: %s", reason_code)
        return
    client.subscribe("health/v1/devices/+/telemetry", qos=1)
    client.subscribe("health/v1/devices/+/events", qos=1)
    client.subscribe("health/v1/devices/+/status", qos=1)
    log.info("Subscribed to device topics")


def on_message(client, userdata, message):
    try:
        kind, document = parse_message(message.topic, message.payload)
    except (ValueError, KeyError) as exc:
        log.warning("Rejected %s: %s", message.topic, exc)
        return
    try:
        save_message(kind, document)
    except Exception:
        log.exception("Failed to save message from %s", message.topic)
        return
    log.info("Stored %s from %s", kind, document["device_id"])


def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="health-watch-ingest")
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message
    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
            break
        except OSError as exc:
            log.warning("Waiting for MQTT broker: %s", exc)
            time.sleep(2)
    client.loop_forever(retry_first_connection=True)


if __name__ == "__main__":
    main()
