# FastAPI local

API đọc PostgreSQL cho web/app và giữ một MQTT client để:

1. publish remote command tới Pi;
2. subscribe `alert-state` retained do Pi xác nhận;
3. chặn lệnh bật lặp trong cùng tiến trình API.

Swagger: <http://localhost:8000/docs>.

## Endpoint

| Method | Đường dẫn | Mô tả |
| --- | --- | --- |
| `GET` | `/health` | Kiểm tra API và kết nối DB |
| `GET` | `/api/v1/devices` | Danh sách thiết bị và online/offline |
| `GET` | `/api/v1/devices/{id}/latest` | Telemetry mới nhất và trạng thái còi |
| `GET` | `/api/v1/devices/{id}/history?limit=60` | Telemetry theo thời gian tăng dần |
| `GET` | `/api/v1/devices/{id}/events?limit=20` | Event mới nhất |
| `POST` | `/api/v1/devices/{id}/commands/remote-alert` | Bật/tắt cảnh báo từ xa |
| `POST` | `/api/v1/activity` | Ghi hoạt động phiên web/app |

`limit` của history là 1–500; event là 1–200.

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
`events_view`, `remote_alert_start`, `remote_alert_stop`.

Đây là log phiên ẩn danh, chưa phải audit người dùng. Không chứa password/token.

## Cấu hình và bảo mật

API nhận `DATABASE_URL` và biến MQTT từ Compose. CORS local đang cho phép mọi
origin và chưa có auth; bắt buộc siết lại trước cloud.
