"""Publisher MQTT chạy nền để lỗi mạng không chặn vòng lặp cảm biến."""

import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import paho.mqtt.client as mqtt

from user_profile import UserProfile


log = logging.getLogger("health_watch.mqtt")


@dataclass(frozen=True)
class BrokerSettings:
    host: str
    port: int
    username: str
    password: str
    device_id: str
    keepalive: int = 30
    outbox_size: int = 200
    tls_enabled: bool = False
    ca_cert: str = ""
    client_cert: str = ""
    client_key: str = ""

    def validate(self) -> None:
        if not self.host:
            raise ValueError("MQTT_HOST chưa được cấu hình")
        if self.tls_enabled:
            if not self.ca_cert or not self.client_cert or not self.client_key:
                raise ValueError(
                    "MQTT_CA_CERT, MQTT_CLIENT_CERT và MQTT_CLIENT_KEY không được để trống khi bật TLS"
                )
        elif not self.username or not self.password:
            raise ValueError("MQTT_USERNAME và MQTT_PASSWORD không được để trống")
        if not 1 <= self.port <= 65535:
            raise ValueError("MQTT_PORT phải nằm trong khoảng 1..65535")
        if self.outbox_size < 10:
            raise ValueError("MQTT_OUTBOX_SIZE phải ít nhất là 10")


def configure_client_auth(client, settings: BrokerSettings) -> None:
    """Cấu hình một trong hai chế độ xác thực: mTLS hoặc username/password."""
    settings.validate()
    if settings.tls_enabled:
        client.tls_set(
            ca_certs=settings.ca_cert,
            certfile=settings.client_cert,
            keyfile=settings.client_key,
        )
    else:
        client.username_pw_set(settings.username, settings.password)


@dataclass
class PendingMessage:
    suffix: str
    document: dict
    kind: str
    retain: bool = False


