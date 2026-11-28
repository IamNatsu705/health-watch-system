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
        steps = SimpleNamespace(steps=0, source_label="AI", distance_km=None,
                                calories_kcal=None, imu_ok=True)
        pulse = SimpleNamespace(bpm=None, finger_present=False, sample_rate=25,
                                ir_history=[1300, 1500, 1100, 1700] * 12)
        empty = SimpleNamespace(bpm=None, finger_present=False, sample_rate=25,
                                ir_history=[])
        now = datetime(2026, 11, 21, 12, 30)
        noisy_graph = render_dashboard(steps, pulse, "", now).crop((153, 75, 220, 99))
        empty_graph = render_dashboard(steps, empty, "", now).crop((153, 75, 220, 99))
        self.assertEqual(noisy_graph.tobytes(), empty_graph.tobytes())

    def test_fall_alert_texts_fit_status_card(self):
        from PIL import Image, ImageDraw
        from screen import FONT_SMALL, FONT_STATUS
        draw = ImageDraw.Draw(Image.new("RGB", (240, 280)))
        steps = SimpleNamespace(steps=0, source_label="AI", distance_km=None,
                                calories_kcal=None, imu_ok=True)
        pulse = SimpleNamespace(bpm=None, finger_present=False, sample_rate=25, ir_history=[])
        for state, detail in (("fall", "Nhấn nút nếu bạn ổn · 30 s"), ("fall", "Đang chờ bạn nhấn nút"),
                              ("fall_alarm", None)):
            render_dashboard(steps, pulse, state, datetime(2026, 11, 28, 8, 0), alert_detail=detail)
        # Thẻ trạng thái: chữ bắt đầu ở x≈52, viền phải ở x=230.
        for title in ("PHÁT HIỆN NGÃ", "BÁO ĐỘNG NGÃ"):
            self.assertLess(52 + draw.textlength(title, font=FONT_STATUS), 226)
        for detail in ("Nhấn nút nếu bạn ổn · 30 s", "Đang chờ bạn nhấn nút", "Nhấn nút để tắt còi"):
            self.assertLess(53 + draw.textlength(detail, font=FONT_SMALL), 226)


if __name__ == "__main__":
    unittest.main()


class StepCardTests(unittest.TestCase):
    def render(self, **overrides):
        values = dict(steps=1234, source_label="AI", distance_km=None, calories_kcal=None, imu_ok=True)
        values.update(overrides)
        pulse = SimpleNamespace(bpm=None, finger_present=False, sample_rate=25, ir_history=[])
        return render_dashboard(SimpleNamespace(**values), pulse, "", datetime(2026, 11, 28, 8, 0))

    def test_imu_error_changes_card_and_badge(self):
        healthy = self.render()
        broken = self.render(imu_ok=False)
        self.assertNotEqual(healthy.crop((55, 150, 230, 186)).tobytes(), broken.crop((55, 150, 230, 186)).tobytes())
        self.assertNotEqual(healthy.crop((174, 8, 224, 28)).tobytes(), broken.crop((174, 8, 224, 28)).tobytes())

    def test_missing_profile_renders_without_numbers(self):
        self.render(distance_km=None, calories_kcal=None)
        self.render(distance_km=1.234, calories_kcal=45.6)
