"""Nạp dữ liệu thật để huấn luyện/đánh giá đếm bước và chạy đúng code của Pi trên đó.

Chỉ dùng dữ liệu ghi từ người thật:

* OxWalk (Small et al., 2022, CC BY 4.0): 39 người, AX3 ở cổ tay, 100 Hz, ±8 g,
  từng bước gán nhãn bằng video quay chân.
* Clemson Pedometer Evaluation (Mattfeld, Jesch, Hoover): 30 người, cổ tay,
  15 Hz, bước gán nhãn bằng video. Dùng làm kiểm định độc lập.
* Bản ghi MPU6050 của nhóm do ``health_watch/record_imu.py`` tạo (CSV + JSON).

Không có hàm nào sinh tín hiệu tổng hợp.
"""

import csv
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

for _stream in (sys.stdout, sys.stderr):
    # PowerShell/cmd trên Windows mặc định cp1252: in tiếng Việt sẽ lỗi nếu không đổi.
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[1]
PI_SOURCE = REPO / "health_watch"
if str(PI_SOURCE) not in sys.path:
    sys.path.insert(0, str(PI_SOURCE))

from processing.steps import SAMPLE_RATE_HZ, StepEngine  # noqa: E402

FS = SAMPLE_RATE_HZ
WALKING_LABEL_MIN_STEPS = 3  # cửa sổ 5 s có >=3 bước gán nhãn được coi là đang đi bộ

# Nhãn hoạt động của bản ghi nhóm (record_imu.py). Chỉ phiên thuần đi bộ hoặc thuần
# không đi bộ mới cho nhãn cửa sổ; phiên trộn lẫn (free_living) không có nhãn từng bước nên
# chỉ dùng để đánh giá tổng số bước, không dùng để huấn luyện (nhãn -1).
WALKING_ACTIVITIES = {
    "walk_normal", "walk_slow", "walk_fast", "stairs_up", "stairs_down", "run", "walk_no_swing",
}
NON_WALKING_ACTIVITIES = {
    "stand", "sit", "desk_work", "gesture_talk", "arm_swing_stand", "brush_teeth", "wash_hands",
    "household", "motorbike_passenger", "bus_or_car",
}
UNLABELED = -1


@dataclass
class Recording:
    """Một bản ghi gia tốc thật ở 100 Hz, đơn vị g."""

    source: str              # oxwalk | clemson | team
    subject: str             # mã người tham gia (nhóm theo người khi đánh giá chéo)
    session: str
    xyz: np.ndarray          # (n, 3) float64, g
    step_index: np.ndarray | None = None   # chỉ số mẫu của từng bước (nếu gán nhãn từng bước)
    true_steps: int | None = None          # tổng số bước thật
    activity: str | None = None            # nhãn hoạt động cả phiên (dữ liệu nhóm)
    gap_index: np.ndarray | None = None    # chỉ số mẫu ngay sau một lần đứt mẫu (tràn FIFO, lỗi I2C)
    meta: dict = field(default_factory=dict)


def load_oxwalk(directory: Path) -> list[Recording]:
    """``directory`` là thư mục ``Wrist_100Hz`` sau khi giải nén OxWalk."""
    recordings = []
    for path in sorted(Path(directory).glob("P*_wrist100.csv")):
        data = np.loadtxt(path, delimiter=",", skiprows=1, usecols=(1, 2, 3, 4), dtype=np.float64)
        steps = np.flatnonzero(data[:, 3] > 0.5)
        recordings.append(Recording(
            source="oxwalk", subject=path.name[:3], session=path.stem,
            xyz=data[:, :3], step_index=steps, true_steps=int(len(steps)),
        ))
    if not recordings:
        raise FileNotFoundError(f"Không thấy P*_wrist100.csv trong {directory}")
    return recordings


def load_clemson(directory: Path) -> list[Recording]:
    """``directory`` chứa P001/Regular/P001_Regular.txt + steps.txt, ...; nội suy 15 Hz → 100 Hz."""
    recordings = []
    for data_path in sorted(Path(directory).glob("P*/*/P*_*.txt")):
        raw = np.loadtxt(data_path)[:, :3]  # 3 cột đầu: cổ tay x, y, z (g)
        steps = []
        with open(data_path.parent / "steps.txt", encoding="utf-8") as handle:
            for line in handle:
                parts = line.split()
                # "left"/"right" là bước; "leftshift"/"rightshift" là dồn trọng tâm, không phải bước.
                if len(parts) == 2 and parts[1] in {"left", "right"}:
                    steps.append(int(parts[0]))
        source_t = np.arange(len(raw)) / 15.0
        target_t = np.arange(0.0, source_t[-1], 1.0 / FS)
        xyz = np.column_stack([np.interp(target_t, source_t, raw[:, k]) for k in range(3)])
        step_index = np.clip(np.round(np.array(steps) / 15.0 * FS).astype(int), 0, len(xyz) - 1)
        recordings.append(Recording(
            source="clemson", subject=data_path.parts[-3], session=data_path.stem,
            xyz=xyz, step_index=step_index, true_steps=len(steps),
            meta={"gait": data_path.parts[-2]},
        ))
    if not recordings:
        raise FileNotFoundError(f"Không thấy dữ liệu Clemson trong {directory}")
    return recordings


