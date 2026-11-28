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

1. Kiểm tra topic đúng cấu trúc và `device_id` có trong `MQTT_DEVICES`. Thiết bị
   lạ bị bỏ, không tự tạo.
2. Parse JSON chuẩn: từ chối `NaN`/`Infinity`. `device_id` trong payload phải khớp topic.
3. Validate bằng JSON Schema trong `contracts/mqtt/` (telemetry v2, event v1, status
   v1), có kiểm tra `date-time`/`uuid`. Ingest dừng khi khởi động nếu thiếu bộ kiểm
   tra format. Telemetry v1 cũ (quãng đường/kcal hằng số mẫu) bị từ chối.
4. Kiểm tra bộ đếm bước so với bản tin trước/sau trong cùng `boot_id`: không giảm,
   không tăng quá 5 bước/s × thời gian chạy + 30.
5. Cập nhật `devices` (online, firmware, `current_boot_id`). Last Will offline của phiên
   cũ đến muộn không đánh dấu phiên mới là offline.
6. Insert với khóa chống trùng, lưu `received_at` (giờ server) và `clock_skew_s`.

Payload bị từ chối được ghi warning và bỏ qua. `null` (chưa đo, không có mô hình AI,
chưa có hồ sơ) được lưu nguyên nghĩa, không chuyển thành 0.

## Độ mới và online

Status retained cho biết online/offline. API còn yêu cầu `last_seen_at` mới
hơn 10 giây để tránh hiển thị online khi status cũ hoặc kết nối bất thường.

## Log và kiểm tra

```powershell
docker compose --env-file infra/local/.env -f infra/local/compose.yaml logs -f ingest
python -m pytest backend/tests   # trên PC, SQLite trong bộ nhớ, không chạm DB thật
```

## Giới hạn

Ingest local xử lý tuần tự qua MQTT callback và chưa có dead-letter queue,
metric hoặc replay từ storage. Pi có outbox RAM, chưa lưu bền vững telemetry
khi mất điện/mạng dài.
