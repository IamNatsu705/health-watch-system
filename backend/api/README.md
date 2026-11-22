# API local

FastAPI đọc PostgreSQL và phục vụ dashboard tại cổng `8000` khi chạy Compose. Tài liệu tương tác ở <http://localhost:8000/docs>.

| Endpoint | Nội dung |
| --- | --- |
| `GET /health` | Kiểm tra API và DB |
| `GET /api/v1/devices` | Danh sách thiết bị và trạng thái mới nhất |
| `GET /api/v1/devices/{id}/latest` | Số đo mới nhất |
| `GET /api/v1/devices/{id}/history?limit=60` | Chuỗi số đo gần đây, thứ tự thời gian tăng |
| `GET /api/v1/devices/{id}/events?limit=20` | Ngã/SOS gần đây |
| `POST /api/v1/activity` | Ghi hành động phiên trình duyệt |

`POST /activity` chỉ nhận `session_id` UUID, `action` trong danh sách cho phép và `device_id` tùy chọn. Dashboard hiện gửi `dashboard_view` và `device_select`. Log không chứa mật khẩu/token. Đây là nhật ký phiên ẩn danh, chưa phải log theo tài khoản người dùng.

`DATABASE_URL` do Compose cung cấp. Schema DB được tạo bằng Alembic trước khi API chạy. Các bảng hiện có: `devices`, `telemetry_samples`, `device_events`, `user_activity_logs`.

Giới hạn: local demo chưa có đăng nhập, phân quyền, HTTPS hoặc cơ chế chia sẻ nhiều người dùng. Cần bổ sung các phần đó trước khi chuyển cloud.
