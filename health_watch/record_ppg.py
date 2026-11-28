"""Thu dữ liệu PPG thô (RED/IR) từ MAX30102 để nghiên cứu nhịp tim (chế độ nghiên cứu).

Chuyển từ chế độ thu dữ liệu nhóm đã chạy trên Pi ngày 27–28/11: chỉ đọc MAX30102, ghi
logs/ppg_*.csv và logs/fifo_*.csv (định dạng giữ nguyên), dừng phiên khi FIFO tràn/đầy hoặc
lỗi I2C để trục thời gian time_s luôn liên tục. Hệ thống đầy đủ (bước chân, TFT, MQTT, còi)
chạy bằng main.py; muốn ghi PPG trong lúc hệ thống chạy thì đặt PPG_CSV_LOG=1.

    sudo systemctl stop health-watch
    .venv/bin/python record_ppg.py          # Ctrl+C để dừng
    sudo systemctl start health-watch
"""

import signal
import subprocess
import sys
import time
from contextlib import ExitStack

from config import I2C_BUS, MAX30102_ADDRESS, SAMPLE_INTERVAL_S
from ppg_log import OK_STATUSES, PpgCsvLogger
from sensors.max30102 import MAX30102

# ================================================================
# CẤU HÌNH — sửa True/False rồi chạy lại.
# ================================================================
ENABLE_PULSE_ANALYSIS = False  # Bật PulseMonitor: nhận diện ngón tay và tính BPM
ENABLE_CONSOLE_LOG = True      # In thông tin đo định kỳ (2 giây); False để giảm I/O Terminal


def service_running() -> bool:
    try:
        return subprocess.run(["systemctl", "is-active", "--quiet", "health-watch"], check=False).returncode == 0
    except FileNotFoundError:
        return False


def sleep_max30102(bus) -> None:
    """Dừng lấy mẫu khi thoát (bit SHDN của MODE_CONFIG); không ngắt nguồn."""
    try:
        value = bus.read_byte_data(MAX30102_ADDRESS, MAX30102.REG_MODE_CONFIG)
        bus.write_byte_data(MAX30102_ADDRESS, MAX30102.REG_MODE_CONFIG, value | 0x80)
    except OSError as exc:
        print(f"Không đưa được MAX30102 về chế độ ngủ: {exc}", flush=True)


def run() -> None:
    from smbus2 import SMBus

    pulse = None
    if ENABLE_PULSE_ANALYSIS:
        from processing.pulse import PulseMonitor
        pulse = PulseMonitor(MAX30102.SAMPLES_PER_SECOND)

    with ExitStack() as resources:
        bus = resources.enter_context(SMBus(I2C_BUS))
        try:
            sensor = MAX30102(bus, MAX30102_ADDRESS)
        except (OSError, RuntimeError, ValueError) as exc:
            raise SystemExit(f"Khong khoi tao duoc MAX30102: {exc}") from exc
        resources.callback(sleep_max30102, bus)
        logger = PpgCsvLogger(MAX30102.SAMPLES_PER_SECOND)
        resources.callback(logger.close)
        print(f"PPG CSV: {logger.csv_path}", flush=True)
        print(f"FIFO CSV: {logger.fifo_path}", flush=True)
        print(f"FIFO Rate={MAX30102.SAMPLES_PER_SECOND} Hz; polling mục tiêu={SAMPLE_INTERVAL_S * 1000:g} ms; "
              f"PULSE_ANALYSIS={pulse is not None}. Nhấn Ctrl+C để dừng.", flush=True)

        latest_ir = None
        max_pulse_analysis_ms = 0.0
        last_log = float("-inf")
        while True:
            started = time.monotonic()
            # FIFO_DATA làm con trỏ đọc tiến lên; không retry mù nếu I2C lỗi.
            poll = sensor.read_poll()
            logger.write(poll)
            if poll.status not in OK_STATUSES:
                # Dừng phiên: không dựng tiếp time_s qua khoảng mất mẫu.
                raise RuntimeError(f"{poll.status}: {poll.detail}; xem {logger.fifo_path.name}"
                                   + (f"; pulse_max_ms={max_pulse_analysis_ms:.3f}" if pulse is not None else ""))
            if poll.samples:
                latest_ir = poll.samples[-1][1]
            if pulse is not None:
                for red, ir in poll.samples:
                    pulse.add(red, ir)
                analysis_start = time.monotonic()
                pulse.analyze(started)
                max_pulse_analysis_ms = max(max_pulse_analysis_ms, (time.monotonic() - analysis_start) * 1000)
            if ENABLE_CONSOLE_LOG and started - last_log >= 2.0:
                if pulse is not None:
                    print(f"IR={pulse.ir} finger={'yes' if pulse.finger_present else 'no'} "
                          f"samples={len(pulse.ir_history)} BPM~={pulse.bpm or '--'} "
                          f"pulse_max_ms={max_pulse_analysis_ms:.3f}", flush=True)
                else:
                    print(f"IR={latest_ir if latest_ir is not None else '--'} "
                          f"samples_total={logger.sample_id} BPM=OFF", flush=True)
                last_log = started
            time.sleep(max(0, SAMPLE_INTERVAL_S - (time.monotonic() - started)))


def stop_on_sigterm(signum, frame):
    raise KeyboardInterrupt


def main() -> int:
    if service_running():
        print("Service health-watch đang chạy và giữ MAX30102. Dừng trước: sudo systemctl stop health-watch")
        return 2
    signal.signal(signal.SIGTERM, stop_on_sigterm)
    try:
        run()
    except KeyboardInterrupt:
        print("Da dung thu du lieu PPG.")
    except RuntimeError as exc:
        print(f"Dung phien PPG: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
