"""Local dashboard API backed by PostgreSQL; serves only data stored from registered real devices."""

from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, func, select, text
from sqlalchemy.orm import Session

from backend.api.mqtt_commands import CommandConflict, MqttCommandPublisher
from backend.common.config import DEVICE_IDS, FRESH_DATA_S, LOCAL_TIMEZONE
from backend.common.database import SessionLocal
from backend.common.models import Device, DeviceEvent, DeviceProfile, TelemetrySample, UserActivityLog


def get_db():
    with SessionLocal() as session:
        yield session


def load_profiles() -> list[tuple[str, dict, str]]:
    """Cấu hình hiện tại của MỌI thiết bị đăng ký, để publish lại (retained) khi kết nối broker.

    Thiết bị không còn hồ sơ nhận ``profile: null``; nhờ vậy lệnh xóa hồ sơ lúc broker
    mất kết nối vẫn tới được Pi. Pi bỏ cấu hình có ``updated_at`` cũ hơn bản đang dùng.
    """
    with SessionLocal() as db:
        return [config_document(device_id, db.get(DeviceProfile, device_id))
                for device_id in sorted(DEVICE_IDS)]


command_publisher = MqttCommandPublisher(allowed_devices=DEVICE_IDS, retained_configs=load_profiles)


@asynccontextmanager
async def lifespan(application: FastAPI):
    command_publisher.start()
    try:
        yield
    finally:
        command_publisher.stop()


app = FastAPI(title="Health Watch Local API", version="0.3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Local only. Restrict origins before cloud deployment.
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)

Db = Annotated[Session, Depends(get_db)]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def iso(value: datetime | None) -> str | None:
    value = as_utc(value)
    return value.isoformat().replace("+00:00", "Z") if value else None


def device_or_404(db: Session, device_id: str) -> Device:
    device = db.get(Device, device_id)
    if device is None or device_id not in DEVICE_IDS:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


def age_seconds(value: datetime | None) -> float | None:
    value = as_utc(value)
    return None if value is None else max(0.0, (utc_now() - value).total_seconds())


def device_view(device: Device, profile: DeviceProfile | None = None) -> dict:
    age = age_seconds(device.last_seen_at)
    return {
        "id": device.id,
        "name": device.name,
        "online": bool(device.online and age is not None and age < FRESH_DATA_S),
        "last_seen_at": iso(device.last_seen_at),
        "last_seen_age_s": None if age is None else round(age, 1),
        "firmware_version": device.firmware_version,
        "has_profile": profile is not None,
    }


def telemetry_view(row: TelemetrySample) -> dict:
    age = age_seconds(row.received_at)
    primary_source = "ai" if row.steps_ai_session is not None else "algorithm"
    return {
        "device_id": row.device_id,
        "boot_id": row.boot_id,
        "sequence": row.sequence,
        "schema_version": row.schema_version,
        "legacy": row.schema_version < 2,
        "measured_at": iso(row.measured_at),
        "received_at": iso(row.received_at),
        "age_s": round(age, 1),
        "fresh": age < FRESH_DATA_S,
        "clock_synced": row.clock_synced,
        "clock_skew_s": None if row.clock_skew_s is None else round(row.clock_skew_s, 1),
        "session_started_at": iso(row.session_started_at),
        "uptime_s": row.uptime_s,
        "firmware_version": row.firmware_version,
        "heart_rate_bpm": row.heart_rate_bpm,
        "finger_present": row.finger_present,
        "imu_status": row.imu_status,
        "step_algorithm": row.step_algorithm,
        "steps_algorithm_session": row.steps_session,
        "steps_ai_session": row.steps_ai_session,
        "step_model": ({"name": row.step_model_name, "version": row.step_model_version}
                       if row.step_model_name else None),
        "steps_primary_session": row.steps_ai_session if primary_source == "ai" else row.steps_session,
        "steps_primary_source": primary_source,
        "walking": row.walking,
        "walking_probability": row.walking_probability,
        "cadence_spm": row.cadence_spm,
        "distance_m_session": row.distance_m_session,
        "calories_kcal_session": row.calories_kcal_session,
        "step_length_m": row.step_length_m,
        "distance_method": row.distance_method,
    }


def event_view(row: DeviceEvent) -> dict:
    return {
        "event_id": row.event_id,
        "device_id": row.device_id,
        "event_type": row.event_type,
        "occurred_at": iso(row.occurred_at),
        "received_at": iso(row.received_at),
    }


def profile_view(row: DeviceProfile | None) -> dict | None:
    if row is None:
        return None
    return {
        "height_cm": row.height_cm,
        "weight_kg": row.weight_kg,
        "step_length_m": row.step_length_m,
        "updated_at": iso(row.updated_at),
    }


