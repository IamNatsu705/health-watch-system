# MQTT ingest local

Tiến trình `python -m backend.ingest.main` subscribe các topic `health/v1/devices/+/telemetry`, `+/events` và `+/status`. Nó đối chiếu `device_id` trong topic/payload, kiểm tra JSON Schema ở `contracts/mqtt/`, rồi ghi PostgreSQL.

- Telemetry được chống trùng bằng unique `(device_id, boot_id, sequence)`.
- Event được chống trùng bằng `event_id`.
- Lưu cả thời gian trên thiết bị và `received_at` của server.
- `heart_rate_bpm: null` được giữ nguyên là chưa có phép đo.
- Status online/offline cập nhật bảng thiết bị; API cũng coi dữ liệu quá 10 giây là không còn mới.

`MQTT_HOST`, `MQTT_USERNAME`, `MQTT_PASSWORD` và `DATABASE_URL` do Compose cung cấp. Bản tin sai schema được ghi cảnh báo trong log và bỏ qua.

Bản local chưa có hàng đợi bền vững trên Pi và chưa bảo đảm gửi bù khi mất điện/mất mạng. Dịch vụ này đủ để thử luồng mock và chống ghi trùng; cần bổ sung cơ chế xác nhận/lưu tạm trước khi đặt yêu cầu không mất dữ liệu.
