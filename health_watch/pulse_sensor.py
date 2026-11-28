"""MAX30102 trong vòng lặp chính, cô lập lỗi để cảm biến nhịp tim không làm dừng bộ đếm bước.

Thuật toán BPM (``processing/pulse.py``) và driver (``sensors/max30102.py``) giữ nguyên;
lớp này chỉ đọc FIFO, đưa mẫu vào PulseMonitor, ghi CSV PPG nếu được bật, và khởi tạo
lại cảm biến khi FIFO tràn/đầy (rollover tắt nên phải reset mới đọc tiếp được) hoặc lỗi I2C.
"""

import logging

from ppg_log import OK_STATUSES, PpgCsvLogger
from sensors.max30102 import MAX30102


log = logging.getLogger("health_watch.pulse_sensor")


class PulseSensor:
    RETRY_S = 5.0

    def __init__(self, bus, address: int, monitor, csv_log: bool = False, logger_factory=PpgCsvLogger,
                 sensor_factory=MAX30102):
        self.bus = bus
        self.address = address
        self.monitor = monitor
        self.csv_log = csv_log
        self.logger_factory = logger_factory
        self.sensor_factory = sensor_factory
        self.sensor = None
        self.logger = None
        self.error = None
        self.failures = 0
        self._next_try = 0.0

    def poll(self, now: float, analyze: bool = True) -> None:
        if self.sensor is None:
            if now < self._next_try:
                return
            try:
                self.sensor = self.sensor_factory(self.bus, self.address)
            except (OSError, RuntimeError, ValueError) as exc:
                self._fail(now, str(exc))
                return
            if self.error:
                log.info("MAX30102 đã hoạt động lại")
            self.error = None
            if self.csv_log:
                self._open_log()

        poll = self.sensor.read_poll()
        if self.logger is not None:
            try:
                self.logger.write(poll)
            except OSError as exc:
                log.warning("Ngừng ghi CSV PPG: %s", exc)
                self._close_log()
        if poll.status not in OK_STATUSES:
            self._fail(now, f"{poll.status}: {poll.detail}")
            return
        for red, ir in poll.samples:
            self.monitor.add(red, ir)
        if analyze:
            self.monitor.analyze(now)

    def _open_log(self) -> None:
        try:
            self.logger = self.logger_factory(self.sensor_factory.SAMPLES_PER_SECOND)
            log.info("Ghi PPG: %s", self.logger.csv_path)
        except OSError as exc:
            log.warning("Không mở được CSV PPG: %s", exc)
            self.logger = None

    def _close_log(self) -> None:
        if self.logger is not None:
            self.logger.close()
            self.logger = None

    def _fail(self, now: float, reason: str) -> None:
        if self.error is None:
            log.warning("MAX30102 lỗi, bộ đếm bước vẫn chạy: %s", reason)
        self.failures += 1
        self.sensor = None
        self.error = reason
        self._next_try = now + self.RETRY_S
        # Phiên CSV kết thúc tại chỗ mất mẫu; khởi tạo lại sẽ mở phiên mới (time_s liên tục).
        self._close_log()
        # Không giữ BPM cũ khi cảm biến mất hoặc dữ liệu bị đứt.
        self.monitor.bpm = None
        self.monitor.finger_present = False
        self.monitor.ir_history.clear()

    def close(self) -> None:
        self._close_log()
