# MQTT contract v1 — bản nháp

Broker nhận ba topic theo ID thiết bị:

```text
health/v1/devices/{device_id}/telemetry
health/v1/devices/{device_id}/events
health/v1/devices/{device_id}/status
```

`{device_id}` trong topic phải trùng `device_id` trong payload. Mỗi Pi dùng ID ổn định và credential riêng khi triển khai cloud. Thiết bị không được publish vào topic của thiết bị khác.

| Topic | Nhịp gửi | Nội dung | Schema |
| --- | --- | --- | --- |
| `telemetry` | Khoảng 1 lần/giây | BPM hợp lệ hoặc `null`, trạng thái ngón tay, bước/km/kcal của phiên | [telemetry.v1.schema.json](telemetry.v1.schema.json) |
| `events` | Khi xảy ra sự kiện | `fall_detected`, `fall_acknowledged`, `sos_pressed`, `sos_released` | [event.v1.schema.json](event.v1.schema.json) |
| `status` | Khi kết nối/ngắt hoặc heartbeat | Online/offline, `boot_id`, phiên bản phần mềm | Schema sẽ chốt cùng Last Will |

Định danh: `device_id` ổn định; `boot_id` là UUID mới mỗi lần chương trình Pi chạy; `sequence` tăng trong mỗi `boot_id`. Timestamp dùng UTC ISO 8601. `heart_rate_bpm: null` nghĩa là chưa tính được, không phải 0. `steps_session` là số bước từ lúc chương trình chạy.

Các bản tin quan trọng dùng QoS 1. MQTT có thể phát lại; ingest chống trùng bằng `(device_id, boot_id, sequence)` với telemetry và `event_id` với event. Không dựa vào thứ tự đến tuyệt đối. Bản đầu không gửi gia tốc thô 25 Hz lên broker.

Ví dụ telemetry:

```json
{
  "schema_version": 1,
  "device_id": "pi-watch-001",
  "boot_id": "4e78c38d-4a24-48c2-81ee-93434f0838bf",
  "sequence": 42,
  "measured_at": "2026-11-21T16:00:00Z",
  "metrics": {
    "heart_rate_bpm": null,
    "finger_present": false,
    "steps_session": 7,
    "distance_m_session": 4.9,
    "calories_kcal_session": 0.26
  }
}
```

Schema này là bản nháp thiết kế; code Pi hiện tại chưa publish MQTT. Trước khi triển khai, xác nhận khoảng gửi, các trường cần hiển thị và cách lưu status/offline với dữ liệu thực tế.
