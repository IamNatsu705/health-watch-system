"""Đọc cảm biến, đếm bước (thuật toán + AI) trên dữ liệu thật, cảnh báo tại chỗ và gửi MQTT."""

import logging
import signal
import time
from contextlib import ExitStack

from smbus2 import SMBus

from alerts import AlertOutputs
from clock import clock_synced
from config import (
    I2C_BUS,
    I2C_READ_ATTEMPTS,
    MAX30102_ADDRESS,
    MAX30102_SAMPLE_AVERAGING,
    MAX30102_SAMPLE_RATE,
    MAX30102_SAMPLES_PER_SECOND,
    MQTT_DEVICE_ID,
    MQTT_ENABLED,
    MQTT_HOST,
    MQTT_KEEPALIVE_S,
    MQTT_OUTBOX_SIZE,
    MQTT_PASSWORD,
    MQTT_PORT,
    MQTT_PUBLISH_INTERVAL_S,
    MQTT_USERNAME,
    MPU6050_ADDRESS,
    PPG_CSV_LOG,
    SAMPLE_INTERVAL_S,
    SCREEN_INTERVAL_S,
)
from inference.walk_gate import load_default_gate
from mqtt_publisher import BrokerSettings, MqttPublisher
from processing.fall import FallDetector
from processing.pulse import PulseMonitor
from processing.steps import StepEngine
from pulse_sensor import PulseSensor
from screen import Screen
from sensors.max30102 import MAX30102
from sensors.mpu6050 import ImuStream
from step_tracker import StepTracker
from storage import DailyStepStore, ProfileStore
from telemetry import DeviceMessageFactory, utc_now


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("health_watch.main")
DAILY_SAVE_INTERVAL_S = 10.0


def sleep_sensor(bus, address, register, mask, name):
    """Dừng lấy mẫu của cảm biến khi thoát (không ngắt nguồn); lần chạy sau tự cấu hình lại."""
    try:
        value = bus.read_byte_data(address, register)
        bus.write_byte_data(address, register, value | mask)
    except OSError as exc:
        log.warning("Không đưa được %s về chế độ ngủ: %s", name, exc)


