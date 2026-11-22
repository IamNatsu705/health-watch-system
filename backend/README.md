# Backend local

`backend/` dùng Python 3.12 trong Docker. Các dịch vụ dùng chung `common/` cho model DB và kiểm tra hợp đồng MQTT:

- [`mock_publisher/`](mock_publisher/README.md) tạo bản tin giả theo schema v1.
- [`ingest/`](ingest/README.md) nhận MQTT và ghi PostgreSQL.
- [`api/`](api/README.md) cung cấp API cho web và ghi hoạt động phiên trình duyệt.
- `migrations/` có revision Alembic `0001_initial`, được Compose chạy trước ingest/API.

`requirements.txt` là dependency chung của image backend để bản local dễ chạy. Khi quy mô tăng, có thể tách image/dependency theo từng dịch vụ mà không đổi MQTT topic hoặc API.

Chạy toàn hệ thống theo [README gốc](../README.md). Backend local chưa có tài khoản, phân quyền và TLS; không dùng cấu hình này để cung cấp dữ liệu sức khỏe thật qua Internet.
