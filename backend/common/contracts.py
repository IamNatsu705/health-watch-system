"""Load MQTT JSON schemas and validate a topic against its payload."""

import json
import math
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

CONTRACT_DIR = Path(__file__).resolve().parents[2] / "contracts" / "mqtt"
TOPIC_PREFIX = ("health", "v1", "devices")
SCHEMAS = {
    "telemetry": "telemetry.v2.schema.json",
    "events": "event.v1.schema.json",
    "status": "status.v1.schema.json",
    "config": "config.v1.schema.json",
}
REQUIRED_FORMATS = ("date-time", "uuid")


@lru_cache(maxsize=None)
def validator(kind: str) -> Draft202012Validator:
    schema = json.loads((CONTRACT_DIR / SCHEMAS[kind]).read_text(encoding="utf-8"))
    checker = FormatChecker()
    missing = [name for name in REQUIRED_FORMATS if name not in checker.checkers]
    if missing:
        # Không có rfc3339-validator thì jsonschema bỏ qua "format" mà không báo lỗi.
        raise RuntimeError(f"jsonschema thiếu bộ kiểm tra format {missing}; cài jsonschema[format-nongpl]")
    return Draft202012Validator(schema, format_checker=checker)


def _reject_constant(value: str):
    raise ValueError(f"giá trị số không hợp lệ: {value}")


def loads_strict(payload: bytes | str):
    """JSON chuẩn: từ chối NaN/Infinity (Python mặc định chấp nhận)."""
    try:
        return json.loads(payload, parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid JSON payload") from exc


def parse_timestamp(text: str) -> datetime:
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("timestamp phải có múi giờ")
    return value.astimezone(timezone.utc)


def validate(kind: str, document: dict) -> None:
    try:
        validator(kind).validate(document)
    except ValidationError as exc:
        location = "/".join(str(part) for part in exc.absolute_path)
        raise ValueError(f"{location or 'payload'}: {exc.message}") from exc


def parse_message(topic: str, payload: bytes, allowed_devices: frozenset[str] | set[str]) -> tuple[str, dict]:
    parts = topic.split("/")
    if len(parts) != 5 or tuple(parts[:3]) != TOPIC_PREFIX or parts[4] not in {"telemetry", "events", "status"}:
        raise ValueError("unexpected MQTT topic")
    if parts[3] not in allowed_devices:
        raise ValueError(f"thiết bị {parts[3]!r} không có trong MQTT_DEVICES")
    document = loads_strict(payload)
    if not isinstance(document, dict) or document.get("device_id") != parts[3]:
        raise ValueError("device_id does not match topic")
    kind = parts[4]
    validate(kind, document)
    if kind == "telemetry":
        for key in ("measured_at", "session_started_at"):
            parse_timestamp(document[key])
        for value in document["metrics"].values():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("số không hữu hạn")
    elif kind == "events":
        parse_timestamp(document["occurred_at"])
    return kind, document
