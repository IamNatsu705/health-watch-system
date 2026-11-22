# Health Watch System

Hệ thống theo dõi sức khỏe thử nghiệm gồm Raspberry Pi, cảm biến, MQTT,
PostgreSQL, FastAPI, dashboard web và ứng dụng Android. Raspberry Pi xử lý
cảm biến tại biên, hiển thị lên TFT, điều khiển LED/còi và trao đổi dữ liệu hai
chiều với backend.

> Đây là dự án học tập, **không phải thiết bị y tế**. BPM, bước chân, calo và
> phát hiện ngã chưa được kiểm định lâm sàng.

## 1. Tính năng hiện có

- Raspberry Pi đọc MPU6050 và MAX30102 qua I2C.
- Hiển thị BPM ước tính, bước, quãng đường, calo và cảnh báo trên TFT ST7789.
- Nút SOS tại thiết bị bật LED đỏ và còi; phát hiện ngã chỉ bật LED đỏ.
- Pi gửi telemetry, event và trạng thái online/offline qua MQTT QoS 1.
- Ingest kiểm tra JSON Schema, chống bản tin trùng và ghi PostgreSQL.
- FastAPI cung cấp dữ liệu thiết bị, lịch sử, event và nhật ký phiên người dùng.
- Web và APK Android dùng chung giao diện Vue.
- Công tắc ON/OFF trên web/app gửi lệnh cảnh báo từ xa qua API → MQTT → Pi.
- Pi xác nhận trạng thái thật của còi/LED qua `alert-state`; backend chặn bật
  lặp khi còi đã bật hoặc lệnh bật trước vẫn đang chờ.
- Có mock publisher để chạy toàn bộ backend/web khi chưa có phần cứng.
- Có script triển khai source lên Pi, backup source cũ và service systemd tự chạy.

AI/Edge AI chưa được triển khai. Vị trí mở rộng được mô tả trong
[kiến trúc](docs/ARCHITECTURE.md).

## 2. Kiến trúc chạy thật

```text
Raspberry Pi                                  Máy tính local / cloud
┌────────────────────────┐                    ┌──────────────────────────┐
│ MPU6050 + MAX30102     │  telemetry/events │ Mosquitto MQTT           │
│ Nút SOS + TFT          ├───────────────────►│          │               │
│ LED xanh/đỏ + còi      │                    │          ▼               │
│                        │                    │ ingest → PostgreSQL      │
│ main.py                │                    │              │           │
│ ├─ xử lý cảm biến      │                    │              ▼           │
│ ├─ cảnh báo tại chỗ    │◄───────────────────┤ API ← web / Android      │
│ └─ MQTT nền            │ commands           │  │                       │
│         │              ├───────────────────►│  └─ MQTT command client │
│         └─ alert-state │ xác nhận output    └──────────────────────────┘
└────────────────────────┘
```

Mất mạng không làm dừng đọc cảm biến hoặc cảnh báo tại chỗ. Hàng đợi MQTT
hiện nằm trong RAM; đây chưa phải cơ chế lưu bền vững khi Pi mất điện.

## 3. Cấu trúc thư mục và nơi chạy

| Đường dẫn | Chức năng | Chạy ở đâu |
| --- | --- | --- |
| [`health_watch/`](health_watch/README.md) | Cảm biến, TFT, nút, LED/còi, MQTT và systemd | Raspberry Pi |
| [`backend/ingest/`](backend/ingest/README.md) | Nhận MQTT, kiểm tra schema, ghi DB | PC local / cloud |
| [`backend/api/`](backend/api/README.md) | FastAPI, truy vấn DB, phát MQTT command | PC local / cloud |
| [`backend/mock_publisher/`](backend/mock_publisher/README.md) | Giả lập telemetry/event của Pi | Chỉ local |
| [`web/`](web/README.md) | Vue dashboard và Android Capacitor | PC / điện thoại |
| [`contracts/`](contracts/README.md) | JSON Schema, topic và quy tắc phiên bản | Dùng chung |
| [`infra/local/`](infra/local/README.md) | Docker Compose local | PC |
| [`infra/cloud/`](infra/cloud/README.md) | Checklist chuyển cloud, chưa triển khai | Tài liệu |
| [`scripts/deploy_pi.ps1`](scripts/deploy_pi.ps1) | Backup và chép source Pi | PowerShell Windows |
| [`docs/runbooks/`](docs/runbooks/README.md) | Vận hành, log, rollback, xử lý lỗi | Người vận hành |

Máy tính là nguồn mã chính. Chỉ thư mục `health_watch/` được chép lên Pi;
không chép `backend/`, `web/`, `infra/`, APK hoặc secret lên Pi.

## 4. Yêu cầu

### Máy tính Windows

- Windows 10/11 64-bit.
- Docker Desktop đang chạy và dùng Linux containers.
- PowerShell 5.1 trở lên.
- OpenSSH Client (`ssh`, `scp`) nếu triển khai Pi.
- Git nếu quản lý source bằng GitHub.
- Node.js 20+ chỉ cần khi chạy/build web ngoài Docker.
- JDK 21 và Android SDK chỉ cần khi build APK.