def config_document(device_id: str, row: DeviceProfile | None) -> tuple[str, dict, str]:
    updated_at = iso(row.updated_at) if row else iso(utc_now())
    return device_id, {
        "schema_version": 1,
        "device_id": device_id,
        "profile": None if row is None else {
            "height_cm": row.height_cm,
            "weight_kg": row.weight_kg,
            "step_length_m": row.step_length_m,
        },
        "updated_at": updated_at,
    }, updated_at


class ActivityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    action: Literal[
        "dashboard_view", "device_select", "history_view", "events_view",
        "remote_alert_start", "remote_alert_stop", "profile_update", "profile_clear",
    ]
    device_id: str | None = Field(default=None, max_length=64)


class RemoteAlertInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: bool
    duration_s: int = Field(default=10, ge=1, le=60)


class ProfileInput(BaseModel):
    """Giới hạn giống contracts/mqtt/config.v1.schema.json và health_watch/user_profile.py."""

    model_config = ConfigDict(extra="forbid")

    height_cm: float = Field(ge=100, le=230, allow_inf_nan=False)
    weight_kg: float = Field(ge=25, le=250, allow_inf_nan=False)
    step_length_m: float | None = Field(default=None, ge=0.25, le=1.3, allow_inf_nan=False)


@app.get("/health")
def health(db: Db):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "registered_devices": len(DEVICE_IDS)}


@app.get("/api/v1/devices")
def devices(db: Db):
    rows = db.scalars(select(Device).where(Device.id.in_(DEVICE_IDS))).all() if DEVICE_IDS else []
    profiles = {row.device_id: row for row in db.scalars(select(DeviceProfile)).all()}
    views = [device_view(row, profiles.get(row.id)) for row in rows]
    # Thiết bị đang gửi dữ liệu lên đầu, sau đó theo thời điểm thấy gần nhất.
    views.sort(key=lambda view: (not view["online"], view["last_seen_age_s"] is None,
                                 view["last_seen_age_s"] or 0, view["id"]))
    return views


@app.get("/api/v1/devices/{device_id}/latest")
def latest(device_id: str, db: Db):
    device = device_or_404(db, device_id)
    # Sắp theo giờ server nhận (đáng tin), không theo giờ thiết bị (Pi không có RTC).
    row = db.scalar(
        select(TelemetrySample)
        .where(TelemetrySample.device_id == device_id)
        .order_by(TelemetrySample.received_at.desc(), TelemetrySample.id.desc())
        .limit(1)
    )
    return {
        "device": device_view(device, db.get(DeviceProfile, device_id)),
        "telemetry": telemetry_view(row) if row else None,
        "remote_alert": command_publisher.state_view(device_id),
    }


@app.get("/api/v1/devices/{device_id}/history")
def history(device_id: str, db: Db, limit: int = Query(60, ge=1, le=500)):
    device_or_404(db, device_id)
    rows = db.scalars(
        select(TelemetrySample)
        .where(TelemetrySample.device_id == device_id)
        .order_by(TelemetrySample.received_at.desc(), TelemetrySample.id.desc())
        .limit(limit)
    ).all()
    return [telemetry_view(row) for row in reversed(rows)]


def day_totals(db: Session, device_id: str, start: datetime, end: datetime) -> dict:
    """Cộng phần tăng của bộ đếm trong từng phiên (boot_id) giữa hai mốc giờ server nhận.

    Bộ đếm phiên chỉ tăng (ingest đảm bảo), nên phần tăng trong ngày = giá trị lớn nhất
    trước ``end`` − giá trị lớn nhất trước ``start``. Phiên khởi động lại bắt đầu từ 0.
    Chỉ dùng telemetry v2 (bộ đếm v1 cũ sai nhiều, xem ml/README.md).
    """
    sample = TelemetrySample
    v2 = (sample.device_id == device_id) & (sample.schema_version >= 2)
    boots_in_day = select(sample.boot_id).where(v2, sample.received_at >= start, sample.received_at < end)
    before_start = sample.received_at < start

    def bounds(column):
        return (func.max(column).label(f"{column.key}_end"),
                func.max(case((before_start, column))).label(f"{column.key}_start"))

    columns = (sample.steps_session, sample.steps_ai_session, sample.distance_m_session,
               sample.calories_kcal_session)
    query = (select(sample.boot_id, *[part for column in columns for part in bounds(column)])
             .where(v2, sample.received_at < end, sample.boot_id.in_(boots_in_day))
             .group_by(sample.boot_id))
    totals = {"algorithm": 0, "ai": 0, "primary": 0, "distance_m": None, "calories_kcal": None}
    sources = set()
    sessions = 0
    for row in db.execute(query).mappings():
        sessions += 1
        delta = {}
        for column in columns:
            end_value = row[f"{column.key}_end"]
            start_value = row[f"{column.key}_start"] or 0
            delta[column.key] = None if end_value is None else max(0, end_value - start_value)
        totals["algorithm"] += delta["steps_session"]
        if delta["steps_ai_session"] is not None:
            totals["ai"] += delta["steps_ai_session"]
            totals["primary"] += delta["steps_ai_session"]
            sources.add("ai")
        else:
            totals["primary"] += delta["steps_session"]
            sources.add("algorithm")
        for key, column in (("distance_m", "distance_m_session"), ("calories_kcal", "calories_kcal_session")):
            if delta[column] is not None:
                totals[key] = (totals[key] or 0) + delta[column]
    source = None if not sources else (next(iter(sources)) if len(sources) == 1 else "mixed")
    return {
        "steps": totals["primary"],
        "source": source,
        "steps_ai": totals["ai"] if "ai" in sources else None,
        "steps_algorithm": totals["algorithm"],
        "distance_m": None if totals["distance_m"] is None else round(totals["distance_m"], 1),
        "calories_kcal": None if totals["calories_kcal"] is None else round(totals["calories_kcal"], 1),
        "sessions": sessions,
    }


