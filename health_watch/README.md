# Health Watch - edge runtime trên Raspberry Pi

Thư mục này dùng riêng cho bài cuối kỳ. `main.py` đọc GY-521/MPU6050 qua FIFO
100 Hz và MAX30102 qua I2C, đếm bước bằng thuật toán xử lý tín hiệu và AI chạy
trên Pi, ước tính quãng đường/kcal khi có hồ sơ người đeo thật, rồi hiện thông
tin lên TFT ST7789V3 240x280 qua SPI. MPU6050 cũng được dùng để thử
phát hiện ngã. Một worker nền gửi telemetry và sự kiện qua MQTT; mất mạng
không chặn vòng lặp cảm biến, màn hình, LED hoặc còi. Pi cũng nhận lệnh
cảnh báo từ web/app và trả trạng thái phần cứng thật qua MQTT.

## Thành phần trong thư mục

| Đường dẫn | Vai trò |
| --- | --- |
| `main.py` | Vòng lặp cảm biến, màn hình, cảnh báo và tích hợp MQTT |
| `config.py` | Chân GPIO, chu kỳ vòng lặp và cấu hình MQTT |
| `sensors/` | Driver MPU6050 (FIFO 100 Hz, tự phát hiện lỗi) và MAX30102 |
| `processing/` | Bộ lọc, đếm bước v2, đặc trưng cửa sổ, BPM thử nghiệm, phát hiện ngã |
| `inference/`, `models/` | Mô hình AI "đang đi bộ hay không" (JSON) và suy luận thuần Python |
| `user_profile.py`, `storage.py`, `step_tracker.py` | Hồ sơ người đeo, ước tính quãng đường/kcal cộng dồn, lưu bước hôm nay |
| `record_imu.py` | Ghi dữ liệu MPU6050 thật có nhãn để kiểm định/huấn luyện AI |
| `record_ppg.py`, `ppg_log.py` | Thu PPG thô (RED/IR) của MAX30102 ra `logs/ppg_*.csv`, `logs/fifo_*.csv` để nghiên cứu nhịp tim |
| `pulse_sensor.py` | MAX30102 trong vòng lặp chính: cô lập lỗi, khởi tạo lại khi FIFO tràn, ghi CSV nếu bật |
| `telemetry.py` | Tạo payload đúng hợp đồng MQTT (telemetry v2) |
| `mqtt_publisher.py` | Kết nối nền, outbox, nhận command/config và publish state |
| `check_*.py` | Kiểm tra I2C, GPIO/cảnh báo và MQTT |
| `tests/` | Unit test không cần phần cứng thật |
| `deploy/pi/` | Script setup và cài systemd |
| `run.sh` | Nạp `.env` rồi chạy chương trình |

## Mạch đang dùng

| Thiết bị | Chân Raspberry Pi (BCM) | Chân vật lý |
| --- | --- | --- |
| MPU6050 và MAX30102 SDA | GPIO2 | 3 |
| MPU6050 và MAX30102 SCL | GPIO3 | 5 |
| TFT SCL/SCLK | GPIO11 | 23 |
| TFT SDA/MOSI | GPIO10 | 19 |
| TFT CS/CE0 | GPIO8 | 24 |
| TFT DC | GPIO25 | 22 |
| TFT RES | GPIO24 | 18 |
| LED xanh (qua điện trở 220 Ω) | GPIO22 | 15 |
| LED đỏ (qua điện trở 220 Ω) | GPIO27 | 13 |
| MH-FMD I/O (kích mức thấp) | GPIO5 | 29 |
| Nút SOS, đầu còn lại nối GND | GPIO23 | 16 |

Nguồn các module: 3,3 V và GND chung. TFT `BLK` đang nối 3,3 V.
Còi MH-FMD có điện trở kéo lên 10 kΩ từ I/O tới 3,3 V. Nút dùng điện trở
kéo lên nội bộ của Pi. Không chạy đồng thời chương trình giữa kỳ đang dùng
các GPIO22/GPIO27/GPIO5. Còi dời từ GPIO17 sang GPIO5 vì GPIO5 có pull-up
mặc định khi Pi khởi động, nên còi kích mức thấp không kêu lúc boot.

