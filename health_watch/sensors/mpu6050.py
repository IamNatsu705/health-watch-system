"""Driver GY-521/MPU6050 (và họ MPU6500/9250) đọc qua FIFO ở 100 Hz đều.

Vì sao dùng FIFO: vòng lặp chính bị màn hình TFT chặn ~170–200 ms mỗi lần vẽ.
Đọc thanh ghi tức thời khi đó làm mất mẫu và lấy mẫu không đều. FIFO của cảm
biến giữ mẫu do chính chip lấy theo đồng hồ PLL, nên mỗi lần đọc nhận đủ các
mẫu cách đều 10 ms.

Cấu hình (theo datasheet/register map MPU-6000/6050 rev 4.2 và MPU-6500):
* PWR_MGMT_1 = 0x01: thoát ngủ, đồng hồ PLL theo gyro X (ổn định hơn dao động nội).
* CONFIG.DLPF_CFG = 3: lọc thông thấp gia tốc 44 Hz/gyro 42 Hz, chống chồng phổ
  khi lấy mẫu 100 Hz (rung xe máy 20–50 Hz không còn bị gập xuống dải bước chân).
* SMPLRT_DIV = 9: 1 kHz / (1 + 9) = 100 Hz.
* ±8 g (4096 LSB/g), ±500 °/s (65,5 LSB/(°/s)).
"""

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class MotionSample:
    ax: float  # g
    ay: float
    az: float
    gx: float  # độ/giây
    gy: float
    gz: float


class ImuError(RuntimeError):
    """Cảm biến trả cấu hình/dữ liệu không hợp lệ."""


REG_SMPLRT_DIV = 0x19
REG_CONFIG = 0x1A
REG_GYRO_CONFIG = 0x1B
REG_ACCEL_CONFIG = 0x1C
REG_ACCEL_CONFIG2 = 0x1D  # chỉ có ở họ MPU6500
REG_FIFO_EN = 0x23
REG_INT_ENABLE = 0x38
REG_INT_STATUS = 0x3A
REG_GYRO_XOUT_H = 0x43
REG_USER_CTRL = 0x6A
REG_PWR_MGMT_1 = 0x6B
REG_FIFO_COUNT_H = 0x72
REG_FIFO_R_W = 0x74
REG_WHO_AM_I = 0x75

PWR_RESET = 0x80
PWR_SLEEP = 0x40
PWR_CLOCK_PLL_X = 0x01
DLPF_44HZ = 0x03
GYRO_500DPS = 0x08
ACCEL_8G = 0x10
FIFO_ACCEL = 0x08
FIFO_GYRO = 0x70
USER_FIFO_ENABLE = 0x40
USER_FIFO_RESET = 0x04
INT_FIFO_OVERFLOW = 0x10

ACCEL_LSB_PER_G = 4096.0
GYRO_LSB_PER_DPS = 65.5
RAW_LIMITS = (-32768, 32767)

# WHO_AM_I → (tên chip, dung lượng FIFO byte, có ACCEL_CONFIG2 không)
CHIPS = {
    0x68: ("MPU6050", 1024, False),
    0x69: ("MPU6050-compatible", 1024, False),  # một số chip clone; cấu hình vẫn được đọc lại để kiểm tra
    0x70: ("MPU6500", 512, True),
    0x71: ("MPU9250", 512, True),
    0x73: ("MPU9255", 512, True),
}


def _signed(high: int, low: int) -> int:
    value = (high << 8) | low
    return value - 65536 if value & 0x8000 else value


