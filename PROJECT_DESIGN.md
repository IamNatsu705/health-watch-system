# Thiết kế dự án Health Watch

## Hiện trạng

Thư mục `health_watch/` bắt nguồn từ bản copy trên Raspberry Pi và đã được bổ sung MQTT hai chiều. Hệ thống chỉ chạy với dữ liệu thật từ Pi đã đăng ký (không còn mock). Pi đếm bước bằng thuật toán xử lý tín hiệu và AI chạy trên thiết bị; mô hình được huấn luyện và đánh giá trên dữ liệu thật (xem [ml/README.md](ml/README.md)). Web và APK dùng cùng giao diện, đồng thời có công tắc ON/OFF để điều khiển LED đỏ/còi trên Pi và đọc trạng thái xác nhận. Lệnh chạy, URL và giới hạn bảo mật ở [README.md](README.md).

```text
health_watch_system/
├─ health_watch/              # Code phần cứng, preflight và systemd; chạy trên Pi
├─ backend/
│  ├─ common/                 # Model PostgreSQL, cấu hình, kiểm tra MQTT contract
│  ├─ ingest/                 # Nhận MQTT và ghi DB, chạy trên PC/cloud
│  ├─ api/                    # HTTP API, chạy trên PC/cloud
│  ├─ migrations/             # Alembic schema version 0001
│  └─ tests/                  # Contract, ingest, API (SQLite trong bộ nhớ)
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
| `ml/` | Có | Huấn luyện/đánh giá AI trên PC | Không; chỉ file mô hình `health_watch/models/` lên Pi |
| `backend/ingest/`, `backend/api/`, `backend/common/` | Có | Container trên máy tính | Không |
| `web/` | Có | Vite trong trình duyệt; Gradle build APK cho Android | Không chép lên Pi; cài APK lên điện thoại |
| `infra/local/`, `contracts/`, `docs/` | Có | Compose/schema/tài liệu trên máy tính | Không chép toàn bộ |

Máy tính là bản mã nguồn chính. Khi sửa code phần cứng, thử phần logic không cần phần cứng tại máy tính rồi đồng bộ riêng `health_watch/` sang `/home/pi/projects/health_watch` trên Pi. File `.venv`, cache, log, ảnh preview và cấu hình bí mật không cần đồng bộ. Nếu chẩn đoán trực tiếp trên Pi, đưa thay đổi đã xác nhận về repo trên máy tính để tránh hai bản lệch nhau.

## Luồng bản local

Pi gửi telemetry v2 mỗi giây, trạng thái online/offline và sự kiện ngã/SOS theo [MQTT contract](contracts/mqtt/README.md), bằng tài khoản MQTT riêng chỉ ghi được topic của chính nó. Ingest chỉ nhận thiết bị trong `MQTT_DEVICES`, kiểm tra schema (có format), từ chối bộ đếm giảm/tăng vô lý và chống ghi trùng bằng `(device_id, boot_id, sequence)`/`event_id`. PostgreSQL lưu `devices`, `telemetry_samples` (kèm nguồn gốc dữ liệu), `device_events`, `device_profiles`, `user_activity_logs`. API cung cấp `/health`, thiết bị, số đo mới nhất (kèm độ mới), lịch sử, bước theo ngày, hồ sơ người đeo, sự kiện và nhật ký thao tác. Web lấy mới mỗi ba giây và ghi rõ dữ liệu cũ.

Với Pi thật, API còn publish topic `commands`; Pi thực thi lệnh bật/tắt rồi publish retained `alert-state`. API subscribe trạng thái này để giao diện hiển thị đúng trạng thái phần cứng và chặn lệnh bật trùng. Hồ sơ người đeo đi theo hướng ngược lại qua topic retained `config`.

Bản local chưa có tài khoản/ủy quyền; log chỉ ghi `session_id` ẩn danh và loại thao tác. Không dùng cho Internet hoặc dữ liệu bệnh nhân thật. BPM, bước, quãng đường và calo không phải số liệu y tế; quãng đường/kcal là ước tính từ hồ sơ người dùng.

## Bước tiếp theo

1. Tiếp tục chạy checklist tích hợp Pi thật sau mỗi thay đổi: unit test, I2C/MQTT preflight, dữ liệu đầu-cuối, công tắc ON/OFF, tự tắt và phục hồi sau mất broker. Dùng IP LAN của máy tính, không dùng `localhost` trên Pi.
2. Bảo mật cho môi trường thật: credential từng Pi và ACL topic đã có; còn thiếu MQTT TLS, HTTPS, đăng nhập người dùng và phân quyền xem thiết bị.
3. Bản Android Capacitor đã dùng chung giao diện/API với dashboard. Trước khi phát hành thật, bổ sung đăng nhập, HTTPS, icon/splash chính thức, ký release và kiểm thử trên nhiều thiết bị.
4. Edge AI đếm bước **đã triển khai** (`walk-gate-rf`, xem [ml/README.md](ml/README.md)); kết quả lưu kèm tên/phiên bản/xác suất và không ghi đè bộ đếm thuật toán. Việc tiếp theo là ghi dữ liệu MPU6050 của nhóm theo [docs/data-collection.md](docs/data-collection.md), đo sai số trên thiết bị và huấn luyện lại.
5. Khi chuyển cloud, chạy migration và backup DB, dùng domain/TLS, giám sát ingest/API và thiết kế lưu đệm trên Pi khi mất mạng.

Xem [kiến trúc chi tiết](docs/ARCHITECTURE.md) và [hướng dẫn chạy local](infra/local/README.md).
