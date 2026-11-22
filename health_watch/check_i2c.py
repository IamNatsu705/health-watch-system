"""Liệt kê các địa chỉ I2C trước khi chạy chương trình chính."""

from smbus2 import SMBus


with SMBus(1) as bus:
    found = []
    for address in range(0x03, 0x78):
        try:
            bus.read_byte(address)
        except OSError:
            continue
        found.append(address)

print("Dia chi I2C:", ", ".join(f"0x{x:02X}" for x in found) or "khong thay")
print("Can thay MAX30102 = 0x57 va MPU6050 = 0x68 (hoac 0x69 neu AD0 len cao).")
