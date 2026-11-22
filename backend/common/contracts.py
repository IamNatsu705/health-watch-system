"""Load MQTT JSON schemas and validate a topic against its payload."""

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker, ValidationError


CONTRACT_DIR = Path(__file__).resolve().parents[2] / "contracts" / "mqtt"
TOPIC_PREFIX = ("health", "v1", "devices")


@lru_cache(maxsize=2)
def validator(kind: str) -> Draft202012Validator:
    name = {"telemetry": "telemetry.v1.schema.json", "events": "event.v1.schema.json"}[kind]
    schema = json.loads((CONTRACT_DIR / name).read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def parse_message(topic: str, payload: bytes) -> tuple[str, dict]:
    parts = topic.split("/")
    if len(parts) != 5 or tuple(parts[:3]) != TOPIC_PREFIX or parts[4] not in {"telemetry", "events", "status"}:
        raise ValueError("unexpected MQTT topic")
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid JSON payload") from exc
    if not isinstance(document, dict) or document.get("device_id") != parts[3]:
        raise ValueError("device_id does not match topic")
    kind = parts[4]
    if kind == "status":
        if document.get("schema_version") != 1 or document.get("state") not in {"online", "offline"}:
            raise ValueError("invalid status payload")
    else:
        try:
            validator(kind).validate(document)
        except ValidationError as exc:
            raise ValueError(exc.message) from exc
    return kind, document
