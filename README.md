# Health Watch System

Hệ thống theo dõi sức khỏe gồm Raspberry Pi, cảm biến, MQTT, PostgreSQL, FastAPI,
dashboard web và ứng dụng Android. Raspberry Pi đọc cảm biến, **đếm bước bằng
thuật toán xử lý tín hiệu và AI chạy ngay trên Pi**, hiển thị lên TFT, điều khiển
LED/còi và trao đổi dữ liệu hai chiều với backend.

Hệ thống **chỉ dùng dữ liệu thật**. Không có thiết bị giả lập, và không giá trị
mặc định nào được hiển thị như số đo. Số nào chưa đo hoặc chưa ước tính được thì
hiển thị `--`.

> Đây là dự án học tập, **không phải thiết bị y tế**. BPM, bước chân, quãng đường,
> calo và phát hiện ngã chưa được kiểm định lâm sàng.

## 1. Tính năng

- Raspberry Pi đọc MPU6050 qua **FIFO 100 Hz** (lọc chống chồng phổ 44 Hz) và
  MAX30102 qua I2C.
- **Đếm bước có AI**: Random Forest "đang đi bộ hay không" chạy trên Pi, huấn
  luyện và đánh giá bằng dữ liệu thật (OxWalk, Clemson). Trên người chưa từng
  thấy, sai số mỗi người là 13,5%; thuật toán cũ sai 80%. Xem [ml/README.md](ml/README.md).
- Số bước hôm nay lưu trên Pi qua các lần khởi động lại. Quãng đường và kcal được
  ước tính từ chiều cao/cân nặng thật do người dùng nhập.
- TFT ST7789: BPM ước tính, bước hôm nay, quãng đường, kcal, trạng thái cảnh báo và
  lỗi cảm biến.
- Nút SOS bật LED đỏ và còi; phát hiện ngã chỉ bật LED đỏ.
- MQTT QoS 1, **mỗi Pi một tài khoản riêng + ACL**: thiết bị chỉ ghi được dữ liệu của
  chính nó.
- Ingest kiểm tra JSON Schema (có kiểm tra format), chỉ nhận thiết bị đã đăng ký,
  chặn bộ đếm giảm hoặc tăng vô lý, chống bản tin trùng.
- FastAPI cung cấp số đo mới nhất (kèm độ mới dữ liệu), lịch sử, tổng bước theo
  ngày, sự kiện, hồ sơ người đeo và nhật ký phiên người dùng.
- Web và APK Android dùng chung giao diện Vue. Dữ liệu cũ được ghi rõ là cũ.
- Công tắc ON/OFF trên web/app gửi lệnh cảnh báo từ xa qua API → MQTT → Pi. Pi xác
  nhận trạng thái thật của còi/LED qua `alert-state`.
- Công cụ `record_imu.py` để nhóm ghi dữ liệu MPU6050 thật có nhãn, phục vụ kiểm
  định và huấn luyện lại AI.

## 2. Kiến trúc

```text
Raspberry Pi                                  Máy tính local
┌──────────────────────────┐                  ┌──────────────────────────┐
│ MPU6050 (FIFO 100 Hz)    │  telemetry v2   │ Mosquitto (ACL/thiết bị) │
│  └─ đếm bước + AI        ├─────────────────►│          │               │
│ MAX30102, nút SOS, TFT   │  events/status   │          ▼               │
│ LED xanh/đỏ + còi        │                  │ ingest → PostgreSQL      │
│                          │◄─────────────────┤              │           │
│ main.py                  │ commands, config │              ▼           │
│ state/ (bước hôm nay,    ├─────────────────►│ API ← web / Android      │
│  hồ sơ người đeo)        │ alert-state      └──────────────────────────┘
└──────────────────────────┘
```

Mất mạng không làm dừng đọc cảm biến, đếm bước hay cảnh báo tại chỗ. Hàng đợi MQTT
nằm trong RAM; khi Pi dừng có kiểm soát, các bản tin còn chờ được gửi nốt trước.

## 3. Cấu trúc thư mục

| Đường dẫn | Chức năng | Chạy ở đâu |
| --- | --- | --- |
| [`health_watch/`](health_watch/README.md) | Cảm biến, đếm bước + AI, TFT, LED/còi, MQTT, systemd | Raspberry Pi |
| [`ml/`](ml/README.md) | Huấn luyện/đánh giá AI đếm bước trên dữ liệu thật | PC |
| [`backend/ingest/`](backend/ingest/README.md) | Nhận MQTT, kiểm tra, ghi DB | PC local |
| [`backend/api/`](backend/api/README.md) | FastAPI, truy vấn DB, MQTT commands/config | PC local |
| [`web/`](web/README.md) | Vue dashboard và Android Capacitor | PC / điện thoại |
| [`contracts/`](contracts/README.md) | JSON Schema, topic và quy tắc phiên bản | Dùng chung |
| [`infra/local/`](infra/local/README.md) | Docker Compose local | PC |
| [`scripts/deploy_pi.ps1`](scripts/deploy_pi.ps1) | Backup và chép source lên Pi | PowerShell Windows |
| [`docs/`](docs/README.md) | Kiến trúc, phần cứng, thu dữ liệu, runbook | Tài liệu |

