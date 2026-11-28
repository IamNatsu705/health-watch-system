# Phần cứng Raspberry Pi

Tài liệu này ghi lại cách nối và kiểm tra phần cứng đang được mã nguồn `health_watch/` sử dụng. Số GPIO là số **BCM**, không phải số chân vật lý.

## 1. Danh sách phần cứng

- Raspberry Pi có I2C và SPI;
- MPU6050 đo gia tốc/góc quay;
- MAX30102 đo tín hiệu quang thử nghiệm;
- màn hình TFT ST7789 dùng SPI;
- LED xanh, LED đỏ và điện trở phù hợp;
- còi active-low;
- nút SOS;
- dây nối và nguồn ổn định.

## 2. Sơ đồ chân

| Thiết bị/tín hiệu | GPIO BCM | Chân vật lý Pi | Ghi chú |
| --- | ---: | ---: | --- |
| I2C SDA | 2 | 3 | MPU6050 và MAX30102 dùng chung bus |
| I2C SCL | 3 | 5 | MPU6050 và MAX30102 dùng chung bus |
| SPI MOSI | 10 | 19 | TFT ST7789 |
| SPI SCLK | 11 | 23 | TFT ST7789 |
| SPI CE0/CS | 8 | 24 | `/dev/spidev0.0` |
| TFT DC | 25 | 22 | Data/command |
| TFT reset | 24 | 18 | Reset màn hình |
| LED xanh | 22 | 15 | Trạng thái bình thường |
| LED đỏ | 27 | 13 | Cảnh báo |
| Còi | 5 | 29 | Active-low: mức thấp bật còi; GPIO5 có pull-up lúc boot nên còi không kêu khi khởi động |
| Nút SOS | 23 | 16 | Dùng pull-up 10 kΩ như mạch hiện tại |
| 3,3 V | — | 1 hoặc 17 | Nguồn logic/cảm biến tương thích |
| GND | — | 6/9/14/... | Tất cả module phải chung GND |

Đối chiếu lại nhãn trên đúng breakout board trước khi cấp nguồn. Không giả định mọi module ST7789/MAX30102 có chân và mức điện áp giống nhau.

## 3. Địa chỉ và thiết bị mong đợi

- MAX30102: `0x57`;
- MPU6050: `0x68`, hoặc `0x69` nếu chân AD0 được kéo cao;
- I2C device: `/dev/i2c-1`;
- SPI device: `/dev/spidev0.0`.

## 4. Kiểm tra trước khi cấp nguồn

1. Tắt nguồn Pi trước khi thay dây.
2. Đối chiếu BCM và chân vật lý trong bảng.
3. Xác nhận nguồn 3,3 V/5 V đúng yêu cầu của từng breakout.
4. Xác nhận tất cả thiết bị chung GND.
5. Kiểm tra LED có điện trở hạn dòng.
6. Kiểm tra còi active-low để tránh còi kêu ngay khi GPIO chưa được khởi tạo.
7. Kiểm tra không có chân GPIO nào bị hai chương trình cùng điều khiển.

## 5. Bật I2C/SPI và quyền thiết bị

Script setup thực hiện tự động:

```bash
cd /home/pi/projects/health_watch
bash deploy/pi/setup.sh
```

Sau khi script thêm user vào nhóm `i2c`, `spi`, `gpio`, đăng xuất/đăng nhập lại hoặc reboot nếu quyền chưa có hiệu lực.

Kiểm tra:

```bash
ls -l /dev/i2c-1 /dev/spidev0.0
groups
i2cdetect -y 1
.venv/bin/python check_i2c.py
```

Kết quả mong đợi có `0x57` và `0x68` hoặc `0x69`.

## 6. Kiểm tra GPIO và cảnh báo

Không chạy test GPIO đồng thời với service:

```bash
sudo systemctl stop health-watch
.venv/bin/python check_alerts.py
```

Quan sát theo hướng dẫn của script:

- trạng thái bình thường: LED xanh;
- cảnh báo: LED đỏ và còi;
- kết thúc: còi tắt, GPIO trở về trạng thái an toàn.

Nếu còi active-low đang kêu ngoài ý muốn, có thể đưa GPIO5 lên mức cao tạm thời:

```bash
sudo pinctrl set 5 op dh
```

Sau khi kiểm tra xong, chạy lại service:

```bash
sudo systemctl start health-watch
sudo journalctl -u health-watch -n 30 --no-pager
```

## 7. Kiểm tra cảm biến khi chạy thật

```bash
cd /home/pi/projects/health_watch
sudo systemctl stop health-watch
set -a
. ./.env
set +a
./run.sh
```

Mong đợi log báo đã nhận MPU6050 và MAX30102, sau đó in bước, gia tốc, IR, trạng thái ngón tay, số mẫu và BPM. Đặt ngón tay ổn định lên MAX30102; `finger=no` với IR xấp xỉ nền là bình thường khi chưa đặt tay.

Dừng bằng `Ctrl+C`, sau đó bật lại service. Không tạo cú ngã thật để thử thuật toán; dùng test đơn vị hoặc chuyển động thiết bị có kiểm soát.

## 8. Chẩn đoán

| Hiện tượng | Kiểm tra |
| --- | --- |
| Không thấy cả hai địa chỉ I2C | I2C đã bật, nguồn, GND, SDA/SCL, dây và mối hàn |
| Chỉ thấy `0x69` | MPU6050 đang kéo AD0 cao; cấu hình/driver phải dùng đúng địa chỉ |
| Không có `/dev/spidev0.0` | SPI chưa bật hoặc chưa reboot |
| TFT trắng/đen | Nguồn, CE0, DC25, RESET24, hướng/màu và dây SPI |
| Còi đảo trạng thái | Xác nhận phần cứng active-low và cấu hình GPIO5 (`BUZZER_GPIO`) |
| GPIO báo bận | Dừng service và chương trình cũ đang dùng GPIO |
| BPM luôn `--` | Đặt ngón tay, kiểm tra IR/FIFO, nguồn và độ ổn định; `--` không phải 0 |
| Số bước sai | Kiểm tra log `imu=ok`, `fifo_overflow=0` và mô hình đã nạp; ghi phiên có đếm tay bằng `record_imu.py` ([thu dữ liệu](../data-collection.md)) |
| Màn hình báo `LỖI CẢM BIẾN` | Kiểm tra dây/nguồn MPU6050; xem `journalctl` dòng `MPU6050 error` |

## 9. An toàn và hiệu chuẩn

Các ảnh `preview_*.png` chỉ là ảnh giao diện mẫu. Khi thu dữ liệu thật, ghi rõ phiên bản phần cứng/phần mềm, vị trí đeo, người thử, thời gian, phương pháp đối chiếu và điều kiện môi trường. Không dùng kết quả hiện tại để chẩn đoán, theo dõi cấp cứu hoặc thay thế thiết bị y tế.
