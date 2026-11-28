"""Ghi dữ liệu gia tốc/gyro THẬT từ MPU6050 kèm nhãn để huấn luyện và kiểm định AI đếm bước.

Chạy trên Pi khi service chính đã dừng (hai chương trình không được cùng đọc FIFO):

    sudo systemctl stop health-watch
    .venv/bin/python record_imu.py --subject S01 --activity walk_normal \
        --placement wrist_left --duration 120
    sudo systemctl start health-watch

Trong lúc ghi, một người đi bộ đeo thiết bị và một người đếm số bước bằng tay
(bộ bấm đếm hoặc quay video chân). Hết giờ (hoặc Ctrl+C), nhập số bước đã đếm.
Mỗi phiên tạo ``recordings/<session>.csv`` (mẫu 100 Hz) và ``<session>.json``
(nhãn + thông tin cảm biến). Chép về PC rồi dùng ``ml/train_walk_gate.py --team``.

Không lưu tên thật: ``--subject`` chỉ là mã ẩn danh (S01, S02...).
"""

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from smbus2 import SMBus

from config import I2C_BUS, MQTT_DEVICE_ID, MPU6050_ADDRESS
from inference.walk_gate import load_default_gate
from clock import clock_synced
from processing.steps import StepEngine
from sensors.mpu6050 import ImuStream
from telemetry import SOFTWARE_VERSION

ACTIVITIES = {
    "walk_normal": "đi bộ tốc độ bình thường",
    "walk_slow": "đi chậm",
    "walk_fast": "đi nhanh",
    "stairs_up": "lên cầu thang",
    "stairs_down": "xuống cầu thang",
    "run": "chạy bộ",
    "stand": "đứng yên",
    "sit": "ngồi yên",
    "desk_work": "ngồi gõ phím/viết",
    "gesture_talk": "nói chuyện, khua tay",
    "brush_teeth": "đánh răng (giả động tác)",
    "wash_hands": "rửa tay",
    "household": "việc nhà: lau bàn, gấp quần áo",
    "motorbike_passenger": "ngồi sau xe máy (chỉ người ngồi sau cầm thiết bị)",
    "bus_or_car": "ngồi xe buýt/ô tô",
    "free_living": "sinh hoạt tự do có lẫn đi bộ",
}
PLACEMENTS = ("wrist_left", "wrist_right", "waist", "hand")
COUNTING_METHODS = ("tally_counter", "video", "manual_count", "none")
SUBJECT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,16}$")
OUTPUT_DIR = Path(__file__).resolve().parent / "recordings"


def service_running() -> bool:
    try:
        result = subprocess.run(["systemctl", "is-active", "--quiet", "health-watch"], check=False)
    except FileNotFoundError:
        return False
    return result.returncode == 0