Chỉ thư mục `health_watch/` được chép lên Pi.

## 4. Yêu cầu

- Windows 10/11, Docker Desktop (Linux containers), PowerShell 5.1+, OpenSSH Client.
- Node.js 20+ nếu chạy/build web ngoài Docker; JDK 21 + Android SDK nếu build APK.
- Python 3.11+ trên PC nếu chạy test backend hoặc huấn luyện AI.
- Raspberry Pi 4, Raspberry Pi OS/Debian (đã thử Debian 13), I2C + SPI, cùng LAN với PC.
- Mạch theo [hướng dẫn phần cứng](docs/hardware/README.md).

## 5. Khởi động server local

Thực hiện trong PowerShell tại thư mục gốc dự án:

```powershell
if (-not (Test-Path .\infra\local\.env)) { Copy-Item .\infra\local\.env.example .\infra\local\.env }
notepad .\infra\local\.env
docker compose --env-file infra/local/.env -f infra/local/compose.yaml up --build -d
docker compose --env-file infra/local/.env -f infra/local/compose.yaml ps
```

Trong `.env`, đổi mọi mật khẩu. `MQTT_DEVICES` liệt kê **các Pi thật** được phép gửi
dữ liệu, mỗi Pi theo dạng `id:mat_khau_rieng`, ví dụ
`MQTT_DEVICES=pi-watch-001:ChuoiNgauNhienDai`. Thiết bị không có trong danh sách
bị broker từ chối và bị ingest bỏ qua.

Nếu trước đây từng chạy bản cũ có mock: migration `0002` tự xóa dữ liệu của
`pi-watch-mock-*` và `smoke-*`. Nếu từng đặt `MOCK_DEVICE_ID` trùng ID của Pi thật
thì không tách được dữ liệu giả. Khi đó hãy tạo lại DB:
`docker compose ... down -v` (xóa toàn bộ dữ liệu cũ), rồi chạy lại `up`.

Mở dashboard <http://localhost:5173>, API Swagger <http://localhost:8000/docs> và
API health <http://localhost:8000/health>. Dashboard trống cho đến khi Pi thật gửi
dữ liệu; đó là hành vi đúng.

Nếu Windows Firewall chặn, chỉ mở inbound TCP trên mạng Private: `1883` (Pi → MQTT),
`8000` (điện thoại → API), `5173` (thiết bị khác mở web). Không port-forward ra Internet.

## 6. Cài và chạy trên Raspberry Pi

### 6.1 Chép source lên Pi (PowerShell trên Windows)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\deploy_pi.ps1 -PiHost pi.local
```

Nếu không phân giải được `pi.local`, dùng IP của Pi. Script sao lưu source cũ vào
`backups/` và chỉ chép các file cần chạy. Các mục `.env`, `.venv`, `state/` và
`recordings/` trên Pi được giữ nguyên.

### 6.2 Cài dependency (SSH vào Pi)

```bash
cd /home/pi/projects/health_watch
bash deploy/pi/setup.sh
sudo reboot
```

Sau khi reboot, chạy `.venv/bin/python check_i2c.py`; kết quả phải có `0x57`
(MAX30102) và `0x68` (MPU6050).

### 6.3 Cấu hình MQTT trên Pi

```bash
cp -n .env.example .env && nano .env && chmod 600 .env
```

```dotenv
MQTT_ENABLED=1
MQTT_HOST=172.20.10.11          # IP LAN của máy tính, không dùng localhost
MQTT_PORT=1883
MQTT_DEVICE_ID=pi-watch-001
MQTT_USERNAME=pi-watch-001      # phải trùng MQTT_DEVICE_ID
MQTT_PASSWORD=ChuoiNgauNhienDai # khớp phần sau dấu ":" trong MQTT_DEVICES
```

**Nâng cấp từ bản cũ:** file `.env` cũ trên Pi dùng tài khoản chung `health_watch`.
Broker mới từ chối tài khoản đó cho thiết bị, nên phải sửa `MQTT_USERNAME` và
`MQTT_PASSWORD` như trên.

### 6.4 Kiểm tra và chạy

```bash
sudo systemctl stop health-watch 2>/dev/null || true
.venv/bin/python -c "import numpy"        # có numpy thì vẽ TFT nhanh hơn nhiều
.venv/bin/python -m unittest discover -s tests -v
set -a; . ./.env; set +a
.venv/bin/python check_mqtt.py
./run.sh
```

Log phải có dòng `Đã nạp mô hình walk-gate-rf 1.0.0` và `MPU6050 ok: {... 'chip': 'MPU6050' ...}`.
Nếu thiếu file mô hình, Pi vẫn đếm bằng thuật toán; khi đó `steps_ai` là `null`, không phải 0.

### 6.5 Chạy nền bằng systemd

```bash
./deploy/pi/install_service.sh
sudo journalctl -u health-watch -f
```

## 7. Sử dụng web và APK

Mở <http://localhost:5173>. Danh sách thiết bị chỉ gồm các Pi đã đăng ký; thiết bị
đang gửi dữ liệu được xếp lên đầu.

- **Bước chân:** tổng hôm nay, kèm nguồn đếm (AI và phiên bản mô hình, hoặc thuật
  toán), trạng thái đang đi bộ, nhịp bước và số đếm của phiên hiện tại.
- **Quãng đường / kcal:** hiển thị `--` cho đến khi nhập chiều cao, cân nặng (và có thể
  nhập chiều dài bước tự đo) ở mục **Hồ sơ người đeo**. Hồ sơ được gửi xuống Pi qua
  topic `config`.
- **Dữ liệu cũ:** khi Pi ngừng gửi, thẻ số đo mờ đi và có dòng "không gửi dữ liệu mới
  từ X phút trước". Khi API lỗi, số liệu bị xóa khỏi màn hình thay vì đứng yên.
- **Công tắc cảnh báo:** ON/OFF do Pi xác nhận; bị khóa khi thiết bị offline.

APK debug nằm ở `web/android/app/build/outputs/apk/debug/app-debug.apk`. Cài bằng
`adb install -r`, rồi nhập địa chỉ API theo IP máy tính, ví dụ `http://172.20.10.11:8000`.
Chi tiết ở [web/README.md](web/README.md).

