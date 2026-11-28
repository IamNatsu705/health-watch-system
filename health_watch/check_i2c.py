"""Kiểm tra bus I2C trước khi chạy chương trình chính.

    .venv/bin/python check_i2c.py              # liệt kê địa chỉ
    .venv/bin/python check_i2c.py --watch 60   # đọc ID hai cảm biến liên tục trong 60 s

Chế độ --watch dùng để tìm dây tiếp xúc kém: trong lúc chạy, lắc nhẹ từng dây và cử động
cổ tay như khi đi bộ. Mỗi lỗi I2C được in ngay kèm thời điểm, nên biết lúc lắc dây nào thì
lỗi. Dừng main.py/service trước khi chạy để hai chương trình không cùng dùng cảm biến.
"""

import argparse
import errno
import time

from config import I2C_BUS, MAX30102_ADDRESS, MPU6050_ADDRESS
from sensors.mpu6050 import CHIPS, REG_PWR_MGMT_1, REG_WHO_AM_I

MAX_PART_ID_REG = 0xFF
MAX_PART_ID = 0x15
MPU_AWAKE = 0x01      # thoát ngủ, đồng hồ PLL; chip tự reset (mất nguồn) sẽ về 0x40
MPU_SLEEP_BIT = 0x40

# Mã lỗi Linux mà driver I2C của Pi trả về (đánh số theo Linux để chạy thử được cả trên PC).
ERRNO_HINTS = {
    5: ("EIO", "tín hiệu SDA/SCL chập chờn, hoặc một chip mất nguồn kéo bus"),
    121: ("EREMOTEIO", "chip không trả lời: đứt dây hoặc mất nguồn"),
    110: ("ETIMEDOUT", "bus bị giữ (SDA/SCL chạm GND hoặc chip treo)"),
}


def _errno_name(code) -> str:
    return ERRNO_HINTS[code][0] if code in ERRNO_HINTS else errno.errorcode.get(code, str(code))


def scan(bus) -> list[int]:
    found = []
    for address in range(0x03, 0x78):
        try:
            bus.read_byte(address)
        except OSError:
            continue
        found.append(address)
    return found


class Probe:
    """Đọc một thanh ghi ID và đếm lỗi I2C, giá trị sai và (với MPU6050) số lần chip tự reset."""

    def __init__(self, name, address, register, valid):
        self.name = name
        self.address = address
        self.register = register
        self.valid = valid
        self.ok = 0
        self.errors = {}
        self.bad_values = 0
        self.resets = 0

    @property
    def failures(self) -> int:
        return sum(self.errors.values()) + self.bad_values + self.resets

    def read(self, bus):
        """Trả về mô tả lỗi, hoặc None nếu đọc đúng."""
        try:
            value = bus.read_byte_data(self.address, self.register)
        except OSError as exc:
            code = exc.errno if exc.errno is not None else -1
            self.errors[code] = self.errors.get(code, 0) + 1
            hint = ERRNO_HINTS[code][1] if code in ERRNO_HINTS else str(exc)
            return f"lỗi I2C {_errno_name(code)} ({hint})"
        if value not in self.valid:
            self.bad_values += 1
            return f"đọc sai ID 0x{value:02X} (dữ liệu bị nhiễu)"
        self.ok += 1
        return None

    def summary(self) -> str:
        errors = ", ".join(f"{_errno_name(code)}×{count}" for code, count in sorted(self.errors.items()))
        text = f"{self.name} 0x{self.address:02X}: đọc đúng {self.ok}, lỗi I2C {sum(self.errors.values())}"
        if errors:
            text += f" [{errors}]"
        text += f", sai ID {self.bad_values}"
        if self.resets:
            text += f", tự reset {self.resets} lần"
        return text


def _wake_mpu(bus, address) -> bool:
    try:
        bus.write_byte_data(address, REG_PWR_MGMT_1, MPU_AWAKE)
        return True
    except OSError:
        return False


def watch(bus, seconds, clock=time.monotonic, sleep=time.sleep, out=print) -> list[Probe]:
    mpu = Probe("MPU6050", MPU6050_ADDRESS, REG_WHO_AM_I, set(CHIPS))
    max_sensor = Probe("MAX30102", MAX30102_ADDRESS, MAX_PART_ID_REG, {MAX_PART_ID})
    probes = (mpu, max_sensor)
    # Đánh thức MPU6050 để phát hiện mất nguồn: chip reset sẽ tự về chế độ ngủ (PWR_MGMT_1=0x40).
    mpu_awake = _wake_mpu(bus, mpu.address)
    start = clock()
    last_power_check = last_report = start
    out(f"Đọc liên tục {seconds:g} s. Lắc nhẹ từng dây của MPU6050 và MAX30102, cử động cổ tay. Ctrl+C để dừng sớm.")
    try:
        while (now := clock()) - start < seconds:
            elapsed = now - start
            for probe in probes:
                problem = probe.read(bus)
                if problem:
                    out(f"  t={elapsed:5.1f}s {probe.name}: {problem}")
            if now - last_power_check >= 0.5:
                last_power_check = now
                try:
                    power = bus.read_byte_data(mpu.address, REG_PWR_MGMT_1)
                except OSError:
                    power = None
                if power is not None and (power & MPU_SLEEP_BIT or not mpu_awake):
                    if mpu_awake:
                        mpu.resets += 1
                        out(f"  t={elapsed:5.1f}s MPU6050: chip vừa tự reset, tức là đã mất nguồn (dây VCC/GND)")
                    mpu_awake = _wake_mpu(bus, mpu.address)
            if now - last_report >= 5.0:
                last_report = now
                status = "ổn" if not any(p.failures for p in probes) else "CÓ LỖI"
                out(f"t={elapsed:5.1f}s {status}: " + " | ".join(
                    f"{p.name} đúng {p.ok}, lỗi {p.failures}" for p in probes))
            sleep(0.004)
    except KeyboardInterrupt:
        out("Dừng sớm.")
    finally:
        try:
            bus.write_byte_data(mpu.address, REG_PWR_MGMT_1, MPU_SLEEP_BIT)
        except OSError:
            pass
    out("Kết quả:")
    for probe in probes:
        out("  " + probe.summary())
    if not any(p.failures for p in probes):
        out("Không có lỗi trong lúc thử: dây I2C và nguồn ổn.")
    else:
        out("Có lỗi: tắt nguồn Pi, cắm chắc hoặc hàn lại dây của cảm biến bị lỗi, rồi chạy lại để xác nhận.")
    return list(probes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--watch", type=float, metavar="GIAY",
                        help="đọc ID MPU6050 và MAX30102 liên tục trong số giây này")
    args = parser.parse_args()

    from smbus2 import SMBus

    with SMBus(I2C_BUS) as bus:
        if args.watch:
            probes = watch(bus, args.watch)
            return 1 if any(p.failures for p in probes) else 0
        found = scan(bus)
    print("Dia chi I2C:", ", ".join(f"0x{x:02X}" for x in found) or "khong thay")
    print("Can thay MAX30102 = 0x57 va MPU6050 = 0x68 (hoac 0x69 neu AD0 len cao).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
