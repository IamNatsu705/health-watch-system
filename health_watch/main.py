"""Thử MAX30102 + MPU6050 và hiển thị trực tiếp, chưa có web/Firebase."""

import time

from smbus2 import SMBus

from alerts import AlertOutputs
from config import (
    I2C_BUS,
    I2C_READ_ATTEMPTS,
    MAX30102_ADDRESS,
    MPU6050_ADDRESS,
    SAMPLE_INTERVAL_S,
    SCREEN_INTERVAL_S,
    STEP_LENGTH_M,
    WEIGHT_KG,
)
from processing.pulse import PulseMonitor
from processing.fall import FallDetector
from processing.steps import StepCounter
from screen import Screen
from sensors.max30102 import MAX30102
from sensors.mpu6050 import MPU6050


def read_i2c(label: str, operation):
    """Thử lại lỗi đọc ngắn hạn, nhưng dừng nếu kết nối thật sự mất."""
    for attempt in range(1, I2C_READ_ATTEMPTS + 1):
        try:
            return operation()
        except OSError as exc:
            print(f"{label}: loi I2C lan {attempt}/{I2C_READ_ATTEMPTS}: {exc}", flush=True)
            if attempt == I2C_READ_ATTEMPTS:
                raise RuntimeError(f"Mat ket noi {label} sau {attempt} lan doc: {exc}") from exc
            time.sleep(0.05)


def main() -> None:
    alerts = AlertOutputs()
    try:
        screen = Screen()
        screen.status("KHOI DONG CAM BIEN", "Kiem tra I2C...")
        with SMBus(I2C_BUS) as bus:
            try:
                mpu = MPU6050(bus, MPU6050_ADDRESS)
                max_sensor = MAX30102(bus, MAX30102_ADDRESS)
            except (OSError, RuntimeError) as exc:
                screen.status("LOI CAM BIEN", str(exc)[:28])
                raise SystemExit(f"Khong khoi tao duoc cam bien: {exc}") from exc

            steps = StepCounter(STEP_LENGTH_M, WEIGHT_KG)
            fall = FallDetector()
            pulse = PulseMonitor(MAX30102.SAMPLES_PER_SECOND)
            last_screen = float("-inf")
            last_log = float("-inf")
            last_alert = None
            last_button = False
            acknowledge_press = False
            print("Da nhan MPU6050 va MAX30102. Nhan Ctrl+C de dung.")

            while True:
                started = time.monotonic()
                try:
                    motion = read_i2c("MPU6050", mpu.read)
                    steps.update(motion, started)
                    was_fall_active = fall.confirmed
                    just_fell = fall.update(motion, started) and not was_fall_active
                    samples = read_i2c("MAX30102", max_sensor.read_samples)
                    for red, ir in samples:
                        pulse.add(red, ir)
                    pulse.analyze(started)
                except RuntimeError as exc:
                    screen.status("LOI DOC I2C", str(exc)[:28])
                    raise SystemExit(f"Loi doc I2C: {exc}") from exc

                button = alerts.button_pressed
                if fall.confirmed and button and not last_button and not just_fell:
                    fall.clear()
                    acknowledge_press = True
                    print("Da xac nhan canh bao nga.")
                if not button:
                    acknowledge_press = False
                sos_pressed = button and not acknowledge_press and not fall.confirmed
                alerts.update(fall_active=fall.confirmed, sos_active=sos_pressed)
                alert_state = "fall" if fall.confirmed else ("sos" if sos_pressed else "")
                if alert_state != last_alert:
                    print({"fall": "PHAT HIEN NGA: LED do bat, coi tat.",
                           "sos": "SOS: LED do va coi bat.",
                           "": "Trang thai binh thuong."}[alert_state])
                    last_alert = alert_state
                    last_screen = float("-inf")
                last_button = button

                if started - last_screen >= SCREEN_INTERVAL_S:
                    screen.update(steps, pulse, alert_state)
                    last_screen = started
                if started - last_log >= 2.0:
                    print(
                        f"steps={steps.steps} kcal~={steps.calories_kcal:.2f} "
                        f"ax={motion.ax:+.2f}g IR={pulse.ir} "
                        f"finger={'yes' if pulse.finger_present else 'no'} "
                        f"samples={len(pulse.ir_history)} BPM~={pulse.bpm or '--'}"
                    )
                    last_log = started
                time.sleep(max(0, SAMPLE_INTERVAL_S - (time.monotonic() - started)))
    finally:
        alerts.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Da dung chuong trinh.")
