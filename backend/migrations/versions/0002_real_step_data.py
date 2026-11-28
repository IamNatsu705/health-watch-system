"""Telemetry v2 (step AI, provenance), profiles, and removal of non-real data.

* Thêm cột nguồn gốc dữ liệu (firmware, thuật toán, mô hình AI, trạng thái IMU, đồng hồ).
* Dữ liệu cũ (v1) đánh dấu ``schema_version=1``, ``step_algorithm='peak-v1'``.
* Quãng đường/kcal v1 là hằng số mẫu (0,70 m/bước, 70 kg, 0,75 kcal/kg/km), không phải
  đo đạc thật → đặt NULL.
* Xóa dữ liệu của thiết bị giả lập: mock publisher (``pi-watch-mock-*``) và smoke test
  (``smoke-*``) đã bị gỡ khỏi hệ thống. Nếu từng chạy mock với ``MOCK_DEVICE_ID`` trùng
  ID thật thì không tách được; khi đó hãy tạo lại DB (xem README).

Revision ID: 0002_real_step_data
Revises: 0001_initial
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_real_step_data"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

SIMULATED = "(device_id LIKE 'pi-watch-mock-%' OR device_id LIKE 'smoke-%')"


def upgrade():
    for table in ("telemetry_samples", "device_events", "user_activity_logs"):
        op.execute(f"DELETE FROM {table} WHERE {SIMULATED}")
    op.execute("DELETE FROM devices WHERE id LIKE 'pi-watch-mock-%' OR id LIKE 'smoke-%'")

    with op.batch_alter_table("devices") as batch:
        batch.add_column(sa.Column("firmware_version", sa.String(64)))
        batch.add_column(sa.Column("current_boot_id", sa.String(36)))
        batch.add_column(sa.Column("last_status_at", sa.DateTime(timezone=True)))

    with op.batch_alter_table("telemetry_samples") as batch:
        batch.add_column(sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"))
        for name, column_type in (
            ("clock_synced", sa.Boolean()),
            ("clock_skew_s", sa.Float()),
            ("session_started_at", sa.DateTime(timezone=True)),
            ("uptime_s", sa.Float()),
            ("firmware_version", sa.String(64)),
            ("imu_status", sa.String(16)),
            ("step_algorithm", sa.String(32)),
            ("steps_ai_session", sa.Integer()),
            ("step_model_name", sa.String(64)),
            ("step_model_version", sa.String(32)),
            ("walking", sa.Boolean()),
            ("walking_probability", sa.Float()),
            ("cadence_spm", sa.Float()),
            ("step_length_m", sa.Float()),
            ("distance_method", sa.String(16)),
        ):
            batch.add_column(sa.Column(name, column_type))
        batch.alter_column("distance_m_session", existing_type=sa.Float(), nullable=True)
        batch.alter_column("calories_kcal_session", existing_type=sa.Float(), nullable=True)
        batch.create_index("ix_telemetry_device_received", ["device_id", "received_at"])
        batch.create_index("ix_telemetry_device_boot_received", ["device_id", "boot_id", "received_at"])

    op.execute(
        "UPDATE telemetry_samples SET step_algorithm = 'peak-v1', "
        "distance_m_session = NULL, calories_kcal_session = NULL WHERE schema_version = 1"
    )
    # Mặc định 1 chỉ để đánh dấu dữ liệu cũ; bỏ đi để bản ghi mới luôn ghi phiên bản tường minh.
    with op.batch_alter_table("telemetry_samples") as batch:
        batch.alter_column("schema_version", existing_type=sa.Integer(), server_default=None)

    op.create_table(
        "device_profiles",
        sa.Column("device_id", sa.String(64), sa.ForeignKey("devices.id"), primary_key=True),
        sa.Column("height_cm", sa.Float(), nullable=False),
        sa.Column("weight_kg", sa.Float(), nullable=False),
        sa.Column("step_length_m", sa.Float()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("device_profiles")
    with op.batch_alter_table("telemetry_samples") as batch:
        batch.drop_index("ix_telemetry_device_boot_received")
        batch.drop_index("ix_telemetry_device_received")
        for name in (
            "distance_method", "step_length_m", "cadence_spm", "walking_probability", "walking",
            "step_model_version", "step_model_name", "steps_ai_session", "step_algorithm",
            "imu_status", "firmware_version", "uptime_s", "session_started_at", "clock_skew_s",
            "clock_synced", "schema_version",
        ):
            batch.drop_column(name)
    with op.batch_alter_table("devices") as batch:
        for name in ("last_status_at", "current_boot_id", "firmware_version"):
            batch.drop_column(name)
    # Không khôi phục được quãng đường/kcal mẫu và dữ liệu giả lập đã xóa (cố ý).
