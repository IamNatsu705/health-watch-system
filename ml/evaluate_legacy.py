"""Đo lại bộ đếm bước cũ (peak-v1, trước nâng cấp) trên cùng dữ liệu thật để so sánh.

Mã thuật toán cũ được chép nguyên văn từ commit dd99904 (health_watch/processing/steps.py).
Bộ đếm cũ chạy ở ~25 Hz nên dữ liệu 100 Hz được lấy 1/4 mẫu (trường hợp tốt nhất;
trên Pi thật còn mất mẫu do màn hình TFT chặn vòng lặp).

    python ml/evaluate_legacy.py --oxwalk .../Wrist_100Hz --clemson .../clemson
"""

import argparse
import math
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml.common import load_clemson, load_oxwalk  # noqa: E402
from ml.train_walk_gate import summarize  # noqa: E402


class LegacyStepCounter:
    """Bản sao thuật toán peak-v1 cũ, chỉ để đo so sánh."""

    def __init__(self):
        self.steps = 0
        self.gravity = 1.0
        self.filtered = 0.0
        self.previous = 0.0
        self.before_previous = 0.0
        self.last_step_time = float("-inf")

    def update(self, motion, now: float) -> None:
        magnitude = math.sqrt(motion.ax**2 + motion.ay**2 + motion.az**2)
        self.gravity = 0.95 * self.gravity + 0.05 * magnitude
        self.filtered = 0.6 * self.filtered + 0.4 * (magnitude - self.gravity)
        is_peak = (
            self.previous > 0.12
            and self.previous > self.before_previous
            and self.previous >= self.filtered
        )
        interval = now - self.last_step_time
        if is_peak and 0.35 <= interval and magnitude < 3.0:
            self.steps += 1
            self.last_step_time = now
        self.before_previous = self.previous
        self.previous = self.filtered


def run_legacy(recording):
    counter = LegacyStepCounter()
    for i in range(0, len(recording.xyz), 4):
        ax, ay, az = recording.xyz[i]
        counter.update(SimpleNamespace(ax=ax, ay=ay, az=az), i / 100.0)
    return recording.true_steps, counter.steps, recording.meta.get("gait")


def report(name, rows):
    true = np.array([r[0] for r in rows], dtype=float)
    predicted = np.array([r[1] for r in rows], dtype=float)
    print(name, summarize(true, predicted))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--oxwalk", type=Path, required=True)
    parser.add_argument("--clemson", type=Path)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    with ProcessPoolExecutor(args.workers) as pool:
        report("OxWalk peak-v1", list(pool.map(run_legacy, load_oxwalk(args.oxwalk))))
        if args.clemson:
            rows = list(pool.map(run_legacy, load_clemson(args.clemson)))
            report("Clemson peak-v1 all", rows)
            for gait in ("Regular", "SemiRegular", "Irregular"):
                report(f"Clemson peak-v1 {gait}", [r for r in rows if r[2] == gait])


if __name__ == "__main__":
    main()
