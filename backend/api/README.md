# FastAPI local

API đọc PostgreSQL cho web/app (chỉ thiết bị trong `MQTT_DEVICES`) và giữ một MQTT
client để:

1. publish remote command tới Pi;
2. subscribe `alert-state` retained do Pi xác nhận;
3. chặn lệnh bật lặp trong cùng tiến trình API;
4. publish hồ sơ người đeo (retained `config`), và publish lại mỗi khi kết nối broker.

Swagger: <http://localhost:8000/docs>.

## Endpoint

| Method | Đường dẫn | Mô tả |
| --- | --- | --- |
| `GET` | `/health` | Kiểm tra API và kết nối DB |
| `GET` | `/api/v1/devices` | Thiết bị đã đăng ký; đang gửi dữ liệu lên đầu |
| `GET` | `/api/v1/devices/{id}/latest` | Telemetry mới nhất theo giờ server nhận, kèm `age_s`/`fresh`, và trạng thái còi |
| `GET` | `/api/v1/devices/{id}/history?limit=60` | Telemetry theo giờ server nhận, tăng dần |
| `GET` | `/api/v1/devices/{id}/steps/daily?days=7` | Bước/quãng đường/kcal theo ngày địa phương |
| `GET` `PUT` `DELETE` | `/api/v1/devices/{id}/profile` | Hồ sơ người đeo (chiều cao, cân nặng, chiều dài bước tự đo) |
| `GET` | `/api/v1/devices/{id}/events?limit=20` | Event mới nhất |
| `POST` | `/api/v1/devices/{id}/commands/remote-alert` | Bật/tắt cảnh báo từ xa |
| `POST` | `/api/v1/activity` | Ghi hoạt động phiên web/app |

`limit` của history là 1–500; event là 1–200; `days` là 1–31.

## Telemetry trả về

`latest.telemetry` (và từng phần tử của `history`) gồm `steps_algorithm_session`,
`steps_ai_session` (`null` nếu Pi không có mô hình), `step_model`,
`steps_primary_session`/`steps_primary_source` (AI nếu có), `walking`,
`walking_probability`, `cadence_spm`, `imu_status`, `distance_m_session`/
`calories_kcal_session` (`null` nếu chưa có hồ sơ), `step_length_m`, `distance_method`,
`firmware_version`, `clock_synced`, `clock_skew_s`, `received_at`, `age_s`, `fresh`
(nhận trong `FRESH_DATA_S` = 10 s) và `legacy` (dữ liệu firmware cũ).

## Bước theo ngày

```json
{"timezone": "Asia/Ho_Chi_Minh", "days": [
  {"date": "2026-11-28", "steps": 6120, "source": "ai", "steps_ai": 6120,
   "steps_algorithm": 5874, "distance_m": 4300.2, "calories_kcal": 150.3, "sessions": 2}
]}
```

Mỗi phiên (`boot_id`) có bộ đếm chỉ tăng. Phần tăng trong ngày = giá trị lớn nhất trước
cuối ngày − giá trị lớn nhất trước đầu ngày; các phiên được cộng lại. Ngày tính theo giờ
server nhận (`LOCAL_TIMEZONE`). Chỉ gồm telemetry v2; ngày không có dữ liệu có
`sessions = 0`.

## Hồ sơ người đeo

`PUT` nhận `{"height_cm": 100–230, "weight_kg": 25–250, "step_length_m": 0.25–1.3 | null}`.
Ngoài khoảng thì trả `422`. Phản hồi có `delivered_to_broker`; nếu là `false`, API sẽ
gửi khi kết nối lại broker. `DELETE` xóa hồ sơ, gửi `profile: null`, và Pi ngừng ước tính.

## Remote alert

Request:

```json
{
  "active": true,
  "duration_s": 10
}
```

`duration_s` từ 1 đến 60. API chỉ gửi khi thiết bị online và telemetry mới
hơn 10 giây. Lệnh MQTT dùng QoS 1, `retain=false`.

Pi phản hồi trạng thái thật bằng `alert-state`. Trạng thái trả trong
`GET .../latest`:

```json
{
  "remote_alert": {
    "known": true,
    "buzzer_active": false,
    "red_led_active": false,
    "source": "normal",
    "expires_at": null,
    "reported_at": "2026-11-22T07:00:00Z",
    "pending": false,
    "pending_active": null
  }
}
```

API trả:

- `202`: command đã publish; `state.pending=true` cho tới khi Pi xác nhận.
- `404`: không có device.
- `409`: device offline, chưa có state Pi, còi đã bật hoặc lệnh bật đang chờ.
- `503`: API không kết nối được MQTT.

`alert-state` hiện giữ trong RAM của API và retained ở broker, không lưu DB.
API restart sẽ nhận lại retained state. Nếu Pi offline thì giao diện không cho
điều khiển dù retained state cũ còn tồn tại.

## Activity log

Payload gồm `session_id` UUID, `action` allowlist và `device_id` tùy chọn.
Các action hiện có: `dashboard_view`, `device_select`, `history_view`,
`events_view`, `remote_alert_start`, `remote_alert_stop`, `profile_update`, `profile_clear`.

Đây là log phiên ẩn danh, chưa phải audit người dùng. Không chứa password/token.

## Cấu hình và bảo mật

API nhận `DATABASE_URL` và biến MQTT từ Compose. CORS local đang cho phép mọi
origin và chưa có auth; bắt buộc siết lại trước cloud.