@app.get("/api/v1/devices/{device_id}/steps/daily")
def daily_steps(device_id: str, db: Db, days: int = Query(7, ge=1, le=31)):
    device_or_404(db, device_id)
    zone = ZoneInfo(LOCAL_TIMEZONE)
    today = datetime.now(zone).date()
    result = []
    for offset in range(days - 1, -1, -1):
        day: date = today - timedelta(days=offset)
        start = datetime.combine(day, time.min, zone).astimezone(timezone.utc)
        end = datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
        result.append({"date": day.isoformat(), **day_totals(db, device_id, start, end)})
    return {"timezone": LOCAL_TIMEZONE, "days": result}


@app.get("/api/v1/devices/{device_id}/events")
def events(device_id: str, db: Db, limit: int = Query(20, ge=1, le=200)):
    device_or_404(db, device_id)
    rows = db.scalars(
        select(DeviceEvent)
        .where(DeviceEvent.device_id == device_id)
        .order_by(DeviceEvent.received_at.desc(), DeviceEvent.event_id.desc())
        .limit(limit)
    ).all()
    return [event_view(row) for row in rows]


@app.get("/api/v1/devices/{device_id}/profile")
def get_profile(device_id: str, db: Db):
    device_or_404(db, device_id)
    return {"profile": profile_view(db.get(DeviceProfile, device_id))}


def publish_profile(device_id: str, row: DeviceProfile | None) -> bool:
    _, document, _ = config_document(device_id, row)
    try:
        command_publisher.publish_config(device_id, document)
    except RuntimeError:
        return False  # Đã lưu DB; API publish lại khi kết nối broker.
    return True


@app.put("/api/v1/devices/{device_id}/profile")
def put_profile(device_id: str, payload: ProfileInput, db: Db):
    device_or_404(db, device_id)
    row = db.get(DeviceProfile, device_id) or DeviceProfile(device_id=device_id)
    row.height_cm = payload.height_cm
    row.weight_kg = payload.weight_kg
    row.step_length_m = payload.step_length_m
    row.updated_at = utc_now()
    db.add(row)
    db.commit()
    return {"profile": profile_view(row), "delivered_to_broker": publish_profile(device_id, row)}


@app.delete("/api/v1/devices/{device_id}/profile")
def delete_profile(device_id: str, db: Db):
    device_or_404(db, device_id)
    row = db.get(DeviceProfile, device_id)
    if row is not None:
        db.delete(row)
        db.commit()
    return {"profile": None, "delivered_to_broker": publish_profile(device_id, None)}


@app.post("/api/v1/devices/{device_id}/commands/remote-alert", status_code=202)
def remote_alert(device_id: str, payload: RemoteAlertInput, db: Db):
    device = device_or_404(db, device_id)
    if not device_view(device)["online"]:
        raise HTTPException(status_code=409, detail="Thiết bị đang offline hoặc dữ liệu đã cũ")

    command_id = str(uuid4())
    issued_at = iso(utc_now())
    document = {
        "schema_version": 1,
        "command_id": command_id,
        "device_id": device_id,
        "command_type": "remote_alert",
        "active": payload.active,
        "duration_s": payload.duration_s,
        "issued_at": issued_at,
    }
    try:
        state = command_publisher.publish(device_id, document)
    except CommandConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Không gửi được lệnh qua MQTT") from exc
    return {
        "accepted": True,
        "command_id": command_id,
        "device_id": device_id,
        "active": payload.active,
        "duration_s": payload.duration_s,
        "issued_at": issued_at,
        "state": state,
    }


@app.post("/api/v1/activity", status_code=202)
def record_activity(payload: ActivityInput, db: Db):
    db.add(
        UserActivityLog(
            session_id=str(payload.session_id),
            action=payload.action,
            device_id=payload.device_id,
            occurred_at=utc_now(),
            details={},
        )
    )
    db.commit()
    return {"accepted": True}
