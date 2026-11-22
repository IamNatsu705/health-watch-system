"""Publish realistic demo telemetry and occasional alert events."""

import json
import logging
import math
import os
import time
from datetime import datetime, timezone
from uuid import uuid4

import paho.mqtt.client as mqtt

from backend.common.config import MQTT_HOST, MQTT_PASSWORD, MQTT_PORT, MQTT_USERNAME


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("health_watch.mock")
DEVICE_ID = os.environ.get("MOCK_DEVICE_ID", "pi-watch-mock-001")
BOOT_ID = str(uuid4())
BASE_TOPIC = f"health/v1/devices/{DEVICE_ID}"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def publish_json(client: mqtt.Client, suffix: str, document: dict, *, retain: bool = False):
    info = client.publish(f"{BASE_TOPIC}/{suffix}", json.dumps(document), qos=1, retain=retain)
    info.wait_for_publish(timeout=5)
    if not info.is_published():
        log.warning("Could not confirm publish: %s", suffix)


def main():
    status = {"schema_version": 1, "device_id": DEVICE_ID, "boot_id": BOOT_ID, "state": "offline"}
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"mock-{DEVICE_ID}")
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.will_set(f"{BASE_TOPIC}/status", json.dumps(status), qos=1, retain=True)
    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
            break
        except OSError as exc:
            log.warning("Waiting for MQTT broker: %s", exc)
            time.sleep(2)
    client.loop_start()
    status["state"] = "online"
    publish_json(client, "status", status, retain=True)
    log.info("Publishing mock device %s", DEVICE_ID)

    sequence = 0
    steps = 0
    try:
        while True:
            sequence += 1
            steps += 1 if sequence % 2 == 0 else 0
            finger_present = (sequence % 45) < 38
            bpm = round(76 + 8 * math.sin(sequence / 7)) if finger_present else None
            telemetry = {
                "schema_version": 1,
                "device_id": DEVICE_ID,
                "boot_id": BOOT_ID,
                "sequence": sequence,
                "measured_at": now_utc(),
                "metrics": {
                    "heart_rate_bpm": bpm,
                    "finger_present": finger_present,
                    "steps_session": steps,
                    "distance_m_session": round(steps * 0.7, 2),
                    "calories_kcal_session": round(steps * 0.7 / 1000 * 70 * 0.75, 3),
                },
            }
            publish_json(client, "telemetry", telemetry)

            event_type = {
                25: "fall_detected", 31: "fall_acknowledged",
                40: "sos_pressed", 43: "sos_released",
            }.get(sequence % 60)
            if event_type:
                event = {
                    "schema_version": 1,
                    "event_id": str(uuid4()),
                    "device_id": DEVICE_ID,
                    "boot_id": BOOT_ID,
                    "sequence": sequence,
                    "event_type": event_type,
                    "occurred_at": now_utc(),
                }
                publish_json(client, "events", event)
                log.info("Mock event: %s", event_type)
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Stopping mock publisher")
    finally:
        status["state"] = "offline"
        publish_json(client, "status", status, retain=True)
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
