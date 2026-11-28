"""Driver MPU6050 dùng FIFO trên bus I2C giả lập thanh ghi (không cần phần cứng)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sensors import mpu6050
from sensors.mpu6050 import ImuError, ImuStream, MPU6050


class FakeMpuBus:
    """Mô phỏng tối thiểu register map MPU6050: ghi/đọc thanh ghi và FIFO."""

    def __init__(self, who_am_i=0x68, capacity=1024):
        self.registers = {0x75: who_am_i, 0x6B: 0x40}
        self.fifo = bytearray()
        self.capacity = capacity
        self.block_reads = []
        self.fail_reads = False
        self.ignore_writes = set()

    def write_byte_data(self, address, register, value):
        if register in self.ignore_writes:
            return
        if register == 0x6B and value & 0x80:
            self.registers = {0x75: self.registers[0x75], 0x6B: 0x40}
            self.fifo.clear()
            return
        if register == 0x6A and value & 0x04:
            self.fifo.clear()
            value &= ~0x04
        self.registers[register] = value

    def read_byte_data(self, address, register):
        if self.fail_reads:
            raise OSError(121, "Remote I/O error")
        value = self.registers.get(register, 0)
        if register == 0x3A:
            self.registers[0x3A] = 0
        return value

    def read_i2c_block_data(self, address, register, length):
        if self.fail_reads:
            raise OSError(121, "Remote I/O error")
        self.block_reads.append((register, length))
        if length > 32:
            raise OSError("SMBus block read tối đa 32 byte")
        if register == 0x72:
            count = len(self.fifo)
            return [(count >> 8) & 0x1F, count & 0xFF]
        if register == 0x74:
            data = list(self.fifo[:length])
            del self.fifo[:length]
            return data
        if register == 0x43:
            return [0, 131, 0, 0, 255, 125]  # gx=+2 °/s, gz=-2 °/s ở ±500 °/s
        return [0] * length

    def push_accel(self, ax_raw, ay_raw, az_raw, count=1):
        for _ in range(count):
            for value in (ax_raw, ay_raw, az_raw):
                self.fifo += (value & 0xFFFF).to_bytes(2, "big")
        if len(self.fifo) > self.capacity:
            del self.fifo[self.capacity:]
            self.registers[0x3A] = 0x10


class MpuDriverTests(unittest.TestCase):
    def setUp(self):
        self.sleep = mpu6050.time.sleep
        mpu6050.time.sleep = lambda seconds: None

    def tearDown(self):
        mpu6050.time.sleep = self.sleep

    def test_configures_fifo_100hz_with_anti_alias_filter(self):
        bus = FakeMpuBus()
        sensor = MPU6050(bus)
        self.assertEqual(bus.registers[0x6B], 0x01)   # PLL, không ngủ
        self.assertEqual(bus.registers[0x19], 9)      # 1 kHz / 10 = 100 Hz
        self.assertEqual(bus.registers[0x1A], 0x03)   # DLPF 44 Hz
        self.assertEqual(bus.registers[0x1C], 0x10)   # ±8 g
        self.assertEqual(bus.registers[0x1B], 0x08)   # ±500 °/s
        self.assertEqual(bus.registers[0x23], 0x08)   # chỉ gia tốc vào FIFO
        self.assertEqual(bus.registers[0x6A], 0x40)
        self.assertEqual(sensor.chip, "MPU6050")

    def test_mpu6500_also_sets_accel_filter(self):
        bus = FakeMpuBus(who_am_i=0x70, capacity=512)
        sensor = MPU6050(bus)
        self.assertEqual(bus.registers[0x1D], 0x03)
        self.assertEqual(sensor.fifo_capacity, 512)

    def test_unknown_chip_and_failed_readback_are_errors(self):
        with self.assertRaises(ImuError):
            MPU6050(FakeMpuBus(who_am_i=0x12))
        bus = FakeMpuBus()
        bus.ignore_writes.add(0x1A)
        with self.assertRaises(ImuError):
            MPU6050(bus)

    def test_reads_fifo_in_aligned_chunks(self):
        bus = FakeMpuBus()
        sensor = MPU6050(bus)
        bus.push_accel(4096, -4096, 8192, count=12)
        frames, overflow = sensor.read_fifo()
        self.assertFalse(overflow)
        self.assertEqual(len(frames), 12)
        self.assertEqual(frames[0], (4096, -4096, 8192))
        fifo_reads = [length for register, length in bus.block_reads if register == 0x74]
        self.assertTrue(all(length % 6 == 0 and length <= 30 for length in fifo_reads))
        sample = sensor.to_sample(frames[0], (0.0, 0.0, 0.0))
        self.assertEqual((sample.ax, sample.ay, sample.az), (1.0, -1.0, 2.0))

    def test_overflow_resets_fifo(self):
        bus = FakeMpuBus()
        sensor = MPU6050(bus)
        bus.push_accel(0, 0, 4096, count=200)
        frames, overflow = sensor.read_fifo()
        self.assertTrue(overflow)
        self.assertEqual(frames, [])
        self.assertEqual(len(bus.fifo), 0)


class ImuStreamTests(unittest.TestCase):
    def setUp(self):
        self.sleep = mpu6050.time.sleep
        mpu6050.time.sleep = lambda seconds: None
        self.bus = FakeMpuBus()
        self.stream = ImuStream(self.bus)

    def tearDown(self):
        mpu6050.time.sleep = self.sleep

    def feed(self, now, frames, raw=(0, 0, 4096), jitter=0):
        for i in range(frames):
            self.bus.push_accel(raw[0] + (i + jitter) % 3, raw[1], raw[2])
        return self.stream.poll(now)

    def test_samples_are_evenly_spaced_despite_irregular_polls(self):
        self.stream.poll(0.0)
        times = []
        now = 0.0
        for frames, wait in ((4, 0.04), (20, 0.2), (4, 0.04), (19, 0.19)):
            now += wait
            times += [t for t, _ in self.feed(now, frames)]
        spacing = [round(b - a, 6) for a, b in zip(times, times[1:])]
        self.assertTrue(all(abs(s - 0.01) < 0.002 for s in spacing), spacing)
        self.assertEqual(self.stream.status, "ok")
        self.assertFalse(self.stream.take_gap())

    def test_overflow_marks_gap(self):
        self.stream.poll(0.0)
        self.feed(0.04, 4)
        self.feed(1.5, 200)
        self.assertTrue(self.stream.take_gap())
        self.assertEqual(self.stream.overflow_count, 1)

    def test_i2c_error_returns_no_samples_and_retries(self):
        self.stream.poll(0.0)
        self.feed(0.04, 4)
        self.bus.fail_reads = True
        self.assertEqual(self.feed(0.08, 4), [])
        self.assertEqual(self.stream.status, "error")
        self.assertTrue(self.stream.take_gap())
        self.bus.fail_reads = False
        self.assertEqual(self.stream.poll(0.5), [])   # chưa tới lúc thử lại
        self.stream.poll(2.2)
        self.assertEqual(self.stream.status, "ok")
        self.assertEqual(self.stream.reinit_count, 1)

    def test_frozen_identical_frames_are_rejected(self):
        self.stream.poll(0.0)
        for i in range(3):
            self.bus.push_accel(10, 20, 4096, count=20)
            result = self.stream.poll(0.2 * (i + 1))
        self.assertEqual(result, [])
        self.assertEqual(self.stream.status, "frozen")

    def test_sensor_reset_to_sleep_is_detected(self):
        self.stream.poll(0.0)
        self.feed(0.04, 4)
        self.bus.registers[0x6B] = 0x40  # sụt áp: chip tự reset về chế độ ngủ
        self.feed(1.2, 4)
        self.assertEqual(self.stream.status, "error")

    def test_no_new_samples_triggers_error(self):
        self.stream.poll(0.0)
        self.feed(0.04, 4)
        self.stream.poll(0.3)
        self.assertEqual(self.stream.status, "ok")
        self.stream.poll(0.7)
        self.assertEqual(self.stream.status, "error")

    def test_saturation_is_reported(self):
        self.stream.poll(0.0)
        self.feed(0.04, 4, raw=(32767, 0, 4096))
        self.assertEqual(self.stream.status, "saturated")
        self.assertTrue(self.stream.ok)


if __name__ == "__main__":
    unittest.main()
