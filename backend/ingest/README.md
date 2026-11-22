# MQTT ingest

Ingest subscribe dữ liệu thiết bị và ghi PostgreSQL.

## Topic nhận

```text
health/v1/devices/+/telemetry
health/v1/devices/+/events
health/v1/devices/+/status
```

`commands` và `alert-state` không đi qua ingest: API publish command và trực
tiếp subscribe state output để cập nhật giao diện với độ trễ thấp.

## Quy trình xử lý

1. Parse JSON và kiểm tra topic có đúng cấu trúc.
2. Yêu cầu `device_id` trong payload khớp topic.
3. Validate telemetry/event bằng JSON Schema trong `contracts/mqtt/`.
4. Cập nhật `devices.online`, `last_seen_at`.
5. Insert telemetry/event với khóa chống trùng.

Payload sai schema được ghi warning và bỏ qua. `heart_rate_bpm: null` được lưu
nguyên nghĩa “chưa có phép đo”, không chuyển thành 0.

## Độ mới và online

Status retained cho biết online/offline. API còn yêu cầu `last_seen_at` mới
hơn 10 giây để tránh hiển thị online khi status cũ hoặc kết nối bất thường.

## Log và kiểm tra

```powershell
docker compose --env-file infra/local/.env -f infra/local/compose.yaml logs -f ingest
docker compose --env-file infra/local/.env -f infra/local/compose.yaml exec -T ingest python -m backend.smoke_local
```

## Giới hạn

Ingest local xử lý tuần tự qua MQTT callback và chưa có dead-letter queue,
metric hoặc replay từ storage. Pi có outbox RAM, chưa lưu bền vững telemetry
khi mất điện/mạng dài.
