# Hạ tầng triển khai

- [`local/`](local/README.md): môi trường thử trên máy tính, dự kiến Docker Compose cho Mosquitto, PostgreSQL, ingest và API.
- [`cloud/`](cloud/README.md): yêu cầu khi chuyển các dịch vụ server lên cloud.

Thư mục này không chép lên Raspberry Pi. Pi chỉ cần địa chỉ broker và thông tin đăng nhập phù hợp từng môi trường. Chưa có `compose.yaml` hay tài nguyên cloud được tạo; README xác định cách vận hành trước khi triển khai.
