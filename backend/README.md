# Backend Health Watch

Backend dùng Python 3.12 trong Docker và gồm ba tiến trình độc lập dùng chung
module `backend/common/`.

| Thành phần | Entry point | Trách nhiệm |
| --- | --- | --- |
| [`ingest/`](ingest/README.md) | `python -m backend.ingest.main` | MQTT → validate → PostgreSQL |
| [`api/`](api/README.md) | `uvicorn backend.api.main:app` | HTTP API và MQTT commands/alert-state |
| `migrations/` | Alembic | Quản lý schema DB |
| `tests/` | `python -m pytest backend/tests` | Contract (dùng mã tạo payload của Pi), ingest, API trên SQLite trong bộ nhớ |

Không có publisher giả lập: chỉ Pi thật trong `MQTT_DEVICES` gửi được dữ liệu.

## Cấu hình

Compose cung cấp:

- `DATABASE_URL`
- `MQTT_HOST`, `MQTT_PORT`
- `MQTT_USERNAME`, `MQTT_PASSWORD` (tài khoản backend)
- `MQTT_DEVICES` (`id:mat_khau,...`; backend chỉ dùng phần ID làm danh sách thiết bị thật)
- `LOCAL_TIMEZONE` (mặc định `Asia/Ho_Chi_Minh`)

Không đặt secret trực tiếp trong source. Dependency chung nằm ở
[`requirements.txt`](requirements.txt).

## Database

Revision `0001_initial` + `0002_real_step_data` tạo:

- `devices`: ID, tên, online, thời điểm thấy cuối, firmware, boot hiện tại.
- `telemetry_samples`: BPM, ngón tay, hai bộ đếm bước (thuật toán, AI) theo phiên, mô hình
  AI, trạng thái đi bộ/nhịp, IMU, quãng đường/kcal ước tính kèm cơ sở ước tính, nguồn gốc
  (firmware, thuật toán, đồng hồ, `received_at`).
- `device_events`: ngã, xác nhận ngã, nhấn/thả SOS.
- `device_profiles`: chiều cao, cân nặng, chiều dài bước tự đo.
- `user_activity_logs`: hành động phiên web/app ẩn danh.

`0002` xóa dữ liệu của thiết bị giả lập cũ (`pi-watch-mock-*`, `smoke-*`), đánh dấu dữ
liệu cũ `schema_version=1`/`peak-v1`, và đặt NULL quãng đường/kcal cũ (đó là hằng số mẫu,
không phải số đo).

Telemetry chống trùng bằng `(device_id, boot_id, sequence)`; event chống
trùng bằng `event_id`.

## Chạy và log

Chạy toàn stack theo [README gốc](../README.md). Xem log riêng:

```powershell
docker compose --env-file infra/local/.env -f infra/local/compose.yaml logs -f ingest api
```

Rebuild sau khi sửa backend:

```powershell
docker compose --env-file infra/local/.env -f infra/local/compose.yaml up --build -d api ingest
```

## Giới hạn

Backend local chưa có tài khoản, phân quyền, HTTPS, rate limit hoặc audit theo
user thật. Không cung cấp trực tiếp qua Internet.
