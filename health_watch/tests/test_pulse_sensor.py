"""Driver MAX30102 (FIFO, tràn), ghi CSV PPG và cô lập lỗi cảm biến nhịp tim khỏi vòng lặp chính."""

import csv
import sys
import tempfile
import unittest
from collections import deque
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ppg_log import FIFO_FIELDS, PpgCsvLogger
from pulse_sensor import PulseSensor
from sensors import max30102 as max_module
from sensors.max30102 import FIFOPoll, MAX30102


class FakeMaxBus:
    """Thanh ghi tối thiểu của MAX30102: PART_ID, con trỏ FIFO, bộ đếm tràn, dữ liệu FIFO."""

    def __init__(self):
        self.registers = {0xFF: 0x15, 0x00: 0, 0x04: 0, 0x05: 0, 0x06: 0}
        self.fifo = deque()

    def push(self, red, ir, count=1):
        for _ in range(count):
            self.fifo.append((red, ir))
            self.registers[0x04] = (self.registers[0x04] + 1) % 32

    def read_byte_data(self, address, register):
        return self.registers.get(register, 0)

    def write_byte_data(self, address, register, value):
        self.registers[register] = value

    def read_i2c_block_data(self, address, register, length):
        if register == 0x04:
            return [self.registers[0x04], self.registers[0x05], self.registers[0x06]]
        if register == 0x07:
            data = []
            for _ in range(length // 6):
                red, ir = self.fifo.popleft()
                data += [(red >> 16) & 3, (red >> 8) & 0xFF, red & 0xFF, (ir >> 16) & 3, (ir >> 8) & 0xFF, ir & 0xFF]
                self.registers[0x06] = (self.registers[0x06] + 1) % 32
            return data
        return [0] * length


class DriverTests(unittest.TestCase):
    def setUp(self):
        self.sleep = max_module.time.sleep
        max_module.time.sleep = lambda s: None

    def tearDown(self):
        max_module.time.sleep = self.sleep

    def test_reads_pending_samples_in_chunks(self):
        bus = FakeMaxBus()
        sensor = MAX30102(bus)
        self.assertEqual(MAX30102.SAMPLES_PER_SECOND, 100)
        bus.push(70000, 90000, count=7)
        poll = sensor.read_poll()
        self.assertEqual(poll.status, "OK")
        self.assertEqual(len(poll.samples), 7)
        self.assertEqual(poll.samples[0], (70000, 90000))
        self.assertEqual(sensor.read_poll().status, "Không có mẫu mới")

    def test_overflow_stops_batch_and_read_samples_raises(self):
        bus = FakeMaxBus()
        sensor = MAX30102(bus)
        bus.push(1, 2, count=3)
        bus.registers[0x05] = 4  # bộ đếm mất mẫu
        poll = sensor.read_poll()
        self.assertEqual(poll.status, "Tràn FIFO")
        self.assertEqual(poll.samples, [])
        with self.assertRaises(RuntimeError):
            sensor.read_samples()

    def test_wrong_part_id_is_rejected(self):
        bus = FakeMaxBus()
        bus.registers[0xFF] = 0x11
        with self.assertRaises(RuntimeError):
            MAX30102(bus)


def make_poll(status="OK", samples=((60000, 70000),), started=1.0):
    return FIFOPoll(started=started, finished=started + 0.001, pending=len(samples), overflow=0,
                    samples=list(samples), status=status, detail="" if status == "OK" else "test")


class LoggerTests(unittest.TestCase):
    def test_csv_format_matches_research_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock = iter([0.0])
            logger = PpgCsvLogger(100, Path(tmp), clock=lambda: next(clock))
            logger.write(make_poll(samples=[(1, 2), (3, 4)], started=0.04))
            logger.write(make_poll(status="Tràn FIFO", samples=[], started=0.08))
            logger.close()
            with open(logger.csv_path, encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.reader(handle))
            with open(logger.fifo_path, encoding="utf-8-sig", newline="") as handle:
                fifo_rows = list(csv.reader(handle))
        self.assertEqual(rows[0], ["sample_id", "time_s", "read_time_s", "red", "ir"] + FIFO_FIELDS)
        self.assertEqual(rows[1][:5], ["0", "0.000000", "0.041000", "1", "2"])
        self.assertEqual(rows[2][:2], ["1", "0.010000"])
        self.assertEqual(len(rows), 3)                       # lô lỗi không vào PPG
        self.assertEqual(len(fifo_rows), 3)                  # nhưng vẫn có dòng FIFO
        self.assertEqual(fifo_rows[2][8], "Tràn FIFO")
        self.assertTrue(logger.csv_path.name.startswith("ppg_") and logger.csv_path.name.endswith("_UTC+07.csv"))


class FakeSensor:
    SAMPLES_PER_SECOND = 100
    instances = []

    def __init__(self, bus, address):
        self.polls = deque()
        FakeSensor.instances.append(self)

    def read_poll(self):
        return self.polls.popleft() if self.polls else make_poll(status="Không có mẫu mới", samples=[])


class FakeLogger:
    opened = []

    def __init__(self, sample_rate):
        self.csv_path = Path(f"ppg_{len(FakeLogger.opened)}.csv")
        self.writes = []
        self.closed = False
        FakeLogger.opened.append(self)

    def write(self, poll):
        self.writes.append(poll.status)

    def close(self):
        self.closed = True


class PulseSensorTests(unittest.TestCase):
    def setUp(self):
        FakeSensor.instances = []
        FakeLogger.opened = []
        self.monitor = SimpleNamespace(bpm=72, finger_present=True, ir_history=[1, 2, 3], added=[], analyzed=0)
        self.monitor.add = lambda red, ir: self.monitor.added.append((red, ir))
        self.monitor.analyze = lambda now: setattr(self.monitor, "analyzed", self.monitor.analyzed + 1)
        self.sensor = PulseSensor(None, 0x57, self.monitor, csv_log=True,
                                  logger_factory=FakeLogger, sensor_factory=FakeSensor)

    def test_samples_go_to_monitor_and_log(self):
        self.sensor.poll(0.0)
        FakeSensor.instances[0].polls.append(make_poll(samples=[(5, 6)]))
        self.sensor.poll(0.04)
        self.assertEqual(self.monitor.added, [(5, 6)])
        self.assertEqual(FakeLogger.opened[0].writes, ["Không có mẫu mới", "OK"])

    def test_fifo_overflow_does_not_raise_and_reinitialises_with_new_csv_session(self):
        self.sensor.poll(0.0)
        FakeSensor.instances[0].polls.append(make_poll(status="FIFO đầy", samples=[]))
        self.sensor.poll(0.04)                       # không ném lỗi ra vòng lặp chính
        self.assertIsNone(self.sensor.sensor)
        self.assertIsNone(self.monitor.bpm)          # không giữ BPM cũ
        self.assertFalse(self.monitor.finger_present)
        self.assertTrue(FakeLogger.opened[0].closed)
        self.sensor.poll(1.0)                        # chưa tới lúc thử lại
        self.assertEqual(len(FakeSensor.instances), 1)
        self.sensor.poll(5.1)
        self.assertEqual(len(FakeSensor.instances), 2)
        self.assertEqual(len(FakeLogger.opened), 2)  # phiên CSV mới, time_s liên tục trong mỗi phiên

    def test_init_errors_are_contained(self):
        def broken(bus, address):
            raise ValueError("SAMPLE_RATE sai")
        sensor = PulseSensor(None, 0x57, self.monitor, sensor_factory=broken)
        sensor.poll(0.0)
        self.assertIsNone(sensor.sensor)
        self.assertIn("SAMPLE_RATE", sensor.error)


if __name__ == "__main__":
    unittest.main()