## 8. Thu dữ liệu thật và huấn luyện lại AI

Mô hình hiện tại được huấn luyện trên dữ liệu thật của OxWalk (cảm biến AX3), chưa
được đo trên MPU6050 của nhóm. Làm theo [docs/data-collection.md](docs/data-collection.md)
để ghi dữ liệu có đếm bước bằng `record_imu.py`, đo sai số thật trên thiết bị và huấn
luyện lại bằng `ml/train_walk_gate.py --team`.

## 9. Kiểm thử

| Phạm vi | Lệnh | Ghi chú |
| --- | --- | --- |
| Pi (driver FIFO, đếm bước, AI, MQTT, TFT) | `python -m unittest discover -s tests -v` trong `health_watch/` | Chạy được cả trên PC; test AI dùng hai đoạn dữ liệu thật của OxWalk |
| Backend (contract, ingest, API) | `python -m pytest backend/tests` ở thư mục gốc | SQLite trong bộ nhớ, không chạm DB thật |
| Web | `npm run build` trong `web/` | |
| Đầu-cuối | Pi thật gửi dữ liệu → dashboard | [tests/integration](tests/integration/README.md) |

Test không ghi dữ liệu nào vào DB thật.

## 10. Dữ liệu và giao thức

MQTT có các topic `telemetry` (v2), `events`, `status`, `commands`, `alert-state`
và `config` dưới `health/v1/devices/{device_id}/`. Xem
[MQTT contract](contracts/mqtt/README.md) và [API](backend/api/README.md).

PostgreSQL có các bảng `devices`, `telemetry_samples`, `device_events`,
`device_profiles` và `user_activity_logs`. Mỗi bản telemetry lưu kèm phiên bản
firmware, thuật toán, mô hình AI, trạng thái IMU và trạng thái đồng hồ, nên mọi số
liệu đều truy được nguồn gốc.

## 11. Giới hạn bảo mật

Bản local chưa có đăng nhập người dùng, CORS mở, MQTT chưa có TLS, Android debug cho
phép HTTP. Mỗi thiết bị đã có tài khoản MQTT riêng và ACL. Không mở hệ thống ra
Internet và không dùng với dữ liệu bệnh nhân thật. Trước khi lên cloud, xem
[infra/cloud/README.md](infra/cloud/README.md).

## 12. Tài liệu chi tiết

- [Kiến trúc và luồng dữ liệu](docs/ARCHITECTURE.md)
- [AI đếm bước: dữ liệu, mô hình, kết quả](ml/README.md)
- [Thu dữ liệu thật](docs/data-collection.md)
- [Phần cứng và nối dây](docs/hardware/README.md)
- [Vận hành, log, cập nhật và rollback](docs/runbooks/README.md)
- [Raspberry Pi](health_watch/README.md) · [Backend](backend/README.md) · [Web/Android](web/README.md)
- [Docker local](infra/local/README.md) · [MQTT contract](contracts/mqtt/README.md) · [Kiểm thử](tests/README.md)
