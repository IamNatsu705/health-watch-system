# Tài liệu Health Watch

Đây là chỉ mục tài liệu của hệ thống. Bắt đầu từ [README ở thư mục gốc](../README.md) nếu cần chạy nhanh toàn bộ dự án.

| Tài liệu | Nội dung |
| --- | --- |
| [Kiến trúc](ARCHITECTURE.md) | Thành phần, luồng dữ liệu hai chiều, độ tin cậy, local/cloud và vị trí mở rộng AI |
| [Phần cứng](hardware/README.md) | Sơ đồ chân, nguồn, kiểm tra I2C/SPI/GPIO và an toàn thử nghiệm |
| [Runbook vận hành](runbooks/README.md) | Khởi động local, đưa code lên Pi, chạy service, kiểm tra điều khiển từ xa và xử lý lỗi |
| [Raspberry Pi](../health_watch/README.md) | Cài môi trường Pi, cấu hình MQTT, chạy tay và systemd |
| [Backend](../backend/README.md) | API, ingest, mock publisher và cơ sở dữ liệu |
| [Web/Android](../web/README.md) | Chạy dashboard, dùng công tắc cảnh báo và build/cài APK |
| [Hợp đồng MQTT/API](../contracts/README.md) | Topic, schema, payload và quy tắc tương thích |
| [Hạ tầng local/cloud](../infra/README.md) | Docker Compose local và yêu cầu trước khi đưa lên cloud |
| [Kiểm thử](../tests/README.md) | Test đơn vị, smoke test, kiểm tra tích hợp thật |
| [Thiết kế dự án](../PROJECT_DESIGN.md) | Cây thư mục và định hướng mở rộng |

## Quy ước tài liệu

- Lệnh PowerShell chạy trên Windows được ghi trong khối `powershell`; lệnh Pi dùng `bash`.
- Đường dẫn Pi chuẩn là `/home/pi/projects/health_watch`.
- Địa chỉ `172.20.10.11` chỉ là ví dụ IP LAN đã dùng; luôn kiểm tra lại bằng `ipconfig`.
- Không đưa `.env`, mật khẩu, token, khóa ký APK hoặc dữ liệu sức khỏe thật vào Git.
- Khi thay đổi topic, payload hoặc API, cập nhật `contracts/` trước rồi cập nhật cả producer và consumer.
- Kết quả BPM, bước chân và phát hiện ngã hiện là thử nghiệm, không phải chẩn đoán hoặc thiết bị y tế.
