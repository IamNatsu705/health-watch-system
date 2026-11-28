"""Đếm bước v2 trên luồng gia tốc đều 100 Hz lấy từ FIFO của MPU6050.

Hai bộ đếm chạy song song trên cùng tín hiệu cảm biến thật:

* ``steps_algorithm`` (``peak-bout-v2``): lọc độ lớn gia tốc 0,5–3 Hz, tìm đỉnh
  với ngưỡng thích nghi theo RMS, và chỉ cộng khi có ít nhất 6 đỉnh liên tiếp
  đều nhịp (loại cú vung tay, gõ, rung lẻ).
* ``steps_ai``: các đỉnh ứng viên (ngưỡng nhạy hơn) chỉ được cộng trong cửa sổ
  5 s mà mô hình AI ``WalkGate`` xác định là đang đi bộ. Có mặt khi nạp được
  mô hình; nếu không thì là ``None`` (không bịa số).

Tham số được chọn bằng dữ liệu thật OxWalk (cổ tay, 100 Hz, bước gán nhãn
bằng video). Quy trình và kết quả đánh giá nằm ở ``ml/README.md``.
"""

import math
from collections import deque

from processing.filters import butter_highpass, butter_lowpass
from processing.step_features import window_features


ALGORITHM_NAME = "peak-bout-v2"
SAMPLE_RATE_HZ = 100.0
WINDOW_S = 5.0
RUNNING_CADENCE_HZ = 2.5  # >=150 bước/phút coi là chạy khi ước tính năng lượng.

BANDPASS_LOW_HZ = 0.5
BANDPASS_HIGH_HZ = 3.0
HIGH_FREQ_HZ = 5.0
LOW_FREQ_HZ = 0.5
MIN_STEP_INTERVAL_S = 0.3

ALGORITHM_FLOOR_G = 0.08
ALGORITHM_RMS_FACTOR = 0.7
CANDIDATE_FLOOR_G = 0.05
CANDIDATE_RMS_FACTOR = 0.5

BOUT_REQUIRED_STEPS = 6
BOUT_MAX_GAP_S = 1.5
BOUT_MAX_CV = 0.2


class PeakPicker:
    """Tìm cực đại cục bộ vượt ngưỡng max(sàn, k·RMS 2 s), giữ đỉnh lớn hơn trong khoảng trơ."""

    def __init__(self, sample_rate_hz: float, floor_g: float, rms_factor: float,
                 min_interval_s: float, rms_window_s: float = 2.0):
        self.floor_g = floor_g
        self.rms_factor = rms_factor
        self.min_gap = max(1, int(round(min_interval_s * sample_rate_hz)))
        self.window = max(1, int(round(rms_window_s * sample_rate_hz)))
        self.reset()

    def reset(self) -> None:
        self._squares = deque()
        self._square_sum = 0.0
        self._y1 = None
        self._y2 = None
        self._threshold1 = 0.0
        self._pending = None

    def push(self, index: int, y: float) -> list[int]:
        square = y * y
        self._squares.append(square)
        self._square_sum += square
        if len(self._squares) > self.window:
            self._square_sum -= self._squares.popleft()
        rms = math.sqrt(max(self._square_sum, 0.0) / len(self._squares))
        threshold = max(self.floor_g, self.rms_factor * rms)

        emitted = []
        if (self._y2 is not None and self._y1 > self._y2 and self._y1 >= y
                and self._y1 > self._threshold1):
            candidate = (index - 1, self._y1)
            if self._pending is None:
                self._pending = candidate
            elif candidate[0] - self._pending[0] < self.min_gap:
                if candidate[1] > self._pending[1]:
                    self._pending = candidate
            else:
                emitted.append(self._pending[0])
                self._pending = candidate
        if self._pending is not None and index - self._pending[0] >= self.min_gap:
            emitted.append(self._pending[0])
            self._pending = None
        self._y2, self._y1, self._threshold1 = self._y1, y, threshold
        return emitted

    def flush(self) -> list[int]:
        if self._pending is None:
            return []
        index = self._pending[0]
        self._pending = None
        return [index]


