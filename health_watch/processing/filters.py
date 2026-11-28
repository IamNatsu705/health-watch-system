"""Bộ lọc IIR bậc 2 (biquad) thuần Python cho xử lý tín hiệu theo từng mẫu.

Hệ số Butterworth bậc 2 được tính bằng biến đổi song tuyến có prewarp
(công thức Audio EQ Cookbook, Q = 1/sqrt(2)); kết quả trùng với
``scipy.signal.butter(2, fc, btype, fs=fs)``. Không cần numpy/scipy trên Pi.
"""

import math


class Biquad:
    """Dạng Direct Form II chuyển vị, giữ trạng thái giữa các mẫu."""

    __slots__ = ("b0", "b1", "b2", "a1", "a2", "z1", "z2")

    def __init__(self, b0: float, b1: float, b2: float, a1: float, a2: float):
        self.b0, self.b1, self.b2, self.a1, self.a2 = b0, b1, b2, a1, a2
        self.z1 = 0.0
        self.z2 = 0.0

    @property
    def dc_gain(self) -> float:
        return (self.b0 + self.b1 + self.b2) / (1.0 + self.a1 + self.a2)

    def reset(self, x: float = 0.0) -> None:
        """Đặt trạng thái ổn định như thể đầu vào đã bằng ``x`` từ lâu.

        Tránh xung quá độ lớn khi bắt đầu hoặc sau khi mất mẫu (ví dụ độ lớn
        gia tốc ~1 g đi vào bộ lọc thông cao sẽ cho đầu ra ~0 ngay lập tức).
        """
        y = self.dc_gain * x
        self.z2 = self.b2 * x - self.a2 * y
        self.z1 = y - self.b0 * x

    def process(self, x: float) -> float:
        y = self.b0 * x + self.z1
        self.z1 = self.b1 * x - self.a1 * y + self.z2
        self.z2 = self.b2 * x - self.a2 * y
        return y


def _prepare(cutoff_hz: float, sample_rate_hz: float) -> tuple[float, float]:
    if not 0 < cutoff_hz < sample_rate_hz / 2:
        raise ValueError("Tần số cắt phải nằm trong (0, fs/2)")
    w0 = 2.0 * math.pi * cutoff_hz / sample_rate_hz
    alpha = math.sin(w0) / (2.0 * (1.0 / math.sqrt(2.0)))
    return math.cos(w0), alpha


def butter_lowpass(cutoff_hz: float, sample_rate_hz: float) -> Biquad:
    cos_w0, alpha = _prepare(cutoff_hz, sample_rate_hz)
    a0 = 1.0 + alpha
    b0 = (1.0 - cos_w0) / 2.0 / a0
    return Biquad(b0, 2.0 * b0, b0, -2.0 * cos_w0 / a0, (1.0 - alpha) / a0)


def butter_highpass(cutoff_hz: float, sample_rate_hz: float) -> Biquad:
    cos_w0, alpha = _prepare(cutoff_hz, sample_rate_hz)
    a0 = 1.0 + alpha
    b0 = (1.0 + cos_w0) / 2.0 / a0
    return Biquad(b0, -2.0 * b0, b0, -2.0 * cos_w0 / a0, (1.0 - alpha) / a0)
