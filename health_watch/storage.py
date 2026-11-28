"""Lưu trạng thái nhỏ trên thẻ nhớ Pi: hồ sơ người đeo và số bước trong ngày.

Ghi kiểu atomic (file tạm + fsync + os.replace) để mất điện giữa chừng không
làm hỏng file. Thư mục ``state/`` không bị script triển khai ghi đè.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from clock import clock_synced
from user_profile import UserProfile


log = logging.getLogger("health_watch.storage")
STATE_DIR = Path(__file__).resolve().parent / "state"


def write_json_atomic(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Bỏ qua file trạng thái hỏng %s: %s", path, exc)
        return None


def parse_utc(text: str | None) -> datetime | None:
    if not isinstance(text, str):
        return None
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value.astimezone(timezone.utc) if value.tzinfo else None


class ProfileStore:
    """Hồ sơ đang dùng và thời điểm (``updated_at`` của backend) của cấu hình đã áp dụng."""

    def __init__(self, path: Path = STATE_DIR / "profile.json"):
        self.path = path
        self.updated_at = None

    def load(self) -> UserProfile | None:
        document = read_json(self.path)
        if not document:
            return None
        self.updated_at = document.get("updated_at") if parse_utc(document.get("updated_at")) else None
        if document.get("profile") is None:
            return None
        try:
            return UserProfile.from_dict(document["profile"])
        except ValueError as exc:
            log.warning("Hồ sơ đã lưu không hợp lệ: %s", exc)
            return None

    def is_newer(self, updated_at: str) -> bool:
        """Bỏ cấu hình cũ hơn bản đã áp dụng (retained cũ đến sau bản mới)."""
        incoming = parse_utc(updated_at)
        current = parse_utc(self.updated_at)
        return incoming is not None and (current is None or incoming >= current)

    def save(self, profile: UserProfile | None, updated_at: str | None = None) -> None:
        write_json_atomic(self.path, {
            "profile": profile.to_dict() if profile else None,
            "updated_at": updated_at,
        })
        self.updated_at = updated_at


class DailyStepStore:
    """Số bước, quãng đường và kcal từ 0 giờ theo giờ địa phương; giữ qua các lần khởi động lại.

    Pi không có RTC: lúc khởi động, giờ hệ thống có thể là giờ tắt máy hôm trước cho tới
    khi NTP đồng bộ. Khi đó ``date`` là ``None`` và chỉ đếm "từ khi bật máy"; ngay khi
    đồng hồ đồng bộ, phần đã đếm được cộng vào đúng ngày hôm nay.
    """

    INT_COUNTERS = ("algorithm", "algorithm_running", "ai", "ai_running")
    FLOAT_COUNTERS = ("distance_m", "kcal")

    def __init__(self, path: Path = STATE_DIR / "daily_steps.json", clock=time.localtime, synced=clock_synced):
        self.path = path
        self.clock = clock
        self.synced = synced
        self.date = None
        self.counts = self._empty()
        self._dirty = False
        self._resolve_date()

    @classmethod
    def _empty(cls) -> dict:
        return {**dict.fromkeys(cls.INT_COUNTERS, 0), **dict.fromkeys(cls.FLOAT_COUNTERS, 0.0)}

    @property
    def date_known(self) -> bool:
        return self.date is not None

    def _today(self) -> str:
        return time.strftime("%Y-%m-%d", self.clock())

    def _resolve_date(self) -> None:
        if self.date is not None or not self.synced():
            return
        today = self._today()
        document = read_json(self.path)
        if document and document.get("date") == today:
            stored = document.get("counts", {})
            for key in self.INT_COUNTERS:
                value = stored.get(key)
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    self.counts[key] += value
            for key in self.FLOAT_COUNTERS:
                value = stored.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
                    self.counts[key] += float(value)
        self.date = today
        self._dirty = True

    def add(self, **deltas) -> None:
        self._resolve_date()
        if self.date is not None:
            today = self._today()
            if today != self.date:
                self.save_quietly()
                self.date = today
                self.counts = self._empty()
        for key, delta in deltas.items():
            if delta:
                self.counts[key] += delta
                self._dirty = True

    def save(self) -> None:
        if not self._dirty or self.date is None:
            return
        write_json_atomic(self.path, {"date": self.date, "counts": self.counts})
        self._dirty = False

    def save_quietly(self) -> None:
        """Lỗi thẻ nhớ (đầy, chỉ đọc) không được làm dừng vòng đo; số vẫn giữ trong RAM."""
        try:
            self.save()
        except OSError as exc:
            log.warning("Không lưu được %s: %s", self.path, exc)
