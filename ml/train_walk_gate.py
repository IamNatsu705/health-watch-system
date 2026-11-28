"""Huấn luyện và đánh giá mô hình AI "đang đi bộ hay không" trên dữ liệu thật.

Ví dụ (chạy trên PC, không chạy trên Pi):

    python ml/train_walk_gate.py --oxwalk D:/data/OxWalk_Dec2022/Wrist_100Hz \
        --clemson D:/data/clemson --team D:/data/team_recordings

Quy trình:
1. Chạy đúng ``StepEngine`` của Pi trên từng bản ghi để lấy đặc trưng cửa sổ 5 s
   và số đỉnh ứng viên (cùng mã với lúc suy luận trên Pi).
2. Đánh giá chéo lồng nhau theo người (GroupKFold): vòng trong chọn ngưỡng,
   vòng ngoài đo sai số đếm bước trên người chưa từng thấy khi huấn luyện.
3. Huấn luyện mô hình cuối trên toàn bộ dữ liệu, xuất JSON cho Pi, kiểm tra
   JSON cho ra đúng xác suất của scikit-learn.
4. Kiểm định độc lập trên Clemson bằng chính đường suy luận của Pi (WalkGate JSON).
"""

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import balanced_accuracy_score, f1_score
from sklearn.model_selection import GroupKFold

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml.common import REPO, load_clemson, load_oxwalk, load_team, run_engine  # noqa: E402

from inference.walk_gate import MODEL_FORMAT, WalkGate  # noqa: E402
from processing.step_features import FEATURE_VERSION, GATE_INPUT_NAMES  # noqa: E402
from processing.steps import ALGORITHM_NAME, WINDOW_S  # noqa: E402

THRESHOLDS = np.round(np.arange(0.40, 0.80, 0.025), 3)
MODEL_NAME = "walk-gate-rf"


def make_forest(seed: int = 0) -> RandomForestClassifier:
    return RandomForestClassifier(
        n_estimators=100, max_depth=10, min_samples_leaf=10, max_features="sqrt",
        class_weight="balanced", n_jobs=-1, random_state=seed,
    )


def build_table(recordings, workers: int) -> dict:
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(run_engine, recordings))
    X, label, subject, candidates, true_window, session = [], [], [], [], [], []
    for result in results:
        for _, _, n_candidates, true_in_window, lab, x in result["windows"]:
            X.append(x)
            label.append(lab)
            subject.append(f"{result['source']}:{result['subject']}")
            session.append(f"{result['source']}:{result['session']}")
            candidates.append(n_candidates)
            true_window.append(-1 if true_in_window is None else true_in_window)
    return {
        "X": np.array(X, dtype=np.float64), "label": np.array(label), "subject": np.array(subject),
        "session": np.array(session), "candidates": np.array(candidates), "true_window": np.array(true_window),
        "sessions": [{k: v for k, v in r.items() if k != "windows"} for r in results],
    }


def session_rows(table, predicted_counts, sessions) -> list[dict]:
    """Số bước thật/AI/thuật toán theo phiên; bỏ phiên không đếm bước thật (true_steps = None)."""
    rows = []
    for info in sessions:
        mask = table["session"] == f"{info['source']}:{info['session']}"
        if not mask.any() or info["true_steps"] is None:
            continue
        rows.append({
            "true": int(info["true_steps"]),
            "ai": int(predicted_counts[mask].sum()),
            "algorithm": int(info["algorithm_steps"]),
            "minutes": info["duration_s"] / 60.0,
        })
    return rows


def score(rows, key: str) -> dict:
    """Sai số theo phiên đi bộ (MAPE) + bước giả trong phiên 0 bước (bước/phút).

    ``objective`` (dùng để chọn ngưỡng) là trung bình sai số mọi phiên: phiên có bước dùng
    |đếm − thật| / thật × 100; phiên 0 bước dùng số bước giả / (số phút × 100 bước/phút) × 100,
    tức là đếm khống bằng 1 phút đi bộ (100 bước) tính như sai 100%.
    """
    walking = [r for r in rows if r["true"] > 0]
    still = [r for r in rows if r["true"] == 0]
    out = {}
    if walking:
        out.update(summarize(np.array([r["true"] for r in walking], dtype=float),
                             np.array([r[key] for r in walking], dtype=float)))
    if still:
        minutes = sum(r["minutes"] for r in still)
        out["zero_step_sessions"] = len(still)
        out["false_steps_per_min"] = round(sum(r[key] for r in still) / minutes, 2)
    errors = ([abs(r[key] - r["true"]) / r["true"] * 100 for r in walking]
              + [r[key] / max(r["minutes"], 1e-9) for r in still])
    out["objective"] = round(float(np.mean(errors)), 3) if errors else None
    return out


