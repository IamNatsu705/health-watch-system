"""Configuration shared by local backend processes."""

import os
import re

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://health_watch:health_watch@localhost:5432/health_watch"
)
MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USERNAME = os.environ.get("MQTT_USERNAME", "health_watch")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")

# Ngày (0h–24h) của số bước theo giờ địa phương người dùng.
LOCAL_TIMEZONE = os.environ.get("LOCAL_TIMEZONE", "Asia/Ho_Chi_Minh")
# Dữ liệu cũ hơn ngưỡng này không được coi là "đang cập nhật".
FRESH_DATA_S = float(os.environ.get("FRESH_DATA_S", "10"))

DEVICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def parse_device_ids(value: str) -> frozenset[str]:
    """``MQTT_DEVICES=pi-watch-001:matkhau,pi-watch-002:matkhau2`` → tập ID thiết bị thật.

    Cùng biến này được Mosquitto dùng để tạo tài khoản riêng cho từng Pi. Backend chỉ
    nhận dữ liệu của các ID có trong danh sách (không tự tạo thiết bị lạ).
    """
    ids = set()
    for item in filter(None, (part.strip() for part in value.split(","))):
        device_id = item.split(":", 1)[0].strip()
        if not DEVICE_ID_PATTERN.fullmatch(device_id):
            raise ValueError(f"ID thiết bị không hợp lệ trong MQTT_DEVICES: {device_id!r}")
        ids.add(device_id)
    return frozenset(ids)


DEVICE_IDS = parse_device_ids(os.environ.get("MQTT_DEVICES", ""))
