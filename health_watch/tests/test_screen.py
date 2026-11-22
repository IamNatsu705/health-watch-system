"""Đồ thị không được biến nhiễu nền thành nhịp tim khi chưa đặt tay."""

import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from screen import render_dashboard


class ScreenTests(unittest.TestCase):
    def test_no_finger_graph_ignores_ir_noise(self):
        steps = SimpleNamespace(steps=0, distance_km=0.0, calories_kcal=0.0)
        pulse = SimpleNamespace(bpm=None, finger_present=False, sample_rate=25,
                                ir_history=[1300, 1500, 1100, 1700] * 12)
        empty = SimpleNamespace(bpm=None, finger_present=False, sample_rate=25,
                                ir_history=[])
        now = datetime(2026, 11, 21, 12, 30)
        noisy_graph = render_dashboard(steps, pulse, "", now).crop((153, 75, 220, 99))
        empty_graph = render_dashboard(steps, empty, "", now).crop((153, 75, 220, 99))
        self.assertEqual(noisy_graph.tobytes(), empty_graph.tobytes())


if __name__ == "__main__":
    unittest.main()
