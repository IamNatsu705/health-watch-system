"""Môi trường test backend: SQLite trong bộ nhớ, hai thiết bị đăng ký, không cần broker thật."""

import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["MQTT_DEVICES"] = "pi-watch-001:test-secret,pi-watch-002:test-secret-2"
os.environ["MQTT_PASSWORD"] = "test"
os.environ["LOCAL_TIMEZONE"] = "Asia/Ho_Chi_Minh"

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
# Dùng chính mã tạo payload của Pi để kiểm tra hợp đồng giữa hai phía.
sys.path.insert(1, str(REPO / "health_watch"))
