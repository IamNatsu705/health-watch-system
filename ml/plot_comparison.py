"""Biểu đồ so sánh đếm bước KHÔNG có AI và CÓ AI, trên dữ liệu thật; tái lập được.

    python ml/plot_comparison.py --oxwalk ml/data/OxWalk_Dec2022/Wrist_100Hz --clemson ml/data/clemson

Ba bộ đếm được so với số bước thật (gán nhãn bằng video):
* "Thuật toán cũ" (peak-v1): bộ đếm trước nâng cấp, chạy ở 25 Hz đều (trường hợp tốt nhất).
* "Thuật toán mới" (peak-bout-v2): xử lý tín hiệu, không AI.
* "AI + thuật toán mới": cổng AI walk-gate-rf.

Để công bằng, số của AI trên OxWalk lấy từ đánh giá chéo lồng nhau theo người: mỗi người
được đếm bằng mô hình CHƯA TỪNG thấy dữ liệu của người đó. Clemson không dùng để huấn
luyện nên dùng mô hình chính thức. Kết quả ghi ra PNG và CSV (số liệu gốc của từng hình).
"""

import argparse
import csv
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml.common import REPO, Recording, load_clemson, load_oxwalk, run_engine  # noqa: E402
from ml.evaluate_legacy import LegacyStepCounter, run_legacy  # noqa: E402
from ml.train_walk_gate import (  # noqa: E402
    build_table, gate_document, nested_evaluation, nested_predictions, session_rows,
)

from inference.walk_gate import DEFAULT_MODEL_PATH, WalkGate  # noqa: E402
from processing.steps import StepEngine  # noqa: E402

# Bảng màu dataviz mặc định, 3 slot đầu (đã kiểm tra mù màu all-pairs); sự thật = mực trung tính.
COLORS = {"old": "#f47230", "algorithm": "#00b894", "ai": "#257de0", "truth": "#191919"}
LABELS = {"old": "Thuật toán cũ (peak-v1)", "algorithm": "Thuật toán mới, không AI",
          "ai": "AI + thuật toán mới", "truth": "Số bước thật (video)"}
TEXT = "#191919"
MUTED = "#666666"
GRID = "#e6e6e6"
EXAMPLES = (("P01", 6000, "Đi bộ thật (P01, 60 giây)"), ("P11", 72000, "Cử động tay, không bước nào (P11, 60 giây)"))


def style(ax):
    ax.set_facecolor("white")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#bbbbbb")
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def write_csv(path: Path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def mape(true, predicted):
    true, predicted = np.asarray(true, float), np.asarray(predicted, float)
    return float(np.mean(np.abs(predicted - true) / true * 100))


def per_person_oxwalk(recordings, workers):
    table = build_table(recordings, workers)
    nested = nested_predictions(table, 5)
    evaluation = nested_evaluation(table, 5, nested)
    predicted = np.where(nested["walking"], table["candidates"], 0)
    rows = session_rows(table, predicted, table["sessions"])
    with ProcessPoolExecutor(workers) as pool:
        legacy = list(pool.map(run_legacy, recordings))
    people = []
    for recording, row, (true, old, _) in zip(recordings, rows, legacy):
        assert row["true"] == true
        people.append((recording.subject, true, old, row["algorithm"], row["ai"]))
    return people, nested, evaluation


def clemson_by_gait(recordings, workers):
    with ProcessPoolExecutor(workers) as pool:
        legacy = list(pool.map(run_legacy, recordings))
        engine = list(pool.map(_run_with_model, recordings))
    rows = []
    for recording, (true, old, gait), result in zip(recordings, legacy, engine):
        rows.append((recording.subject, gait, true, old, result["algorithm_steps"], result["ai_steps"]))
    return rows


def _run_with_model(recording):
    return run_engine(recording, gate=WalkGate.load(DEFAULT_MODEL_PATH))


def example_series(recording: Recording, start: int, gate: WalkGate):
    """Số bước cộng dồn mỗi 0,1 s trên một đoạn 60 s thật."""
    xyz = recording.xyz[start:start + 6000]
    truth_index = recording.step_index[(recording.step_index >= start) & (recording.step_index < start + 6000)] - start
    old, engine = LegacyStepCounter(), StepEngine(gate=gate)
    series = []
    for i, (ax, ay, az) in enumerate(xyz.tolist()):
        engine.add_sample(ax, ay, az)
        if i % 4 == 0:
            old.update(SimpleNamespace(ax=ax, ay=ay, az=az), i / 100.0)
        if i % 10 == 9 or i == len(xyz) - 1:
            if i == len(xyz) - 1:
                engine.reset_signal()
            series.append(((i + 1) / 100.0, int(np.count_nonzero(truth_index <= i)),
                           old.steps, engine.steps_algorithm, engine.steps_ai))
    return series


def held_out_gate(nested, subject_key: str) -> WalkGate:
    """Mô hình của fold mà người này nằm ở tập kiểm tra: chưa từng thấy người đó."""
    for (model, threshold), subjects in zip(nested["fold_models"], nested["fold_subjects"]):
        if subject_key in subjects:
            return WalkGate(gate_document(model, threshold, f"cv-without-{subject_key.split(':')[1]}"))
    raise KeyError(subject_key)


def figure_per_person(people, path: Path):
    fig, ax = plt.subplots(figsize=(7.2, 6.2), dpi=200)
    style(ax)
    true = np.array([p[1] for p in people])
    low, high = 60, 9000
    ax.plot([low, high], [low, high], color=MUTED, linestyle="--", linewidth=1.2, zorder=1)
    ax.text(5200, 3900, "đếm đúng", color=MUTED, fontsize=9, rotation=38)
    for column, key in ((2, "old"), (3, "algorithm"), (4, "ai")):
        counted = np.array([p[column] for p in people])
        ax.scatter(true, counted, s=46, color=COLORS[key], edgecolor="white", linewidth=1.2, zorder=3,
                   label=f"{LABELS[key]}: sai TB {mape(true, counted):.1f}%")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(low, high)
    ax.set_ylim(low, high)
    ticks = [100, 200, 500, 1000, 2000, 5000]
    for axis in (ax.xaxis, ax.yaxis):
        axis.set_major_locator(matplotlib.ticker.FixedLocator(ticks))
        axis.set_major_formatter(matplotlib.ticker.FixedFormatter([f"{t:,}".replace(",", ".") for t in ticks]))
        axis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.set_xlabel("Số bước thật trong ~1 giờ sinh hoạt tự do (video, thang log)", color=TEXT, fontsize=10)
    ax.set_ylabel("Số bước bộ đếm báo (thang log)", color=TEXT, fontsize=10)
    ax.set_title("OxWalk: 39 người, mỗi chấm là một người\n"
                 "AI đánh giá chéo, mỗi người đếm bằng mô hình chưa từng thấy người đó",
                 color=TEXT, fontsize=11, loc="left")
    ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=TEXT)
    worst = max(people, key=lambda p: p[2] / p[1])
    ax.annotate(f"{worst[0]}: thật {worst[1]}, cũ đếm {worst[2]}", xy=(worst[1], worst[2]),
                xytext=(worst[1] * 1.6, worst[2] * 1.9), fontsize=8.5, color=TEXT,
                arrowprops={"arrowstyle": "-", "color": MUTED, "linewidth": 0.8})
    fig.tight_layout()
    fig.savefig(path, facecolor="white")
    plt.close(fig)


