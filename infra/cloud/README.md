# Chuyển sang cloud

Cloud sẽ chạy broker MQTT, `backend/ingest`, PostgreSQL, `backend/api` và host `web/`. Raspberry Pi vẫn ở tại người dùng, gửi MQTT qua Internet. APK gọi API HTTPS theo tên miền.

Trước khi chuyển cần có:

- TLS cho MQTT và HTTPS cho API/web.
- Credential riêng cho từng Pi và quyền publish chỉ vào topic của chính nó.
- Xác thực/phân quyền người dùng ở API, kể cả khi web và APK có cùng mã giao diện.
- Migration DB, sao lưu và kiểm tra khôi phục PostgreSQL.
- Log lỗi, healthcheck và theo dõi Pi offline.
- Chính sách giữ/xóa telemetry và user activity logs.
- Kiểm tra mất mạng, kết nối lại, bản tin trùng và đồng hồ Pi lệch.

Chưa chọn nhà cung cấp cloud; cấu trúc dữ liệu và MQTT topic v1 không gắn với một nhà cung cấp. Không mở PostgreSQL trực tiếp ra Internet.
