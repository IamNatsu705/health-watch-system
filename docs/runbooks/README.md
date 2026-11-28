# Runbook cài đặt và vận hành local với Raspberry Pi thật

Mô hình hiện tại:

- Windows chạy Mosquitto, PostgreSQL, ingest, FastAPI và web bằng Docker Compose;
- Raspberry Pi chạy `health_watch/` và service `health-watch`;
- web/Android gọi API trên Windows;
- Pi và điện thoại không truy cập PostgreSQL trực tiếp.

## 1. Khởi động backend trên Windows

Từ PowerShell ở thư mục gốc:

```powershell
Set-Location C:\Project\health_watch_system
if (-not (Test-Path infra/local/.env)) { Copy-Item infra/local/.env.example infra/local/.env }
docker compose --env-file infra/local/.env -f infra/local/compose.yaml up --build -d --remove-orphans
docker compose --env-file infra/local/.env -f infra/local/compose.yaml ps
Invoke-RestMethod http://localhost:8000/health
```

Chỉ chạy lệnh `Copy-Item` lần đầu; nếu `.env` đã có thì giữ credential hiện tại. Lấy IP LAN bằng `ipconfig`. Ví dụ phiên đã thử là `172.20.10.11`, nhưng IP có thể thay đổi.

Windows Firewall cần cho phép trên mạng Private:

- TCP 1883: Pi tới MQTT;
- TCP 8000: Android/máy khác tới API;
- TCP 5173: mở dashboard từ thiết bị khác nếu cần.

Không port-forward các cổng này ra Internet.

## 2. Đưa mã Pi từ Windows sang Raspberry Pi

Chạy trên PowerShell Windows, không chạy trong terminal SSH:

```powershell
Set-Location C:\Project\health_watch_system
powershell -ExecutionPolicy Bypass -File .\scripts\deploy_pi.ps1 -PiHost pi.local
```

Script chỉ chép các file cần cho Pi, giữ nguyên `.env` và `.venv`, đồng thời tạo backup source ở:

```text
/home/pi/projects/health_watch/backups/source-YYYYMMDD-HHMMSS.tar.gz
```

Nếu mDNS không hoạt động, dùng IP Pi:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\deploy_pi.ps1 -PiHost 172.20.10.2
```

## 3. Cài lần đầu trên Pi

```bash
ssh pi@pi.local
cd /home/pi/projects/health_watch
bash deploy/pi/setup.sh
cp -n .env.example .env
nano .env
```

Đặt ít nhất:

```dotenv
MQTT_HOST=172.20.10.11
MQTT_PORT=1883
MQTT_USERNAME=<giống infra/local/.env>
MQTT_PASSWORD=<giống infra/local/.env>
MQTT_DEVICE_ID=pi-01
```

Không copy `.venv` từ Windows sang Pi. Script setup tạo môi trường Python đúng kiến trúc ARM.

## 4. Preflight trên Pi

Dừng service trước khi chạy tay:

```bash
cd /home/pi/projects/health_watch
sudo systemctl stop health-watch 2>/dev/null || true
timedatectl show -p NTPSynchronized
ls -l /dev/i2c-1 /dev/spidev0.0
.venv/bin/python check_i2c.py
.venv/bin/python -m unittest discover -s tests -v
set -a
. ./.env
set +a
.venv/bin/python check_mqtt.py
./run.sh
```

Kết quả mong đợi:

- `NTPSynchronized=yes`;
- I2C có `0x57` và `0x68` hoặc `0x69`;
- bộ test Pi hiện tại qua;
- `check_mqtt.py` xác thực thành công nhưng không publish dữ liệu thử;
- `run.sh` nhận cả hai cảm biến và MQTT báo online.

Dừng lần chạy tay bằng `Ctrl+C`.

## 5. Cài và bật systemd

```bash
cd /home/pi/projects/health_watch
./deploy/pi/install_service.sh
sudo systemctl status health-watch --no-pager
sudo journalctl -u health-watch -n 50 --no-pager
```

Service được bật tự khởi động. Các lệnh thường dùng:

```bash
sudo systemctl restart health-watch
sudo systemctl stop health-watch
sudo systemctl start health-watch
sudo journalctl -u health-watch -f
```

Không chạy `main.py`, `run.sh`, `check_alerts.py` hoặc chương trình GPIO cũ khi service đang chạy.

## 6. Kiểm tra dữ liệu đầu-cuối

Trên Windows:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/devices
docker compose --env-file infra/local/.env -f infra/local/compose.yaml logs --tail 100 ingest api
```

Mở <http://localhost:5173>, chọn `MQTT_DEVICE_ID` của Pi và kiểm tra dữ liệu cập nhật. Chỉ thiết bị trong `MQTT_DEVICES` được hiển thị.

## 7. Kiểm tra công tắc cảnh báo từ xa

