"""MQTT publisher dedicated to short-lived commands sent from the API to a Pi."""

import json
import logging
import threading
import time
from datetime import datetime, timezone
from uuid import UUID

import paho.mqtt.client as mqtt

from backend.common.config import MQTT_HOST, MQTT_PASSWORD, MQTT_PORT, MQTT_USERNAME


log = logging.getLogger("health_watch.api.commands")


class CommandConflict(RuntimeError):
    """The real device state makes the requested command unsafe or redundant."""


class MqttCommandPublisher:
    """Maintain one broker connection and publish non-retained QoS 1 commands."""

    def __init__(self) -> None:
        self._connected = threading.Event()
        self._lock = threading.Lock()
        self._states: dict[str, dict] = {}
        self._pending: dict[str, dict] = {}
        self._started = False
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="health-watch-api-commands",
        )
        self.client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            log.warning("MQTT rejected API connection: %s", reason_code)
            return
        result, _ = client.subscribe("health/v1/devices/+/alert-state", qos=1)
        if result != mqtt.MQTT_ERR_SUCCESS:
            log.warning("Could not subscribe to device alert state: %s", mqtt.error_string(result))
        self._connected.set()
        log.info("API command publisher connected to MQTT")

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties) -> None:
        self._connected.clear()
        if self._started:
            log.warning("API command publisher disconnected from MQTT: %s", reason_code)

    def _on_message(self, client, userdata, message) -> None:
        try:
            parts = message.topic.split("/")
            if len(parts) != 5 or parts[:3] != ["health", "v1", "devices"] or parts[4] != "alert-state":
                raise ValueError("unexpected topic")
            document = json.loads(message.payload.decode("utf-8"))
            device_id = parts[3]
            if not isinstance(document, dict) or document.get("device_id") != device_id:
                raise ValueError("device_id does not match topic")
            if document.get("schema_version") != 1:
                raise ValueError("unsupported schema")
            if not isinstance(document.get("buzzer_active"), bool):
                raise ValueError("buzzer_active must be boolean")
            if not isinstance(document.get("red_led_active"), bool):
                raise ValueError("red_led_active must be boolean")
            if document.get("source") not in {"normal", "remote", "sos", "fall"}:
                raise ValueError("invalid source")
            command_id = document.get("last_command_id")
            if command_id is not None:
                document["last_command_id"] = str(UUID(str(command_id)))
            reported_at = datetime.fromisoformat(document["reported_at"].replace("Z", "+00:00"))
            if reported_at.tzinfo is None:
                raise ValueError("reported_at must include timezone")
        except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            log.warning("Rejected alert state: %s", exc)
            return

        with self._lock:
            self._states[device_id] = dict(document)
            pending = self._pending.get(device_id)
            if pending and (
                document.get("last_command_id") == pending["command_id"]
                or document["buzzer_active"] == pending["active"]
            ):
                self._pending.pop(device_id, None)

    def _cleanup_pending_locked(self, device_id: str) -> None:
        pending = self._pending.get(device_id)
        if pending and time.monotonic() >= pending["deadline"]:
            self._pending.pop(device_id, None)

    def state_view(self, device_id: str) -> dict:
        with self._lock:
            self._cleanup_pending_locked(device_id)
            state = self._states.get(device_id)
            pending = self._pending.get(device_id)
            return {
                "known": state is not None,
                "buzzer_active": bool(state and state["buzzer_active"]),
                "red_led_active": bool(state and state["red_led_active"]),
                "source": state["source"] if state else "unknown",
                "expires_at": state.get("expires_at") if state else None,
                "reported_at": state.get("reported_at") if state else None,
                "pending": pending is not None,
                "pending_active": pending["active"] if pending else None,
                "pending_command_id": pending["command_id"] if pending else None,
            }

    def start(self) -> None:
        if self._started:
            return
        if not MQTT_HOST or not MQTT_USERNAME or not MQTT_PASSWORD:
            raise RuntimeError("MQTT command publisher is not configured")
        self._started = True
        self.client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=30)
        self.client.loop_start()

    def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        self.client.disconnect()
        self.client.loop_stop()
        self._connected.clear()

    def publish(self, device_id: str, document: dict) -> dict:
        if not self._connected.wait(timeout=2):
            raise RuntimeError("MQTT broker is not connected")
        active = document["active"]
        command_id = document["command_id"]
        with self._lock:
            self._cleanup_pending_locked(device_id)
            state = self._states.get(device_id)
            pending = self._pending.get(device_id)
            if active and state is None:
                raise CommandConflict("Chưa nhận được trạng thái còi từ Raspberry Pi")
            if active and state["buzzer_active"]:
                raise CommandConflict("Còi đang bật; không gửi lệnh bật lặp")
            if active and pending and pending["active"]:
                raise CommandConflict("Lệnh bật còi đang chờ Raspberry Pi xác nhận")
            self._pending[device_id] = {
                "active": active,
                "command_id": command_id,
                "deadline": time.monotonic() + 5,
            }
        topic = f"health/v1/devices/{device_id}/commands"
        payload = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
        try:
            info = self.client.publish(topic, payload, qos=1, retain=False)
            info.wait_for_publish(timeout=3)
            if not info.is_published():
                raise RuntimeError(mqtt.error_string(info.rc))
        except RuntimeError:
            with self._lock:
                current = self._pending.get(device_id)
                if current and current["command_id"] == command_id:
                    self._pending.pop(device_id, None)
            raise
        return self.state_view(device_id)
