"""Đọc cảm biến, đếm bước (thuật toán + AI) trên dữ liệu thật, cảnh báo tại chỗ và gửi MQTT."""

import logging
import time
from types import SimpleNamespace

from smbus2 import SMBus

from alerts import AlertOutputs
from clock import clock_synced
from config import (
    I2C_BUS,
    I2C_READ_ATTEMPTS,
    MAX30102_ADDRESS,
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
    SAMPLE_INTERVAL_S,
    SCREEN_INTERVAL_S,
)
from inference.walk_gate import load_default_gate
from mqtt_publisher import BrokerSettings, MqttPublisher
from processing.fall import FallDetector
from processing.pulse import PulseMonitor
from processing.steps import StepEngine
from screen import Screen
from sensors.max30102 import MAX30102
from sensors.mpu6050 import ImuStream
from storage import DailyStepStore, ProfileStore
from telemetry import DeviceMessageFactory, utc_now
from user_profile import active_kcal, distance_m


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("health_watch.main")
DAILY_SAVE_INTERVAL_S = 10.0


class PulseSensor:
    """Cô lập MAX30102: lỗi cảm biến nhịp tim không được làm dừng bộ đếm bước.

    Thuật toán BPM (``processing/pulse.py``) giữ nguyên; lớp này chỉ khởi tạo lại
    cảm biến khi lỗi và xóa giá trị cũ để không hiển thị BPM của lúc trước.
    """

    RETRY_S = 5.0

    def __init__(self, bus, address: int, monitor: PulseMonitor):
        self.bus = bus
        self.address = address
        self.monitor = monitor
        self.sensor = None
        self.error = None
        self._next_try = 0.0

    def _read(self):
        for attempt in range(1, I2C_READ_ATTEMPTS + 1):
            try:
                return self.sensor.read_samples()
            except OSError:
                if attempt == I2C_READ_ATTEMPTS:
                    raise
                time.sleep(0.02)

    def poll(self, now: float) -> None:
        if self.sensor is None:
            if now < self._next_try:
                return
            try:
                self.sensor = MAX30102(self.bus, self.address)
            except (OSError, RuntimeError) as exc:
                self._fail(now, exc)
                return
            if self.error:
                log.info("MAX30102 đã hoạt động lại")
            self.error = None
        try:
            samples = self._read()
        except OSError as exc:
            self._fail(now, exc)
            return
        for red, ir in samples:
            self.monitor.add(red, ir)
        self.monitor.analyze(now)

    def _fail(self, now: float, exc: Exception) -> None:
        if self.error is None:
            log.warning("MAX30102 lỗi, bộ đếm bước vẫn chạy: %s", exc)
        self.sensor = None
        self.error = str(exc)
        self._next_try = now + self.RETRY_S
        self.monitor.bpm = None
        self.monitor.finger_present = False
        self.monitor.ir_history.clear()


class StepTracker:
    """Nối bộ đếm phiên với số bước trong ngày và hồ sơ người đeo."""

    def __init__(self, engine: StepEngine, daily: DailyStepStore, profile):
        self.engine = engine
        self.daily = daily
        self.profile = profile
        self._last = (0, 0, 0, 0)

    def sync(self) -> None:
        engine = self.engine
        current = (
            engine.steps_algorithm,
            engine.running_steps_algorithm,
            engine.steps_ai or 0,
            engine.running_steps_ai or 0,
        )
        deltas = [now - before for now, before in zip(current, self._last)]
        self.daily.add(algorithm=deltas[0], algorithm_running=deltas[1], ai=deltas[2], ai_running=deltas[3])
        self._last = current

    @property
    def source_key(self) -> str:
        return "ai" if self.engine.gate is not None else "algorithm"

    def today(self) -> tuple[int, int]:
        key = self.source_key
        return self.daily.counts[key], self.daily.counts[f"{key}_running"]

    def screen_view(self, imu: ImuStream) -> SimpleNamespace:
        steps, running = self.today()
        distance = distance_m(steps, self.profile)
        return SimpleNamespace(
            steps=steps,
            source_label="AI" if self.engine.gate is not None else "Thuật toán",
            distance_km=None if distance is None else distance / 1000.0,
            calories_kcal=active_kcal(steps, running, self.profile),
            imu_ok=imu.ok,
        )

    def distance_basis(self) -> dict | None:
        if self.profile is None:
            return None
        return {
            "step_length_m": self.profile.effective_step_length_m,
            "method": self.profile.step_length_method,
        }


def main() -> None:
    alerts = AlertOutputs()
    publisher = None
    messages = None
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

        with SMBus(I2C_BUS) as bus:
            imu = ImuStream(bus, MPU6050_ADDRESS)
            pulse = PulseMonitor(MAX30102.SAMPLES_PER_SECOND)
            pulse_sensor = PulseSensor(bus, MAX30102_ADDRESS, pulse)
            fall = FallDetector()

            def telemetry() -> dict:
                steps = engine.primary_steps
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
                    distance_m_session=distance_m(steps, tracker.profile),
                    calories_kcal_session=active_kcal(steps, engine.primary_running_steps, tracker.profile),
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
                        tracker.profile = update["profile"]
                        profile_store.save(tracker.profile)
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
                    tracker.daily.save()
                    last_daily_save = started
                if started - last_screen >= SCREEN_INTERVAL_S:
                    screen.update(tracker.screen_view(imu), pulse, alert_state)
                    last_screen = started
                if started - last_log >= 2.0:
                    print(
                        f"imu={imu.status} fifo_overflow={imu.overflow_count} "
                        f"steps_alg={engine.steps_algorithm} steps_ai={engine.steps_ai} "
                        f"walking={engine.walking} p={engine.walking_probability} "
                        f"IR={pulse.ir} finger={'yes' if pulse.finger_present else 'no'} "
                        f"BPM~={pulse.bpm or '--'}"
                    )
                    last_log = started
                time.sleep(max(0, SAMPLE_INTERVAL_S - (time.monotonic() - started)))
    finally:
        if tracker is not None:
            try:
                tracker.daily.save()
            except OSError as exc:
                log.warning("Không lưu được số bước trong ngày: %s", exc)
        if publisher:
            if final_telemetry is not None:
                publisher.publish_telemetry(final_telemetry())
            publisher.stop()
        alerts.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Da dung chuong trinh.")
