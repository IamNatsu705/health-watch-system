# MQTT contract v1

Base topic:

```text
health/v1/devices/{device_id}
```

`device_id` trong payload phải trùng ID trong topic và chỉ gồm chữ, số, `.`,
`_`, `-`, tối đa 64 ký tự.

## 1. Topic

| Topic suffix | Hướng | QoS | Retain | Nội dung |
| --- | --- | --- | --- | --- |
| `telemetry` | Pi → broker | 1 | Không | Số đo tổng hợp khoảng 1 Hz |
| `events` | Pi → broker | 1 | Không | Ngã, xác nhận ngã, nhấn/thả SOS |
| `status` | Pi → broker | 1 | Có | Online/offline và Last Will |
| `commands` | API → Pi | 1 | Không | Bật/tắt cảnh báo từ xa |
| `alert-state` | Pi → API | 1 | Có | Trạng thái thật của còi/LED |

Schema:

- [telemetry.v1.schema.json](telemetry.v1.schema.json)
- [event.v1.schema.json](event.v1.schema.json)
- [command.v1.schema.json](command.v1.schema.json)
- [alert-state.v1.schema.json](alert-state.v1.schema.json)

Status hiện được validate tối thiểu trong code ingest.

## 2. Định danh và chống trùng

- `device_id`: ổn định qua các lần reboot.
- `boot_id`: UUID mới mỗi lần tiến trình Pi chạy.
- `sequence`: tăng trong một `boot_id` cho telemetry/event.
- `event_id`: UUID riêng để chống event trùng.
- `command_id`: UUID để Pi bỏ lệnh QoS 1 bị giao lại.

PostgreSQL chống telemetry trùng bằng `(device_id, boot_id, sequence)` và
event trùng bằng `event_id`.

## 3. Telemetry

Ví dụ:

```json
{
  "schema_version": 1,
  "device_id": "pi-watch-001",
  "boot_id": "4e78c38d-4a24-48c2-81ee-93434f0838bf",
  "sequence": 42,
  "measured_at": "2026-11-22T07:00:00Z",
  "metrics": {
    "heart_rate_bpm": null,
    "finger_present": false,
    "steps_session": 7,
    "distance_m_session": 4.9,
    "calories_kcal_session": 0.26
  }
}
```

`heart_rate_bpm: null` nghĩa là chưa tính được, không phải 0. Bước/mét/kcal
là giá trị của phiên chạy hiện tại. Bản v1 không gửi gia tốc thô liên tục.

## 4. Event

`event_type` cho phép:

```text
fall_detected
fall_acknowledged
sos_pressed
sos_released
```

Event dùng `occurred_at` của Pi và backend lưu thêm `received_at`.

## 5. Command cảnh báo từ xa

```json
{
  "schema_version": 1,
  "command_id": "bbdf9f34-cc32-4765-a01c-97e921f64047",
  "device_id": "pi-watch-001",
  "command_type": "remote_alert",
  "active": true,
  "duration_s": 10,
  "issued_at": "2026-11-22T07:00:00Z"
}
```

Pi chỉ nhận command đúng device, UUID hợp lệ, `duration_s` 1–60 và timestamp
không quá cũ/ở tương lai quá mức cho phép. Command không retained để thiết bị
không thực thi lệnh cũ sau reconnect. Pi giữ danh sách command ID gần đây để
bỏ bản tin trùng.

## 6. Trạng thái còi/LED

```json
{
  "schema_version": 1,
  "device_id": "pi-watch-001",
  "boot_id": "4e78c38d-4a24-48c2-81ee-93434f0838bf",
  "buzzer_active": true,
  "red_led_active": true,
  "source": "remote",
  "last_command_id": "bbdf9f34-cc32-4765-a01c-97e921f64047",
  "expires_at": "2026-11-22T07:00:10Z",
  "reported_at": "2026-11-22T07:00:00Z"
}
```

`source`: `normal`, `remote`, `sos` hoặc `fall`. State được retained để API
nhận lại sau restart. API vẫn kiểm tra device online; không dùng retained state
cũ để cho phép điều khiển thiết bị offline.

## 7. Độ tin cậy và bảo mật

QoS 1 có thể giao trùng và không bảo đảm tồn tại qua mọi lần mất điện. Local
chưa TLS/ACL theo thiết bị. Cloud phải cấp credential riêng và giới hạn quyền:

- Pi publish các topic dữ liệu/state của chính nó.
- Pi chỉ subscribe `commands` của chính nó.
- API publish command và subscribe state của các device được quản lý.
