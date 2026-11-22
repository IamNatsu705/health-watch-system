"""Đọc gia tốc và con quay hồi chuyển của GY-521/MPU6050."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MotionSample:
    ax: float  # g
    ay: float
    az: float
    gx: float  # độ/giây
    gy: float
    gz: float


class MPU6050:
    def __init__(self, bus, address: int = 0x68):
        self.bus = bus
        self.address = address
        who_am_i = bus.read_byte_data(address, 0x75)
        if who_am_i not in (0x68, 0x69, 0x70):
            raise RuntimeError(
                f"MPU6050 tại 0x{address:02X} trả WHO_AM_I=0x{who_am_i:02X}"
            )
        bus.write_byte_data(address, 0x6B, 0x00)  # Thoát chế độ ngủ.
        bus.write_byte_data(address, 0x1B, 0x08)  # Gyro ±500 độ/giây.
        bus.write_byte_data(address, 0x1C, 0x10)  # Gia tốc ±8 g để thấy va chạm >2 g.

    @staticmethod
    def _signed(high: int, low: int) -> int:
        value = (high << 8) | low
        return value - 65536 if value & 0x8000 else value

    def read(self) -> MotionSample:
        raw = self.bus.read_i2c_block_data(self.address, 0x3B, 14)
        values = [self._signed(raw[i], raw[i + 1]) for i in (0, 2, 4, 8, 10, 12)]
        return MotionSample(
            values[0] / 4096.0,
            values[1] / 4096.0,
            values[2] / 4096.0,
            values[3] / 65.5,
            values[4] / 65.5,
            values[5] / 65.5,
        )