def figure_summary(people, clemson, path: Path):
    groups = [("OxWalk\n(sinh hoạt tự do,\n39 người)", [(p[1], p[2], p[3], p[4]) for p in people])]
    for gait, name in (("Regular", "Clemson\nđi đều"), ("SemiRegular", "Clemson\nđi bán đều"),
                       ("Irregular", "Clemson\nđi lộn xộn\ntrong phòng")):
        groups.append((name, [(r[2], r[3], r[4], r[5]) for r in clemson if r[1] == gait]))
    fig, ax = plt.subplots(figsize=(8.6, 5.0), dpi=200)
    style(ax)
    ax.grid(axis="x", visible=False)
    width = 0.26
    x = np.arange(len(groups))
    for offset, (index, key) in zip((-width, 0, width), ((1, "old"), (2, "algorithm"), (3, "ai"))):
        values = [mape([r[0] for r in rows], [r[index] for r in rows]) for _, rows in groups]
        bars = ax.bar(x + offset, values, width - 0.03, color=COLORS[key], label=LABELS[key], zorder=3)
        for bar, value in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, value + 1.2, f"{value:.1f}", ha="center",
                    va="bottom", fontsize=8, color=TEXT)
    ax.set_xticks(x, [name for name, _ in groups], fontsize=9, color=TEXT)
    ax.set_ylabel("Sai số trung bình mỗi người/phiên (%)\nthấp hơn là tốt hơn", color=TEXT, fontsize=10)
    ax.set_title("Sai số đếm bước: không AI và có AI (dữ liệu thật, bước gán nhãn bằng video)",
                 color=TEXT, fontsize=11, loc="left")
    ax.legend(frameon=False, fontsize=9, loc="upper right", labelcolor=TEXT)
    ax.set_ylim(0, 100)
    fig.tight_layout()
    fig.savefig(path, facecolor="white")
    plt.close(fig)


def label_line_ends(ax, finals):
    """Nhãn số ở cuối mỗi đường, giãn ra để không chồng; giá trị trùng chỉ ghi một lần."""
    low, high = ax.get_ylim()
    gap = 0.06 * (high - low)
    placed = []
    for value in sorted(set(finals)):
        y = value if not placed or value - placed[-1] >= gap else placed[-1] + gap
        placed.append(y)
        ax.text(61, y, str(value), color=TEXT, fontsize=9, va="center")


