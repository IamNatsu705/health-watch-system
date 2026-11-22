"""End-to-end local check: MQTT -> ingest -> PostgreSQL -> HTTP API."""

import json
import time
from datetime import datetime, timezone
from urllib.request import urlopen
from uuid import uuid4

import paho.mqtt.client as mqtt
from sqlalchemy import delete, func, select

from backend.common.config import MQTT_HOST, MQTT_PASSWORD, MQTT_PORT, MQTT_USERNAME
from backend.common.database import SessionLocal
from backend.common.models import Device, DeviceEvent, TelemetrySample


def counts(device_id: str) -> tuple[int, int]:
    with SessionLocal() as db:
        samples = db.scalar(select(func.count()).select_from(TelemetrySample).where(TelemetrySample.device_id == device_id))
        events = db.scalar(select(func.count()).select_from(DeviceEvent).where(DeviceEvent.device_id == device_id))
    return samples, events


def publish(client: mqtt.Client, topic: str, data: dict):
    result = client.publish(topic, json.dumps(data), qos=1)
    result.wait_for_publish(timeout=5)
    if not result.is_published():
        raise RuntimeError(f"MQTT publish not confirmed: {topic}")


def main():
    device_id = f"smoke-{uuid4().hex[:12]}"
    boot_id = str(uuid4())
    topic = f"health/v1/devices/{device_id}"
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    telemetry = {
        "schema_version": 1, "device_id": device_id, "boot_id": boot_id,
        "sequence": 1, "measured_at": now,
        "metrics": {"heart_rate_bpm": 78, "finger_present": True,
                    "steps_session": 4, "distance_m_session": 2.8,
                    "calories_kcal_session": 0.15},
    }
    event = {
        "schema_version": 1, "event_id": str(uuid4()), "device_id": device_id,
        "boot_id": boot_id, "sequence": 1,
        "event_type": "sos_pressed", "occurred_at": now,
    }
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"smoke-{device_id}")
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
        client.loop_start()
        publish(client, f"{topic}/telemetry", telemetry)
        publish(client, f"{topic}/telemetry", telemetry)  # QoS 1 duplicate
        publish(client, f"{topic}/events", event)
        publish(client, f"{topic}/events", event)
        invalid = {**telemetry, "sequence": 2, "metrics": {"heart_rate_bpm": 100}}
        publish(client, f"{topic}/telemetry", invalid)

        for _ in range(30):
            if counts(device_id) == (1, 1):
                break
            time.sleep(0.2)
        time.sleep(0.5)  # Allow the invalid message to reach ingest.
        assert counts(device_id) == (1, 1), "Duplicate or invalid MQTT data was stored"
        with urlopen(f"http://api:8000/api/v1/devices/{device_id}/latest", timeout=5) as response:
            latest = json.load(response)
        assert latest["telemetry"]["heart_rate_bpm"] == 78
        with urlopen(f"http://api:8000/api/v1/devices/{device_id}/events", timeout=5) as response:
            events = json.load(response)
        assert len(events) == 1 and events[0]["event_type"] == "sos_pressed"
        print("PASS: MQTT -> ingest -> PostgreSQL -> API; duplicate and invalid messages rejected")
    finally:
        client.disconnect()
        client.loop_stop()
        with SessionLocal.begin() as db:
            db.execute(delete(TelemetrySample).where(TelemetrySample.device_id == device_id))
            db.execute(delete(DeviceEvent).where(DeviceEvent.device_id == device_id))
            db.execute(delete(Device).where(Device.id == device_id))


if __name__ == "__main__":
    main()
