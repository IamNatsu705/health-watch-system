"""Tạo payload MQTT v1 độc lập với phần cứng."""

import re
from datetime import datetime, timezone
from uuid import UUID, uuid4


EVENT_TYPES = {"fall_detected", "fall_acknowledged", "sos_pressed", "sos_released"}
DEVICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class DeviceMessageFactory:
    """Giữ boot_id và sequence nhất quán trong một lần chạy chương trình."""

    def __init__(self, device_id: str, boot_id: str | None = None):
        if not DEVICE_ID_PATTERN.fullmatch(device_id):
            raise ValueError("MQTT_DEVICE_ID chỉ được chứa chữ, số, dấu chấm, gạch dưới hoặc gạch ngang")
        self.device_id = device_id
        self.boot_id = str(UUID(boot_id)) if boot_id else str(uuid4())
        self._sequence = 0

    def _next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    def telemetry(
        self,
        *,
        heart_rate_bpm: int | None,
        finger_present: bool,
        steps_session: int,
        distance_m_session: float,
        calories_kcal_session: float,
    ) -> dict:
        return {
            "schema_version": 1,
            "device_id": self.device_id,
            "boot_id": self.boot_id,
            "sequence": self._next_sequence(),
            "measured_at": utc_now(),
            "metrics": {
                "heart_rate_bpm": heart_rate_bpm,
                "finger_present": bool(finger_present),
                "steps_session": int(steps_session),
                "distance_m_session": round(float(distance_m_session), 3),
                "calories_kcal_session": round(float(calories_kcal_session), 3),
            },
        }

    def event(self, event_type: str) -> dict:
        if event_type not in EVENT_TYPES:
            raise ValueError(f"Loại sự kiện MQTT không hợp lệ: {event_type}")
        return {
            "schema_version": 1,
            "event_id": str(uuid4()),
            "device_id": self.device_id,
            "boot_id": self.boot_id,
            "sequence": self._next_sequence(),
            "event_type": event_type,
            "occurred_at": utc_now(),
        }

    def status(self, state: str) -> dict:
        if state not in {"online", "offline"}:
            raise ValueError(f"Trạng thái MQTT không hợp lệ: {state}")
        return {
            "schema_version": 1,
            "device_id": self.device_id,
            "boot_id": self.boot_id,
            "state": state,
            "software_version": "health-watch-pi/0.1.0",
        }