## Chép từ Windows bằng PowerShell

Lệnh cũ `scp -r pi@pi.local:/home/pi/projects/health_watch ...` có chiều **Pi → Windows**. Khi đưa code mới lên thiết bị, đảo chiều: nguồn trên Windows đứng trước, đích `pi@...:` đứng sau.

Chạy trên **PowerShell của Windows**, từ thư mục dự án lớn `health_watch_system/`, không chạy trong terminal SSH. Cách khuyên dùng:

```powershell
Set-Location 'C:\Project\health_watch_system'
powershell -ExecutionPolicy Bypass -File .\scripts\deploy_pi.ps1 -PiHost pi.local
```

Nếu `pi.local` không phân giải được, dùng IP của Pi, ví dụ
`-PiHost 192.168.110.50`. Script chỉ chép allowlist source cần chạy, tạo bản
sao lưu source cũ trong `backups/`, và **giữ nguyên** `.env` cùng `.venv` trên
Pi. Nó không chép `backend/`, `web/`, `infra/`, APK, cache hoặc secret lên Pi.

Nếu muốn chạy SCP thủ công, tạo thư mục đích trước rồi chép theo chiều
Windows → Pi. Không dùng `scp -r .\health_watch` nếu thư mục Windows có
`.env` hoặc `.venv`:

```powershell
ssh pi@pi.local "mkdir -p /home/pi/projects/health_watch"
scp .\health_watch\main.py .\health_watch\config.py .\health_watch\alerts.py .\health_watch\screen.py .\health_watch\telemetry.py .\health_watch\mqtt_publisher.py .\health_watch\check_i2c.py .\health_watch\check_alerts.py .\health_watch\check_mqtt.py .\health_watch\requirements.txt .\health_watch\.env.example .\health_watch\run.sh pi@pi.local:/home/pi/projects/health_watch/
scp -r .\health_watch\sensors .\health_watch\processing .\health_watch\tests .\health_watch\deploy pi@pi.local:/home/pi/projects/health_watch/
```

Nếu username không phải `pi`, truyền thêm `-PiUser <username>` cho script.
Đường dẫn mặc định trên Pi là `/home/pi/projects/health_watch`.

## Chuẩn bị trên Pi 4, Debian 13 (Trixie)

Chạy trong phiên SSH:

```bash
cd /home/pi/projects/health_watch
bash deploy/pi/setup.sh
sudo reboot
```

Sau khi Pi lên lại, SSH vào và kiểm tra:

```bash
cd /home/pi/projects/health_watch
ls /dev/i2c-1 /dev/spidev0.0
.venv/bin/python check_i2c.py
```

`check_i2c.py` cần thấy `0x57` (MAX30102) và `0x68` (MPU6050; có thể là
`0x69` nếu AD0 được kéo lên cao). Nếu thiếu một địa chỉ, kiểm tra điện áp,
GND, SDA/SCL và mối hàn trước khi chạy `main.py`. Chương trình hiện đặt
MPU6050 ở `0x68` trong `config.py`.

`setup.sh` có thể chạy lại sau mỗi lần cập nhật `requirements.txt`; nó không
xóa `.venv`. Nếu `/dev/i2c-1` hoặc `/dev/spidev0.0` chưa xuất hiện, kiểm tra
I2C/SPI trong `raspi-config` rồi reboot. Bật lại venv thủ công bằng:

```bash
cd /home/pi/projects/health_watch
source .venv/bin/activate
```

## Cấu hình Pi gửi MQTT về máy tính local

Trên máy tính, khai báo Pi trong `infra/local/.env` (`MQTT_DEVICES=pi-watch-001:mat_khau_rieng`)
rồi chạy stack tại thư mục gốc dự án:

```powershell
docker compose --env-file infra/local/.env -f infra/local/compose.yaml up --build -d
ipconfig
```

