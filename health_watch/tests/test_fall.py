"""Kiểm tra chuỗi ngã và các chuyển động dễ gây báo nhầm."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from processing.fall import FallDetector
from sensors.mpu6050 import MotionSample


def sample(ax=0.0, ay=0.0, az=1.0, gx=0.0):
    return MotionSample(ax, ay, az, gx, 0.0, 0.0)


class FallDetectorTests(unittest.TestCase):
    def setUp(self):
        self.detector = FallDetector()
        for i in range(20):
            self.detector.update(sample(), i * 0.04)

    def test_free_fall_impact_rotation_and_stillness_confirm(self):
        for t in (1.00, 1.04, 1.08):
            self.assertFalse(self.detector.update(sample(az=0.3), t))
        self.detector.update(sample(az=3.2), 1.12)
        for i in range(50):
            self.detector.update(sample(ax=1, az=0), 1.16 + i * 0.04)
        self.assertTrue(self.detector.confirmed)
        self.detector.clear()
        self.assertFalse(self.detector.confirmed)

    def test_impact_without_rotation_does_not_confirm(self):
        self.detector.update(sample(az=3.2), 1.0)
        for i in range(60):
            self.detector.update(sample(), 1.04 + i * 0.04)
        self.assertFalse(self.detector.confirmed)

    def test_rotation_without_impact_does_not_confirm(self):
        for i in range(80):
            self.detector.update(sample(ax=1, az=0), 1.0 + i * 0.04)
        self.assertFalse(self.detector.confirmed)

    def test_movement_after_impact_prevents_confirmation(self):
        self.detector.update(sample(az=3.2), 1.0)
        for i in range(80):
            self.detector.update(sample(ax=1, az=0, gx=100), 1.04 + i * 0.04)
        self.assertFalse(self.detector.confirmed)


class SampleRateIndependenceTests(unittest.TestCase):
    def baseline_after(self, rate_hz, seconds=0.4):
        detector = FallDetector()
        detector.update(sample(ax=0.0, az=1.0), 0.0)
        steps = int(seconds * rate_hz)
        for i in range(1, steps + 1):
            detector.update(sample(ax=0.6, az=0.8), i / rate_hz)
        return detector.baseline[0]

    def test_baseline_time_constant_same_at_25_and_100_hz(self):
        self.assertAlmostEqual(self.baseline_after(25), self.baseline_after(100), places=6)

    def test_free_fall_impact_rotation_and_stillness_confirm_at_100_hz(self):
        detector = FallDetector()
        for i in range(100):
            detector.update(sample(), i * 0.01)
        t = 1.0
        for _ in range(12):
            detector.update(sample(az=0.3), t)
            t += 0.01
        detector.update(sample(az=3.2), t)
        for _ in range(250):
            t += 0.01
            detector.update(sample(ax=1, az=0), t)
        self.assertTrue(detector.confirmed)


if __name__ == "__main__":
    unittest.main()
