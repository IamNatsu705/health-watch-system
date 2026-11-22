"""Kiểm tra mạng và xác thực broker mà không publish dữ liệu cảm biến."""

import sys
import threading
from uuid import uuid4

import paho.mqtt.client as mqtt

from config import (
    MQTT_ENABLED,
    MQTT_HOST,
    MQTT_KEEPALIVE_S,
    MQTT_PASSWORD,
    MQTT_PORT,
    MQTT_USERNAME,
)
from mqtt_publisher import BrokerSettings


def main() -> int:
    if not MQTT_ENABLED:
        print("MQTT_ENABLED đang tắt trong .env", file=sys.stderr)
        return 1

    settings = BrokerSettings(
        host=MQTT_HOST,
        port=MQTT_PORT,
        username=MQTT_USERNAME,
        password=MQTT_PASSWORD,
        device_id="preflight",
        keepalive=MQTT_KEEPALIVE_S,
    )
    try:
        settings.validate()
    except ValueError as exc:
        print(f"Cấu hình MQTT không hợp lệ: {exc}", file=sys.stderr)
        return 1

    finished = threading.Event()
    outcome = {"ok": False, "reason": "hết thời gian chờ"}
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"health-watch-preflight-{uuid4().hex[:8]}",
    )
    client.username_pw_set(settings.username, settings.password)

    def on_connect(client, userdata, flags, reason_code, properties):
        outcome["ok"] = not reason_code.is_failure
        outcome["reason"] = str(reason_code)
        finished.set()

    def on_connect_fail(client, userdata):
        outcome["reason"] = "không mở được kết nối TCP tới broker"
        finished.set()

    client.on_connect = on_connect
    client.on_connect_fail = on_connect_fail
    client.connect_async(settings.host, settings.port, settings.keepalive)
    client.loop_start()
    try:
        finished.wait(timeout=10)
        if not outcome["ok"]:
            print(
                f"MQTT thất bại tại {settings.host}:{settings.port}: {outcome['reason']}",
                file=sys.stderr,
            )
            return 1
        print(
            f"MQTT OK: đã xác thực tới {settings.host}:{settings.port}; "
            "không publish dữ liệu thử."
        )
        client.disconnect()
        return 0
    finally:
        client.loop_stop()


if __name__ == "__main__":
    raise SystemExit(main())