Ghi lại IPv4 của card Wi-Fi/Ethernet cùng mạng với Pi. Broker phải cho phép
Windows Firewall nhận TCP cổng `1883`. Trên Pi, tạo file cấu hình riêng:

```bash
cd /home/pi/projects/health_watch
cp -n .env.example .env
nano .env
```

Sửa tối thiểu các giá trị sau. `MQTT_HOST` là IP của **máy tính**, không phải
`localhost`. Mỗi Pi có tài khoản MQTT riêng: `MQTT_USERNAME` trùng
`MQTT_DEVICE_ID`, và mật khẩu khớp phần sau dấu `:` của Pi này trong `MQTT_DEVICES`.
Broker chỉ cho tài khoản này ghi vào `health/v1/devices/pi-watch-001/...`.

```dotenv
MQTT_ENABLED=1
MQTT_HOST=192.168.1.10
MQTT_PORT=1883
MQTT_DEVICE_ID=pi-watch-001
MQTT_USERNAME=pi-watch-001
MQTT_PASSWORD=mat_khau_rieng
```

Nạp biến môi trường rồi chạy trong cùng terminal:

```bash
set -a
. ./.env
set +a
.venv/bin/python check_mqtt.py
./run.sh
```

`check_mqtt.py` chỉ xác thực với broker, không gửi số đo giả. Khi `run.sh`
đúng, terminal Pi báo `MQTT đã kết nối và gửi trạng thái online`. Trên máy
tính, mở <http://localhost:5173> hoặc gọi API `/api/v1/devices`. Mỗi lần chạy
có một `boot_id`; backend dùng nó cùng `sequence` để chống ghi trùng QoS 1.

## Chạy thử tích hợp

Thử riêng nút, hai LED và còi trước:

```bash
sudo systemctl stop health-watch 2>/dev/null || true
.venv/bin/python check_alerts.py
```

Khi thả nút: LED xanh sáng, LED đỏ và còi tắt. Khi giữ nút: LED đỏ và còi
bật, LED xanh tắt. Nhấn `Ctrl+C` để dừng; lúc đó cả hai LED và còi đều tắt.
Nếu còi kêu ngay khi khởi động, kiểm tra nhãn VCC/GND/I/O của module,
điện trở 10 kΩ kéo I/O lên 3,3 V và tránh nhầm thứ tự chân.

Sau đó chạy thử tích hợp:

```bash
./run.sh
```

Có thể kiểm tra logic phát hiện ngã và quy tắc còi/LED mà không cần tác động
lên phần cứng bằng:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Màn hình quay 180° theo cách đặt hiện tại; giao diện nền tối và các thẻ màu
hiển thị nhịp tim ước tính, bước chân, quãng đường, calo ước tính và trạng
thái cảnh báo. Terminal còn in gia tốc và IR thô để chẩn đoán cảm biến.
Khi chưa đặt tay, đồ thị nhịp tim là đường ngang và BPM hiện `--`. Đặt tay
ổn định trên vùng cảm biến cho tới khi terminal báo `finger=yes` và tích đủ
ít nhất 125 mẫu (khoảng 5 giây ở 25 mẫu/giây); nếu sóng chưa đều, BPM vẫn
hiện `--` thay vì đoán một con số.
Khi giữ nút SOS, đèn đỏ và còi bật, đèn xanh tắt; thả nút thì bình thường.
Khi web/app gửi lệnh cảnh báo từ xa, Pi bật đèn đỏ và còi trong 10 giây
(tối đa 60 giây theo contract), rồi tự tắt. Gạt công tắc trên web/app về
**OFF** để gửi lệnh dừng sớm.
Pi bỏ lệnh trùng, lệnh sai thiết bị và lệnh đã cũ; command MQTT không retained.
Mỗi khi còi hoặc LED đổi trạng thái, Pi gửi `alert-state` retained để web/app
hiển thị trạng thái phần cứng thật và backend chặn lệnh bật lặp.
Khi phát hiện ngã, **chỉ LED đỏ bật, còi tắt**; màn hình giữ dòng
`PHÁT HIỆN NGÃ`. Nhấn nút một lần để xác nhận và xóa cảnh báo; thả nút ra
trước khi dùng nút SOS tiếp. Nhấn `Ctrl+C` để dừng; chương trình gửi trạng
thái offline, dừng worker MQTT và tắt các ngõ ra khi thoát.
Nếu màn hình không hiện nhưng terminal vẫn có số, kiểm tra dây SPI, chân
`DC/RES/CS` và `BLK`. Nếu chương trình báo lỗi cảm biến, chạy lại
`.venv/bin/python check_i2c.py`.

