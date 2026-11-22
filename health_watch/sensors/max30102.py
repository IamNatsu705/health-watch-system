"""Cấu hình MAX30102 và đọc mẫu Red/IR từ FIFO."""

import time


class MAX30102:
    SAMPLES_PER_SECOND = 25  # Cảm biến chạy 100 Hz, FIFO trung bình 4 mẫu.

    def __init__(self, bus, address: int = 0x57):
        self.bus = bus
        self.address = address
        part_id = bus.read_byte_data(address, 0xFF)
        if part_id != 0x15:
            raise RuntimeError(
                f"MAX30102 tại 0x{address:02X} trả PART_ID=0x{part_id:02X}"
            )

        bus.write_byte_data(address, 0x09, 0x40)  # Reset.
        time.sleep(0.1)
        for register in (0x04, 0x05, 0x06):
            bus.write_byte_data(address, register, 0)
        bus.write_byte_data(address, 0x08, 0x50)  # Trung bình 4, FIFO tự cuộn.
        bus.write_byte_data(address, 0x0A, 0x27)  # 100 Hz, LED pulse 411 us.
        bus.write_byte_data(address, 0x0C, 0x24)  # Dòng LED đỏ mức thử thấp.
        bus.write_byte_data(address, 0x0D, 0x24)  # Dòng LED hồng ngoại.
        bus.write_byte_data(address, 0x09, 0x03)  # Chế độ Red + IR.

    def read_samples(self) -> list[tuple[int, int]]:
        write_pointer = self.bus.read_byte_data(self.address, 0x04) & 0x1F
        read_pointer = self.bus.read_byte_data(self.address, 0x06) & 0x1F
        available = (write_pointer - read_pointer) & 0x1F
        samples = []

        # SMBus giới hạn một lần đọc tối đa 32 byte: 5 mẫu x 6 byte = 30.
        while available:
            count = min(available, 5)
            raw = self.bus.read_i2c_block_data(self.address, 0x07, count * 6)
            for i in range(0, len(raw), 6):
                red = ((raw[i] << 16) | (raw[i + 1] << 8) | raw[i + 2]) & 0x3FFFF
                ir = ((raw[i + 3] << 16) | (raw[i + 4] << 8) | raw[i + 5]) & 0x3FFFF
                samples.append((red, ir))
            available -= count
        return samples