1. Đảm bảo Pi hiện online và đang được chọn.
2. Giao diện ban đầu phải hiển thị còi OFF sau khi nhận retained `alert-state`.
3. Gạt công tắc sang ON.
4. Giao diện chuyển sang chờ, sau đó ON khi Pi xác nhận; LED đỏ và còi bật.
5. Thử gạt về OFF để dừng sớm.
6. Bật lại và không thao tác: Pi phải tự tắt sau khoảng 10 giây, giao diện trở về OFF.
7. Khi đang ON/chờ, giao diện và API phải ngăn lệnh ON trùng.

Theo dõi đồng thời:

```bash
sudo journalctl -u health-watch -f
```

Và trên Windows:

```powershell
docker compose --env-file infra/local/.env -f infra/local/compose.yaml logs -f api mosquitto
```

Nếu công tắc không xác định được trạng thái, restart Pi service để nó publish retained state, sau đó kiểm tra API còn kết nối broker.

## 8. Cập nhật code Pi sau này

1. Sửa và test source trên Windows.
2. Chạy `scripts/deploy_pi.ps1`.
3. SSH vào Pi.
4. Nếu `requirements.txt` đổi, chạy lại `bash deploy/pi/setup.sh`.
5. Chạy test.
6. Restart service và xem log.

```bash
cd /home/pi/projects/health_watch
.venv/bin/python -m unittest discover -s tests -v
sudo systemctl restart health-watch
sudo journalctl -u health-watch -n 50 --no-pager
```

## 9. Rollback source Pi

Chọn đúng backup trước khi giải nén:

```bash
cd /home/pi/projects/health_watch
ls -lh backups/
sudo systemctl stop health-watch
tar -xzf backups/source-YYYYMMDD-HHMMSS.tar.gz
sudo systemctl start health-watch
sudo journalctl -u health-watch -n 50 --no-pager
```

Backup source không chứa `.env` hoặc `.venv`.

## 10. Vận hành Docker và dữ liệu

```powershell
# Xem trạng thái và log
docker compose --env-file infra/local/.env -f infra/local/compose.yaml ps
docker compose --env-file infra/local/.env -f infra/local/compose.yaml logs --tail 100

# Dừng nhưng giữ dữ liệu PostgreSQL
docker compose --env-file infra/local/.env -f infra/local/compose.yaml down

# CẢNH BÁO: xóa cả volume và dữ liệu local
docker compose --env-file infra/local/.env -f infra/local/compose.yaml down -v
```

Không dùng `down -v` nếu chưa chủ động chấp nhận mất dữ liệu local.

## 11. Chẩn đoán nhanh

| Hiện tượng | Kiểm tra đầu tiên |
| --- | --- |
| Pi offline trên web | `systemctl status`, `journalctl`, `check_mqtt.py`, IP broker |
| MQTT báo từ chối | Trên Pi `MQTT_USERNAME` = `MQTT_DEVICE_ID`; mật khẩu khớp mục của Pi trong `MQTT_DEVICES` |
| MQTT timeout | Cùng mạng, IP Windows hiện tại, firewall TCP 1883 |
| Không có dữ liệu DB | Log `ingest`, schema/topic và migration |
| API lỗi | `/health`, log `api`, trạng thái PostgreSQL/MQTT |
| APK không vào API | Dùng IP LAN thay `localhost`; mở TCP 8000 |
| Công tắc bị khóa | Thiết bị phải online và đã gửi `alert-state` |
| Bước chân không tăng | Log Pi: `imu=`, `fifo_overflow=`, `steps_ai=`; web hiện cảnh báo IMU nếu cảm biến lỗi |
| Web báo "Dữ liệu cũ" | Pi không gửi telemetry mới: kiểm tra service, mạng, log `Rejected` của ingest |
| Công tắc chờ mãi | Log API/Pi/broker; topic command và credential |
| Còi đang bật nhưng web báo OFF | Kiểm tra Pi publish retained `alert-state`, restart API/Pi có kiểm soát |
| Thiếu `0x57`/`0x68` | Nguồn 3,3 V, GND chung, SDA/SCL, dây/mối hàn |
| GPIO bận/hành vi lạ | Dừng service và mọi chương trình cũ dùng GPIO5/22/23/27 |
| Service restart liên tục | Xem journal; sửa lỗi rồi `sudo systemctl reset-failed health-watch` |

## 12. Tắt hệ thống an toàn

Trên Pi:

```bash
sudo systemctl stop health-watch
sudo shutdown -h now
```

Chờ Pi tắt hoàn toàn trước khi tháo nguồn. Trên Windows, dùng `docker compose ... down` để giữ volume.

Đây là hệ thống thử nghiệm. Trước khi đưa lên Internet cần MQTT TLS/ACL, credential riêng từng thiết bị, HTTPS, đăng nhập/phân quyền, backup, monitoring và quy trình cập nhật an toàn.