Nếu xuất hiện `[Errno 5] Input/output error` khi di chuyển breadboard,
tắt nguồn Pi rồi kiểm tra và cắm chắc bốn dây nguồn/GND/SDA/SCL của cả hai
cảm biến. Mã sẽ thử lại tối đa 3 lần và ghi rõ lỗi ở MPU6050 hay MAX30102;
nếu vẫn lỗi liên tiếp thì dừng để tránh coi dữ liệu mất kết nối là số đo thật.

## Chạy tự động bằng systemd

Chỉ cài service sau khi `check_i2c.py`, `check_alerts.py`, `check_mqtt.py` và
`./run.sh` đều chạy đúng. Dừng lần chạy tay bằng `Ctrl+C`, rồi:

```bash
cd /home/pi/projects/health_watch
./deploy/pi/install_service.sh
sudo systemctl status health-watch --no-pager
sudo journalctl -u health-watch -f
```

Service chạy bằng user Pi, nạp `.env`, tự khởi động cùng máy và tự chạy lại
khi chương trình lỗi. Để sửa mạch hoặc chạy script kiểm tra GPIO, dừng service
trước để tránh hai tiến trình cùng giữ chân:

```bash
sudo systemctl stop health-watch
# chạy kiểm tra hoặc sửa mạch
sudo systemctl start health-watch
```

Quy trình cập nhật, xem log và khôi phục source cũ nằm trong
[runbook vận hành](../docs/runbooks/README.md).

Sau khi chép một phiên bản mới có thay đổi điều khiển MQTT, chạy:

```bash
cd /home/pi/projects/health_watch
.venv/bin/python -m unittest discover -s tests -v
sudo systemctl restart health-watch
sudo journalctl -u health-watch -n 30 --no-pager
```

## Đếm bước, AI và ghi dữ liệu thật

- MPU6050 lấy mẫu 100 Hz vào FIFO (lọc 44 Hz, đồng hồ PLL). Vòng lặp chính đọc FIFO
  mỗi 40 ms, nên vẽ TFT không làm mất mẫu. Log in `imu=ok fifo_overflow=0` khi bình
  thường. Nếu `fifo_overflow` tăng, vòng lặp bị chặn quá ~0,85 s (FIFO chứa gia tốc + gyro).
- Có hai bộ đếm: `steps_alg` (thuật toán `peak-bout-v2`) và `steps_ai` (cổng AI
  `walk-gate-rf`). Màn hình và web dùng số AI khi `models/walk_gate.json` nạp được;
  nếu thiếu hoặc hỏng file, Pi ghi cảnh báo và chỉ dùng thuật toán.
- Kết quả đánh giá trên dữ liệu thật nằm ở [ml/README.md](../ml/README.md). Cần đo lại
  trên MPU6050 của nhóm bằng `record_imu.py` theo [docs/data-collection.md](../docs/data-collection.md).
- Số bước, quãng đường, kcal hôm nay lưu ở `state/daily_steps.json` (mỗi 10 s và khi
  dừng), qua 0 giờ thì đặt lại theo múi giờ của Pi (`setup.sh` đặt `Asia/Ho_Chi_Minh`,
  đổi bằng biến `PI_TIMEZONE`). Pi không có RTC: trước khi NTP đồng bộ, màn hình ghi
  `BƯỚC TỪ KHI BẬT` và không nạp/ghi số của một ngày đoán sai; đồng bộ xong thì cộng
  vào đúng ngày.
