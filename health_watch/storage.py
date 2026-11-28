"""Lưu trạng thái nhỏ trên thẻ nhớ Pi: hồ sơ người đeo và số bước trong ngày.

Ghi kiểu atomic (file tạm + fsync + os.replace) để mất điện giữa chừng không
làm hỏng file. Thư mục ``state/`` không bị script triển khai ghi đè.
"""

import json
import logging
import os
import time
from pathlib import Path

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


class ProfileStore:
    def __init__(self, path: Path = STATE_DIR / "profile.json"):
        self.path = path

    def load(self) -> UserProfile | None:
        document = read_json(self.path)
        if not document or document.get("profile") is None:
            return None
        try:
            return UserProfile.from_dict(document["profile"])
        except ValueError as exc:
            log.warning("Hồ sơ đã lưu không hợp lệ: %s", exc)
            return None

    def save(self, profile: UserProfile | None) -> None:
        write_json_atomic(self.path, {"profile": profile.to_dict() if profile else None})


class DailyStepStore:
    """Số bước từ 0 giờ theo giờ địa phương của Pi; giữ qua các lần khởi động lại."""

    COUNTERS = ("algorithm", "algorithm_running", "ai", "ai_running")

    def __init__(self, path: Path = STATE_DIR / "daily_steps.json", clock=time.localtime):
        self.path = path
        self.clock = clock
        self.date = self._today()
        self.counts = dict.fromkeys(self.COUNTERS, 0)
        document = read_json(self.path)
        if document and document.get("date") == self.date:
            for key in self.COUNTERS:
                value = document.get("counts", {}).get(key, 0)
                if isinstance(value, int) and value >= 0:
                    self.counts[key] = value
        self._dirty = False

    def _today(self) -> str:
        return time.strftime("%Y-%m-%d", self.clock())

    def add(self, **deltas: int) -> None:
        today = self._today()
        if today != self.date:
            self.save()
            self.date = today
            self.counts = dict.fromkeys(self.COUNTERS, 0)
        for key, delta in deltas.items():
            if delta:
                self.counts[key] += delta
                self._dirty = True

    def save(self) -> None:
        if not self._dirty:
            return
        write_json_atomic(self.path, {"date": self.date, "counts": self.counts})
        self._dirty = False
