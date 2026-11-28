"""Số bước trong ngày, quãng đường/kcal cộng dồn theo hồ sơ tại thời điểm bước được đếm."""

import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from step_tracker import StepTracker
from storage import DailyStepStore
from user_profile import UserProfile


class FakeEngine:
    def __init__(self, gate=True):
        self.gate = object() if gate else None
        self.steps_algorithm = 0
        self.running_steps_algorithm = 0
        self.steps_ai = 0 if gate else None
        self.running_steps_ai = 0 if gate else None


class StepTrackerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        day = time.struct_time((2026, 11, 28, 9, 0, 0, 5, 332, 0))
        self.daily = DailyStepStore(Path(self.tmp.name) / "daily.json", clock=lambda: day, synced=lambda: True)
        self.engine = FakeEngine()
        self.tracker = StepTracker(self.engine, self.daily, None)

    def tearDown(self):
        self.tmp.cleanup()

    def walk(self, ai, algorithm=None):
        self.engine.steps_ai += ai
        self.engine.steps_algorithm += algorithm if algorithm is not None else ai
        self.tracker.sync()

    def test_no_profile_means_no_estimates(self):
        self.walk(100)
        self.assertEqual(self.tracker.session_estimates(), (None, None))
        view = self.tracker.screen_view(SimpleNamespace(ok=True))
        self.assertEqual(view.steps, 100)
        self.assertIsNone(view.distance_km)
        self.assertEqual(view.title, "BƯỚC HÔM NAY")

    def test_profile_change_does_not_recompute_earlier_steps(self):
        self.walk(1000)                                   # trước khi có hồ sơ: không tính quãng đường
        self.tracker.profile = UserProfile(170, 60, step_length_m=0.5)
        self.walk(100)                                    # 100 × 0,5 m
        self.tracker.profile = UserProfile(170, 60, step_length_m=0.8)
        self.walk(10)                                     # 10 × 0,8 m
        distance, kcal = self.tracker.session_estimates()
        self.assertAlmostEqual(distance, 58.0)
        self.assertAlmostEqual(self.daily.counts["distance_m"], 58.0)
        self.assertAlmostEqual(kcal, 60 * (0.05 + 0.008) * 0.5)
        self.assertEqual(self.daily.counts["ai"], 1110)

    def test_algorithm_is_primary_without_model(self):
        engine = FakeEngine(gate=False)
        tracker = StepTracker(engine, self.daily, UserProfile(170, 60, step_length_m=0.7))
        engine.steps_algorithm = 10
        tracker.sync()
        self.assertAlmostEqual(tracker.session_estimates()[0], 7.0)
        self.assertEqual(tracker.screen_view(SimpleNamespace(ok=True)).source_label, "Thuật toán")

    def test_unknown_date_is_labelled(self):
        daily = DailyStepStore(Path(self.tmp.name) / "other.json", synced=lambda: False)
        tracker = StepTracker(self.engine, daily, None)
        self.assertEqual(tracker.screen_view(SimpleNamespace(ok=True)).title, "BƯỚC TỪ KHI BẬT")


if __name__ == "__main__":
    unittest.main()