- Hồ sơ người đeo nhận từ web/app qua MQTT `config` và lưu ở `state/profile.json`; cấu
  hình có `updated_at` cũ hơn bản đang dùng bị bỏ qua. Chưa có hồ sơ thì quãng đường
  và kcal là `--`. Quãng đường/kcal được cộng dồn theo từng nhóm bước với hồ sơ tại
  thời điểm đó, nên đổi hồ sơ không tính lại các bước trước.
- Khi MPU6050 lỗi (I2C, chip tự reset, dữ liệu đứng yên), màn hình hiện
  `LỖI CẢM BIẾN` và huy hiệu `IMU!`, bộ đếm dừng, Pi tự khởi tạo lại mỗi 2 s. Lỗi
  MAX30102 không làm dừng đếm bước.

## Thu dữ liệu PPG (nhịp tim)

Driver `sensors/max30102.py` giám sát FIFO (32 mẫu): khi FIFO tràn hoặc đầy, lô mẫu đó bị
bỏ. Tần số được chọn theo chế độ:

- `record_ppg.py` (nghiên cứu, không bật TFT): mặc định của driver là 200 Hz, trung bình 2,
  tức 100 mẫu/s; FIFO đệm 0,32 s.
- `main.py` (hệ thống đầy đủ): `MAX30102_SAMPLE_RATE=100`, `MAX30102_SAMPLE_AVERAGING=4` trong
  `config.py`, tức 25 mẫu/s; FIFO đệm 1,28 s. Ở 100 mẫu/s, FIFO tràn mỗi lần vẽ TFT (đã đo
  trên Pi ngày 28/11). Log in `tft_ms_max` và `ppg_reinit` để theo dõi.

- **Chỉ thu PPG** (chế độ nghiên cứu, dừng service trước): `.venv/bin/python record_ppg.py`.
  Phiên dừng ngay khi mất mẫu để `time_s` luôn liên tục. Hai cờ `ENABLE_PULSE_ANALYSIS` và
  `ENABLE_CONSOLE_LOG` nằm ở đầu file.
- **Thu PPG trong lúc hệ thống chạy**: đặt `PPG_CSV_LOG=1` trong `.env`. Khi FIFO tràn hoặc
  I2C lỗi, Pi khởi tạo lại cảm biến sau 5 s và mở phiên CSV mới. Bước chân không bị ảnh hưởng.
- `logs/` không bị script triển khai ghi đè và không đưa vào Git.

## Giới hạn cần biết

- Quãng đường = số bước × chiều dài bước (tự đo, hoặc 0,414 × chiều cao); kcal hoạt
  động theo phương trình ACSM. Cả hai đều là ước tính.
- `BPM~` là ước tính từ các đỉnh IR, chưa qua đánh giá độ chính xác. Số IR thô
  giúp xác nhận MAX30102 đang thu tín hiệu. Chưa tính SpO2 vì cần thuật toán
  và hiệu chuẩn phù hợp; không điền số giả lên màn hình.
- Phát hiện ngã dựa trên rơi/va chạm, đổi hướng so với trước va chạm và ít
  cử động khoảng 1,8 giây; hiện nhận mẫu 100 Hz từ FIFO. Logic chưa được hiệu
  chỉnh cho cách đeo thật. Không làm người thử té ngã để kiểm tra.
- MPU6050 đặt thang ±8 g, ±500 °/s. Driver đọc lại thanh ghi sau khi cấu hình
  và từ chối chạy nếu chip không nhận cấu hình.
- Hàng đợi MQTT nằm trong RAM. Khi dừng có kiểm soát, các bản tin còn chờ được gửi
  nốt (tối đa 3 s); mất điện thì mất phần chưa gửi.
- MQTT local chưa bật TLS. Không mở cổng broker ra Internet.

Nguồn tham khảo: mã mẫu `SmartWatchTEAM/Smart-watch-IoT`, datasheet MAX30102
của Analog Devices, datasheet MPU6050 của TDK và thư viện RGB Display của
Adafruit. Mã ở đây viết lại cho Raspberry Pi, không chạy firmware ESP32 `.ino`.
