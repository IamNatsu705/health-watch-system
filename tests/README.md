# Kiểm thử hệ thống

Các lớp kiểm thử được tách theo phạm vi để dễ xác định lỗi nằm ở logic Pi, backend hay kết nối thật.

## 1. Ma trận kiểm thử

| Lớp | Vị trí | Cần phần cứng/dịch vụ | Mục tiêu |
| --- | --- | --- | --- |
| Unit Pi | `health_watch/tests/` | Không | Phát hiện ngã, alert output, telemetry factory, outbox MQTT, screen |
| Backend unit | `backend/tests/` | Tùy test; chạy trong image API | Command và trạng thái cảnh báo |
| Smoke local | `backend/smoke_local.py` | Docker stack + mock | Schema, ingest, chống trùng, API |
| Build web | `web/` | Node.js | Bắt lỗi compile/bundle |
| Android build | `web/android/` | Node/JDK/Android SDK | Tạo APK debug |
| Tích hợp Pi thật | [integration/README.md](integration/README.md) | Toàn bộ hệ thống | MQTT, DB, web/app, command và GPIO |

## 2. Unit test trên Raspberry Pi

```bash
cd /home/pi/projects/health_watch
.venv/bin/python -m unittest discover -s tests -v
```

Các test này dùng giả lập/phụ thuộc được thay thế, không xác nhận dây phần cứng thật.

## 3. Backend test bằng Docker

Từ thư mục gốc trên Windows:

```powershell
docker compose --env-file infra/local/.env -f infra/local/compose.yaml run --rm api python -m unittest discover -s backend/tests -v
```

## 4. Smoke test toàn bộ local

Khởi động stack với mock:

```powershell
docker compose --env-file infra/local/.env -f infra/local/compose.yaml --profile mock up --build -d
docker compose --env-file infra/local/.env -f infra/local/compose.yaml exec -T ingest python -m backend.smoke_local
```

Smoke test xác nhận dữ liệu giả đi qua broker, ingest, DB và API; đồng thời kiểm tra schema và chống ghi trùng. Mock không xử lý remote command, vì vậy không dùng bài này để xác nhận công tắc còi.

## 5. Build web và APK

```powershell
Set-Location C:\Project\health_watch_system\web
npm.cmd install
npm.cmd run build
npm.cmd run android:apk
```

Nếu chỉ sửa backend/Pi và máy chưa có Android SDK, tối thiểu vẫn chạy `npm.cmd run build`.

## 6. Tiêu chí trước khi chạy thật

- Tất cả unit test qua.
- `check_i2c.py` nhận đúng hai địa chỉ.
- `check_mqtt.py` xác thực được broker.
- Smoke local qua với mock.
- Khi chuyển sang Pi thật, mock đã dừng.
- Dữ liệu Pi hiện trong API/web.
- Công tắc ON/OFF được xác nhận bằng GPIO thật và `alert-state`.
- Mất broker không làm treo vòng lặp phần cứng; cảnh báo tự tắt đúng hạn.

Test phần mềm không chứng minh độ chính xác y tế, độ bền phần cứng hoặc an toàn của việc tạo cú ngã thật.
