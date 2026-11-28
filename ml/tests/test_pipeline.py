"""Kiểm tra cơ chế nạp/gán nhãn bản ghi nhóm và hàm mục tiêu chọn ngưỡng.

Tín hiệu dùng ở đây là hai đoạn OxWalk thật (health_watch/tests/data), lưu lại theo định
dạng của record_imu.py chỉ để kiểm tra cơ chế; test này không tạo dữ liệu huấn luyện.
"""

import csv
import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ml.common import UNLABELED, load_team, run_engine  # noqa: E402
from ml.train_walk_gate import score  # noqa: E402

DATA = Path(__file__).resolve().parents[2] / "health_watch" / "tests" / "data"


def excerpt(name):
    with gzip.open(DATA / name, "rt", encoding="utf-8") as handle:
        next(handle)
        return [tuple(float(v) for v in line.split(",")[:3]) for line in handle]


def write_session(directory: Path, session: str, samples, activity: str, true_steps, gap_at=None):
    with open(directory / f"{session}.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sample_index", "t_s", "ax_g", "ay_g", "az_g", "gx_dps", "gy_dps", "gz_dps", "gap_before"])
        for i, (ax, ay, az) in enumerate(samples):
            writer.writerow([i, f"{i / 100:.4f}", ax, ay, az, 0, 0, 0, int(i == gap_at)])
    (directory / f"{session}.json").write_text(json.dumps({
        "format": "health-watch-imu-recording-v1", "session_id": session, "subject_id": "S01",
        "activity": activity, "true_step_count": true_steps, "sample_rate_hz": 100.0,
    }), encoding="utf-8")


class TeamPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        walking = excerpt("oxwalk_P01_walking_60s.csv.gz")
        moving = excerpt("oxwalk_P11_no_steps_60s.csv.gz")
        write_session(root, "a_walk", walking, "walk_normal", 114, gap_at=3000)
        write_session(root, "b_talk", moving, "gesture_talk", 0)
        write_session(root, "c_free", moving[:3000] + walking[:3000], "free_living", 57)
        cls.recordings = {r.session: r for r in load_team(root)}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_gap_column_is_read(self):
        self.assertEqual(self.recordings["a_walk"].gap_index.tolist(), [3000])

    def test_labels_follow_activity_and_skip_uncertain_windows(self):
        walk = run_engine(self.recordings["a_walk"])["windows"]
        labels = [row[4] for row in walk]
        self.assertEqual(labels[0], UNLABELED)
        self.assertEqual(labels[-1], UNLABELED)
        self.assertTrue(all(label == 1 for label in labels[1:-1]))
        talk = run_engine(self.recordings["b_talk"])["windows"]
        self.assertTrue(all(row[4] == 0 for row in talk))
        free = run_engine(self.recordings["c_free"])["windows"]
        self.assertTrue(all(row[4] == UNLABELED for row in free))

    def test_windows_after_gap_use_absolute_sample_indices(self):
        walk = run_engine(self.recordings["a_walk"])["windows"]
        starts = [row[0] for row in walk]
        self.assertEqual(starts, sorted(starts))
        self.assertIn(3000, starts)           # đoạn sau chỗ đứt bắt đầu lại từ mẫu 3000
        self.assertTrue(all(end <= 6000 for _, end, *_ in walk))

    def test_objective_penalises_false_steps_in_zero_step_sessions(self):
        rows = [
            {"true": 100, "ai": 90, "algorithm": 80, "minutes": 1.0},
            {"true": 0, "ai": 20, "algorithm": 50, "minutes": 2.0},
        ]
        ai = score(rows, "ai")
        self.assertEqual(ai["mape_percent"], 10.0)
        self.assertEqual(ai["false_steps_per_min"], 10.0)
        self.assertAlmostEqual(ai["objective"], (10.0 + 10.0) / 2)
        self.assertGreater(score(rows, "algorithm")["objective"], ai["objective"])
        self.assertIsNone(score([], "ai")["objective"])
        self.assertTrue(np.isfinite(score(rows[1:], "ai")["objective"]))


if __name__ == "__main__":
    unittest.main()