def main() -> None:
    alerts = AlertOutputs()
    publisher = None
    messages = None
    engine = None
    tracker = None
    final_telemetry = None
    try:
        if MQTT_ENABLED:
            if MQTT_PUBLISH_INTERVAL_S <= 0:
                raise ValueError("MQTT_PUBLISH_INTERVAL_S phải lớn hơn 0")
            if MQTT_USERNAME != MQTT_DEVICE_ID:
                log.warning("MQTT_USERNAME (%s) khác MQTT_DEVICE_ID (%s): broker sẽ từ chối "
                            "dữ liệu vì mỗi thiết bị chỉ được ghi vào topic của chính nó",
                            MQTT_USERNAME, MQTT_DEVICE_ID)
            messages = DeviceMessageFactory(MQTT_DEVICE_ID)
            publisher = MqttPublisher(
                BrokerSettings(
                    host=MQTT_HOST,
                    port=MQTT_PORT,
                    username=MQTT_USERNAME,
                    password=MQTT_PASSWORD,
                    device_id=messages.device_id,
                    keepalive=MQTT_KEEPALIVE_S,
                    outbox_size=MQTT_OUTBOX_SIZE,
                ),
                online_status=messages.status("online"),
                offline_status=messages.status("offline"),
            )
            publisher.start()
        else:
            print("MQTT dang tat. Dat MQTT_ENABLED=1 sau khi cau hinh broker.")

        screen = Screen()
        screen.status("KHOI DONG CAM BIEN", "Kiem tra I2C...")
        gate = load_default_gate()
        engine = StepEngine(gate=gate)
        profile_store = ProfileStore()
        tracker = StepTracker(engine, DailyStepStore(), profile_store.load())
        session_started_at = utc_now()
        process_started = time.monotonic()

        with SMBus(I2C_BUS) as bus, ExitStack() as cleanup:
            # Gyro vào FIFO cùng gia tốc: mỗi mẫu 100 Hz có gyro đúng thời điểm (phát hiện ngã cần).
            imu = ImuStream(bus, MPU6050_ADDRESS, fifo_gyro=True)
            pulse = PulseMonitor(MAX30102_SAMPLES_PER_SECOND)

            def make_max30102(bus_, address):
                return MAX30102(bus_, address, sample_rate=MAX30102_SAMPLE_RATE,
                                sample_averaging=MAX30102_SAMPLE_AVERAGING)

            pulse_sensor = PulseSensor(bus, MAX30102_ADDRESS, pulse, csv_log=PPG_CSV_LOG,
                                       sensor_factory=make_max30102)
            tft_ms_max = 0.0
            fall = FallDetector()
            # Khi thoát (trước khi đóng bus): đóng CSV PPG, đưa hai cảm biến về chế độ ngủ.
            cleanup.callback(sleep_sensor, bus, MPU6050_ADDRESS, 0x6B, 0x40, "MPU6050")
            cleanup.callback(sleep_sensor, bus, MAX30102_ADDRESS, 0x09, 0x80, "MAX30102")
            cleanup.callback(pulse_sensor.close)

            def telemetry() -> dict:
                distance, kcal = tracker.session_estimates()
                return messages.telemetry(
                    heart_rate_bpm=pulse.bpm,
                    finger_present=pulse.finger_present,
                    imu_status=imu.status,
                    steps_algorithm_session=engine.steps_algorithm,
                    steps_ai_session=engine.steps_ai,
                    step_model=engine.model,
                    walking=engine.walking,
                    walking_probability=engine.walking_probability,
                    cadence_spm=None if engine.cadence_hz is None else engine.cadence_hz * 60.0,
                    distance_m_session=distance,
                    calories_kcal_session=kcal,
                    distance_basis=tracker.distance_basis(),
                    session_started_at=session_started_at,
                    uptime_s=time.monotonic() - process_started,
                    clock_synced=clock_synced(),
                )

            last_screen = float("-inf")
            last_log = float("-inf")
            last_publish = float("-inf")
            last_daily_save = time.monotonic()
            last_alert = None
            last_button = False
            last_sos = False
            last_imu_status = None
            acknowledge_press = False
            remote_alert_until = float("-inf")
            last_command_id = None
            last_reported_output = None
            print("Bat dau doc MPU6050 (FIFO 100 Hz) va MAX30102. Nhan Ctrl+C de dung.")

            while True:
                started = time.monotonic()
                batch = imu.poll(started)
                if imu.take_gap():
                    engine.reset_signal()
                just_fell = False
                for sample_time, motion in batch:
                    engine.add_sample(motion.ax, motion.ay, motion.az)
                    was_fall_active = fall.confirmed
                    if fall.update(motion, sample_time) and not was_fall_active:
                        just_fell = True
                tracker.sync()
                if imu.status != last_imu_status:
                    if imu.ok:
                        log.info("MPU6050 %s: %s", imu.status, imu.sensor.info if imu.sensor else "")
                    else:
                        log.warning("MPU6050 %s: %s", imu.status, imu.error)
                    last_imu_status = imu.status
                    last_screen = float("-inf")
                pulse_sensor.poll(started)

                if publisher:
                    for command in publisher.pop_commands():
                        last_command_id = command["command_id"]
                        if command["active"]:
                            remote_alert_until = started + command["duration_s"]
                        else:
                            remote_alert_until = float("-inf")
                    for update in publisher.pop_profile_updates():
                        if not profile_store.is_newer(update["updated_at"]):
                            log.info("Bỏ cấu hình hồ sơ cũ hơn bản đang dùng (%s)", update["updated_at"])
                            continue
                        tracker.profile = update["profile"]
                        try:
                            profile_store.save(tracker.profile, update["updated_at"])
                        except OSError as exc:
                            log.warning("Không lưu được hồ sơ (vẫn dùng trong RAM): %s", exc)
                        last_screen = float("-inf")
                remote_alert_active = started < remote_alert_until

                button = alerts.button_pressed
                fall_acknowledged = False
                if fall.confirmed and button and not last_button and not just_fell:
                    fall.clear()
                    acknowledge_press = True
                    fall_acknowledged = True
                    print("Da xac nhan canh bao nga.")
                if not button:
                    acknowledge_press = False
                sos_pressed = button and not acknowledge_press and not fall.confirmed
                alerts.update(
                    fall_active=fall.confirmed,
                    sos_active=sos_pressed or remote_alert_active,
                )
                alert_state = (
                    "fall" if fall.confirmed else
                    ("sos" if sos_pressed else ("remote" if remote_alert_active else ""))
                )
                output_source = (
                    "remote" if remote_alert_active else
                    ("sos" if sos_pressed else ("fall" if fall.confirmed else "normal"))
                )
                output_state = (
                    sos_pressed or remote_alert_active,
                    fall.confirmed or sos_pressed or remote_alert_active,
                    output_source,
                )
                if alert_state != last_alert:
                    print({"fall": "PHAT HIEN NGA: LED do bat, coi tat.",
                           "sos": "SOS: LED do va coi bat.",
                           "remote": "CANH BAO TU XA: LED do va coi bat.",
                           "": "Trang thai binh thuong."}[alert_state])
                    last_alert = alert_state
                    last_screen = float("-inf")

                if publisher and messages:
                    if output_state != last_reported_output:
                        publisher.publish_alert_state(
                            messages.alert_state(
                                buzzer_active=output_state[0],
                                red_led_active=output_state[1],
                                source=output_source,
                                last_command_id=last_command_id,
                                remote_remaining_s=max(0, remote_alert_until - started),
                            )
                        )
                        last_reported_output = output_state
                    if just_fell:
                        publisher.publish_event(messages.event("fall_detected"))
                    if fall_acknowledged:
                        publisher.publish_event(messages.event("fall_acknowledged"))
                    if sos_pressed != last_sos:
                        event_type = "sos_pressed" if sos_pressed else "sos_released"
                        publisher.publish_event(messages.event(event_type))
                    if started - last_publish >= MQTT_PUBLISH_INTERVAL_S:
                        publisher.publish_telemetry(telemetry())
                        last_publish = started
                    final_telemetry = telemetry
                last_sos = sos_pressed
                last_button = button

                if started - last_daily_save >= DAILY_SAVE_INTERVAL_S:
                    tracker.daily.save_quietly()
                    last_daily_save = started
                if started - last_screen >= SCREEN_INTERVAL_S:
                    tft_started = time.monotonic()
                    screen.update(tracker.screen_view(imu), pulse, alert_state)
                    tft_ms_max = max(tft_ms_max, (time.monotonic() - tft_started) * 1000)
                    last_screen = started
                    # Đọc FIFO MAX30102 ngay sau lúc vẽ TFT để giảm tối đa thời gian không đọc.
                    pulse_sensor.poll(time.monotonic(), analyze=False)
                if started - last_log >= 2.0:
                    print(
                        f"imu={imu.status} fifo_overflow={imu.overflow_count} "
                        f"steps_alg={engine.steps_algorithm} steps_ai={engine.steps_ai} "
                        f"walking={engine.walking} p={engine.walking_probability} "
                        f"IR={pulse.ir} finger={'yes' if pulse.finger_present else 'no'} "
                        f"BPM~={pulse.bpm or '--'} ppg_reinit={pulse_sensor.failures} "
                        f"tft_ms_max={tft_ms_max:.0f}"
                    )
                    tft_ms_max = 0.0
                    last_log = started
                time.sleep(max(0, SAMPLE_INTERVAL_S - (time.monotonic() - started)))
    finally:
        if engine is not None and tracker is not None:
            engine.reset_signal()  # xả cửa sổ AI / chuỗi bước đang chờ để không mất bước cuối
            tracker.sync()
        if tracker is not None:
            tracker.daily.save_quietly()
        if publisher:
            if final_telemetry is not None:
                publisher.publish_telemetry(final_telemetry())
            publisher.stop()
        alerts.close()


def stop_on_sigterm(signum, frame):
    # systemctl/kill gửi SIGTERM: đi qua finally như Ctrl+C (lưu số bước, gửi nốt MQTT, tắt còi).
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, stop_on_sigterm)
    try:
        main()
    except KeyboardInterrupt:
        print("Da dung chuong trinh.")
