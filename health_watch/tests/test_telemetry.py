"""Kiểm tra payload do Pi tạo (telemetry v2, event/alert-state v1)."""

import sys
import unittest
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from telemetry import SOFTWARE_VERSION, DeviceMessageFactory


class DeviceMessageFactoryTests(unittest.TestCase):
    def telemetry(self, factory, **overrides):
        values = dict(
            heart_rate_bpm=None, finger_present=False, imu_status="ok",
            steps_algorithm_session=7, steps_ai_session=6,
            step_model={"name": "walk-gate-rf", "version": "1.0.0"},
            walking=True, walking_probability=0.91234, cadence_spm=110.04,
            distance_m_session=4.8999, calories_kcal_session=0.2574,
            distance_basis={"step_length_m": 0.7, "method": "measured"},
            session_started_at="2026-11-28T00:00:00.000Z", uptime_s=12.34, clock_synced=True,
        )
        values.update(overrides)
        return factory.telemetry(**values)

    def test_telemetry_v2_carries_provenance_and_rounds_estimates(self):
        factory = DeviceMessageFactory("pi-watch-test", "78449bd4-f6c9-47df-b55b-1055ae825440")
        payload = self.telemetry(factory)
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["sequence"], 1)
        self.assertTrue(payload["measured_at"].endswith("Z"))
        self.assertEqual(payload["step_algorithm"], "peak-bout-v2")
        self.assertEqual(payload["firmware_version"], SOFTWARE_VERSION)
        metrics = payload["metrics"]
        self.assertEqual(metrics["steps_ai_session"], 6)
        self.assertEqual(metrics["distance_m_session"], 4.9)
        self.assertEqual(metrics["calories_kcal_session"], 0.26)
        self.assertEqual(metrics["walking_probability"], 0.912)

    def test_missing_profile_and_model_are_null_not_invented(self):
        factory = DeviceMessageFactory("pi-watch-test")
        payload = self.telemetry(factory, steps_ai_session=None, step_model=None, walking=None,
                                 walking_probability=None, cadence_spm=None, distance_m_session=None,
                                 calories_kcal_session=None, distance_basis=None)
        metrics = payload["metrics"]
        for key in ("steps_ai_session", "distance_m_session", "calories_kcal_session", "walking"):
            self.assertIsNone(metrics[key])
        self.assertIsNone(payload["step_model"])

    def test_rejects_inconsistent_ai_fields_and_unknown_imu_status(self):
        factory = DeviceMessageFactory("pi-watch-test")
        with self.assertRaises(ValueError):
            self.telemetry(factory, step_model=None)
        with self.assertRaises(ValueError):
            self.telemetry(factory, imu_status="fake")

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

    def test_alert_state_reports_real_outputs_and_expiry(self):
        factory = DeviceMessageFactory("pi-watch-test")
        command_id = "3e4a9a2e-639a-456d-8cce-aad4137ba544"
        payload = factory.alert_state(
            buzzer_active=True,
            red_led_active=True,
            source="remote",
            last_command_id=command_id,
            remote_remaining_s=10,
        )
        self.assertTrue(payload["buzzer_active"])
        self.assertEqual(payload["source"], "remote")
        self.assertEqual(payload["last_command_id"], command_id)
        self.assertIsNotNone(payload["expires_at"])


if __name__ == "__main__":
    unittest.main()
