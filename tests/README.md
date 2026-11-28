# Kiểm thử hệ thống

Các lớp kiểm thử được tách theo phạm vi để dễ xác định lỗi nằm ở logic Pi, backend hay kết nối thật.

## 1. Ma trận kiểm thử

| Lớp | Vị trí | Cần phần cứng/dịch vụ | Mục tiêu |
| --- | --- | --- | --- |
| Unit Pi | `health_watch/tests/` | Không | Driver MPU6050 FIFO (bus giả lập thanh ghi), bộ lọc, đếm bước, mô hình AI trên 2 đoạn dữ liệu thật OxWalk, hồ sơ/lưu trạng thái, phát hiện ngã, alert, telemetry v2, MQTT, screen |
| Backend | `backend/tests/` | Không (SQLite trong bộ nhớ) | Contract dùng chính mã tạo payload của Pi; ingest từ chối dữ liệu sai/thiết bị lạ; API latest/daily/profile; trạng thái cảnh báo |
| Đánh giá AI | `ml/` | PC + dataset thật | Sai số đếm bước theo người (xem `ml/README.md`) |
| Build web | `web/` | Node.js | Bắt lỗi compile/bundle |
| Android build | `web/android/` | Node/JDK/Android SDK | Tạo APK debug |
| Tích hợp Pi thật | [integration/README.md](integration/README.md) | Toàn bộ hệ thống | MQTT, DB, web/app, command và GPIO |

## 2. Unit test trên Raspberry Pi

```bash
cd /home/pi/projects/health_watch
.venv/bin/python -m unittest discover -s tests -v
```

Các test này cũng chạy được trên PC (`python -m unittest discover -s tests -v` trong
`health_watch/`). Chúng thay phần cứng bằng bus I2C giả lập thanh ghi, nên không xác
nhận dây phần cứng thật.

## 3. Backend test

Từ thư mục gốc, với Python có `backend/requirements.txt` và `pytest`, `httpx`:

```powershell
python -m pytest backend/tests
```

Test dùng SQLite trong bộ nhớ, **không ghi gì vào PostgreSQL thật**. Repo không còn
smoke test ghi dữ liệu thử vào DB đang dùng.

## 4. Kiểm định độ chính xác đếm bước

Đánh giá mô hình trên dữ liệu thật: [ml/README.md](../ml/README.md). Đánh giá trên
MPU6050 của nhóm: [docs/data-collection.md](../docs/data-collection.md).

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
- Backend test qua.
- Log Pi có `Đã nạp mô hình walk-gate-rf`, `imu=ok`, `fifo_overflow=0`.
- Dữ liệu Pi hiện trong API/web, nguồn đếm bước là AI.
- Công tắc ON/OFF được xác nhận bằng GPIO thật và `alert-state`.
- Mất broker không làm treo vòng lặp phần cứng; cảnh báo tự tắt đúng hạn.

Test phần mềm không chứng minh độ chính xác y tế, độ bền phần cứng hoặc an toàn của việc tạo cú ngã thật.