def count_errors(table, probabilities, threshold, sessions) -> dict:
    """Sai số đếm bước theo phiên khi cộng đỉnh trong các cửa sổ AI cho là đi bộ."""
    predicted = np.where(probabilities >= threshold, table["candidates"], 0)
    rows = session_rows(table, predicted, sessions)
    return {"ai": score(rows, "ai"), "algorithm": score(rows, "algorithm")}


def summarize(true, predicted) -> dict:
    ape = np.abs(predicted - true) / true * 100
    return {
        "sessions": int(len(true)),
        "true_steps": int(true.sum()),
        "predicted_steps": int(predicted.sum()),
        "mape_percent": round(float(ape.mean()), 1),
        "median_ape_percent": round(float(np.median(ape)), 1),
        "total_error_percent": round(float((predicted.sum() / true.sum() - 1) * 100), 1),
    }


def best_threshold(table, probabilities, sessions) -> float:
    scores = [count_errors(table, probabilities, t, sessions)["ai"]["objective"] for t in THRESHOLDS]
    return float(THRESHOLDS[int(np.argmin(scores))])


def fit_labeled(X, y, seed: int = 0) -> RandomForestClassifier:
    """Chỉ huấn luyện trên cửa sổ có nhãn (bỏ nhãn -1: phiên trộn lẫn, đầu/cuối phiên đi bộ)."""
    labeled = y >= 0
    return make_forest(seed).fit(X[labeled], y[labeled])


def cross_validated_probabilities(table, index, folds, seed=0) -> np.ndarray:
    probabilities = np.zeros(len(index))
    X, y, groups = table["X"][index], table["label"][index], table["subject"][index]
    for train, test in GroupKFold(n_splits=folds).split(X, y, groups):
        model = fit_labeled(X[train], y[train], seed)
        probabilities[test] = model.predict_proba(X[test])[:, 1]
    return probabilities


def subset(table, mask) -> dict:
    keys = ("X", "label", "subject", "session", "candidates", "true_window")
    return {k: table[k][mask] for k in keys}


def nested_evaluation(table, folds: int) -> dict:
    """Vòng ngoài: người kiểm tra không tham gia chọn ngưỡng hay huấn luyện."""
    outer_probabilities = np.zeros(len(table["X"]))
    outer_threshold = np.zeros(len(table["X"]))
    chosen = []
    splitter = GroupKFold(n_splits=folds)
    for train, test in splitter.split(table["X"], table["label"], table["subject"]):
        inner = subset(table, np.isin(np.arange(len(table["X"])), train))
        inner_sessions = [s for s in table["sessions"]
                          if f"{s['source']}:{s['session']}" in set(inner["session"])]
        inner_prob = cross_validated_probabilities(inner, np.arange(len(inner["X"])), folds - 1)
        threshold = best_threshold(inner, inner_prob, inner_sessions)
        chosen.append(threshold)
        model = fit_labeled(table["X"][train], table["label"][train])
        outer_probabilities[test] = model.predict_proba(table["X"][test])[:, 1]
        outer_threshold[test] = threshold
    walking = outer_probabilities >= outer_threshold
    predicted = np.where(walking, table["candidates"], 0)
    rows = session_rows(table, predicted, table["sessions"])
    labeled = table["label"] >= 0
    return {
        "method": f"GroupKFold({folds}) theo người, ngưỡng chọn bằng GroupKFold({folds - 1}) bên trong",
        "thresholds_chosen": chosen,
        "window_f1": round(float(f1_score(table["label"][labeled], walking[labeled])), 3),
        "window_balanced_accuracy": round(float(balanced_accuracy_score(table["label"][labeled], walking[labeled])), 3),
        "ai": score(rows, "ai"),
        "algorithm": score(rows, "algorithm"),
    }


def export_forest(model: RandomForestClassifier) -> list[dict]:
    trees = []
    for estimator in model.estimators_:
        tree = estimator.tree_
        values = tree.value[:, 0, :]
        positive = list(model.classes_).index(1)
        prob = values[:, positive] / np.maximum(values.sum(axis=1), 1e-12)
        trees.append({
            "left": tree.children_left.tolist(),
            "right": tree.children_right.tolist(),
            "feature": [int(f) if f >= 0 else 0 for f in tree.feature],
            "threshold": [float(t) if l != -1 else 0.0 for t, l in zip(tree.threshold, tree.children_left)],
            "p": [round(float(p), 6) for p in prob],
        })
    return trees


