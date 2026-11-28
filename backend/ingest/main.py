"""Subscribe to device topics and persist validated messages from registered devices only."""

import logging
import time
from datetime import datetime, timezone
from uuid import uuid4

import paho.mqtt.client as mqtt
from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from backend.common.config import DEVICE_IDS, MQTT_HOST, MQTT_PASSWORD, MQTT_PORT, MQTT_USERNAME
from backend.common.contracts import parse_message, parse_timestamp
from backend.common.database import SessionLocal
from backend.common.models import Device, DeviceEvent, TelemetrySample


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("health_watch.ingest")

# Giới hạn vật lý để chặn bộ đếm hỏng: chạy nhanh nhất ~4 bước/s; AI cộng theo cửa sổ 5 s
# và thuật toán cộng cả chuỗi 6 bước một lúc nên cho thêm biên.
MAX_STEPS_PER_S = 5.0
STEP_BURST_ALLOWANCE = 30


class RejectedMessage(ValueError):
    """Bản tin hợp lệ về cú pháp nhưng mâu thuẫn với dữ liệu đã lưu."""


def insert_ignore(db: Session, model, values: dict, conflict_columns: list[str]):
    dialect = db.get_bind().dialect.name
    insert = postgresql.insert if dialect == "postgresql" else sqlite.insert
    return db.execute(insert(model).values(**values).on_conflict_do_nothing(index_elements=conflict_columns))


def _neighbours(db: Session, device_id: str, boot_id: str, sequence: int):
    columns = (TelemetrySample.sequence, TelemetrySample.steps_session,
               TelemetrySample.steps_ai_session, TelemetrySample.uptime_s)
    base = select(*columns).where(TelemetrySample.device_id == device_id,
                                  TelemetrySample.boot_id == boot_id)
    before = db.execute(base.where(TelemetrySample.sequence < sequence)
                        .order_by(TelemetrySample.sequence.desc()).limit(1)).first()
    after = db.execute(base.where(TelemetrySample.sequence > sequence)
                       .order_by(TelemetrySample.sequence.asc()).limit(1)).first()
    return before, after


def check_step_progress(db: Session, document: dict) -> None:
    """Trong một boot_id, bộ đếm chỉ tăng và không tăng nhanh hơn giới hạn vật lý."""
    metrics = document["metrics"]
    before, after = _neighbours(db, document["device_id"], document["boot_id"], document["sequence"])
    for name, value in (("steps_session", metrics["steps_algorithm_session"]),
                        ("steps_ai_session", metrics["steps_ai_session"])):
        if value is None:
            continue
        earlier = getattr(before, name) if before else None
        later = getattr(after, name) if after else None
        if earlier is not None and value < earlier:
            raise RejectedMessage(f"{name} giảm từ {earlier} xuống {value} trong cùng phiên")
        if later is not None and value > later:
            raise RejectedMessage(f"{name} lớn hơn bản tin sau ({later}) trong cùng phiên")
        if earlier is not None and before.uptime_s is not None:
            elapsed = max(0.0, document["uptime_s"] - before.uptime_s)
            if value - earlier > MAX_STEPS_PER_S * elapsed + STEP_BURST_ALLOWANCE:
                raise RejectedMessage(f"{name} tăng {value - earlier} bước trong {elapsed:.1f} s")
        elif earlier is None and value > MAX_STEPS_PER_S * document["uptime_s"] + STEP_BURST_ALLOWANCE:
            raise RejectedMessage(f"{name}={value} vượt quá thời gian chạy {document['uptime_s']} s")


def _device(db: Session, device_id: str, received_at: datetime, seen: bool = True) -> Device:
    insert_ignore(db, Device, {"id": device_id, "name": device_id, "online": False}, ["id"])
    device = db.get(Device, device_id)
    if seen:
        device.last_seen_at = received_at
    return device


