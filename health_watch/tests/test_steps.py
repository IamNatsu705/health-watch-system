"""Bộ đếm bước v2 và mô hình AI trên đoạn dữ liệu thật OxWalk (xem tests/data/README.md)."""

import gzip
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from inference.walk_gate import DEFAULT_MODEL_PATH, WalkGate
from processing.filters import Biquad, butter_highpass, butter_lowpass
from processing.step_features import GATE_INPUT_NAMES
from processing.steps import BoutCounter, PeakPicker, StepEngine

DATA = Path(__file__).resolve().parent / "data"


def load_excerpt(name: str):
    with gzip.open(DATA / name, "rt", encoding="utf-8") as handle:
        next(handle)
        rows = [line.split(",") for line in handle]
    return [(float(a), float(b), float(c)) for a, b, c, _ in rows], sum(int(r[3]) for r in rows)


class FixedGate:
    """Cổng cố định để kiểm tra cơ chế cộng bước, không phải mô hình thật."""

    name = "fixed"
    version = "test"
    window_s = 5.0
    sample_rate_hz = 100.0
    threshold = 0.5

    def __init__(self, probability: float):
        self.probability = probability

    def predict_proba(self, x) -> float:
        return self.probability


def run(engine: StepEngine, samples) -> StepEngine:
    for ax, ay, az in samples:
        engine.add_sample(ax, ay, az)
    engine.reset_signal()
    return engine


class FilterTests(unittest.TestCase):
    def test_butterworth_coefficients_match_scipy(self):
        # Giá trị tham chiếu từ scipy.signal.butter(2, fc, btype, fs=100).
        low = butter_lowpass(3.0, 100.0)
        self.assertAlmostEqual(low.b0, 0.007820208033497191, places=12)
        self.assertAlmostEqual(low.a1, -1.734725768809275, places=12)
        self.assertAlmostEqual(low.a2, 0.7660066009432638, places=12)
        high = butter_highpass(0.5, 100.0)
        self.assertAlmostEqual(high.b0, 0.9780304792065595, places=12)
        self.assertAlmostEqual(high.a1, -1.9555782403150352, places=12)

    def test_reset_starts_in_steady_state(self):
        high = butter_highpass(0.5, 100.0)
        high.reset(1.0)
        self.assertAlmostEqual(max(abs(high.process(1.0)) for _ in range(200)), 0.0, places=12)
        low = butter_lowpass(0.5, 100.0)
        low.reset(1.0)
        self.assertAlmostEqual(low.process(1.0), 1.0, places=12)

    def test_biquad_dc_gain(self):
        self.assertAlmostEqual(Biquad(0.5, 0.0, 0.0, 0.0, 0.0).dc_gain, 0.5)


class PeakAndBoutTests(unittest.TestCase):
    def test_refractory_keeps_larger_peak(self):
        picker = PeakPicker(100.0, floor_g=0.05, rms_factor=0.0, min_interval_s=0.3)
        signal = [0.0] * 100
        signal[10] = 0.2   # đỉnh nhỏ
        signal[20] = 0.5   # đỉnh lớn hơn trong 0,3 s → thay thế
        signal[70] = 0.3   # đỉnh tách biệt
        peaks = []
        for i, value in enumerate(signal):
            peaks += picker.push(i, value)
        peaks += picker.flush()
        self.assertEqual(peaks, [20, 70])

    def test_bout_requires_regular_sequence(self):
        bout = BoutCounter(required_steps=6, max_gap_s=1.5, max_cv=0.2)
        committed = []
        for i in range(10):
            committed += bout.add(i * 0.55)
        self.assertEqual(sum(c for c, _ in committed), 10)
        self.assertAlmostEqual(committed[0][1], 1 / 0.55, places=6)

    def test_isolated_peaks_are_not_steps(self):
        bout = BoutCounter()
        committed = []
        for t in (0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0):  # cách >1,5 s: mỗi đỉnh là chuỗi mới
            committed += bout.add(t)
        self.assertEqual(committed, [])

    def test_irregular_peaks_are_not_steps(self):
        bout = BoutCounter()
        committed = []
        t = 0.0
        for interval in (0.3, 1.2, 0.35, 1.1, 0.4, 1.3, 0.3, 1.0):
            t += interval
            committed += bout.add(t)
        self.assertEqual(committed, [])


