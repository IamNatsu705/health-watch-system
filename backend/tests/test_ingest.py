"""Contract + ingest: chỉ dữ liệu thật, hợp lệ, của thiết bị đã đăng ký mới được lưu."""

import json
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from backend.common.config import DEVICE_IDS, parse_device_ids
from backend.common.contracts import loads_strict, parse_message, validate
from backend.common.models import Device, TelemetrySample
from backend.ingest.main import RejectedMessage, save_message
from backend.tests.helpers import BOOT_A, BOOT_B, session_factory, telemetry
from telemetry import DeviceMessageFactory

TOPIC = "health/v1/devices/pi-watch-001/telemetry"


def encode(document) -> bytes:
    return json.dumps(document).encode("utf-8")


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.factory = DeviceMessageFactory("pi-watch-001", BOOT_A)

    def test_pi_payload_matches_schema_with_and_without_ai(self):
        for document in (telemetry(self.factory, steps=12, ai=10, distance=7.0),
                         telemetry(self.factory, steps=12)):
            kind, parsed = parse_message(TOPIC, encode(document), DEVICE_IDS)
            self.assertEqual(kind, "telemetry")
            self.assertEqual(parsed["schema_version"], 2)

    def test_pi_status_and_event_match_schema(self):
        parse_message("health/v1/devices/pi-watch-001/status", encode(self.factory.status("online")), DEVICE_IDS)
        for event_type in ("fall_detected", "fall_cancelled", "fall_alarm", "fall_acknowledged",
                           "sos_pressed", "sos_released"):
            kind, parsed = parse_message("health/v1/devices/pi-watch-001/events",
                                         encode(self.factory.event(event_type)), DEVICE_IDS)
            self.assertEqual((kind, parsed["event_type"]), ("events", event_type))

    def test_rejects_unregistered_device_and_topic_mismatch(self):
        other = DeviceMessageFactory("pi-watch-mock-001")
        with self.assertRaises(ValueError):
            parse_message("health/v1/devices/pi-watch-mock-001/telemetry",
                          encode(telemetry(other, steps=1)), DEVICE_IDS)
        with self.assertRaises(ValueError):
            parse_message("health/v1/devices/pi-watch-002/telemetry",
                          encode(telemetry(self.factory, steps=1)), DEVICE_IDS)

    def test_rejects_nan_infinity_and_old_v1_payload(self):
        document = telemetry(self.factory, steps=1)
        text = json.dumps(document).replace('"cadence_spm": null', '"cadence_spm": NaN')
        with self.assertRaises(ValueError):
            parse_message(TOPIC, text.encode(), DEVICE_IDS)
        with self.assertRaises(ValueError):
            loads_strict('{"x": Infinity}')
        legacy = {"schema_version": 1, "device_id": "pi-watch-001", "boot_id": BOOT_A, "sequence": 1,
                  "measured_at": "2026-11-28T00:00:00Z",
                  "metrics": {"heart_rate_bpm": None, "finger_present": False, "steps_session": 7,
                              "distance_m_session": 4.9, "calories_kcal_session": 0.26}}
        with self.assertRaises(ValueError):
            parse_message(TOPIC, encode(legacy), DEVICE_IDS)

    def test_format_checks_are_active(self):
        document = telemetry(self.factory, steps=1)
        document["measured_at"] = "2026-11-28T07:00:00"  # thiếu múi giờ
        with self.assertRaises(ValueError):
            parse_message(TOPIC, encode(document), DEVICE_IDS)
        document = telemetry(self.factory, steps=1)
        document["boot_id"] = "not-a-uuid"
        with self.assertRaises(ValueError):
            parse_message(TOPIC, encode(document), DEVICE_IDS)

    def test_inconsistent_ai_or_estimate_fields_are_rejected(self):
        document = telemetry(self.factory, steps=5, ai=4)
        document["step_model"] = None
        with self.assertRaises(ValueError):
            validate("telemetry", document)
        document = telemetry(self.factory, steps=5, distance=3.5)
        document["distance_basis"] = None   # quãng đường không có cơ sở ước tính
        with self.assertRaises(ValueError):
            validate("telemetry", document)

    def test_device_list_parsing(self):
        self.assertEqual(parse_device_ids("a:1, b-2:x,"), {"a", "b-2"})
        with self.assertRaises(ValueError):
            parse_device_ids("bad id:1")


