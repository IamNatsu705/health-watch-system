"""Ghi dữ liệu PPG thô (RED/IR) và nhật ký FIFO của MAX30102 ra CSV để nghiên cứu nhịp tim.

Định dạng giữ nguyên như bản thu dữ liệu nhóm đã chạy trên Pi (logs/ppg_*.csv và
logs/fifo_*.csv, UTF-8 có BOM, tên file theo giờ Việt Nam). ``time_s`` = sample_id / tần số
FIFO nên chỉ đúng khi không mất mẫu: khi FIFO tràn hoặc lỗi I2C, phiên CSV phải dừng
(bản thu riêng ``record_ppg.py``) hoặc mở phiên CSV mới (``main.py``).
"""

import csv
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

VIETNAM_TZ = timezone(timedelta(hours=7))
OK_STATUSES = ("OK", "Không có mẫu mới")
FIFO_FIELDS = [
    "Lần đọc FIFO", "Số mẫu chờ trước khi đọc", "Bộ đếm mất mẫu FIFO",
    "Số mẫu đọc thành công", "Khoảng cách hai lần đọc (ms)",
    "Khoảng cách đọc lớn nhất (ms)", "Trạng thái FIFO", "Chi tiết",
]
LOG_DIR = Path(__file__).resolve().parent / "logs"


class PpgCsvLogger:
    def __init__(self, sample_rate: int, log_dir: Path = LOG_DIR, clock=time.monotonic):
        log_dir.mkdir(parents=True, exist_ok=True)
        session = datetime.now(VIETNAM_TZ).strftime("%Y-%m-%d_%H-%M-%S_%f_UTC+07")
        self.sample_rate = sample_rate
        self.csv_path = log_dir / f"ppg_{session}.csv"
        self.fifo_path = log_dir / f"fifo_{session}.csv"
        self._csv_file = self.csv_path.open("x", newline="", encoding="utf-8-sig")
        try:
            self._fifo_file = self.fifo_path.open("x", newline="", encoding="utf-8-sig")
        except OSError:
            self._csv_file.close()
            raise
        self._writer = csv.writer(self._csv_file)
        self._fifo_writer = csv.writer(self._fifo_file)
        self._writer.writerow(["sample_id", "time_s", "read_time_s", "red", "ir"] + FIFO_FIELDS)
        self._fifo_writer.writerow(["Thời điểm bắt đầu đọc (s)", "Thời điểm đọc xong (s)"] + FIFO_FIELDS)
        self._csv_file.flush()
        self._fifo_file.flush()
        self.log_start = clock()
        self.sample_id = 0
        self.poll_id = 0
        self._previous_poll = None
        self._max_interval_ms = None

    def write(self, poll) -> None:
        """Mỗi lần polling một dòng FIFO (kể cả 0 mẫu hoặc lỗi); mẫu chỉ ghi khi lô hợp lệ."""
        interval_ms = None
        if self._previous_poll is not None:
            interval_ms = (poll.started - self._previous_poll) * 1000
            self._max_interval_ms = max(self._max_interval_ms or 0, interval_ms)
        self._previous_poll = poll.started
        read_time_s = poll.finished - self.log_start
        diag = [
            self.poll_id, poll.pending, poll.overflow, len(poll.samples),
            "" if interval_ms is None else f"{interval_ms:.3f}",
            "" if self._max_interval_ms is None else f"{self._max_interval_ms:.3f}",
            poll.status, poll.detail,
        ]
        self._fifo_writer.writerow([f"{poll.started - self.log_start:.6f}", f"{read_time_s:.6f}"] + diag)
        self._fifo_file.flush()
        self.poll_id += 1
        if poll.status not in OK_STATUSES:
            return  # Không ghi lô lỗi vào PPG; không dựng tiếp time_s qua khoảng mất mẫu.
        for red, ir in poll.samples:
            time_s = self.sample_id / self.sample_rate
            self._writer.writerow([self.sample_id, f"{time_s:.6f}", f"{read_time_s:.6f}", red, ir] + diag)
            self.sample_id += 1
        if poll.samples:
            self._csv_file.flush()

    def close(self) -> None:
        for handle in (self._csv_file, self._fifo_file):
            try:
                handle.close()
            except OSError:
                pass
