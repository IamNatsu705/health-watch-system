"""Kiểm tra payload do Pi tạo khớp MQTT contract v1."""

import sys
import unittest
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from telemetry import DeviceMessageFactory


class DeviceMessageFactoryTests(unittest.TestCase):
    def test_telemetry_contains_stable_identity_and_session_metrics(self):
        factory = DeviceMessageFactory("pi-watch-test", "78449bd4-f6c9-47df-b55b-1055ae825440")
        payload = factory.telemetry(
            heart_rate_bpm=None,
            finger_present=False,
            steps_session=7,
            distance_m_session=4.8999,
            calories_kcal_session=0.2574,
        )

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["device_id"], "pi-watch-test")
        self.assertEqual(payload["sequence"], 1)
        self.assertTrue(payload["measured_at"].endswith("Z"))
        self.assertEqual(payload["metrics"]["heart_rate_bpm"], None)
        self.assertEqual(payload["metrics"]["distance_m_session"], 4.9)
        self.assertEqual(payload["metrics"]["calories_kcal_session"], 0.257)

    def test_events_increment_sequence_and_have_unique_ids(self):
        factory = DeviceMessageFactory("pi-watch-test")
        first = factory.event("fall_detected")
        second = factory.event("fall_acknowledged")

        self.assertEqual((first["sequence"], second["sequence"]), (1, 2))
        self.assertNotEqual(first["event_id"], second["event_id"])
        UUID(first["event_id"])
        self.assertEqual(first["boot_id"], second["boot_id"])

    def test_rejects_invalid_device_and_event(self):
        with self.assertRaises(ValueError):
            DeviceMessageFactory("id co khoang trang")
        factory = DeviceMessageFactory("valid-id")
        with self.assertRaises(ValueError):
            factory.event("unknown")


if __name__ == "__main__":
    unittest.main()
