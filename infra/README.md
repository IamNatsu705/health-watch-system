# Hạ tầng Health Watch

Thư mục này chứa cấu hình chạy các dịch vụ server. Nó không được chép lên
Raspberry Pi.

| Thư mục | Trạng thái | Mục đích |
| --- | --- | --- |
| [`local/`](local/README.md) | Đã triển khai | Docker Compose cho Mosquitto (ACL theo thiết bị), PostgreSQL, ingest, API và web |
| [`cloud/`](cloud/README.md) | Tài liệu thiết kế | Checklist và kiến trúc mục tiêu khi đưa server lên cloud |

Pi chỉ cần địa chỉ broker, port, username/password và `device_id` trong
`health_watch/.env`. Web Android chỉ cần địa chỉ HTTP API.

Không commit `infra/local/.env`. Không lưu credential thật trong README,
Compose hoặc source.
