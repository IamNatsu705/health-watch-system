# Backend Health Watch

Backend dùng Python 3.12 trong Docker và gồm ba tiến trình độc lập dùng chung
module `backend/common/`.

| Thành phần | Entry point | Trách nhiệm |
| --- | --- | --- |
| [`ingest/`](ingest/README.md) | `python -m backend.ingest.main` | MQTT → validate → PostgreSQL |
| [`api/`](api/README.md) | `uvicorn backend.api.main:app` | HTTP API và MQTT commands/alert-state |
| [`mock_publisher/`](mock_publisher/README.md) | `python -m backend.mock_publisher.main` | Giả lập Pi trong local |
| `migrations/` | Alembic | Quản lý schema DB |
| `smoke_local.py` | `python -m backend.smoke_local` | Test đầu-cuối local |

## Cấu hình

Compose cung cấp:

- `DATABASE_URL`
- `MQTT_HOST`, `MQTT_PORT`
- `MQTT_USERNAME`, `MQTT_PASSWORD`

Không đặt secret trực tiếp trong source. Dependency chung nằm ở
[`requirements.txt`](requirements.txt).

## Database

Revision Alembic `0001_initial` tạo:

- `devices`: ID, tên, online và thời điểm thấy cuối.
- `telemetry_samples`: BPM, ngón tay, bước, mét, kcal theo phiên.
- `device_events`: ngã, xác nhận ngã, nhấn/thả SOS.
- `user_activity_logs`: hành động phiên web/app ẩn danh.

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