def save_message(kind: str, document: dict, session_factory=SessionLocal, received_at: datetime | None = None,
                 retained: bool = False) -> bool:
    """Lưu bản tin; trả False nếu là bản trùng (QoS 1 giao lại).

    ``retained``: broker giao lại status cũ khi ingest kết nối. Bản đó không chứng minh
    thiết bị đang sống, nên không được làm thiết bị hiện "online".
    """
    received_at = received_at or datetime.now(timezone.utc)
    device_id = document["device_id"]
    with session_factory.begin() as db:
        if kind == "status":
            device = _device(db, device_id, received_at, seen=not retained)
            device.firmware_version = document["software_version"]
            if retained:
                if document["state"] == "offline" and device.current_boot_id in (None, document["boot_id"]):
                    device.online = False
                return True
            device.last_status_at = received_at
            if document["state"] == "online":
                device.online = True
                device.current_boot_id = document["boot_id"]
            elif device.current_boot_id in (None, document["boot_id"]):
                device.online = False
            else:
                log.info("Bỏ Last Will cũ của %s (boot %s)", device_id, document["boot_id"])
            return True

        if kind == "telemetry":
            check_step_progress(db, document)
            device = _device(db, device_id, received_at)
            device.online = True
            device.firmware_version = document["firmware_version"]
            device.current_boot_id = document["boot_id"]
            metrics = document["metrics"]
            measured_at = parse_timestamp(document["measured_at"])
            model = document["step_model"] or {}
            basis = document["distance_basis"] or {}
            result = insert_ignore(db, TelemetrySample, {
                "device_id": device_id,
                "boot_id": document["boot_id"],
                "sequence": document["sequence"],
                "schema_version": document["schema_version"],
                "measured_at": measured_at,
                "received_at": received_at,
                "clock_synced": document["clock_synced"],
                "clock_skew_s": (measured_at - received_at).total_seconds(),
                "session_started_at": parse_timestamp(document["session_started_at"]),
                "uptime_s": document["uptime_s"],
                "firmware_version": document["firmware_version"],
                "heart_rate_bpm": metrics["heart_rate_bpm"],
                "finger_present": metrics["finger_present"],
                "imu_status": metrics["imu_status"],
                "step_algorithm": document["step_algorithm"],
                "steps_session": metrics["steps_algorithm_session"],
                "steps_ai_session": metrics["steps_ai_session"],
                "step_model_name": model.get("name"),
                "step_model_version": model.get("version"),
                "walking": metrics["walking"],
                "walking_probability": metrics["walking_probability"],
                "cadence_spm": metrics["cadence_spm"],
                "distance_m_session": metrics["distance_m_session"],
                "calories_kcal_session": metrics["calories_kcal_session"],
                "step_length_m": basis.get("step_length_m"),
                "distance_method": basis.get("method"),
            }, ["device_id", "boot_id", "sequence"])
            return result.rowcount != 0

        if kind == "events":
            device = _device(db, device_id, received_at)
            device.online = True
            result = insert_ignore(db, DeviceEvent, {
                "event_id": document["event_id"],
                "device_id": device_id,
                "boot_id": document["boot_id"],
                "sequence": document["sequence"],
                "event_type": document["event_type"],
                "occurred_at": parse_timestamp(document["occurred_at"]),
                "received_at": received_at,
            }, ["event_id"])
            return result.rowcount != 0
    raise ValueError(f"loại bản tin không hỗ trợ: {kind}")


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        log.error("MQTT connection failed: %s", reason_code)
        return
    for suffix in ("telemetry", "events", "status"):
        client.subscribe(f"health/v1/devices/+/{suffix}", qos=1)
    log.info("Subscribed to device topics; registered devices: %s", ", ".join(sorted(DEVICE_IDS)))


def on_message(client, userdata, message):
    try:
        kind, document = parse_message(message.topic, message.payload, DEVICE_IDS)
    except (ValueError, KeyError) as exc:
        log.warning("Rejected %s: %s", message.topic, exc)
        return
    try:
        stored = save_message(kind, document, retained=bool(getattr(message, "retain", False)))
    except RejectedMessage as exc:
        log.warning("Rejected %s: %s", message.topic, exc)
        return
    except Exception:
        log.exception("Failed to save message from %s", message.topic)
        return
    if stored:
        log.debug("Stored %s from %s", kind, document["device_id"])


def main():
    if not DEVICE_IDS:
        raise SystemExit("MQTT_DEVICES trống: chưa đăng ký thiết bị thật nào, ingest không nhận dữ liệu.")
    # Hậu tố ngẫu nhiên: client khác (kể cả một Pi) không đoán được ID để chiếm kết nối.
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"health-watch-ingest-{uuid4().hex[:12]}")
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