class IngestTests(unittest.TestCase):
    def setUp(self):
        self.sessions = session_factory()
        self.factory = DeviceMessageFactory("pi-watch-001", BOOT_A)
        self.now = datetime(2026, 11, 28, 3, 0, tzinfo=timezone.utc)

    def save(self, document, seconds=0, kind="telemetry"):
        return save_message(kind, document, self.sessions, self.now + timedelta(seconds=seconds))

    def count(self):
        with self.sessions() as db:
            return db.scalar(select(func.count()).select_from(TelemetrySample))

    def test_stores_v2_fields_and_ignores_duplicates(self):
        document = telemetry(self.factory, steps=20, ai=18, uptime=30, distance=12.6)
        self.assertTrue(self.save(document))
        self.assertFalse(self.save(document, seconds=1))
        with self.sessions() as db:
            row = db.scalars(select(TelemetrySample)).one()
            self.assertEqual((row.steps_session, row.steps_ai_session), (20, 18))
            self.assertEqual(row.step_model_name, "walk-gate-rf")
            self.assertEqual(row.distance_method, "measured")
            self.assertIsNotNone(row.clock_skew_s)
            self.assertEqual(db.get(Device, "pi-watch-001").firmware_version, "health-watch-pi/0.2.0")

    def test_counter_cannot_decrease_within_boot_but_new_boot_restarts(self):
        self.save(telemetry(self.factory, steps=50, uptime=40))
        with self.assertRaises(RejectedMessage):
            self.save(telemetry(self.factory, steps=40, uptime=41), seconds=1)
        restarted = DeviceMessageFactory("pi-watch-001", BOOT_B)
        self.assertTrue(self.save(telemetry(restarted, steps=0, uptime=1), seconds=2))
        self.assertEqual(self.count(), 2)

    def test_physically_impossible_jump_is_rejected(self):
        self.save(telemetry(self.factory, steps=10, uptime=10))
        with self.assertRaises(RejectedMessage):
            self.save(telemetry(self.factory, steps=500, uptime=11), seconds=1)
        with self.assertRaises(RejectedMessage):
            self.save(telemetry(DeviceMessageFactory("pi-watch-001", BOOT_B), steps=9999, uptime=5))

    def test_ai_window_burst_is_allowed(self):
        self.save(telemetry(self.factory, steps=10, ai=10, uptime=10))
        self.assertTrue(self.save(telemetry(self.factory, steps=12, ai=27, uptime=11), seconds=1))

    def test_late_out_of_order_message_must_fit_between_neighbours(self):
        first = telemetry(self.factory, steps=10, uptime=10)
        second = telemetry(self.factory, steps=20, uptime=12)
        third = telemetry(self.factory, steps=30, uptime=14)
        self.save(first)
        self.save(third, seconds=4)
        self.assertTrue(self.save(second, seconds=5))
        bogus = dict(second, sequence=second["sequence"] + 100)
        bogus["metrics"] = dict(second["metrics"], steps_algorithm_session=5)
        with self.assertRaises(RejectedMessage):
            self.save(bogus, seconds=6)

    def test_retained_online_status_does_not_prove_device_is_alive(self):
        status = self.factory.status("online")
        save_message("status", status, self.sessions, self.now, retained=True)
        with self.sessions() as db:
            device = db.get(Device, "pi-watch-001")
            self.assertFalse(device.online)
            self.assertIsNone(device.last_seen_at)
        save_message("status", status, self.sessions, self.now, retained=False)
        with self.sessions() as db:
            self.assertTrue(db.get(Device, "pi-watch-001").online)

    def test_stale_last_will_from_previous_boot_does_not_mark_offline(self):
        old = DeviceMessageFactory("pi-watch-001", BOOT_A)
        new = DeviceMessageFactory("pi-watch-001", BOOT_B)
        self.save(new.status("online"), kind="status")
        self.save(old.status("offline"), seconds=1, kind="status")
        with self.sessions() as db:
            self.assertTrue(db.get(Device, "pi-watch-001").online)
        self.save(new.status("offline"), seconds=2, kind="status")
        with self.sessions() as db:
            self.assertFalse(db.get(Device, "pi-watch-001").online)


if __name__ == "__main__":
    unittest.main()