class EngineTests(unittest.TestCase):
    def test_still_sensor_counts_nothing(self):
        engine = run(StepEngine(gate=FixedGate(1.0)), [(0.0, 0.0, 1.0)] * 3000)
        self.assertEqual(engine.steps_algorithm, 0)
        self.assertEqual(engine.steps_ai, 0)

    def test_without_model_ai_count_is_absent_not_zero(self):
        engine = run(StepEngine(gate=None), [(0.0, 0.0, 1.0)] * 600)
        self.assertIsNone(engine.steps_ai)
        self.assertIsNone(engine.model)
        self.assertEqual(engine.primary_source, "algorithm")

    def test_gate_controls_ai_count_on_real_walking(self):
        samples, true_steps = load_excerpt("oxwalk_P01_walking_60s.csv.gz")
        open_gate = run(StepEngine(gate=FixedGate(1.0)), samples)
        closed_gate = run(StepEngine(gate=FixedGate(0.0)), samples)
        self.assertEqual(closed_gate.steps_ai, 0)
        self.assertGreater(open_gate.steps_ai, 0.8 * true_steps)
        self.assertEqual(open_gate.steps_algorithm, closed_gate.steps_algorithm)

    def test_signal_reset_does_not_chain_steps_across_gap(self):
        samples, _ = load_excerpt("oxwalk_P01_walking_60s.csv.gz")
        engine = StepEngine(gate=FixedGate(1.0))
        for ax, ay, az in samples[:3000]:
            engine.add_sample(ax, ay, az)
        engine.reset_signal()
        self.assertIsNone(engine.walking)
        for ax, ay, az in samples[3000:]:
            engine.add_sample(ax, ay, az)
        engine.reset_signal()
        self.assertGreater(engine.steps_algorithm, 0)

    def test_rejects_model_with_other_sample_rate(self):
        gate = FixedGate(1.0)
        gate.sample_rate_hz = 25.0
        with self.assertRaises(ValueError):
            StepEngine(100.0, gate=gate)


@unittest.skipUnless(DEFAULT_MODEL_PATH.exists(), "chưa có models/walk_gate.json")
class RealModelTests(unittest.TestCase):
    """Hồi quy toàn bộ đường suy luận trên Pi với mô hình JSON thật."""

    @classmethod
    def setUpClass(cls):
        cls.gate = WalkGate.load(DEFAULT_MODEL_PATH)

    def test_real_walking_is_counted(self):
        samples, true_steps = load_excerpt("oxwalk_P01_walking_60s.csv.gz")
        engine = run(StepEngine(gate=self.gate), samples)
        self.assertLess(abs(engine.steps_ai - true_steps) / true_steps, 0.15)
        self.assertLess(abs(engine.steps_algorithm - true_steps) / true_steps, 0.20)

    def test_real_arm_movement_without_steps_is_rejected_by_ai(self):
        samples, true_steps = load_excerpt("oxwalk_P11_no_steps_60s.csv.gz")
        self.assertEqual(true_steps, 0)
        engine = run(StepEngine(gate=self.gate), samples)
        self.assertLessEqual(engine.steps_ai, 5)
        # Đây là lý do cần AI: chỉ xử lý tín hiệu vẫn đếm khống khi khua tay đều nhịp
        # (đo được 49 bước giả trong 60 s). Giữ ràng buộc để phát hiện nếu tệ hơn.
        self.assertLessEqual(engine.steps_algorithm, 60)

    def test_probability_is_bounded(self):
        x = [0.0] * len(GATE_INPUT_NAMES)
        probability = self.gate.predict_proba(x)
        self.assertTrue(0.0 <= probability <= 1.0 and math.isfinite(probability))


if __name__ == "__main__":
    unittest.main()
