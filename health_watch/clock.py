"""Trạng thái đồng hồ hệ thống của Pi (không có RTC, dựa vào NTP)."""

import os

SYNC_FLAG = "/run/systemd/timesync/synchronized"


def clock_synced() -> bool:
    """systemd-timesyncd tạo file này khi đồng hồ đã đồng bộ NTP từ lúc khởi động."""
    return os.path.exists(SYNC_FLAG)