class MPU6050:
    SAMPLE_RATE_HZ = 100.0

    def __init__(self, bus, address: int = 0x68, fifo_gyro: bool = False):
        self.bus = bus
        self.address = address
        self.fifo_gyro = fifo_gyro
        self.frame_size = 12 if fifo_gyro else 6
        self.chip = None
        self.who_am_i = None
        self.fifo_capacity = 0
        self.configure()

    @property
    def info(self) -> dict:
        return {
            "chip": self.chip,
            "who_am_i": f"0x{self.who_am_i:02X}" if self.who_am_i is not None else None,
            "sample_rate_hz": self.SAMPLE_RATE_HZ,
            "accel_range_g": 8,
            "gyro_range_dps": 500,
            "dlpf_hz": 44,
            "fifo_bytes": self.fifo_capacity,
            "fifo_gyro": self.fifo_gyro,
        }

    def _write(self, register: int, value: int) -> None:
        self.bus.write_byte_data(self.address, register, value)

    def _read(self, register: int) -> int:
        return self.bus.read_byte_data(self.address, register)

    def configure(self) -> None:
        who_am_i = self._read(REG_WHO_AM_I)
        if who_am_i not in CHIPS:
            raise ImuError(f"Chip tại 0x{self.address:02X} trả WHO_AM_I=0x{who_am_i:02X}, không phải MPU6050/6500")
        self.chip, self.fifo_capacity, has_accel_config2 = CHIPS[who_am_i]
        self.who_am_i = who_am_i

        self._write(REG_PWR_MGMT_1, PWR_RESET)  # Xóa cấu hình còn sót của chương trình cũ.
        time.sleep(0.1)
        self._write(REG_PWR_MGMT_1, PWR_CLOCK_PLL_X)
        time.sleep(0.01)
        divider = int(round(1000.0 / self.SAMPLE_RATE_HZ)) - 1
        expected = {
            REG_SMPLRT_DIV: divider,
            REG_CONFIG: DLPF_44HZ,
            REG_GYRO_CONFIG: GYRO_500DPS,
            REG_ACCEL_CONFIG: ACCEL_8G,
        }
        if has_accel_config2:
            expected[REG_ACCEL_CONFIG2] = DLPF_44HZ  # Họ 6500 lọc gia tốc ở thanh ghi riêng.
        for register, value in expected.items():
            self._write(register, value)
        self._write(REG_INT_ENABLE, INT_FIFO_OVERFLOW)
        fifo_mask = FIFO_ACCEL | (FIFO_GYRO if self.fifo_gyro else 0)
        self._write(REG_FIFO_EN, 0)
        self._write(REG_USER_CTRL, USER_FIFO_RESET)
        time.sleep(0.002)
        self._write(REG_FIFO_EN, fifo_mask)
        self._write(REG_USER_CTRL, USER_FIFO_ENABLE)
        expected[REG_FIFO_EN] = fifo_mask
        expected[REG_PWR_MGMT_1] = PWR_CLOCK_PLL_X

        # Đọc lại để không chạy với cấu hình sai mà tưởng là đúng.
        masks = {REG_CONFIG: 0x07, REG_GYRO_CONFIG: 0x18, REG_ACCEL_CONFIG: 0x18,
                 REG_ACCEL_CONFIG2: 0x0F, REG_PWR_MGMT_1: 0x4F}
        for register, value in expected.items():
            mask = masks.get(register, 0xFF)
            actual = self._read(register)
            if actual & mask != value & mask:
                raise ImuError(f"Thanh ghi 0x{register:02X}={actual:#04x}, mong đợi {value:#04x}")
        self._read(REG_INT_STATUS)  # Xóa cờ ngắt cũ.

    def reset_fifo(self) -> None:
        self._write(REG_USER_CTRL, USER_FIFO_RESET)
        self._write(REG_USER_CTRL, USER_FIFO_ENABLE)

    def is_awake(self) -> bool:
        """Sụt áp có thể làm chip tự reset về chế độ ngủ mà I2C vẫn trả lời bình thường."""
        value = self._read(REG_PWR_MGMT_1)
        return not value & PWR_SLEEP and value & 0x07 == PWR_CLOCK_PLL_X

    def read_fifo(self) -> tuple[list[tuple[int, ...]], bool]:
        """Trả về (danh sách khung raw, có tràn FIFO không). Khi tràn, FIFO được xóa."""
        status = self._read(REG_INT_STATUS)
        high, low = self.bus.read_i2c_block_data(self.address, REG_FIFO_COUNT_H, 2)
        count = ((high & 0x1F) << 8) | low
        if status & INT_FIFO_OVERFLOW or count >= self.fifo_capacity - self.frame_size or count % self.frame_size:
            self.reset_fifo()
            return [], True
        frames = []
        per_read = (30 // self.frame_size) * self.frame_size  # SMBus đọc tối đa 32 byte mỗi lần.
        remaining = count
        while remaining:
            size = min(remaining, per_read)
            raw = self.bus.read_i2c_block_data(self.address, REG_FIFO_R_W, size)
            if len(raw) != size:
                raise ImuError("Đọc FIFO thiếu byte")
            for offset in range(0, size, self.frame_size):
                frames.append(tuple(
                    _signed(raw[offset + i], raw[offset + i + 1]) for i in range(0, self.frame_size, 2)
                ))
            remaining -= size
        return frames, False

    def read_gyro(self) -> tuple[float, float, float]:
        raw = self.bus.read_i2c_block_data(self.address, REG_GYRO_XOUT_H, 6)
        return tuple(_signed(raw[i], raw[i + 1]) / GYRO_LSB_PER_DPS for i in (0, 2, 4))

    def to_sample(self, frame: tuple[int, ...], gyro: tuple[float, float, float] | None = None) -> MotionSample:
        ax, ay, az = (value / ACCEL_LSB_PER_G for value in frame[:3])
        if self.fifo_gyro:
            gx, gy, gz = (value / GYRO_LSB_PER_DPS for value in frame[3:6])
        else:
            gx, gy, gz = gyro if gyro is not None else (0.0, 0.0, 0.0)
        return MotionSample(ax, ay, az, gx, gy, gz)

    @staticmethod
    def is_saturated(frame: tuple[int, ...]) -> bool:
        return any(value in RAW_LIMITS for value in frame[:3])


class ImuStream:
    """Bọc driver: gán thời gian đều cho mẫu FIFO, phát hiện lỗi và tự khởi tạo lại.

    Không bao giờ bịa mẫu: khi cảm biến lỗi, ``poll`` trả danh sách rỗng và
    ``status`` cho biết lý do; bộ đếm bước dừng tăng thay vì đoán.
    """

    RETRY_S = 2.0
    NO_DATA_S = 0.5
    FROZEN_FRAMES = 50          # 0,5 s khung giống hệt nhau: chip treo (nhiễu MEMS thật không cho vậy)
    SATURATED_HOLD_S = 1.0
    AWAKE_CHECK_S = 1.0

    def __init__(self, bus, address: int = 0x68, fifo_gyro: bool = False, sensor_factory=MPU6050):
        self.bus = bus
        self.address = address
        self.fifo_gyro = fifo_gyro
        self.sensor_factory = sensor_factory
        self.sensor = None
        self.status = "starting"
        self.error = None
        self.overflow_count = 0
        self.reinit_count = 0
        self.gap_count = 0
        self.sample_count = 0
        self._gap = False
        self._next_init_at = 0.0
        self._next_awake_check = 0.0
        self._last_t = None
        self._last_data_at = None
        self._last_frame = None
        self._same_frames = 0
        self._saturated_until = float("-inf")

    @property
    def dt(self) -> float:
        return 1.0 / MPU6050.SAMPLE_RATE_HZ

    @property
    def ok(self) -> bool:
        return self.status in ("ok", "saturated")

    def take_gap(self) -> bool:
        """True nếu luồng mẫu bị đứt từ lần gọi trước (bộ đếm bước cần reset bộ lọc)."""
        gap, self._gap = self._gap, False
        return gap

    def _mark_gap(self) -> None:
        if self._last_t is not None:
            self._gap = True
            self.gap_count += 1
        self._last_t = None
        self._last_frame = None
        self._same_frames = 0

    def _fail(self, now: float, reason: str) -> None:
        self.sensor = None
        self.status = "error"
        self.error = reason
        self._next_init_at = now + self.RETRY_S
        self._mark_gap()

    def poll(self, now: float) -> list[tuple[float, MotionSample]]:
        if self.sensor is None:
            if now < self._next_init_at:
                return []
            try:
                self.sensor = self.sensor_factory(self.bus, self.address, fifo_gyro=self.fifo_gyro)
            except (OSError, ImuError) as exc:
                self._fail(now, f"khởi tạo: {exc}")
                return []
            if self.status != "starting":
                self.reinit_count += 1
            self.status = "ok"
            self.error = None
            self._last_data_at = now
            self._next_awake_check = now + self.AWAKE_CHECK_S

        try:
            if now >= self._next_awake_check:
                self._next_awake_check = now + self.AWAKE_CHECK_S
                if not self.sensor.is_awake():
                    raise ImuError("chip tự reset/ngủ (có thể do sụt áp)")
            frames, overflow = self.sensor.read_fifo()
            gyro = self.sensor.read_gyro() if frames and not self.fifo_gyro else None
        except (OSError, ImuError) as exc:
            self._fail(now, str(exc))
            return []

        if overflow:
            self.overflow_count += 1
            self._mark_gap()
            self._last_data_at = now
            return []
        if not frames:
            if now - self._last_data_at > self.NO_DATA_S:
                self._fail(now, "không có mẫu mới từ FIFO")
            return []
        self._last_data_at = now

        for frame in frames:
            self._same_frames = self._same_frames + 1 if frame == self._last_frame else 0
            self._last_frame = frame
            if self.sensor.is_saturated(frame):
                self._saturated_until = now + self.SATURATED_HOLD_S
        if self._same_frames >= self.FROZEN_FRAMES:
            self._fail(now, "dữ liệu gia tốc đứng yên tuyệt đối")
            self.status = "frozen"
            return []

        # Khung cuối được lấy gần thời điểm đọc; các khung trước cách nhau đúng 1/fs.
        # Neo thời gian theo đồng hồ Pi nhưng chỉnh chậm để không làm méo khoảng cách mẫu.
        n = len(frames)
        dt = self.dt
        if self._last_t is None:
            last = now
        else:
            predicted = self._last_t + n * dt
            error = now - predicted
            last = now if abs(error) > 0.25 else predicted + 0.02 * error
            first = last - (n - 1) * dt
            if first <= self._last_t:
                last += self._last_t + dt - first
        self._last_t = last
        self.sample_count += n
        self.status = "saturated" if now < self._saturated_until else "ok"
        return [(last - (n - 1 - i) * dt, self.sensor.to_sample(frame, gyro)) for i, frame in enumerate(frames)]
