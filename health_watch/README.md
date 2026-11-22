# Health Watch - thử phần cứng trên Raspberry Pi

Thư mục này dùng riêng cho bài cuối kỳ. `main.py` đọc GY-521/MPU6050 và
MAX30102 qua I2C, đếm bước thử nghiệm, ước tính quãng đường/calo, rồi hiện
thông tin lên TFT ST7789V3 240x280 qua SPI. MPU6050 cũng được dùng để thử
phát hiện ngã. Chưa dùng Flask, web hay Firebase.

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
| MH-FMD I/O (kích mức thấp) | GPIO17 | 11 |
| Nút SOS, đầu còn lại nối GND | GPIO23 | 16 |

Nguồn các module: 3,3 V và GND chung. TFT `BLK` đang nối 3,3 V.
Còi MH-FMD có điện trở kéo lên 10 kΩ từ I/O tới 3,3 V. Nút dùng điện trở
kéo lên nội bộ của Pi. Không chạy đồng thời chương trình giữa kỳ đang dùng
các GPIO22/GPIO27/GPIO17.

## Chép từ Windows bằng PowerShell

Chạy trên **máy Windows**, từ thư mục dự án lớn `health_watch_system/`, không chạy trong phiên SSH. Chỉ chép mã nguồn Pi đang có; không chép cả dự án hoặc `.venv` của bản copy:

```powershell
Set-Location 'C:\Project\health_watch_system'
scp .\health_watch\main.py .\health_watch\config.py .\health_watch\alerts.py .\health_watch\screen.py .\health_watch\requirements.txt pi@pi:/home/pi/projects/health_watch/
scp .\health_watch\check_i2c.py .\health_watch\check_alerts.py pi@pi:/home/pi/projects/health_watch/
scp -r .\health_watch\sensors .\health_watch\processing pi@pi:/home/pi/projects/health_watch/
```

Nếu Windows không phân giải được tên máy `pi`, thay `pi@pi` bằng
`pi@<địa-chỉ-IP-của-Pi>`. Thư mục trên Pi là
`/home/pi/projects/health_watch`. Sau khi thêm publisher MQTT hoặc file Python mới, cập nhật danh sách file triển khai tương ứng. Các thư mục `backend/`, `web/`, `infra/`, `contracts/` ở cấp dự án lớn không chạy trên Pi.

## Chuẩn bị trên Pi 4, Debian 13 (Trixie)

Chạy trong phiên SSH:

```bash
cd /home/pi/projects/health_watch
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_spi 0
sudo apt update
sudo apt install -y python3-venv python3-spidev python3-libgpiod i2c-tools fonts-dejavu-core
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
python -m pip install -r requirements.txt
ls /dev/i2c-1 /dev/spidev0.0
python check_i2c.py
```

`check_i2c.py` cần thấy `0x57` (MAX30102) và `0x68` (MPU6050; có thể là
`0x69` nếu AD0 được kéo lên cao). Nếu thiếu một địa chỉ, kiểm tra điện áp,
GND, SDA/SCL và mối hàn trước khi chạy `main.py`. Chương trình hiện đặt
MPU6050 ở `0x68` trong `config.py`.

Nếu `/dev/i2c-1` hoặc `/dev/spidev0.0` chưa xuất hiện sau khi bật giao tiếp,
khởi động lại Pi rồi SSH vào lại. Bật lại venv bằng:

```bash
cd /home/pi/projects/health_watch
source .venv/bin/activate
```

## Chạy thử tích hợp

Thử riêng nút, hai LED và còi trước:

```bash
python check_alerts.py
```

Khi thả nút: LED xanh sáng, LED đỏ và còi tắt. Khi giữ nút: LED đỏ và còi
bật, LED xanh tắt. Nhấn `Ctrl+C` để dừng; lúc đó cả hai LED và còi đều tắt.
Nếu còi kêu ngay khi khởi động, kiểm tra nhãn VCC/GND/I/O của module,
điện trở 10 kΩ kéo I/O lên 3,3 V và tránh nhầm thứ tự chân.

Sau đó chạy thử tích hợp:

```bash
python main.py
```