def load_team(directory: Path) -> list[Recording]:
    """Bản ghi do ``record_imu.py`` tạo: ``<session>.csv`` + ``<session>.json``."""
    recordings = []
    for meta_path in sorted(Path(directory).glob("*.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("format") != "health-watch-imu-recording-v1":
            continue
        if abs(float(meta["sample_rate_hz"]) - FS) > 1e-6:
            raise ValueError(f"{meta_path.name}: tần số {meta['sample_rate_hz']} khác {FS}")
        csv_path = meta_path.with_suffix(".csv")
        with open(csv_path, newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        xyz = np.array([[float(r["ax_g"]), float(r["ay_g"]), float(r["az_g"])] for r in rows])
        gap_index = np.array([i for i, r in enumerate(rows) if i and r.get("gap_before") == "1"], dtype=int)
        if len(gap_index):
            print(f"Cảnh báo: {meta_path.name} có {len(gap_index)} lần đứt mẫu (xử lý như Pi)", file=sys.stderr)
        activity = str(meta["activity"])
        if activity not in WALKING_ACTIVITIES | NON_WALKING_ACTIVITIES | {"free_living"}:
            raise ValueError(f"{meta_path.name}: hoạt động lạ {activity!r}")
        recordings.append(Recording(
            source="team", subject=str(meta["subject_id"]), session=str(meta["session_id"]),
            xyz=xyz, true_steps=meta.get("true_step_count"), activity=activity,
            gap_index=gap_index, meta=meta,
        ))
    return recordings


class _CollectGate:
    """Cổng giả lập chỉ để thu đặc trưng cửa sổ; không quyết định gì (xác suất 0)."""

    name = "collect-features"
    version = "0"
    threshold = 0.5
    window_s = 5.0
    sample_rate_hz = FS

    def predict_proba(self, x) -> float:
        return 0.0


class _CollectingEngine(StepEngine):
    def __init__(self):
        super().__init__(FS, gate=_CollectGate())
        self.windows = []
        self.offset = 0  # chỉ số tuyệt đối của mẫu đầu đoạn hiện tại (engine đánh số lại sau mỗi lần đứt)

    def on_window(self, window, candidates, x, probability):
        self.windows.append((window.start + self.offset, window.end + self.offset, len(candidates), list(x)))


def window_label(recording: Recording, start: int, end: int, first: bool, last: bool):
    if recording.step_index is not None:
        true_in_window = int(np.count_nonzero((recording.step_index >= start) & (recording.step_index < end)))
        return true_in_window, int(true_in_window >= WALKING_LABEL_MIN_STEPS)
    if recording.activity in NON_WALKING_ACTIVITIES:
        return None, 0
    if recording.activity in WALKING_ACTIVITIES and not (first or last):
        # Bỏ cửa sổ đầu/cuối phiên đi bộ: người đeo có thể chưa bắt đầu hoặc đã dừng.
        return None, 1
    return None, UNLABELED


def run_engine(recording: Recording, gate=None) -> dict:
    """Chạy đúng ``StepEngine`` của Pi trên bản ghi; trả số bước và đặc trưng từng cửa sổ.

    Chỗ đứt mẫu trong bản ghi (``gap_index``) được xử lý giống Pi: ``reset_signal()``.
    """
    engine = _CollectingEngine() if gate is None else StepEngine(FS, gate=gate)
    gaps = set(recording.gap_index.tolist()) if recording.gap_index is not None else set()
    for index, (ax, ay, az) in enumerate(recording.xyz.tolist()):
        if index in gaps:
            engine.reset_signal()
            if gate is None:
                engine.offset = index
        engine.add_sample(ax, ay, az)
    engine.reset_signal()  # xả các đỉnh/cửa sổ còn chờ ở cuối bản ghi
    result = {
        "source": recording.source,
        "subject": recording.subject,
        "session": recording.session,
        "activity": recording.activity,
        "true_steps": recording.true_steps,
        "algorithm_steps": engine.steps_algorithm,
        "ai_steps": engine.steps_ai if gate is not None else None,
        "duration_s": len(recording.xyz) / FS,
    }
    if gate is None:
        rows = []
        count = len(engine.windows)
        for i, (start, end, n_candidates, x) in enumerate(engine.windows):
            true_in_window, label = window_label(recording, start, end, i == 0, i == count - 1)
            rows.append((start, end, n_candidates, true_in_window, label, x))
        result["windows"] = rows
    return result