Kiểm tra nhanh:

```powershell
docker version
docker compose version
ssh -V
node --version
java -version
```

### Raspberry Pi

- Raspberry Pi 4 chạy Raspberry Pi OS/Debian; dự án đã thử với Debian 13.
- Python 3, I2C, SPI và kết nối mạng cùng LAN với máy tính.
- Mạch theo [hướng dẫn phần cứng](docs/hardware/README.md).

## 5. Chạy nhanh bằng mock data

Thực hiện trong PowerShell tại thư mục gốc dự án:

```powershell
Set-Location 'C:\Project\health_watch_system'
if (-not (Test-Path .\infra\local\.env)) { Copy-Item .\infra\local\.env.example .\infra\local\.env }
notepad .\infra\local\.env
docker compose --env-file infra/local/.env -f infra/local/compose.yaml --profile mock up --build -d
docker compose --env-file infra/local/.env -f infra/local/compose.yaml --profile mock ps
```

Đổi `POSTGRES_PASSWORD` và `MQTT_PASSWORD` trong `.env` nếu máy tính dùng
chung mạng với người khác. Giá trị mẫu chỉ dành cho demo local.

Mở:

- Dashboard: <http://localhost:5173>
- API Swagger: <http://localhost:8000/docs>
- API health: <http://localhost:8000/health>
- MQTT broker: `localhost:1883`

Mock gửi telemetry mỗi giây và event ngã/SOS trong chu kỳ 60 giây. Mock hiện
không mô phỏng GPIO và `alert-state`, vì vậy công tắc còi từ xa chỉ hoạt động
với Pi thật đã chạy code mới.

Kiểm tra đường dữ liệu:

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/api/v1/devices
Invoke-RestMethod http://localhost:8000/api/v1/devices/pi-watch-mock-001/latest
docker compose --env-file infra/local/.env -f infra/local/compose.yaml --profile mock exec -T ingest python -m backend.smoke_local
```

Kết quả smoke test đúng:

```text
PASS: MQTT -> ingest -> PostgreSQL -> API; duplicate and invalid messages rejected
```

## 6. Chạy với Raspberry Pi thật

### 6.1 Khởi động server local, tắt mock

```powershell
Set-Location 'C:\Project\health_watch_system'
docker compose --env-file infra/local/.env -f infra/local/compose.yaml --profile mock stop mock-pi
docker compose --env-file infra/local/.env -f infra/local/compose.yaml up --build -d
docker compose --env-file infra/local/.env -f infra/local/compose.yaml ps
ipconfig
```

Ghi IPv4 của card Wi-Fi/Ethernet cùng mạng với Pi. Ví dụ trong quá trình thử:
`172.20.10.11`. Không dùng `localhost` trong cấu hình Pi hoặc Android.

Nếu Windows Firewall chặn, chỉ cho phép inbound TCP trên mạng Private:

- `1883`: Pi kết nối MQTT.
- `8000`: điện thoại gọi API.
- `5173`: trình duyệt thiết bị khác mở web, nếu cần.

Không port-forward các cổng này ra Internet.

### 6.2 Chép source lên Pi

Chạy trên PowerShell Windows, không chạy trong terminal SSH của Pi:

```powershell
Set-Location 'C:\Project\health_watch_system'
powershell -ExecutionPolicy Bypass -File .\scripts\deploy_pi.ps1 -PiHost pi.local
```

Nếu mDNS không tìm được `pi.local`, dùng IP Pi:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\deploy_pi.ps1 -PiHost 172.20.10.2
```

Script backup source Pi vào `backups/source-YYYYMMDD-HHMMSS.tar.gz`, chỉ
chép allowlist source cần chạy và giữ nguyên `.env`, `.venv`, backup trên Pi.

### 6.3 Cài dependency trên Pi

Trong terminal SSH Pi:

```bash
cd /home/pi/projects/health_watch
bash deploy/pi/setup.sh
sudo reboot
```

Sau reboot:

```bash
cd /home/pi/projects/health_watch
ls -l /dev/i2c-1 /dev/spidev0.0
.venv/bin/python check_i2c.py
```

Kết quả I2C cần có `0x57` và `0x68` (`0x69` nếu AD0 của MPU6050 ở mức cao).

### 6.4 Cấu hình MQTT trên Pi

```bash
cd /home/pi/projects/health_watch
cp -n .env.example .env
nano .env
chmod 600 .env
```

Ví dụ:

```dotenv
MQTT_ENABLED=1
MQTT_HOST=172.20.10.11
MQTT_PORT=1883
MQTT_USERNAME=health_watch
MQTT_PASSWORD=mat_khau_khop_voi_infra_local_env
MQTT_DEVICE_ID=pi-watch-001
MQTT_PUBLISH_INTERVAL_S=1.0
MQTT_KEEPALIVE_S=30
MQTT_OUTBOX_SIZE=200
```

### 6.5 Preflight và chạy tay

Không chạy test GPIO khi service đang giữ chân:

```bash
sudo systemctl stop health-watch 2>/dev/null || true
cd /home/pi/projects/health_watch
timedatectl show -p NTPSynchronized
.venv/bin/python check_i2c.py
.venv/bin/python -m unittest discover -s tests -v
set -a
. ./.env
set +a
.venv/bin/python check_mqtt.py
./run.sh
```

`check_mqtt.py` chỉ kiểm tra xác thực, không publish dữ liệu thử. Dừng lần chạy
tay bằng `Ctrl+C` trước khi cài service.

### 6.6 Chạy nền bằng systemd

```bash
cd /home/pi/projects/health_watch
./deploy/pi/install_service.sh
sudo systemctl status health-watch --no-pager
sudo journalctl -u health-watch -f
```

Xem [README của Pi](health_watch/README.md) và
[runbook](docs/runbooks/README.md) để kiểm thử mạch, cập nhật và rollback.

## 7. Sử dụng web và APK

### Web

Mở <http://localhost:5173>, chọn `pi-watch-001` và theo dõi BPM, trạng thái
ngón tay, bước, quãng đường, calo, online/offline và event ngã/SOS.

Công tắc cảnh báo:

- `OFF`: còi đang tắt.
- `ON`: Pi đã xác nhận còi bật.
- viền vàng/nhấp nháy: đang chờ Pi xác nhận.
- offline/không có `alert-state`: công tắc bị khóa.

Lệnh bật mặc định kéo dài 10 giây rồi Pi tự tắt. API từ chối bật lặp nếu còi
đã bật hoặc lệnh bật trước vẫn đang chờ.

### Android APK

APK debug nằm ở:

```text
HealthWatch-debug.apk
web/android/app/build/outputs/apk/debug/app-debug.apk
```

Cài bằng ADB:

```powershell
adb install -r .\HealthWatch-debug.apk
```

Trong app, nhập API theo IP máy tính, ví dụ `http://172.20.10.11:8000`.
Điện thoại và PC phải cùng LAN. Chi tiết tại [web/README.md](web/README.md).

## 8. Lệnh vận hành thường dùng

```powershell
docker compose --env-file infra/local/.env -f infra/local/compose.yaml ps
docker compose --env-file infra/local/.env -f infra/local/compose.yaml logs -f ingest api web mosquitto
docker compose --env-file infra/local/.env -f infra/local/compose.yaml up --build -d
docker compose --env-file infra/local/.env -f infra/local/compose.yaml down
```

```bash
sudo systemctl restart health-watch
sudo systemctl status health-watch --no-pager
sudo journalctl -u health-watch -n 100 --no-pager
```

`down` giữ volume PostgreSQL. Không dùng `down -v` nếu chưa chủ ý xóa dữ liệu.

## 9. Kiểm thử

| Phạm vi | Lệnh |
| --- | --- |
| Logic Pi | `.venv/bin/python -m unittest discover -s tests -v` trên Pi |
| Web production build | `npm run build` trong `web/` |
| APK debug | `npm run android:apk` trong `web/` |
| MQTT → DB → API | `python -m backend.smoke_local` trong container ingest |
| API health | `Invoke-RestMethod http://localhost:8000/health` |

Test phần mềm không xác nhận độ chính xác y tế hoặc chất lượng dây/mạch thật.

## 10. Dữ liệu và giao thức

MQTT dùng năm topic:

```text
health/v1/devices/{device_id}/telemetry
health/v1/devices/{device_id}/events
health/v1/devices/{device_id}/status
health/v1/devices/{device_id}/commands
health/v1/devices/{device_id}/alert-state
```

Xem [MQTT contract](contracts/mqtt/README.md) và
[API](backend/api/README.md). PostgreSQL có bốn bảng chính: `devices`,
`telemetry_samples`, `device_events`, `user_activity_logs`.

## 11. Giới hạn bảo mật và chuyển cloud

Bản local hiện chưa có đăng nhập/phân quyền; CORS mở; MQTT không TLS và dùng
một tài khoản chung; Android debug cho phép HTTP; `alert-state` nằm trong bộ
nhớ API và MQTT retained, không lưu DB; chưa có lịch backup ngoài máy.

Không dùng bản local qua Internet hoặc với dữ liệu bệnh nhân thật. Trước khi
chuyển cloud cần HTTPS, MQTT TLS, credential/ACL theo thiết bị, xác thực người
dùng, backup/restore, giám sát, rate limit và audit. Xem
[infra/cloud/README.md](infra/cloud/README.md).

## 12. Tài liệu chi tiết

- [Kiến trúc và luồng dữ liệu](docs/ARCHITECTURE.md)
- [Phần cứng và nối dây](docs/hardware/README.md)
- [Vận hành, log, cập nhật và rollback](docs/runbooks/README.md)
- [Raspberry Pi](health_watch/README.md)
- [Backend](backend/README.md)
- [Web và Android](web/README.md)
- [Docker local](infra/local/README.md)
- [Cloud checklist](infra/cloud/README.md)
- [MQTT contract](contracts/mqtt/README.md)
- [Kiểm thử](tests/README.md)
