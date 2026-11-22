# Thiết kế dự án Health Watch

## Hiện trạng

Thư mục `health_watch/` bắt nguồn từ bản copy trên Raspberry Pi và đã được bổ sung MQTT hai chiều. Bản local trên máy tính **đã chạy được** bằng dữ liệu mock; Pi thật cũng đã kết nối broker, gửi telemetry và chạy bằng systemd. Web và APK dùng cùng giao diện, đồng thời có công tắc ON/OFF để điều khiển LED đỏ/còi trên Pi và đọc trạng thái xác nhận. Lệnh chạy, URL và giới hạn bảo mật ở [README.md](README.md).

```text
health_watch_system/
├─ health_watch/              # Code phần cứng, preflight và systemd; chạy trên Pi
├─ backend/
│  ├─ common/                 # Model PostgreSQL, cấu hình, kiểm tra MQTT contract
│  ├─ ingest/                 # Nhận MQTT và ghi DB, chạy trên PC/cloud
│  ├─ api/                    # HTTP API, chạy trên PC/cloud
│  ├─ mock_publisher/         # Pi giả lập, chỉ để thử local
│  ├─ migrations/             # Alembic schema version 0001
│  └─ smoke_local.py          # Kiểm tra tích hợp đầu-cuối
├─ contracts/mqtt/            # Topic và JSON Schema v1
├─ infra/local/               # Docker Compose, Mosquitto, .env.example
├─ scripts/deploy_pi.ps1      # Đồng bộ allowlist source từ Windows sang Pi
├─ web/                       # Dashboard Vue 3/Vite + app Android Capacitor
│  └─ android/               # Dự án native Android, build APK trên máy tính
├─ docs/                      # Thiết kế và runbook
└─ tests/                     # Vị trí dành cho test bổ sung
```

## Sửa ở đâu, chạy ở đâu?

| Phần | Sửa trên máy tính | Chạy local hiện tại | Chép lên Pi? |
| --- | --- | --- | --- |
| `health_watch/` | Có | Chỉ chạy thử phần cứng trực tiếp trên Pi | Có, chỉ source của thư mục này |
| `backend/mock_publisher/` | Có | Container `mock-pi` thay cho Pi | Không |
| `backend/ingest/`, `backend/api/`, `backend/common/` | Có | Container trên máy tính | Không |
| `web/` | Có | Vite trong trình duyệt; Gradle build APK cho Android | Không chép lên Pi; cài APK lên điện thoại |
| `infra/local/`, `contracts/`, `docs/` | Có | Compose/schema/tài liệu trên máy tính | Không chép toàn bộ |

Máy tính là bản mã nguồn chính. Khi sửa code phần cứng, thử phần logic không cần phần cứng tại máy tính rồi đồng bộ riêng `health_watch/` sang `/home/pi/projects/health_watch` trên Pi. File `.venv`, cache, log, ảnh preview và cấu hình bí mật không cần đồng bộ. Nếu chẩn đoán trực tiếp trên Pi, đưa thay đổi đã xác nhận về repo trên máy tính để tránh hai bản lệch nhau.

## Luồng bản local

Mock publisher gửi telemetry mỗi giây, trạng thái online/offline và sự kiện ngã/SOS định kỳ theo [MQTT contract v1](contracts/mqtt/README.md). Ingest kiểm tra schema, `device_id` khớp topic và chống ghi trùng bằng `(device_id, boot_id, sequence)` cho số đo, `event_id` cho sự kiện. PostgreSQL lưu `devices`, `telemetry_samples`, `device_events`, `user_activity_logs`. API cung cấp `/health`, danh sách thiết bị, số đo mới nhất, lịch sử, sự kiện và nhận nhật ký thao tác trình duyệt. Web lấy mới mỗi ba giây và phân biệt dữ liệu cũ/mới.

Với Pi thật, API còn publish topic `commands`; Pi thực thi lệnh bật/tắt rồi publish retained `alert-state`. API subscribe trạng thái này để giao diện hiển thị đúng trạng thái phần cứng và chặn lệnh bật trùng. Mock không mô phỏng luồng điều khiển nên công tắc bị khóa khi chọn thiết bị mock.

Bản local chưa có tài khoản/ủy quyền; log chỉ ghi `session_id` ẩn danh và loại thao tác. Không dùng cho Internet hoặc dữ liệu bệnh nhân thật. BPM, bước, quãng đường và calo từ mock chỉ là số liệu minh họa, không có ý nghĩa y tế.

## Bước tiếp theo

1. Tiếp tục chạy checklist tích hợp Pi thật sau mỗi thay đổi: unit test, I2C/MQTT preflight, dữ liệu đầu-cuối, công tắc ON/OFF, tự tắt và phục hồi sau mất broker. Dùng IP LAN của máy tính, không dùng `localhost` trên Pi.
2. Thêm cấu hình/bảo mật cho môi trường thật: credential từng Pi, quyền topic, MQTT TLS, HTTPS, đăng nhập người dùng và phân quyền xem thiết bị.
3. Bản Android Capacitor đã dùng chung giao diện/API với dashboard. Trước khi phát hành thật, bổ sung đăng nhập, HTTPS, icon/splash chính thức, ký release và kiểm thử trên nhiều thiết bị.
4. Chọn bài toán Edge AI sau khi có dữ liệu và tiêu chí đánh giá; kết quả model phải lưu kèm tên/phiên bản/độ tin cậy, không ghi đè số đo gốc. AI **chưa triển khai**.
5. Khi chuyển cloud, chạy migration và backup DB, dùng domain/TLS, giám sát ingest/API và thiết kế lưu đệm trên Pi khi mất mạng.

Xem [kiến trúc chi tiết](docs/ARCHITECTURE.md) và [hướng dẫn chạy local](infra/local/README.md).
