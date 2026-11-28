"""The local database schema shared by ingest and API."""

from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    online: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    firmware_version: Mapped[str | None] = mapped_column(String(64))
    current_boot_id: Mapped[str | None] = mapped_column(String(36))
    last_status_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TelemetrySample(Base):
    """Một bản telemetry thật từ Pi.

    ``schema_version`` 1 là dữ liệu cũ (thuật toán ``peak-v1``, quãng đường/kcal từng
    là hằng số mẫu nên đã bị đặt NULL khi nâng cấp). ``steps_session`` là bộ đếm
    của thuật toán xử lý tín hiệu; ``steps_ai_session`` là bộ đếm có AI (NULL nếu
    Pi không nạp được mô hình).
    """

    __tablename__ = "telemetry_samples"
    __table_args__ = (
        UniqueConstraint("device_id", "boot_id", "sequence", name="uq_telemetry_identity"),
        Index("ix_telemetry_device_received", "device_id", "received_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    boot_id: Mapped[str] = mapped_column(String(36))
    sequence: Mapped[int] = mapped_column(Integer)
    schema_version: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    clock_synced: Mapped[bool | None] = mapped_column(Boolean)
    clock_skew_s: Mapped[float | None] = mapped_column(Float)
    session_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uptime_s: Mapped[float | None] = mapped_column(Float)
    firmware_version: Mapped[str | None] = mapped_column(String(64))
    heart_rate_bpm: Mapped[int | None] = mapped_column(Integer)
    finger_present: Mapped[bool] = mapped_column(Boolean)
    imu_status: Mapped[str | None] = mapped_column(String(16))
    step_algorithm: Mapped[str | None] = mapped_column(String(32))
    steps_session: Mapped[int] = mapped_column(Integer)
    steps_ai_session: Mapped[int | None] = mapped_column(Integer)
    step_model_name: Mapped[str | None] = mapped_column(String(64))
    step_model_version: Mapped[str | None] = mapped_column(String(32))
    walking: Mapped[bool | None] = mapped_column(Boolean)
    walking_probability: Mapped[float | None] = mapped_column(Float)
    cadence_spm: Mapped[float | None] = mapped_column(Float)
    distance_m_session: Mapped[float | None] = mapped_column(Float)
    calories_kcal_session: Mapped[float | None] = mapped_column(Float)
    step_length_m: Mapped[float | None] = mapped_column(Float)
    distance_method: Mapped[str | None] = mapped_column(String(16))


class DeviceEvent(Base):
    __tablename__ = "device_events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    boot_id: Mapped[str] = mapped_column(String(36))
    sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(40))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DeviceProfile(Base):
    """Chiều cao/cân nặng do người dùng nhập; dùng để Pi ước tính quãng đường và kcal."""

    __tablename__ = "device_profiles"

    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), primary_key=True)
    height_cm: Mapped[float] = mapped_column(Float)
    weight_kg: Mapped[float] = mapped_column(Float)
    step_length_m: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UserActivityLog(Base):
    __tablename__ = "user_activity_logs"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(40))
    device_id: Mapped[str | None] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
