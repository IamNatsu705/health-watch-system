"""HTTP API trên dữ liệu đã lưu: chọn bản mới theo giờ server, độ mới, tổng ngày, hồ sơ."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.api import main as api
from backend.common.contracts import validate
from backend.common.models import Device, TelemetrySample
from backend.ingest.main import save_message
from backend.tests.helpers import BOOT_A, BOOT_B, session_factory, telemetry
from mqtt_publisher import BrokerSettings, MqttPublisher
from telemetry import DeviceMessageFactory


class StubPublisher:
    def __init__(self):
        self.configs = []

    def start(self):
        pass

    def stop(self):
        pass

    def state_view(self, device_id):
        return {"known": False, "buzzer_active": False, "pending": False}

    def publish_config(self, device_id, document):
        self.configs.append((device_id, document))

    def publish(self, device_id, document):
        raise RuntimeError("không dùng trong test")


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.sessions = session_factory()
        self.publisher = StubPublisher()
        patches = [patch.object(api, "command_publisher", self.publisher),
                   patch.object(api, "SessionLocal", self.sessions)]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

        def get_db():
            with self.sessions() as session:
                yield session

        api.app.dependency_overrides[api.get_db] = get_db
        self.addCleanup(api.app.dependency_overrides.clear)
        self.client = TestClient(api.app)
        self.factory = DeviceMessageFactory("pi-watch-001", BOOT_A)

    def store(self, document, received_at):
        save_message("telemetry", document, self.sessions, received_at)

    def test_unknown_and_unregistered_devices_are_hidden(self):
        with self.sessions.begin() as db:
            db.add(Device(id="pi-watch-mock-001", name="mock", online=True,
                          last_seen_at=datetime.now(timezone.utc)))
        self.assertEqual(self.client.get("/api/v1/devices").json(), [])
        self.assertEqual(self.client.get("/api/v1/devices/pi-watch-mock-001/latest").status_code, 404)

    def test_latest_uses_server_receive_time_and_reports_freshness(self):
        now = datetime.now(timezone.utc)
        old_boot = DeviceMessageFactory("pi-watch-001", BOOT_B)
        # Bản tin cũ mang giờ thiết bị ở tương lai (đồng hồ Pi sai) không được "ghim" làm bản mới nhất.
        skewed = telemetry(old_boot, steps=999, uptime=1000)
        skewed["measured_at"] = "2099-01-01T00:00:00Z"
        self.store(skewed, now - timedelta(minutes=5))
        self.store(telemetry(self.factory, steps=12, ai=10, uptime=20), now - timedelta(seconds=2))
        body = self.client.get("/api/v1/devices/pi-watch-001/latest").json()
        current = body["telemetry"]
        self.assertEqual(current["steps_primary_session"], 10)
        self.assertEqual(current["steps_primary_source"], "ai")
        self.assertTrue(current["fresh"])
        self.assertTrue(body["device"]["online"])

        later = datetime.now(timezone.utc) - timedelta(minutes=10)
        with self.sessions.begin() as db:
            for row in db.scalars(api.select(TelemetrySample)).all():
                row.received_at = later
            db.get(Device, "pi-watch-001").last_seen_at = later
        body = self.client.get("/api/v1/devices/pi-watch-001/latest").json()
        self.assertFalse(body["telemetry"]["fresh"])
        self.assertFalse(body["device"]["online"])
        self.assertGreater(body["telemetry"]["age_s"], 500)

    def test_daily_totals_sum_sessions_and_split_days(self):
        zone = api.ZoneInfo("Asia/Ho_Chi_Minh")
        today = datetime.now(zone).replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_late = (today - timedelta(minutes=10)).astimezone(timezone.utc)
        morning = (today + timedelta(minutes=30)).astimezone(timezone.utc)
        # Phiên A: 100 bước trước nửa đêm, lên 160 sau nửa đêm → hôm nay +60.
        self.store(telemetry(self.factory, steps=110, ai=100, uptime=600), yesterday_late)
        self.store(telemetry(self.factory, steps=170, ai=160, uptime=3000), morning)
        # Pi khởi động lại (phiên B) và đếm thêm 40 bước.
        restarted = DeviceMessageFactory("pi-watch-001", BOOT_B)
        self.store(telemetry(restarted, steps=0, ai=0, uptime=1), morning + timedelta(minutes=1))
        self.store(telemetry(restarted, steps=45, ai=40, uptime=60), morning + timedelta(minutes=2))
        # Dữ liệu v1 cũ (thuật toán lỗi) không được cộng vào tổng ngày.
        with self.sessions.begin() as db:
            db.add(TelemetrySample(
                device_id="pi-watch-001", boot_id="33333333-3333-4333-8333-333333333333", sequence=1,
                schema_version=1, measured_at=morning, received_at=morning, finger_present=False,
                steps_session=5000, step_algorithm="peak-v1"))
        days = self.client.get("/api/v1/devices/pi-watch-001/steps/daily?days=2").json()["days"]
        self.assertEqual(days[0]["steps"], 100)
        self.assertEqual(days[1]["steps"], 100)        # 60 + 40
        self.assertEqual(days[1]["steps_algorithm"], 105)
        self.assertEqual(days[1]["source"], "ai")
        self.assertEqual(days[1]["sessions"], 2)
        self.assertIsNone(days[1]["distance_m"])

    def test_profile_is_validated_stored_and_published_as_valid_config(self):
        with self.sessions.begin() as db:
            db.add(Device(id="pi-watch-001", name="pi-watch-001", online=False))
        bad = self.client.put("/api/v1/devices/pi-watch-001/profile", json={"height_cm": 50, "weight_kg": 60})
        self.assertEqual(bad.status_code, 422)
        ok = self.client.put("/api/v1/devices/pi-watch-001/profile",
                             json={"height_cm": 168, "weight_kg": 58.5, "step_length_m": None})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(self.client.get("/api/v1/devices/pi-watch-001/profile").json()["profile"]["height_cm"], 168)
        device_id, document = self.publisher.configs[-1]
        validate("config", document)
        # Pi chấp nhận đúng tài liệu mà API gửi (kiểm tra hợp đồng hai phía).
        pi = MqttPublisher(BrokerSettings("broker", 1883, "pi-watch-001", "x", "pi-watch-001"), {}, {})
        self.assertEqual(pi.validate_config(document)["profile"].weight_kg, 58.5)
        self.client.delete("/api/v1/devices/pi-watch-001/profile")
        self.assertIsNone(self.publisher.configs[-1][1]["profile"])
        self.assertIsNone(self.client.get("/api/v1/devices/pi-watch-001/profile").json()["profile"])


if __name__ == "__main__":
    unittest.main()
