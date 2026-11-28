"""Tạo payload MQTT (telemetry v2, event/status/alert-state v1) độc lập với phần cứng."""

import re
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from processing.steps import ALGORITHM_NAME as STEP_ALGORITHM

SOFTWARE_VERSION = "health-watch-pi/0.2.0"
EVENT_TYPES = {
    "fall_detected", "fall_cancelled", "fall_alarm", "fall_acknowledged", "sos_pressed", "sos_released",
}
IMU_STATUSES = {"starting", "ok", "saturated", "error", "frozen"}
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
        imu_status: str,
        steps_algorithm_session: int,
        steps_ai_session: int | None,
        step_model: dict | None,
        walking: bool | None,
        walking_probability: float | None,
        cadence_spm: float | None,
        distance_m_session: float | None,
        calories_kcal_session: float | None,
        distance_basis: dict | None,
        session_started_at: str,
        uptime_s: float,
        clock_synced: bool,
    ) -> dict:
        if imu_status not in IMU_STATUSES:
            raise ValueError(f"imu_status không hợp lệ: {imu_status}")
        if (steps_ai_session is None) != (step_model is None):
            raise ValueError("steps_ai_session và step_model phải cùng có hoặc cùng không")

        def rounded(value, digits):
            return None if value is None else round(float(value), digits)

        return {
            "schema_version": 2,
            "device_id": self.device_id,
            "boot_id": self.boot_id,
            "sequence": self._next_sequence(),
            "measured_at": utc_now(),
            "session_started_at": session_started_at,
            "uptime_s": round(float(uptime_s), 1),
            "clock_synced": bool(clock_synced),
            "firmware_version": SOFTWARE_VERSION,
            "step_algorithm": STEP_ALGORITHM,
            "step_model": dict(step_model) if step_model else None,
            "distance_basis": dict(distance_basis) if distance_basis else None,
            "metrics": {
                "heart_rate_bpm": heart_rate_bpm,
                "finger_present": bool(finger_present),
                "imu_status": imu_status,
                "steps_algorithm_session": int(steps_algorithm_session),
                "steps_ai_session": None if steps_ai_session is None else int(steps_ai_session),
                "walking": None if walking is None else bool(walking),
                "walking_probability": rounded(walking_probability, 3),
                "cadence_spm": rounded(cadence_spm, 1),
                "distance_m_session": rounded(distance_m_session, 1),
                "calories_kcal_session": rounded(calories_kcal_session, 2),
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
            "software_version": SOFTWARE_VERSION,
        }

    def alert_state(
        self,
        *,
        buzzer_active: bool,
        red_led_active: bool,
        source: str,
        last_command_id: str | None,
        remote_remaining_s: float = 0,
    ) -> dict:
        if source not in {"normal", "remote", "sos", "fall"}:
            raise ValueError(f"Nguồn cảnh báo không hợp lệ: {source}")
        command_id = str(UUID(last_command_id)) if last_command_id else None
        now = datetime.now(timezone.utc)
        expires_at = None
        if source == "remote" and remote_remaining_s > 0:
            expires_at = (now + timedelta(seconds=remote_remaining_s)).isoformat(
                timespec="milliseconds"
            ).replace("+00:00", "Z")
        return {
            "schema_version": 1,
            "device_id": self.device_id,
            "boot_id": self.boot_id,
            "buzzer_active": bool(buzzer_active),
            "red_led_active": bool(red_led_active),
            "source": source,
            "last_command_id": command_id,
            "expires_at": expires_at,
            "reported_at": now.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        }