class BoutCounter:
    """Chỉ xác nhận bước khi đã thấy chuỗi đỉnh đều nhịp; trả về (số bước, nhịp Hz)."""

    def __init__(self, required_steps: int = BOUT_REQUIRED_STEPS, max_gap_s: float = BOUT_MAX_GAP_S,
                 max_cv: float = BOUT_MAX_CV, min_interval_s: float = MIN_STEP_INTERVAL_S):
        self.required_steps = required_steps
        self.max_gap_s = max_gap_s
        self.max_cv = max_cv
        self.min_interval_s = min_interval_s
        self.reset()

    def reset(self) -> None:
        self._buffer = []
        self._in_bout = False
        self._last = None

    def add(self, t: float) -> list[tuple[int, float]]:
        committed = []
        if self._last is not None and t - self._last > self.max_gap_s:
            self._buffer = []
            self._in_bout = False
        if self._in_bout:
            interval = t - self._last
            committed.append((1, 1.0 / interval if interval > 0 else 0.0))
        else:
            self._buffer.append(t)
            if len(self._buffer) >= self.required_steps:
                recent = self._buffer[-self.required_steps:]
                intervals = [b - a for a, b in zip(recent, recent[1:])]
                mean = sum(intervals) / len(intervals)
                std = math.sqrt(sum((v - mean) ** 2 for v in intervals) / len(intervals))
                if (min(intervals) >= self.min_interval_s and max(intervals) <= self.max_gap_s
                        and mean > 0 and std / mean <= self.max_cv):
                    committed.append((len(recent), 1.0 / mean))
                    self._in_bout = True
                    self._buffer = []
                else:
                    self._buffer = self._buffer[-(self.required_steps - 1):]
        self._last = t
        return committed


class _Window:
    __slots__ = ("start", "end", "m", "y", "hf", "lf")

    def __init__(self, start, end, m, y, hf, lf):
        self.start, self.end, self.m, self.y, self.hf, self.lf = start, end, m, y, hf, lf