class MqttPublisher:
    """Hàng đợi RAM có giới hạn và một worker gửi QoS 1 ở luồng nền."""

    def __init__(self, settings: BrokerSettings, online_status: dict, offline_status: dict):
        settings.validate()
        self.settings = settings
        self.base_topic = f"health/v1/devices/{settings.device_id}"
        self.online_status = online_status
        self.offline_status = offline_status
        self._outbox: deque[PendingMessage] = deque()
        self._commands: deque[dict] = deque(maxlen=20)
        self._seen_command_ids: deque[str] = deque(maxlen=100)
        self._profile_updates: deque[dict] = deque(maxlen=5)
        self._condition = threading.Condition()
        self._connected = False
        self._stopping = False
        self._accepting = True
        self._sending = False
        self._started = False
        self._worker = threading.Thread(target=self._send_loop, name="mqtt-outbox", daemon=True)

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"health-watch-{settings.device_id}",
        )
        configure_client_auth(self.client, settings)
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.max_inflight_messages_set(10)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.will_set(
            f"{self.base_topic}/status",
            self._encode(offline_status),
            qos=1,
            retain=True,
        )

    @staticmethod
    def _encode(document: dict) -> str:
        return json.dumps(document, ensure_ascii=False, separators=(",", ":"))

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._worker.start()
        self.client.connect_async(self.settings.host, self.settings.port, self.settings.keepalive)
        self.client.loop_start()
        log.info("MQTT đang kết nối tới %s:%s", self.settings.host, self.settings.port)

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            log.warning("MQTT từ chối kết nối: %s", reason_code)
            return
        if self._stopping:
            return
        info = client.publish(
            f"{self.base_topic}/status",
            self._encode(self.online_status),
            qos=1,
            retain=True,
        )
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            log.warning("Không xếp được trạng thái online: %s", mqtt.error_string(info.rc))
        for suffix in ("commands", "config"):
            result, _ = client.subscribe(f"{self.base_topic}/{suffix}", qos=1)
            if result != mqtt.MQTT_ERR_SUCCESS:
                log.warning("Không đăng ký được topic %s: %s", suffix, mqtt.error_string(result))
        with self._condition:
            self._connected = True
            self._condition.notify_all()
        log.info("MQTT đã kết nối và gửi trạng thái online")

    def _on_message(self, client, userdata, message) -> None:
        if getattr(message, "topic", f"{self.base_topic}/commands") == f"{self.base_topic}/config":
            self._on_config(message)
            return
        try:
            document = json.loads(message.payload.decode("utf-8"))
            command = self._validate_command(document)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            log.warning("Bỏ lệnh MQTT không hợp lệ: %s", exc)
            return

        with self._condition:
            command_id = command["command_id"]
            if command_id in self._seen_command_ids:
                log.info("Bỏ lệnh MQTT trùng command_id=%s", command_id)
                return
            self._seen_command_ids.append(command_id)
            self._commands.append(command)
            self._condition.notify_all()
        log.info("Đã nhận lệnh remote_alert active=%s", command["active"])

    def _on_config(self, message) -> None:
        try:
            document = json.loads(message.payload.decode("utf-8"))
            update = self.validate_config(document)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            log.warning("Bỏ cấu hình MQTT không hợp lệ: %s", exc)
            return
        with self._condition:
            self._profile_updates.append(update)
        log.info("Đã nhận hồ sơ người đeo từ backend (%s)", "xóa" if update["profile"] is None else "cập nhật")

    def validate_config(self, document: dict) -> dict:
        if not isinstance(document, dict):
            raise ValueError("payload phải là object")
        if document.get("schema_version") != 1:
            raise ValueError("schema_version không được hỗ trợ")
        if document.get("device_id") != self.settings.device_id:
            raise ValueError("device_id không khớp")
        updated_at = document.get("updated_at")
        if not isinstance(updated_at, str):
            raise ValueError("updated_at bị thiếu")
        parsed = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("updated_at phải có múi giờ")
        raw_profile = document.get("profile")
        if raw_profile is None:
            return {"profile": None, "updated_at": updated_at}
        profile = UserProfile.from_dict({**raw_profile, "updated_at": updated_at})
        return {"profile": profile, "updated_at": updated_at}

    def pop_profile_updates(self) -> list[dict]:
        with self._condition:
            updates = list(self._profile_updates)
            self._profile_updates.clear()
        return updates

    @property
    def connected(self) -> bool:
        return self._connected

    def _validate_command(self, document: dict) -> dict:
        if not isinstance(document, dict):
            raise ValueError("payload phải là object")
        if document.get("schema_version") != 1:
            raise ValueError("schema_version không được hỗ trợ")
        if document.get("device_id") != self.settings.device_id:
            raise ValueError("device_id không khớp")
        if document.get("command_type") != "remote_alert":
            raise ValueError("command_type không được hỗ trợ")

        command_id = str(UUID(str(document.get("command_id"))))
        active = document.get("active")
        duration_s = document.get("duration_s")
        if not isinstance(active, bool):
            raise ValueError("active phải là boolean")
        if isinstance(duration_s, bool) or not isinstance(duration_s, int) or not 1 <= duration_s <= 60:
            raise ValueError("duration_s phải nằm trong khoảng 1..60")

        issued_at_text = document.get("issued_at")
        if not isinstance(issued_at_text, str):
            raise ValueError("issued_at bị thiếu")
        issued_at = datetime.fromisoformat(issued_at_text.replace("Z", "+00:00"))
        if issued_at.tzinfo is None:
            raise ValueError("issued_at phải có múi giờ")
        age_s = (datetime.now(timezone.utc) - issued_at.astimezone(timezone.utc)).total_seconds()
        if age_s > 120 or age_s < -30:
            raise ValueError("lệnh đã cũ hoặc timestamp ở tương lai")

        return {
            "command_id": command_id,
            "active": active,
            "duration_s": duration_s,
        }

    def pop_commands(self) -> list[dict]:
        """Return commands for the hardware loop; GPIO is never touched on MQTT's thread."""
        with self._condition:
            commands = list(self._commands)
            self._commands.clear()
        return commands

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties) -> None:
        with self._condition:
            self._connected = False
            self._condition.notify_all()
        if not self._stopping:
            log.warning("MQTT mất kết nối (%s), sẽ tự kết nối lại", reason_code)

    def publish_telemetry(self, document: dict) -> None:
        self._enqueue(PendingMessage("telemetry", document, "telemetry"))

    def publish_event(self, document: dict) -> None:
        self._enqueue(PendingMessage("events", document, "event"))

    def publish_alert_state(self, document: dict) -> None:
        self._enqueue(PendingMessage("alert-state", document, "state", retain=True))

    def _enqueue(self, message: PendingMessage) -> None:
        if not self._started or self._stopping or not self._accepting:
            return
        with self._condition:
            if message.kind == "state":
                self._outbox = deque(
                    pending for pending in self._outbox if pending.kind != "state"
                )
            if len(self._outbox) >= self.settings.outbox_size:
                telemetry_index = next(
                    (index for index, pending in enumerate(self._outbox) if pending.kind == "telemetry"),
                    None,
                )
                if telemetry_index is not None:
                    del self._outbox[telemetry_index]
                    log.warning("MQTT outbox đầy; bỏ một telemetry cũ")
                elif message.kind == "telemetry":
                    log.warning("MQTT outbox đầy sự kiện; bỏ telemetry mới")
                    return
                else:
                    self._outbox.popleft()
                    log.error("MQTT outbox đầy sự kiện; bỏ bản tin cũ nhất")
            self._outbox.append(message)
            self._condition.notify_all()

    def _send_loop(self) -> None:
        while True:
            with self._condition:
                self._condition.wait_for(
                    lambda: self._stopping or (self._connected and bool(self._outbox))
                )
                if self._stopping:
                    return
                pending = self._outbox.popleft()
                self._sending = True
            try:
                info = self.client.publish(
                    f"{self.base_topic}/{pending.suffix}",
                    self._encode(pending.document),
                    qos=1,
                    retain=pending.retain,
                )
                info.wait_for_publish(timeout=5)
                if not info.is_published():
                    raise RuntimeError(mqtt.error_string(info.rc))
            except (RuntimeError, ValueError) as exc:
                log.warning("Chưa gửi được MQTT (%s); giữ bản tin để thử lại", exc)
                with self._condition:
                    self._outbox.appendleft(pending)
                    self._sending = False
                    self._condition.notify_all()
                time.sleep(1)
            else:
                with self._condition:
                    self._sending = False
                    self._condition.notify_all()

    def stop(self, flush_timeout_s: float = 3.0) -> None:
        """Gửi nốt bản tin còn chờ (tối đa ``flush_timeout_s``) rồi báo offline và ngắt."""
        if not self._started:
            return
        deadline = time.monotonic() + flush_timeout_s
        with self._condition:
            self._accepting = False
            while (self._connected and (self._outbox or self._sending)
                   and time.monotonic() < deadline):
                self._condition.wait(timeout=0.1)
            if self._outbox:
                log.warning("Dừng khi còn %d bản tin MQTT chưa gửi", len(self._outbox))
            self._stopping = True
            connected = self._connected
        if connected:
            try:
                info = self.client.publish(
                    f"{self.base_topic}/status",
                    self._encode(self.offline_status),
                    qos=1,
                    retain=True,
                )
                info.wait_for_publish(timeout=2)
            except RuntimeError:
                pass
        with self._condition:
            self._condition.notify_all()
        self._worker.join(timeout=2)
        self.client.disconnect()
        self.client.loop_stop()
        self._started = False