def ask_step_count(prompt: str) -> int | None:
    while True:
        text = input(prompt).strip()
        if not text:
            return None
        if text.isdigit():
            return int(text)
        print("Nhập số nguyên không âm, hoặc Enter nếu không đếm.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--subject", required=True, help="Mã ẩn danh của người đeo, ví dụ S01")
    parser.add_argument("--activity", required=True, choices=sorted(ACTIVITIES))
    parser.add_argument("--placement", required=True, choices=PLACEMENTS)
    parser.add_argument("--duration", type=float, default=120.0, help="Số giây ghi (mặc định 120)")
    parser.add_argument("--counting", choices=COUNTING_METHODS, default="tally_counter",
                        help="Cách đếm số bước thật")
    parser.add_argument("--countdown", type=int, default=5, help="Đếm ngược trước khi ghi")
    parser.add_argument("--notes", default="", help="Ghi chú ngắn: giày dép, mặt đường, tốc độ...")
    args = parser.parse_args()

    if not SUBJECT_PATTERN.fullmatch(args.subject):
        parser.error("--subject chỉ gồm chữ, số, _ hoặc -, tối đa 16 ký tự (không dùng tên thật)")
    if not 5 <= args.duration <= 3600:
        parser.error("--duration phải trong 5–3600 giây")
    if service_running():
        print("Service health-watch đang chạy và giữ MPU6050. Dừng trước: sudo systemctl stop health-watch")
        return 2

    session_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{args.subject}_{args.activity}_{uuid4().hex[:6]}"
    OUTPUT_DIR.mkdir(exist_ok=True)
    csv_path = OUTPUT_DIR / f"{session_id}.csv"
    meta_path = OUTPUT_DIR / f"{session_id}.json"
    gate = load_default_gate()
    engine = StepEngine(gate=gate)

    print(f"Hoạt động: {ACTIVITIES[args.activity]}; vị trí: {args.placement}; thời lượng {args.duration:.0f} s")
    for remaining in range(args.countdown, 0, -1):
        print(f"Bắt đầu sau {remaining}...", flush=True)
        time.sleep(1)
    print("ĐANG GHI. Bắt đầu hoạt động và đếm bước. Ctrl+C để dừng sớm.", flush=True)

    started_wall = datetime.now(timezone.utc)
    synced = clock_synced()
    sample_index = 0
    sensor_info = None
    with SMBus(I2C_BUS) as bus, open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sample_index", "t_s", "ax_g", "ay_g", "az_g", "gx_dps", "gy_dps", "gz_dps", "gap_before"])
        stream = ImuStream(bus, MPU6050_ADDRESS, fifo_gyro=True)
        start = time.monotonic()
        first_t = None
        gap_pending = False
        last_print = start
        try:
            while time.monotonic() - start < args.duration:
                now = time.monotonic()
                batch = stream.poll(now)
                if stream.take_gap():
                    engine.reset_signal()
                    gap_pending = True
                if not stream.ok and stream.error:
                    print(f"Lỗi cảm biến: {stream.error}", flush=True)
                for t, sample in batch:
                    if sensor_info is None and stream.sensor is not None:
                        sensor_info = stream.sensor.info
                    if first_t is None:
                        first_t = t
                    writer.writerow([
                        sample_index, f"{t - first_t:.4f}",
                        f"{sample.ax:.6f}", f"{sample.ay:.6f}", f"{sample.az:.6f}",
                        f"{sample.gx:.4f}", f"{sample.gy:.4f}", f"{sample.gz:.4f}",
                        int(gap_pending),
                    ])
                    gap_pending = False
                    sample_index += 1
                    engine.add_sample(sample.ax, sample.ay, sample.az)
                if now - last_print >= 5:
                    print(f"  {now - start:5.0f} s, {sample_index} mẫu, đứt mẫu {stream.gap_count}", flush=True)
                    last_print = now
                time.sleep(0.02)
        except KeyboardInterrupt:
            print("Dừng sớm theo yêu cầu.")
    engine.reset_signal()
    duration = sample_index * stream.dt
    print(f"Đã ghi {sample_index} mẫu ({duration:.1f} s), đứt mẫu {stream.gap_count} lần, tràn FIFO {stream.overflow_count} lần.")
    if sample_index == 0:
        csv_path.unlink(missing_ok=True)
        print("Không có mẫu nào; không lưu phiên.")
        return 1

    if args.activity in {"stand", "sit", "desk_work", "bus_or_car"}:
        default_hint = " (thường là 0)"
    else:
        default_hint = ""
    true_steps = None
    if args.counting != "none":
        true_steps = ask_step_count(f"Số bước đếm được{default_hint}, Enter nếu không đếm: ")

    meta = {
        "format": "health-watch-imu-recording-v1",
        "session_id": session_id,
        "subject_id": args.subject,
        "activity": args.activity,
        "placement": args.placement,
        "true_step_count": true_steps,
        "counting_method": args.counting if true_steps is not None else "none",
        "notes": args.notes,
        "device_id": MQTT_DEVICE_ID,
        "firmware_version": SOFTWARE_VERSION,
        "started_at": started_wall.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "clock_synced": synced,
        "duration_s": round(duration, 2),
        "sample_rate_hz": 1.0 / stream.dt,
        "samples": sample_index,
        "gap_count": stream.gap_count,
        "overflow_count": stream.overflow_count,
        "sensor": sensor_info,
        "live_result": {
            "steps_algorithm": engine.steps_algorithm,
            "steps_ai": engine.steps_ai,
            "model": engine.model,
        },
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Thuật toán đếm {engine.steps_algorithm} bước; AI đếm {engine.steps_ai if engine.steps_ai is not None else '— (chưa có mô hình)'} bước.")
    if true_steps:
        for name, value in (("Thuật toán", engine.steps_algorithm), ("AI", engine.steps_ai)):
            if value is not None:
                print(f"  {name}: sai số {(value - true_steps) / true_steps * 100:+.1f}%")
    print(f"Đã lưu {csv_path.name} và {meta_path.name} trong {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
