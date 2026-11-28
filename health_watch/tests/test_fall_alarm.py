"""Luồng báo động sau khi phát hiện ngã: hủy, báo động khi nằm yên, chờ khi người đeo cử động."""

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fall_alarm import ALARM, CHECK, IDLE, FallAlarm

RATE_HZ = 100


def feed(alarm, start, seconds, sample=lambda t: (0.0, 0.0, 1.0)):
    """Đưa mẫu 100 Hz trong [start, start + seconds), gọi update như vòng lặp chính; trả số lần báo động."""
    escalations = 0
    for i in range(int(seconds * RATE_HZ)):
        t = start + i / RATE_HZ
        alarm.observe(*sample(t), t)
        escalations += alarm.update(t)
    return escalations


def lying(t):
    return (1.0, 0.0, 0.0)  # nằm nghiêng, trọng lực theo trục x


def walking(t):
    return (0.3 * math.sin(2 * math.pi * 1.8 * t), 0.0, 1.0 + 0.4 * math.sin(2 * math.pi * 1.8 * t))


class FallAlarmTests(unittest.TestCase):
    def test_button_in_cancel_window_cancels_without_alarm(self):
        alarm = FallAlarm(cancel_window_s=30, immobile_s=10)
        feed(alarm, 0, 2, lying)
        self.assertTrue(alarm.start(2.0))
        self.assertEqual(feed(alarm, 2, 10, lying), 0)
        self.assertEqual(alarm.state, CHECK)
        self.assertAlmostEqual(alarm.remaining_s(12.0), 20.0)
        self.assertEqual(alarm.acknowledge(), CHECK)
        self.assertEqual(alarm.state, IDLE)
        self.assertFalse(alarm.buzzer_on(12.0))
        self.assertIsNone(alarm.remaining_s(12.0))

    def test_lying_still_escalates_once_after_window(self):
        alarm = FallAlarm(cancel_window_s=30, immobile_s=10)
        feed(alarm, 0, 2, lying)
        alarm.start(2.0)
        self.assertEqual(feed(alarm, 2, 29.9, lying), 0)
        self.assertEqual(alarm.state, CHECK)
        self.assertEqual(feed(alarm, 31.9, 10, lying), 1)  # đúng một lần, ở giây thứ 30
        self.assertEqual(alarm.state, ALARM)
        self.assertTrue(alarm.buzzer_on(40.0) and alarm.buzzer_on(40.7))  # liên tục
        self.assertEqual(alarm.acknowledge(), ALARM)

    def test_moving_after_fall_waits_for_button_then_escalates_once_still(self):
        alarm = FallAlarm(cancel_window_s=30, immobile_s=10)
        feed(alarm, 0, 2, lying)
        alarm.start(2.0)
        self.assertEqual(feed(alarm, 2, 40, walking), 0)  # đứng dậy đi: không báo động, vẫn chờ
        self.assertEqual(alarm.state, CHECK)
        self.assertTrue(alarm.buzzer_on(42.2) and not alarm.buzzer_on(42.7))
        # Nằm lại: động tác nằm xuống (đổi hướng trọng lực) cũng là cử động, nên báo động sau
        # khi đã yên đủ 10 s kể từ lúc nằm xong (~2–3 s để trung bình trượt ổn định).
        escalated_at = None
        for i in range(20 * RATE_HZ):
            t = 42 + i / RATE_HZ
            alarm.observe(*lying(t), t)
            if alarm.update(t):
                self.assertIsNone(escalated_at)
                escalated_at = t
        self.assertIsNotNone(escalated_at)
        self.assertTrue(52.0 <= escalated_at <= 56.0, escalated_at)
        self.assertEqual(alarm.state, ALARM)

    def test_missing_imu_samples_count_as_immobile(self):
        alarm = FallAlarm(cancel_window_s=30, immobile_s=10)
        alarm.start(0.0)
        self.assertFalse(alarm.update(29.9))
        self.assertTrue(alarm.update(30.0))  # cảm biến lỗi: thà báo động thừa còn hơn bỏ sót

    def test_wrist_rotation_counts_as_movement_but_offset_and_noise_do_not(self):
        alarm = FallAlarm(cancel_window_s=30, immobile_s=10)
        feed(alarm, 0, 2, lambda t: (0.05, -0.04, 1.08))  # offset kiểu MPU6050 chưa hiệu chuẩn
        alarm.start(2.0)
        feed(alarm, 2, 5, lambda t: (0.05 + 0.005 * math.sin(40 * t), -0.04, 1.08))
        self.assertEqual(alarm.last_motion_at, 2.0)
        angle = math.radians(20)  # xoay cổ tay 20°: trọng lực đổi hướng, độ lớn vẫn 1 g
        feed(alarm, 7, 1, lambda t: (math.sin(angle), 0.0, math.cos(angle)))
        self.assertGreater(alarm.last_motion_at, 7.0)

    def test_beep_pattern_and_restart_does_not_reset_clock(self):
        alarm = FallAlarm(cancel_window_s=30, immobile_s=10, beep_period_s=1.0, beep_on_s=0.5)
        self.assertFalse(alarm.buzzer_on(0.0))
        alarm.start(5.0)
        self.assertEqual([alarm.buzzer_on(5.0 + x) for x in (0.0, 0.4, 0.6, 1.1, 1.7)],
                         [True, True, False, True, False])
        self.assertFalse(alarm.start(10.0))
        self.assertEqual(alarm.started_at, 5.0)


if __name__ == "__main__":
    unittest.main()