class StepEngine:
    def __init__(self, sample_rate_hz: float = SAMPLE_RATE_HZ, gate=None):
        if gate is not None and abs(gate.sample_rate_hz - sample_rate_hz) > 1e-6:
            raise ValueError("Mô hình được huấn luyện ở tần số lấy mẫu khác")
        self.sample_rate_hz = sample_rate_hz
        self.gate = gate
        self.window_len = int(round((gate.window_s if gate else WINDOW_S) * sample_rate_hz))
        self._bandpass_high = butter_highpass(BANDPASS_LOW_HZ, sample_rate_hz)
        self._bandpass_low = butter_lowpass(BANDPASS_HIGH_HZ, sample_rate_hz)
        self._high_freq = butter_highpass(HIGH_FREQ_HZ, sample_rate_hz)
        self._low_freq = butter_lowpass(LOW_FREQ_HZ, sample_rate_hz)
        self._algorithm_picker = PeakPicker(
            sample_rate_hz, ALGORITHM_FLOOR_G, ALGORITHM_RMS_FACTOR, MIN_STEP_INTERVAL_S)
        self._candidate_picker = PeakPicker(
            sample_rate_hz, CANDIDATE_FLOOR_G, CANDIDATE_RMS_FACTOR, MIN_STEP_INTERVAL_S)
        self._bout = BoutCounter()
        self._delay = self._candidate_picker.min_gap + 2

        self.steps_algorithm = 0
        self.running_steps_algorithm = 0
        self.steps_ai = 0 if gate is not None else None
        self.running_steps_ai = 0 if gate is not None else None
        self.walking = None
        self.walking_probability = None
        self.cadence_hz = None
        self.windows_evaluated = 0
        self.samples_processed = 0
        self.segments = 0
        self._new_primary = []
        self._start_segment()

    @property
    def model(self) -> dict | None:
        if self.gate is None:
            return None
        return {"name": self.gate.name, "version": self.gate.version}

    @property
    def primary_source(self) -> str:
        return "ai" if self.gate is not None else "algorithm"

    @property
    def primary_steps(self) -> int:
        return self.steps_ai if self.gate is not None else self.steps_algorithm

    @property
    def primary_running_steps(self) -> int:
        return self.running_steps_ai if self.gate is not None else self.running_steps_algorithm

    def _start_segment(self) -> None:
        self._started = False
        self._index = 0
        self._window_start = 0
        self._m, self._y, self._hf, self._lf = [], [], [], []
        self._closed = deque()
        self._candidates = deque()
        self._prev_features = None
        self._algorithm_picker.reset()
        self._candidate_picker.reset()
        self._bout.reset()
        self.segments += 1

    def reset_signal(self) -> None:
        """Gọi khi luồng mẫu bị đứt (tràn FIFO, khởi tạo lại cảm biến)."""
        if self._started:
            for index in self._algorithm_picker.flush():
                self._on_algorithm_peak(index)
            if self.gate is not None:
                self._candidates.extend(self._candidate_picker.flush())
                while self._closed:
                    self._evaluate(self._closed.popleft())
        self.walking = None
        self.walking_probability = None
        self.cadence_hz = None
        self._start_segment()

    def drain_new_steps(self) -> list[tuple[int, float]]:
        """Các bước mới của nguồn chính (AI nếu có, ngược lại là thuật toán) kèm nhịp Hz."""
        steps, self._new_primary = self._new_primary, []
        return steps

    def add_sample(self, ax: float, ay: float, az: float) -> None:
        m = math.sqrt(ax * ax + ay * ay + az * az)
        if not self._started:
            self._bandpass_high.reset(m)
            self._bandpass_low.reset(0.0)
            self._high_freq.reset(m)
            self._low_freq.reset(m)
            self._started = True
        y = self._bandpass_low.process(self._bandpass_high.process(m))
        index = self._index
        for peak in self._algorithm_picker.push(index, y):
            self._on_algorithm_peak(peak)

        if self.gate is not None:
            self._candidates.extend(self._candidate_picker.push(index, y))
            self._m.append(m)
            self._y.append(y)
            self._hf.append(self._high_freq.process(m))
            self._lf.append(self._low_freq.process(m))
        self._index += 1
        self.samples_processed += 1

        if self.gate is not None:
            if self._index - self._window_start >= self.window_len:
                self._closed.append(_Window(self._window_start, self._index,
                                            self._m, self._y, self._hf, self._lf))
                self._m, self._y, self._hf, self._lf = [], [], [], []
                self._window_start = self._index
            while self._closed and self._index >= self._closed[0].end + self._delay:
                self._evaluate(self._closed.popleft())

    def _add_steps(self, source: str, count: int, cadence_hz: float) -> None:
        running = count if cadence_hz >= RUNNING_CADENCE_HZ else 0
        if source == "ai":
            self.steps_ai += count
            self.running_steps_ai += running
        else:
            self.steps_algorithm += count
            self.running_steps_algorithm += running
        if source == self.primary_source and count:
            self._new_primary.append((count, cadence_hz))

    def _on_algorithm_peak(self, index: int) -> None:
        for count, cadence in self._bout.add(index / self.sample_rate_hz):
            self._add_steps("algorithm", count, cadence)

    def window_input(self, window: _Window, candidates: list[int]) -> list[float]:
        features = window_features(window.m, window.y, window.hf, window.lf,
                                   candidates, self.sample_rate_hz)
        previous = self._prev_features if self._prev_features is not None else features
        self._prev_features = features
        return features + previous

    def _evaluate(self, window: _Window) -> None:
        candidates = []
        while self._candidates and self._candidates[0] < window.end:
            index = self._candidates.popleft()
            if index >= window.start:
                candidates.append(index - window.start)
        x = self.window_input(window, candidates)
        probability = self.gate.predict_proba(x)
        walking = probability >= self.gate.threshold
        cadence = None
        if len(candidates) >= 2:
            intervals = sorted(b - a for a, b in zip(candidates, candidates[1:]))
            middle = intervals[len(intervals) // 2] if len(intervals) % 2 else (
                intervals[len(intervals) // 2 - 1] + intervals[len(intervals) // 2]) / 2
            cadence = self.sample_rate_hz / middle if middle > 0 else None
        if walking:
            self._add_steps("ai", len(candidates), cadence or 0.0)
        self.walking = walking
        self.walking_probability = probability
        self.cadence_hz = cadence if walking else None
        self.windows_evaluated += 1
        self.on_window(window, candidates, x, probability)

    def on_window(self, window, candidates, x, probability) -> None:
        """Điểm móc cho công cụ huấn luyện/đánh giá (``ml/``); trên Pi không làm gì."""
