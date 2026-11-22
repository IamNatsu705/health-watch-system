"""Local dashboard API backed by PostgreSQL."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.common.database import SessionLocal
from backend.common.models import Device, DeviceEvent, TelemetrySample, UserActivityLog
from backend.api.mqtt_commands import CommandConflict, MqttCommandPublisher


command_publisher = MqttCommandPublisher()


@asynccontextmanager
async def lifespan(application: FastAPI):
    command_publisher.start()
    try:
        yield
    finally:
        command_publisher.stop()


app = FastAPI(title="Health Watch Local API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Local demo only. Restrict origins before cloud deployment.
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def get_db():
    with SessionLocal() as session:
        yield session


Db = Annotated[Session, Depends(get_db)]


def device_or_404(db: Session, device_id: str) -> Device:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


def device_view(device: Device) -> dict:
    recent = device.last_seen_at is not None and (
        datetime.now(timezone.utc) - device.last_seen_at
    ).total_seconds() < 10
    return {
        "id": device.id,
        "name": device.name,
        "online": bool(device.online and recent),
        "last_seen_at": device.last_seen_at,
    }


def telemetry_view(row: TelemetrySample) -> dict:
    return {
        "device_id": row.device_id,
        "boot_id": row.boot_id,
        "sequence": row.sequence,
        "measured_at": row.measured_at,
        "received_at": row.received_at,
        "heart_rate_bpm": row.heart_rate_bpm,
        "finger_present": row.finger_present,
        "steps_session": row.steps_session,
        "distance_m_session": row.distance_m_session,
        "calories_kcal_session": row.calories_kcal_session,
    }


def event_view(row: DeviceEvent) -> dict:
    return {
        "event_id": row.event_id,
        "device_id": row.device_id,
        "event_type": row.event_type,
        "occurred_at": row.occurred_at,
        "received_at": row.received_at,
    }


class ActivityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    action: Literal[
        "dashboard_view", "device_select", "history_view", "events_view",
        "remote_alert_start", "remote_alert_stop",
    ]
    device_id: str | None = Field(default=None, max_length=64)


class RemoteAlertInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: bool
    duration_s: int = Field(default=10, ge=1, le=60)


@app.get("/health")
def health(db: Db):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/api/v1/devices")
def devices(db: Db):
    rows = db.scalars(select(Device).order_by(Device.id)).all()
    return [device_view(row) for row in rows]


@app.get("/api/v1/devices/{device_id}/latest")
def latest(device_id: str, db: Db):
    device = device_or_404(db, device_id)
    row = db.scalar(
        select(TelemetrySample)
        .where(TelemetrySample.device_id == device_id)
        .order_by(TelemetrySample.measured_at.desc(), TelemetrySample.id.desc())
        .limit(1)
    )
    return {
        "device": device_view(device),
        "telemetry": telemetry_view(row) if row else None,
        "remote_alert": command_publisher.state_view(device_id),
    }


@app.get("/api/v1/devices/{device_id}/history")
def history(device_id: str, db: Db, limit: int = Query(60, ge=1, le=500)):
    device_or_404(db, device_id)
    rows = db.scalars(
        select(TelemetrySample)
        .where(TelemetrySample.device_id == device_id)
        .order_by(TelemetrySample.measured_at.desc(), TelemetrySample.id.desc())
        .limit(limit)
    ).all()
    return [telemetry_view(row) for row in reversed(rows)]


@app.get("/api/v1/devices/{device_id}/events")
def events(device_id: str, db: Db, limit: int = Query(20, ge=1, le=200)):
    device_or_404(db, device_id)
    rows = db.scalars(
        select(DeviceEvent)
        .where(DeviceEvent.device_id == device_id)
        .order_by(DeviceEvent.occurred_at.desc(), DeviceEvent.event_id.desc())
        .limit(limit)
    ).all()
    return [event_view(row) for row in rows]


@app.post("/api/v1/devices/{device_id}/commands/remote-alert", status_code=202)
def remote_alert(device_id: str, payload: RemoteAlertInput, db: Db):
    device = device_or_404(db, device_id)
    if not device_view(device)["online"]:
        raise HTTPException(status_code=409, detail="Thiết bị đang offline hoặc dữ liệu đã cũ")

    command_id = str(uuid4())
    issued_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
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
            occurred_at=datetime.now(timezone.utc),
            details={},
        )
    )
    db.commit()
    return {"accepted": True}