Có thể kiểm tra logic phát hiện ngã và quy tắc còi/LED mà không cần tác động
lên phần cứng bằng:

```bash
python -m unittest discover -s tests -v
```

Màn hình quay 180° theo cách đặt hiện tại; giao diện nền tối và các thẻ màu
hiển thị nhịp tim ước tính, bước chân, quãng đường, calo ước tính và trạng
thái cảnh báo. Terminal còn in gia tốc và IR thô để chẩn đoán cảm biến.
Khi chưa đặt tay, đồ thị nhịp tim là đường ngang và BPM hiện `--`. Đặt tay
ổn định trên vùng cảm biến cho tới khi terminal báo `finger=yes` và tích đủ
ít nhất 125 mẫu (khoảng 5 giây ở 25 mẫu/giây); nếu sóng chưa đều, BPM vẫn
hiện `--` thay vì đoán một con số.
Khi giữ nút SOS, đèn đỏ và còi bật, đèn xanh tắt; thả nút thì bình thường.
Khi phát hiện ngã, **chỉ LED đỏ bật, còi tắt**; màn hình giữ dòng
`PHÁT HIỆN NGÃ`. Nhấn nút một lần để xác nhận và xóa cảnh báo; thả nút ra
trước khi dùng nút SOS tiếp. Nhấn `Ctrl+C` để dừng; chương trình tắt các
ngõ ra khi thoát.
Nếu màn hình không hiện nhưng terminal vẫn có số, kiểm tra dây SPI, chân
`DC/RES/CS` và `BLK`. Nếu chương trình báo lỗi cảm biến, chạy lại
`python check_i2c.py`.

Nếu xuất hiện `[Errno 5] Input/output error` khi di chuyển breadboard,
tắt nguồn Pi rồi kiểm tra và cắm chắc bốn dây nguồn/GND/SDA/SCL của cả hai
cảm biến. Mã sẽ thử lại tối đa 3 lần và ghi rõ lỗi ở MPU6050 hay MAX30102;
nếu vẫn lỗi liên tiếp thì dừng để tránh coi dữ liệu mất kết nối là số đo thật.

## Giới hạn cần biết

- Bộ đếm bước là thuật toán tìm đỉnh gia tốc để thử phần cứng. Lắc tay có thể
  tạo bước giả. Cần cố định MPU6050 lên người và so với số bước đếm tay.
- `KCAL~` dùng bước chân, chiều dài bước mẫu 0,70 m, cân nặng mẫu 70 kg và
  hệ số minh họa 0,75 kcal/(kg·km). Sửa hai giá trị đầu trong `config.py`.
- `BPM~` là ước tính từ các đỉnh IR, chưa qua đánh giá độ chính xác. Số IR thô
  giúp xác nhận MAX30102 đang thu tín hiệu. Chưa tính SpO2 vì cần thuật toán
  và hiệu chuẩn phù hợp; không điền số giả lên màn hình.
- Phát hiện ngã dựa trên rơi/va chạm, đổi hướng so với trước va chạm và ít
  cử động khoảng 1,8 giây. Đây là logic thử nghiệm chuyển từ repo tham khảo
  sang MPU6050; chưa được hiệu chỉnh cho cách đeo thật. Lắc, thả hoặc đập
  riêng module có thể cho kết quả khác một cú ngã thật. Không làm người thử
  té ngã để kiểm tra; cố định module, kiểm tra dây rồi thử chuyển động có
  kiểm soát. Mạch breadboard đang lỏng có thể mất I2C khi di chuyển.
- MPU6050 được đặt thang gia tốc ±8 g, con quay ±500 độ/giây để đọc được
  mức va chạm dùng trong thuật toán. Hai giá trị này khác phiên bản trước
  (±2 g, ±250 độ/giây); không phải thay dây hay cài thêm thư viện.

Nguồn tham khảo: mã mẫu `SmartWatchTEAM/Smart-watch-IoT`, datasheet MAX30102
của Analog Devices, datasheet MPU6050 của TDK và thư viện RGB Display của
Adafruit. Mã ở đây viết lại cho Raspberry Pi, không chạy firmware ESP32 `.ino`.