def figure_examples(examples, path: Path):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), dpi=200, sharey=False)
    for ax, (title, series) in zip(axes, examples):
        style(ax)
        t = [row[0] for row in series]
        for column, key, dash in ((1, "truth", "--"), (2, "old", "-"), (3, "algorithm", "-"), (4, "ai", "-")):
            ax.plot(t, [row[column] for row in series], color=COLORS[key], linewidth=2.4 if key == "ai" else 2,
                    linestyle=dash, label=LABELS[key], zorder=4 if key == "ai" else 3)
        ax.set_xlim(0, 66)
        label_line_ends(ax, [series[-1][column] for column in (1, 2, 3, 4)])
        ax.set_title(title, color=TEXT, fontsize=10.5, loc="left")
        ax.set_xlabel("Thời gian (giây)", color=TEXT, fontsize=9.5)
    axes[0].set_ylabel("Số bước cộng dồn", color=TEXT, fontsize=9.5)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False, fontsize=9, labelcolor=TEXT)
    fig.suptitle("Ví dụ trên tín hiệu thật: AI dùng mô hình chưa từng thấy người này",
                 x=0.01, ha="left", color=TEXT, fontsize=11)
    fig.tight_layout(rect=(0, 0.08, 1, 0.95))
    fig.savefig(path, facecolor="white")
    plt.close(fig)


def web_summary(people, clemson, examples, path: Path):
    """Số liệu cho mục so sánh trên dashboard (web/src/data/step_evaluation.json)."""
    groups = [{"key": "oxwalk", "label": "OxWalk · sinh hoạt tự do", "sessions": len(people),
               "rows": [(p[1], p[2], p[3], p[4]) for p in people]}]
    for gait, label in (("Regular", "Clemson · đi đều"), ("SemiRegular", "Clemson · đi bán đều"),
                        ("Irregular", "Clemson · đi lộn xộn trong phòng")):
        rows = [(r[2], r[3], r[4], r[5]) for r in clemson if r[1] == gait]
        groups.append({"key": f"clemson_{gait.lower()}", "label": label, "sessions": len(rows), "rows": rows})
    gate = WalkGate.load(DEFAULT_MODEL_PATH)
    document = {
        "generated_by": "ml/plot_comparison.py",
        "model": f"{gate.name} {gate.version}",
        "note": ("AI trên OxWalk: đánh giá chéo theo người (mô hình chưa từng thấy người được đếm). "
                 "Clemson: không dùng để huấn luyện. Số bước thật gán nhãn bằng video."),
        "groups": [{
            "key": g["key"], "label": g["label"], "sessions": g["sessions"],
            "true_steps": int(sum(r[0] for r in g["rows"])),
            "mape": {name: round(mape([r[0] for r in g["rows"]], [r[i] for r in g["rows"]]), 1)
                     for i, name in ((1, "old"), (2, "algorithm"), (3, "ai"))},
        } for g in groups],
        "examples": [{
            "title": title,
            "series": [[row[0], row[1], row[2], row[3], row[4]] for row in series[4::5] or series],
        } for title, series in examples],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--oxwalk", type=Path, required=True)
    parser.add_argument("--clemson", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=REPO / "docs" / "figures")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    oxwalk = load_oxwalk(args.oxwalk)
    people, nested, evaluation = per_person_oxwalk(oxwalk, args.workers)
    write_csv(args.out / "oxwalk_per_person.csv",
              ["participant", "true_steps", "old_peak_v1", "new_algorithm", "ai_cross_validated"], people)
    clemson = clemson_by_gait(load_clemson(args.clemson), args.workers)
    write_csv(args.out / "clemson_per_session.csv",
              ["participant", "gait", "true_steps", "old_peak_v1", "new_algorithm", "ai_model_1_0_0"], clemson)

    by_subject = {r.subject: r for r in oxwalk}
    examples = []
    for subject, start, title in EXAMPLES:
        series = example_series(by_subject[subject], start, held_out_gate(nested, f"oxwalk:{subject}"))
        write_csv(args.out / f"example_{subject}.csv",
                  ["t_s", "true_steps", "old_peak_v1", "new_algorithm", "ai_cross_validated"], series)
        examples.append((title, series))

    figure_per_person(people, args.out / "steps_per_person_oxwalk.png")
    figure_summary(people, clemson, args.out / "steps_error_summary.png")
    figure_examples(examples, args.out / "steps_examples.png")
    web_summary(people, clemson, examples, REPO / "web" / "src" / "data" / "step_evaluation.json")
    true = [p[1] for p in people]
    print("OxWalk MAPE: cũ %.1f%%, mới %.1f%%, AI %.1f%% (đánh giá chéo: %s)" % (
        mape(true, [p[2] for p in people]), mape(true, [p[3] for p in people]),
        mape(true, [p[4] for p in people]), evaluation["ai"]["mape_percent"]))
    for _, series in examples:
        print("ví dụ cuối đoạn:", series[-1])
    print("Đã ghi hình và CSV vào", args.out)


if __name__ == "__main__":
    main()
