"""Tạo DB SQLite riêng cho từng test và payload bằng chính DeviceMessageFactory của Pi."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.common.models import Base
from telemetry import DeviceMessageFactory

BOOT_A = "11111111-1111-4111-8111-111111111111"
BOOT_B = "22222222-2222-4222-8222-222222222222"


def session_factory():
    engine = create_engine("sqlite+pysqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def telemetry(factory: DeviceMessageFactory, *, steps, ai=None, uptime=10.0, distance=None, **overrides):
    values = dict(
        heart_rate_bpm=None, finger_present=False, imu_status="ok",
        steps_algorithm_session=steps, steps_ai_session=ai,
        step_model={"name": "walk-gate-rf", "version": "1.0.0"} if ai is not None else None,
        walking=None, walking_probability=None, cadence_spm=None,
        distance_m_session=distance, calories_kcal_session=None if distance is None else distance * 0.03,
        distance_basis={"step_length_m": 0.7, "method": "measured"} if distance is not None else None,
        session_started_at="2026-11-28T00:00:00.000Z", uptime_s=uptime, clock_synced=True,
    )
    values.update(overrides)
    return factory.telemetry(**values)
