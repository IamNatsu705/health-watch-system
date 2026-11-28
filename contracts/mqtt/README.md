# MQTT contract

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
| `config` | API → Pi | 1 | Có | Hồ sơ người đeo (chiều cao, cân nặng, chiều dài bước) |

Schema:

- [telemetry.v2.schema.json](telemetry.v2.schema.json) (v1 đã bỏ: quãng đường/kcal là hằng số mẫu)
- [event.v1.schema.json](event.v1.schema.json)
- [status.v1.schema.json](status.v1.schema.json)
- [command.v1.schema.json](command.v1.schema.json)
- [alert-state.v1.schema.json](alert-state.v1.schema.json)
- [config.v1.schema.json](config.v1.schema.json)

Quyền ghi topic do ACL của broker quyết định. Pi chỉ ghi `telemetry`, `events`,
`status`, `alert-state` của chính nó và chỉ đọc `commands`, `config` của chính nó.
Backend chỉ đọc dữ liệu thiết bị và chỉ ghi `commands`, `config`.

## 2. Định danh và chống trùng

- `device_id`: ổn định qua các lần reboot.
- `boot_id`: UUID mới mỗi lần tiến trình Pi chạy.
- `sequence`: tăng trong một `boot_id` cho telemetry/event.
- `event_id`: UUID riêng để chống event trùng.
- `command_id`: UUID để Pi bỏ lệnh QoS 1 bị giao lại.

PostgreSQL chống telemetry trùng bằng `(device_id, boot_id, sequence)` và
event trùng bằng `event_id`.

## 3. Telemetry v2

Ví dụ (Pi có mô hình AI và hồ sơ người đeo):

```json
{
  "schema_version": 2,
  "device_id": "pi-watch-001",
  "boot_id": "4e78c38d-4a24-48c2-81ee-93434f0838bf",
  "sequence": 42,
  "measured_at": "2026-11-28T07:00:00.120Z",
  "session_started_at": "2026-11-28T06:59:18.004Z",
  "uptime_s": 42.1,
  "clock_synced": true,
  "firmware_version": "health-watch-pi/0.2.0",
  "step_algorithm": "peak-bout-v2",
  "step_model": {"name": "walk-gate-rf", "version": "1.0.0"},
  "distance_basis": {"step_length_m": 0.704, "method": "height_ratio"},
  "metrics": {
    "heart_rate_bpm": null,
    "finger_present": false,
    "imu_status": "ok",
    "steps_algorithm_session": 61,
    "steps_ai_session": 64,
    "walking": true,
    "walking_probability": 0.93,
    "cadence_spm": 109.1,
    "distance_m_session": 45.1,
    "calories_kcal_session": 1.33
  }
}
```

Quy tắc:

- `steps_*_session` là bộ đếm của phiên chạy hiện tại (`boot_id`) và chỉ tăng. Tổng
  theo ngày do API tính (`/steps/daily`).
- `step_model = null` ⇔ `steps_ai_session = null`: Pi không nạp được mô hình. Số này
  là null, không phải 0.
- `distance_basis = null` ⇒ `distance_m_session = calories_kcal_session = null`: chưa
  có hồ sơ người đeo thật. Không dùng số mẫu.
- `imu_status`: `starting`, `ok`, `saturated` (có va chạm vượt ±8 g), `error`,
  `frozen` (chip treo). Khác `ok`/`saturated` thì bộ đếm không tăng.
- `heart_rate_bpm: null` nghĩa là chưa tính được, không phải 0.
- `clock_synced = false`: Pi chưa đồng bộ NTP, nên `measured_at` có thể sai. Backend
  sắp xếp và chia ngày theo `received_at` của server.
- JSON không được chứa `NaN`/`Infinity`. Không gửi gia tốc thô liên tục; dữ liệu thô
  chỉ được ghi cục bộ bằng `record_imu.py` để huấn luyện/kiểm định.

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

## 7. Hồ sơ người đeo (`config`)

```json
{
  "schema_version": 1,
  "device_id": "pi-watch-001",
  "profile": {"height_cm": 170, "weight_kg": 62.5, "step_length_m": null},
  "updated_at": "2026-11-28T07:00:00Z"
}
```

`profile: null` là xóa hồ sơ. Retained, và API publish lại mỗi khi kết nối broker. Pi
kiểm tra phạm vi giá trị rồi lưu `state/profile.json`.

## 8. Độ tin cậy và bảo mật

QoS 1 có thể giao trùng và không bảo đảm tồn tại qua mọi lần mất điện. Local đã có
tài khoản và ACL theo thiết bị (xem `infra/local/mosquitto/start.sh`) nhưng chưa có TLS;
cloud phải thêm TLS.
