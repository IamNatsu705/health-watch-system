"""Mô hình Random Forest "đang đi bộ hay không" xuất ra JSON, suy luận thuần Python.

File mô hình do ``ml/train_walk_gate.py`` tạo từ dữ liệu thật (OxWalk và dữ liệu
nhóm tự ghi). Không dùng pickle: file JSON chỉ chứa cây quyết định, nên không
thực thi mã khi nạp và không phụ thuộc phiên bản scikit-learn trên Pi.
"""

import json
import logging
import math
from array import array
from pathlib import Path

from processing.step_features import FEATURE_VERSION, GATE_INPUT_NAMES


log = logging.getLogger("health_watch.inference")
MODEL_FORMAT = "health-watch-rf-v1"
DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "walk_gate.json"


class ModelError(ValueError):
    """File mô hình không dùng được; hệ thống chạy tiếp không có AI."""


class _Tree:
    __slots__ = ("left", "right", "feature", "threshold", "prob")

    def __init__(self, document: dict, n_features: int):
        self.left = document["left"]
        self.right = document["right"]
        self.feature = document["feature"]
        self.threshold = document["threshold"]
        self.prob = document["p"]
        n = len(self.left)
        if not n or any(len(seq) != n for seq in (self.right, self.feature, self.threshold, self.prob)):
            raise ModelError("Cây quyết định có mảng không cùng độ dài")
        for i in range(n):
            left, right = self.left[i], self.right[i]
            if left == -1:
                if right != -1 or not 0.0 <= self.prob[i] <= 1.0:
                    raise ModelError("Nút lá không hợp lệ")
                continue
            if not (i < left < n and i < right < n):
                raise ModelError("Chỉ số nút con không hợp lệ")
            if not 0 <= self.feature[i] < n_features or not math.isfinite(self.threshold[i]):
                raise ModelError("Đặc trưng/ngưỡng của nút không hợp lệ")

    def predict(self, x) -> float:
        node = 0
        left, right, feature, threshold = self.left, self.right, self.feature, self.threshold
        while left[node] != -1:
            node = left[node] if x[feature[node]] <= threshold[node] else right[node]
        return self.prob[node]


class WalkGate:
    def __init__(self, document: dict):
        if document.get("format") != MODEL_FORMAT:
            raise ModelError("Sai định dạng file mô hình")
        if document.get("feature_version") != FEATURE_VERSION:
            raise ModelError("Mô hình được huấn luyện với phiên bản đặc trưng khác")
        if tuple(document.get("feature_names", ())) != GATE_INPUT_NAMES:
            raise ModelError("Danh sách đặc trưng của mô hình không khớp mã nguồn")
        self.name = str(document["model_name"])
        self.version = str(document["model_version"])
        self.threshold = float(document["threshold"])
        self.window_s = float(document["window_s"])
        self.sample_rate_hz = float(document["sample_rate_hz"])
        if not 0.0 < self.threshold < 1.0:
            raise ModelError("Ngưỡng quyết định phải trong (0, 1)")
        self.trees = [_Tree(tree, len(GATE_INPUT_NAMES)) for tree in document["trees"]]
        if not self.trees:
            raise ModelError("Mô hình không có cây nào")
        self.metadata = {
            key: document.get(key)
            for key in ("created_at", "training_data", "evaluation")
        }

    @classmethod
    def load(cls, path: Path | str = DEFAULT_MODEL_PATH) -> "WalkGate":
        try:
            document = json.loads(Path(path).read_text(encoding="utf-8"))
            return cls(document)
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ModelError(f"Không nạp được mô hình {path}: {exc}") from exc

    def predict_proba(self, x) -> float:
        if len(x) != len(GATE_INPUT_NAMES):
            raise ValueError("Số đặc trưng không khớp mô hình")
        if not all(math.isfinite(value) for value in x):
            raise ValueError("Đặc trưng không hữu hạn")
        # scikit-learn so sánh đặc trưng ở float32; làm tròn giống hệt để kết quả trùng khớp.
        x32 = array("f", x)
        return sum(tree.predict(x32) for tree in self.trees) / len(self.trees)


def load_default_gate(path: Path | str = DEFAULT_MODEL_PATH) -> WalkGate | None:
    """Nạp mô hình mặc định; trả None (không có AI) nếu thiếu hoặc không hợp lệ."""
    try:
        gate = WalkGate.load(path)
    except ModelError as exc:
        log.warning("Chạy không có AI đếm bước: %s", exc)
        return None
    log.info("Đã nạp mô hình %s %s (%d cây)", gate.name, gate.version, len(gate.trees))
    return gate
