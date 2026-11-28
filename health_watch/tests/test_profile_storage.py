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
        store.save(UserProfile(165, 55, None, "2026-11-28T00:00:00Z"), "2026-11-28T00:00:00Z")
        self.assertEqual(store.load().weight_kg, 55)
        store.save(None, "2026-11-28T01:00:00Z")
        self.assertIsNone(store.load())
        self.assertEqual(ProfileStore(self.dir / "profile.json").load(), None)

    def test_older_config_is_not_applied(self):
        store = ProfileStore(self.dir / "profile.json")
        store.save(UserProfile(165, 55), "2026-11-28T08:00:00Z")
        reloaded = ProfileStore(self.dir / "profile.json")
        reloaded.load()
        self.assertFalse(reloaded.is_newer("2026-11-28T07:59:59Z"))
        self.assertTrue(reloaded.is_newer("2026-11-28T08:00:01+00:00"))
        self.assertFalse(reloaded.is_newer("not a date"))

    def test_corrupt_profile_is_ignored(self):
        (self.dir / "profile.json").write_text("{not json", encoding="utf-8")
        self.assertIsNone(ProfileStore(self.dir / "profile.json").load())

    def test_daily_steps_persist_and_roll_over(self):
        day = {"value": time.struct_time((2026, 11, 28, 10, 0, 0, 5, 332, 0))}
        path = self.dir / "daily.json"
        store = DailyStepStore(path, clock=lambda: day["value"], synced=lambda: True)
        store.add(algorithm=40, ai=35, ai_running=5, distance_m=24.5, kcal=0.9)
        store.save()
        restored = DailyStepStore(path, clock=lambda: day["value"], synced=lambda: True)
        self.assertEqual(restored.counts["ai"], 35)
        self.assertAlmostEqual(restored.counts["distance_m"], 24.5)
        day["value"] = time.struct_time((2026, 11, 29, 0, 0, 5, 6, 333, 0))
        restored.add(ai=2)
        self.assertEqual(restored.counts["ai"], 2)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["date"], "2026-11-28")

    def test_unsynced_clock_does_not_load_or_write_a_guessed_day(self):
        path = self.dir / "daily.json"
        yesterday = time.struct_time((2026, 11, 27, 23, 50, 0, 4, 331, 0))
        today = time.struct_time((2026, 11, 28, 7, 0, 0, 5, 332, 0))
        DailyStepStore(path, clock=lambda: yesterday, synced=lambda: True).add(ai=8000)
        first = DailyStepStore(path, clock=lambda: yesterday, synced=lambda: True)
        first.add(ai=0)
        first._dirty = True
        first.save()
        state = {"clock": yesterday, "synced": False}
        store = DailyStepStore(path, clock=lambda: state["clock"], synced=lambda: state["synced"])
        self.assertFalse(store.date_known)
        store.add(ai=300)
        self.assertEqual(store.counts["ai"], 300)     # chỉ "từ khi bật máy", không nạp 8000 của hôm qua
        store.save()                                   # chưa biết ngày: không ghi
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["date"], "2026-11-27")
        state.update(clock=today, synced=True)
        store.add(ai=1)
        self.assertEqual(store.date, "2026-11-28")
        self.assertEqual(store.counts["ai"], 301)

    def test_storage_errors_do_not_raise(self):
        store = DailyStepStore(self.dir / "missing_dir" / "x" / "daily.json", synced=lambda: True)
        store.add(ai=3)
        store.path = self.dir  # một thư mục: ghi file sẽ lỗi
        store.save_quietly()
        self.assertEqual(store.counts["ai"], 3)


if __name__ == "__main__":
    unittest.main()
