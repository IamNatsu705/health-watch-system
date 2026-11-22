"""Initial local schema.

Revision ID: 0001_initial
Revises:
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "devices",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("online", sa.Boolean(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "telemetry_samples",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.String(64), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("boot_id", sa.String(36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heart_rate_bpm", sa.Integer()),
        sa.Column("finger_present", sa.Boolean(), nullable=False),
        sa.Column("steps_session", sa.Integer(), nullable=False),
        sa.Column("distance_m_session", sa.Float(), nullable=False),
        sa.Column("calories_kcal_session", sa.Float(), nullable=False),
        sa.UniqueConstraint("device_id", "boot_id", "sequence", name="uq_telemetry_identity"),
    )
    op.create_index("ix_telemetry_samples_device_id", "telemetry_samples", ["device_id"])
    op.create_index("ix_telemetry_samples_measured_at", "telemetry_samples", ["measured_at"])
    op.create_table(
        "device_events",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.String(64), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("boot_id", sa.String(36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_device_events_device_id", "device_events", ["device_id"])
    op.create_index("ix_device_events_occurred_at", "device_events", ["occurred_at"])
    op.create_table(
        "user_activity_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("device_id", sa.String(64)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
    )
    op.create_index("ix_user_activity_logs_session_id", "user_activity_logs", ["session_id"])


def downgrade():
    op.drop_table("user_activity_logs")
    op.drop_table("device_events")
    op.drop_table("telemetry_samples")
    op.drop_table("devices")
