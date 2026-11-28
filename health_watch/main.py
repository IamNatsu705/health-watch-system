"""Đọc cảm biến, đếm bước (thuật toán + AI) trên dữ liệu thật, cảnh báo tại chỗ và gửi MQTT."""

import logging
import math
import signal
import time
from contextlib import ExitStack

from smbus2 import SMBus

from alerts import AlertOutputs
from clock import clock_synced
from config import (
    FALL_CANCEL_WINDOW_S,
    FALL_IMMOBILE_S,
    I2C_BUS,
    I2C_READ_ATTEMPTS,
    MAX30102_ADDRESS,
    MAX30102_SAMPLE_AVERAGING,
    MAX30102_SAMPLE_RATE,
    MAX30102_SAMPLES_PER_SECOND,
    MQTT_DEVICE_ID,
    MQTT_ENABLED,
    MQTT_CA_CERT,
    MQTT_CLIENT_CERT,
    MQTT_CLIENT_KEY,
    MQTT_HOST,
    MQTT_KEEPALIVE_S,
    MQTT_OUTBOX_SIZE,
    MQTT_PASSWORD,
    MQTT_PORT,
    MQTT_PUBLISH_INTERVAL_S,
    MQTT_TLS_ENABLED,
    MQTT_USERNAME,
    MPU6050_ADDRESS,
    PPG_CSV_LOG,
    SAMPLE_INTERVAL_S,
    SCREEN_INTERVAL_S,
)
from fall_alarm import ALARM, CHECK, FallAlarm
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
    last_command_id = None
    last_reported_output = None
    try:
        if MQTT_ENABLED:
            if MQTT_PUBLISH_INTERVAL_S <= 0:
                raise ValueError("MQTT_PUBLISH_INTERVAL_S phải lớn hơn 0")
            if not MQTT_TLS_ENABLED and MQTT_USERNAME != MQTT_DEVICE_ID:
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
                    tls_enabled=MQTT_TLS_ENABLED,
                    ca_cert=MQTT_CA_CERT,
                    client_cert=MQTT_CLIENT_CERT,
                    client_key=MQTT_CLIENT_KEY,
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
            fall_alarm = FallAlarm(cancel_window_s=FALL_CANCEL_WINDOW_S, immobile_s=FALL_IMMOBILE_S)
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
            print("Bat dau doc MPU6050 (FIFO 100 Hz) va MAX30102. Nhan Ctrl+C de dung.")

            while True:
                started = time.monotonic()
                batch = imu.poll(started)
                if imu.take_gap():
                    engine.reset_signal()
                just_fell = False
                for sample_time, motion in batch:
                    engine.add_sample(motion.ax, motion.ay, motion.az)
                    fall_alarm.observe(motion.ax, motion.ay, motion.az, sample_time)
                    was_fall_active = fall.confirmed
                    if fall.update(motion, sample_time) and not was_fall_active:
                        just_fell = True
                if just_fell:
                    fall_alarm.start(started)
                tracker.sync()
                if imu.status != last_imu_status:
                    if imu.status == "saturated":
                        log.info("MPU6050: va chạm vượt thang ±8 g")
                    elif imu.ok and last_imu_status == "saturated":
                        pass  # trở lại bình thường sau va chạm, không cần log
                    elif imu.ok:
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
                fall_response = None
                # Lần nhấn mới (không phải nút đang giữ từ trước) trả lời cảnh báo ngã: trong thời
                # gian hủy = người đeo báo ổn; sau khi đã báo động = tắt còi.
                if fall_alarm.active and button and not last_button and not just_fell:
                    phase = fall_alarm.acknowledge()
                    fall.clear()
                    acknowledge_press = True
                    fall_response = "fall_cancelled" if phase == CHECK else "fall_acknowledged"
                    print("Nguoi deo bao on, huy canh bao nga." if phase == CHECK else "Da tat bao dong nga.")
                if not button:
                    acknowledge_press = False
                fall_escalated = fall_alarm.update(started)
                sos_pressed = button and not acknowledge_press and not fall_alarm.active
                alerts.update(
                    fall_active=fall_alarm.active,
                    sos_active=sos_pressed or remote_alert_active,
                    buzzer_active=sos_pressed or remote_alert_active or fall_alarm.buzzer_on(started),
                )
                fall_state = {CHECK: "fall", ALARM: "fall_alarm"}.get(fall_alarm.state, "")
                alert_state = fall_state or ("sos" if sos_pressed else ("remote" if remote_alert_active else ""))
                remaining = fall_alarm.remaining_s(started)
                alert_detail = None
                if remaining is not None:
                    alert_detail = (f"Nhấn nút nếu bạn ổn · {math.ceil(remaining)} s" if remaining > 0
                                    else "Đang chờ bạn nhấn nút")
                output_source = (
                    "remote" if remote_alert_active else
                    ("sos" if sos_pressed else ("fall" if fall_alarm.active else "normal"))
                )
                # Còi bíp ngắt quãng vẫn báo là "đang bật": web hiện trạng thái báo động, không nhấp
                # nháy theo từng tiếng bíp (và không gửi alert-state mỗi nửa giây). Mã lệnh nằm trong
                # bộ so sánh để Pi xác nhận MỌI lệnh từ xa, kể cả lệnh không đổi được còi (ví dụ lệnh
                # tắt tới đúng lúc đang báo ngã): web không phải chờ hết hạn rồi giật ngược trạng thái.
                output_state = (
                    sos_pressed or remote_alert_active or fall_alarm.active,
                    fall_alarm.active or sos_pressed or remote_alert_active,
                    output_source,
                    last_command_id,
                )
                if alert_state != last_alert:
                    print({"fall": f"PHAT HIEN NGA: LED do + coi bip, nhan nut trong {FALL_CANCEL_WINDOW_S:g} s neu on.",
                           "fall_alarm": "BAO DONG NGA: nguoi deo nam yen, khong phan hoi; coi keu lien tuc.",
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
                    if fall_escalated:
                        publisher.publish_event(messages.event("fall_alarm"))
                    if fall_response:
                        publisher.publish_event(messages.event(fall_response))
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
                    screen.update(tracker.screen_view(imu), pulse, alert_state, alert_detail)
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
        try:
            alerts.close()  # tắt còi/LED ngay; xả hàng đợi MQTT phía dưới có thể mất vài giây
        finally:
            if engine is not None and tracker is not None:
                engine.reset_signal()  # xả cửa sổ AI / chuỗi bước đang chờ để không mất bước cuối
                tracker.sync()
            if tracker is not None:
                tracker.daily.save_quietly()
            if publisher:
                if messages is not None and last_reported_output is not None and any(last_reported_output[:2]):
                    # alert-state là retained: báo còi/LED đã tắt, không để trạng thái "đang kêu" cũ lại.
                    publisher.publish_alert_state(messages.alert_state(
                        buzzer_active=False, red_led_active=False, source="normal",
                        last_command_id=last_command_id, remote_remaining_s=0,
                    ))
                if final_telemetry is not None:
                    publisher.publish_telemetry(final_telemetry())
                publisher.stop()


def stop_on_sigterm(signum, frame):
    # systemctl/kill gửi SIGTERM: đi qua finally như Ctrl+C (lưu số bước, gửi nốt MQTT, tắt còi).
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, stop_on_sigterm)
    try:
        main()
    except KeyboardInterrupt:
        print("Da dung chuong trinh.")