def external_clemson(recordings, gate_path: Path, workers: int) -> dict:
    gate = WalkGate.load(gate_path)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_run_with_gate, recordings, [gate_path] * len(recordings)))
    out = {}
    for name, keep in (("all", lambda r: True),) + tuple(
            (g, (lambda gait: (lambda r: r["gait"] == gait))(g)) for g in ("Regular", "SemiRegular", "Irregular")):
        chosen = [r for r in results if keep(r)]
        true = np.array([r["true_steps"] for r in chosen], dtype=float)
        out[name] = {
            "ai": summarize(true, np.array([r["ai_steps"] for r in chosen], dtype=float)),
            "algorithm": summarize(true, np.array([r["algorithm_steps"] for r in chosen], dtype=float)),
        }
    out["model"] = f"{gate.name} {gate.version}"
    return out


def _run_with_gate(recording, gate_path):
    result = run_engine(recording, gate=WalkGate.load(gate_path))
    result["gait"] = recording.meta.get("gait")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--oxwalk", type=Path, required=True, help="Thư mục OxWalk Wrist_100Hz")
    parser.add_argument("--team", type=Path, help="Thư mục bản ghi record_imu.py của nhóm")
    parser.add_argument("--clemson", type=Path, help="Thư mục Clemson (kiểm định độc lập)")
    parser.add_argument("--out", type=Path, default=REPO / "health_watch" / "models" / "walk_gate.json")
    parser.add_argument("--version", default="1.0.0")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    recordings = load_oxwalk(args.oxwalk)
    datasets = [f"OxWalk wrist 100 Hz ({len(recordings)} người, Small et al. 2022, CC BY 4.0)"]
    if args.team:
        team = load_team(args.team)
        recordings += team
        datasets.append(f"Bản ghi MPU6050 của nhóm ({len(team)} phiên, "
                        f"{len({r.subject for r in team})} người)")
    print("Đang chạy StepEngine trên", len(recordings), "bản ghi...", flush=True)
    table = build_table(recordings, args.workers)
    labeled = table["label"] >= 0
    print(f"{len(table['X'])} cửa sổ ({int(labeled.sum())} có nhãn), tỷ lệ đi bộ "
          f"{table['label'][labeled].mean():.3f}", flush=True)

    evaluation = {"cross_validation": nested_evaluation(table, args.folds)}
    print(json.dumps(evaluation["cross_validation"], ensure_ascii=False, indent=2), flush=True)

    all_index = np.arange(len(table["X"]))
    threshold = best_threshold(table, cross_validated_probabilities(table, all_index, args.folds),
                               table["sessions"])
    model = fit_labeled(table["X"], table["label"])
    document = {
        "format": MODEL_FORMAT,
        "model_name": MODEL_NAME,
        "model_version": args.version,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "feature_version": FEATURE_VERSION,
        "feature_names": list(GATE_INPUT_NAMES),
        "window_s": WINDOW_S,
        "sample_rate_hz": 100.0,
        "threshold": threshold,
        "step_algorithm": ALGORITHM_NAME,
        "training_data": {
            "datasets": datasets,
            "windows": int(labeled.sum()),
            "walking_fraction": round(float(table["label"][labeled].mean()), 3),
            "label": ("cửa sổ 5 s có >=3 bước gán nhãn từ video (OxWalk); phiên nhóm thuần đi bộ = 1 "
                      "(bỏ cửa sổ đầu/cuối), thuần không đi bộ = 0; free_living chỉ dùng để đánh giá"),
        },
        "evaluation": evaluation,
        "trees": export_forest(model),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    gate = WalkGate.load(args.out)
    sample = table["X"][:: max(1, len(table["X"]) // 2000)]
    expected = model.predict_proba(sample)[:, 1]
    got = np.array([gate.predict_proba(list(x)) for x in sample])
    max_diff = float(np.abs(expected - got).max())
    if max_diff > 1e-5:
        raise SystemExit(f"JSON xuất ra lệch scikit-learn {max_diff}")
    print(f"Đã xuất {args.out} ({args.out.stat().st_size / 1e6:.2f} MB), ngưỡng {threshold}, "
          f"lệch so với sklearn {max_diff:.2e}", flush=True)

    if args.clemson:
        evaluation["external_clemson"] = external_clemson(load_clemson(args.clemson), args.out, args.workers)
        print(json.dumps(evaluation["external_clemson"], ensure_ascii=False, indent=2), flush=True)
        document["evaluation"] = evaluation
        args.out.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main()
