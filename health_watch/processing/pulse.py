"""Ước tính nhịp tim từ dao động IR để kiểm tra cảm biến, chưa hiệu chuẩn y tế."""

from collections import deque
from statistics import mean, median, pstdev


class PulseMonitor:
    def __init__(self, sample_rate: int = 25):
        self.sample_rate = sample_rate
        self.ir_history = deque(maxlen=sample_rate * 8)
        self.red = 0
        self.ir = 0
        self.bpm = None
        self.finger_present = False
        self._last_analysis = float("-inf")

    def add(self, red: int, ir: int) -> None:
        self.red = red
        self.ir = ir
        self.ir_history.append(ir)

    def analyze(self, now: float) -> None:
        if now - self._last_analysis < 1.0:
            return
        self._last_analysis = now
        values = list(self.ir_history)
        self.finger_present = len(values) >= self.sample_rate and mean(values[-self.sample_rate:]) > 10_000
        if not self.finger_present:
            self.bpm = None
            self.ir_history.clear()
            return
        if len(values) < self.sample_rate * 5:
            self.bpm = None
            return

        # Bỏ độ sáng nền bằng trung bình trượt, rồi tìm đỉnh cách nhau >=0,35 s.
        half_window = max(2, self.sample_rate // 4)
        centered = []
        for i, value in enumerate(values):
            baseline = mean(values[max(0, i - half_window):min(len(values), i + half_window + 1)])
            centered.append(value - baseline)
        noise = pstdev(centered)
        threshold = max(80.0, noise * 0.45)
        peaks = []
        min_gap = int(0.35 * self.sample_rate)
        for i in range(1, len(centered) - 1):
            if centered[i] > threshold and centered[i] > centered[i - 1] and centered[i] >= centered[i + 1]:
                if not peaks or i - peaks[-1] >= min_gap:
                    peaks.append(i)
                elif centered[i] > centered[peaks[-1]]:
                    peaks[-1] = i
        intervals = [
            (b - a) / self.sample_rate for a, b in zip(peaks, peaks[1:])
            if 0.35 <= (b - a) / self.sample_rate <= 1.5
        ]
        if len(intervals) < 3:
            self.bpm = None
            return
        bpm = round(60 / median(intervals[-5:]))
        self.bpm = bpm if 40 <= bpm <= 180 else None
