"""Driver MAX30102: cấu hình, đọc RED/IR và giám sát FIFO.
Dùng cho nguyên mẫu nghiên cứu; không dùng để chẩn đoán y tế.
"""

import time
from dataclasses import dataclass, field


@dataclass
class FIFOPoll:
    """Kết quả của một lần đọc FIFO, dùng để ghi CSV trong main.py."""

    started: float                         # Thời điểm bắt đầu (s)
    finished: float = 0.0                  # Thời điểm kết thúc (s)
    pending: int | None = None             # Số mẫu chờ trước khi đọc
    overflow: int | None = None            # Bộ đếm mất mẫu
    samples: list[tuple[int, int]] = field(default_factory=list)
    status: str = "OK"
    detail: str = ""


class MAX30102:
    # ================================================================
    # 1. THÔNG SỐ THÍ NGHIỆM — chỉ sửa ở đây, sau đó khởi động lại
    # ================================================================
    SAMPLE_RATE = 200    # Hz: 50, 100, 200 hoặc 400 (RED + IR, 411 µs)
    SAMPLE_AVERAGING = 2    # Số mẫu gộp: 1, 2, 4, 8, 16, 32

    FIFO_RATE = SAMPLE_RATE / SAMPLE_AVERAGING   # Cặp RED/IR mỗi giây
    SAMPLES_PER_SECOND = int(FIFO_RATE)          # Tương thích main.py/PulseMonitor

    # PulseMonitor hiện yêu cầu tần số là số nguyên. Driver kiểm tra điều này
    # trước khi cấu hình phần cứng, tránh làm tròn sai trục thời gian CSV.
    FIFO_DEPTH = 32          # Tối đa 32 cặp RED/IR
    ADC_MASK = 0x3FFFF       # Giữ 18 bit dữ liệu ADC
    LED_RED_AMPLITUDE = 0x24 # Giữ nguyên cấu hình LED trước đó
    LED_IR_AMPLITUDE = 0x24

    # ================================================================
    # 2. ĐỊA CHỈ THANH GHI VÀ BẢNG MÃ BIT (theo datasheet MAX30102)
    # ================================================================
    REG_INTERRUPT_STATUS = 0x00
    REG_INTERRUPT_ENABLE = 0x02
    REG_FIFO_WR_PTR = 0x04
    REG_FIFO_OVF_COUNTER = 0x05
    REG_FIFO_RD_PTR = 0x06
    REG_FIFO_DATA = 0x07
    REG_FIFO_CONFIG = 0x08
    REG_MODE_CONFIG = 0x09
    REG_SPO2_CONFIG = 0x0A
    REG_LED_RED = 0x0C
    REG_LED_IR = 0x0D
    REG_PART_ID = 0xFF

    A_FULL_FLAG = 0x80       # Bit 7: cờ FIFO đầy với ngưỡng A_FULL = 0
    POINTER_MASK = 0x1F     # Con trỏ FIFO và bộ đếm tràn đều có 5 bit
    BYTES_PER_SAMPLE = 6    # 3 byte RED + 3 byte IR
    MAX_SAMPLES_PER_READ = 5 # SMBus tối đa 32 byte; đọc 5 x 6 = 30 byte

    # Giới hạn theo Table 11: chế độ SpO2 (RED + IR), xung 411 µs.
    SAMPLE_RATE_BITS = {50: 0b000, 100: 0b001, 200: 0b010, 400: 0b011}
    AVERAGING_BITS = {1: 0b000, 2: 0b001, 4: 0b010,
                      8: 0b011, 16: 0b100, 32: 0b101}

    def __init__(self, bus, address: int = 0x57, sample_rate: int | None = None,
                 sample_averaging: int | None = None):
        self.bus = bus
        self.address = address
        # Tùy chọn: hệ thống đầy đủ (main.py, có TFT chặn vòng lặp ~0,2–0,4 s) dùng tần số FIFO
        # thấp hơn để FIFO 32 mẫu không tràn; mặc định giữ thông số thí nghiệm ở trên.
        if sample_rate is not None:
            self.SAMPLE_RATE = sample_rate
        if sample_averaging is not None:
            self.SAMPLE_AVERAGING = sample_averaging
        self.FIFO_RATE = self.SAMPLE_RATE / self.SAMPLE_AVERAGING
        self.SAMPLES_PER_SECOND = int(self.FIFO_RATE)
        self._validate_config()
        self._configure_sensor()

    def _validate_config(self):
        """Kiểm tra tổ hợp cấu hình trước khi ghi thanh ghi."""
        if self.SAMPLE_RATE not in self.SAMPLE_RATE_BITS:
            raise ValueError("SAMPLE_RATE phải là 50, 100, 200 hoặc 400 Hz khi dùng xung 411 µs.")
        if self.SAMPLE_AVERAGING not in self.AVERAGING_BITS:
            raise ValueError("SAMPLE_AVERAGING phải là 1, 2, 4, 8, 16 hoặc 32.")
        if self.SAMPLE_RATE % self.SAMPLE_AVERAGING != 0:
            raise ValueError("FIFO_RATE phải là số nguyên để tương thích PulseMonitor hiện tại.")

    def _read_register(self, register):
        return self.bus.read_byte_data(self.address, register)

    def _write_register(self, register, value):
        self.bus.write_byte_data(self.address, register, value)

    # ================================================================
    # 3. KHỞI TẠO VÀ CẤU HÌNH CẢM BIẾN
    # ================================================================
    def _configure_sensor(self):
        part_id = self._read_register(self.REG_PART_ID)
        if part_id != 0x15:
            raise RuntimeError(
                f"MAX30102 tại 0x{self.address:02X} trả PART_ID=0x{part_id:02X}"
            )

        # Reset cảm biến và đưa các con trỏ FIFO về 0.
        self._write_register(self.REG_MODE_CONFIG, 0x40)
        time.sleep(0.1)
        for register in (self.REG_FIFO_WR_PTR, self.REG_FIFO_OVF_COUNTER,
                         self.REG_FIFO_RD_PTR):
            self._write_register(register, 0)

        # FIFO_CONFIG (0x08):
        # bit 7:5 = số mẫu trung bình; bit 4 = rollover (0: tắt).
        # bit 3:0 = A_FULL (0: cảnh báo khi đủ 32 mẫu chưa đọc).
        averaging_bits = self.AVERAGING_BITS[self.SAMPLE_AVERAGING]
        fifo_config = averaging_bits << 5
        self._write_register(self.REG_FIFO_CONFIG, fifo_config)
        self._write_register(self.REG_INTERRUPT_ENABLE, self.A_FULL_FLAG)

        # SPO2_CONFIG (0x0A):
        # bit 6:5 = ADC range 4096 nA (01)
        # bit 4:2 = mã SAMPLE_RATE
        # bit 1:0 = độ rộng xung 411 µs, ADC 18 bit (11)
        adc_range_bits = 0b01
        sample_rate_bits = self.SAMPLE_RATE_BITS[self.SAMPLE_RATE]
        pulse_width_bits = 0b11
        spo2_config = (adc_range_bits << 5) | (sample_rate_bits << 2) | pulse_width_bits
        self._write_register(self.REG_SPO2_CONFIG, spo2_config)

        self._write_register(self.REG_LED_RED, self.LED_RED_AMPLITUDE)
        self._write_register(self.REG_LED_IR, self.LED_IR_AMPLITUDE)
        self._read_register(self.REG_INTERRUPT_STATUS)  # Xóa cờ cũ
        self._write_register(self.REG_MODE_CONFIG, 0x03) # Bắt đầu RED + IR

    # ================================================================
    # 4. KIỂM TRA FIFO TRƯỚC KHI ĐỌC DỮ LIỆU
    # ================================================================
    def _check_fifo(self, poll):
        """Ghi nhận con trỏ, bộ đếm mất mẫu và cờ đầy vào poll."""
        status = self._read_register(self.REG_INTERRUPT_STATUS)

        # Đọc WR_PTR, OVF_COUNTER và RD_PTR trong một giao dịch I2C.
        registers = self.bus.read_i2c_block_data(self.address, self.REG_FIFO_WR_PTR, 3)
        if len(registers) != 3:
            raise OSError("Không đọc đủ 3 byte thanh ghi FIFO")

        write_pointer, overflow, read_pointer = (v & self.POINTER_MASK for v in registers)
        poll.pending = (write_pointer - read_pointer) % self.FIFO_DEPTH
        poll.overflow = overflow

        # Cảm biến vẫn tạo mẫu trong lúc Pi kiểm tra con trỏ.
        # Kiểm tra lại trước khi đọc FIFO_DATA (pop sẽ reset OVF_COUNTER).
        status |= self._read_register(self.REG_INTERRUPT_STATUS)
        overflow = self._read_register(self.REG_FIFO_OVF_COUNTER) & self.POINTER_MASK
        poll.overflow = max(poll.overflow, overflow)

        if poll.overflow or status & self.A_FULL_FLAG:
            # Rollover tắt, chưa đọc mẫu nào trong lần polling này.
            poll.pending = self.FIFO_DEPTH
            poll.status = "Tràn FIFO" if poll.overflow else "FIFO đầy"
            poll.detail = "Dừng phiên trước khi đọc để tránh mất tính liên tục của dữ liệu."

    # ================================================================
    # 5. ĐỌC VÀ GIẢI MÃ CÁC CẶP RED/IR
    # ================================================================
    def _decode_adc(self, byte1, byte2, byte3):
        """Ghép 3 byte thành một giá trị ADC 18 bit."""
        return ((byte1 << 16) | (byte2 << 8) | byte3) & self.ADC_MASK

    def _read_fifo_samples(self, poll):
        """Đọc số mẫu đang chờ tại thời điểm kiểm tra con trỏ."""
        remaining = poll.pending
        while remaining > 0:
            count = min(remaining, self.MAX_SAMPLES_PER_READ)
            byte_count = count * self.BYTES_PER_SAMPLE
            raw = self.bus.read_i2c_block_data(self.address, self.REG_FIFO_DATA, byte_count)
            if len(raw) != byte_count:
                raise OSError("Không đọc đủ byte dữ liệu FIFO")

            for i in range(0, byte_count, self.BYTES_PER_SAMPLE):
                red = self._decode_adc(raw[i], raw[i + 1], raw[i + 2])
                ir = self._decode_adc(raw[i + 3], raw[i + 4], raw[i + 5])
                poll.samples.append((red, ir))
            remaining -= count

    # ================================================================
    # 6. HÀM CHÍNH ĐƯỢC MAIN.PY GỌI MỖI LẦN POLLING
    # ================================================================
    def read_poll(self) -> FIFOPoll:
        poll = FIFOPoll(started=time.monotonic())
        try:
            self._check_fifo(poll)
            if poll.status != "OK":
                return poll

            self._read_fifo_samples(poll)

            # Kiểm tra thêm sau khi đọc. Không bảo đảm phát hiện mọi mất mẫu
            # vì OVF_COUNTER có thể đã bị reset khi lấy mẫu khỏi FIFO.
            status = self._read_register(self.REG_INTERRUPT_STATUS)
            overflow = self._read_register(self.REG_FIFO_OVF_COUNTER) & self.POINTER_MASK
            poll.overflow = max(poll.overflow, overflow)

            if poll.overflow or status & self.A_FULL_FLAG:
                poll.status = "Tràn FIFO" if poll.overflow else "FIFO đầy"
                poll.detail = "Phát hiện cờ trong/sau lần đọc; không dùng lô mẫu này."
            elif not poll.samples:
                poll.status = "Không có mẫu mới"

        except OSError as exc:
            # Không tự retry FIFO_DATA: con trỏ có thể đã tiến lên.
            poll.status = "Lỗi I2C"
            poll.detail = str(exc)
        finally:
            poll.finished = time.monotonic()
        return poll

    def read_samples(self) -> list[tuple[int, int]]:
        """Giữ tương thích với code cũ chỉ cần danh sách cặp RED/IR."""
        poll = self.read_poll()
        if poll.status not in ("OK", "Không có mẫu mới"):
            raise RuntimeError(f"{poll.status}: {poll.detail}")
        return poll.samples
