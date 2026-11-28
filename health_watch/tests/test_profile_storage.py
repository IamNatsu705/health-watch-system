"""Hồ sơ người đeo, ước tính quãng đường/kcal và lưu số bước trong ngày."""

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from storage import DailyStepStore, ProfileStore
from user_profile import UserProfile, active_kcal, distance_m


class ProfileTests(unittest.TestCase):
    def test_no_profile_means_no_estimate(self):
        self.assertIsNone(distance_m(1000, None))
        self.assertIsNone(active_kcal(1000, 0, None))

    def test_height_based_and_measured_step_length(self):
        estimated = UserProfile(height_cm=170, weight_kg=60)
        self.assertEqual(estimated.effective_step_length_m, 0.704)
        self.assertEqual(estimated.step_length_method, "height_ratio")
        measured = UserProfile(height_cm=170, weight_kg=60, step_length_m=0.65)
        self.assertEqual(distance_m(100, measured), 65.0)
        self.assertEqual(measured.step_length_method, "measured")

    def test_acsm_walking_and_running_energy(self):
        profile = UserProfile(height_cm=170, weight_kg=60, step_length_m=0.5)
        # 2000 bước × 0,5 m = 1 km; đi 0,5 kcal/kg/km, chạy 1,0 kcal/kg/km.
        self.assertAlmostEqual(active_kcal(2000, 0, profile), 30.0)
        self.assertAlmostEqual(active_kcal(2000, 2000, profile), 60.0)

    def test_rejects_out_of_range_values(self):
        for document in ({"height_cm": 20, "weight_kg": 60}, {"height_cm": 170, "weight_kg": True},
                         {"height_cm": float("nan"), "weight_kg": 60},
                         {"height_cm": 170, "weight_kg": 60, "step_length_m": 3}):
            with self.assertRaises(ValueError):
                UserProfile.from_dict(document)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_profile_round_trip_and_clear(self):
        store = ProfileStore(self.dir / "profile.json")
        self.assertIsNone(store.load())
        store.save(UserProfile(165, 55, None, "2026-11-28T00:00:00Z"))
        self.assertEqual(store.load().weight_kg, 55)
        store.save(None)
        self.assertIsNone(store.load())

    def test_corrupt_profile_is_ignored(self):
        (self.dir / "profile.json").write_text("{not json", encoding="utf-8")
        self.assertIsNone(ProfileStore(self.dir / "profile.json").load())

    def test_daily_steps_persist_and_roll_over(self):
        day = {"value": time.struct_time((2026, 11, 28, 10, 0, 0, 5, 332, 0))}
        path = self.dir / "daily.json"
        store = DailyStepStore(path, clock=lambda: day["value"])
        store.add(algorithm=40, ai=35, ai_running=5)
        store.save()
        restored = DailyStepStore(path, clock=lambda: day["value"])
        self.assertEqual(restored.counts["ai"], 35)
        day["value"] = time.struct_time((2026, 11, 29, 0, 0, 5, 6, 333, 0))
        restored.add(ai=2)
        self.assertEqual(restored.counts["ai"], 2)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["date"], "2026-11-28")


if __name__ == "__main__":
    unittest.main()
