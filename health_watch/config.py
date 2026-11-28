"""Cấu hình phần cứng và MQTT cho Raspberry Pi 4 của nhóm."""

import os
import socket

I2C_BUS = 1
MPU6050_ADDRESS = 0x68
MAX30102_ADDRESS = 0x57

DISPLAY_WIDTH = 240
DISPLAY_HEIGHT = 280
DISPLAY_Y_OFFSET = 20
DISPLAY_DC_GPIO = 25
DISPLAY_RESET_GPIO = 24
DISPLAY_ROTATION = 180  # Màn hình đang lắp ngược chiều nhìn.

GREEN_LED_GPIO = 22
RED_LED_GPIO = 27
BUZZER_GPIO = 5  # MH-FMD kích mức thấp; pull-up giữ còi tắt khi boot.
SOS_BUTTON_GPIO = 23  # Nút nối GPIO23 với GND, dùng pull-up nội bộ.

# Sau khi phát hiện ngã: LED đỏ + còi bíp, người đeo có FALL_CANCEL_WINDOW_S giây để bấm nút
# báo ổn. Hết giờ mà người đeo nằm yên (không cử động trong FALL_IMMOBILE_S giây gần nhất)
# thì còi kêu liên tục và gửi sự kiện fall_alarm. Xem fall_alarm.py.
FALL_CANCEL_WINDOW_S = 30.0
FALL_IMMOBILE_S = 10.0

# Chiều cao/cân nặng không đặt cứng ở đây: người dùng nhập trên web/app, backend
# gửi qua topic MQTT `config`, Pi lưu ở state/profile.json. Chưa có hồ sơ thì
# quãng đường/kcal hiển thị "--" thay vì dùng số mẫu.

# MAX30102 trong hệ thống đầy đủ: 100 Hz, trung bình 4 → 25 cặp RED/IR mỗi giây (thiết kế gốc
# của PulseMonitor). FIFO 32 mẫu khi đó đệm 1,28 s, đủ cho lúc vẽ TFT chặn vòng lặp. Ở 100 mẫu/s
# FIFO chỉ đệm 0,32 s và tràn mỗi khi vẽ TFT (đã thấy trên Pi 28/11). Thu PPG nghiên cứu tần số cao:
# record_ppg.py (dùng thông số mặc định trong sensors/max30102.py, không bật TFT).
MAX30102_SAMPLE_RATE = 100
MAX30102_SAMPLE_AVERAGING = 4
MAX30102_SAMPLES_PER_SECOND = MAX30102_SAMPLE_RATE // MAX30102_SAMPLE_AVERAGING

# Vòng lặp chính 40 ms; MPU6050 tự lấy mẫu 100 Hz vào FIFO nên vẽ TFT không làm mất mẫu.
SAMPLE_INTERVAL_S = 0.04
SCREEN_INTERVAL_S = 1.0
I2C_READ_ATTEMPTS = 3

# MQTT lấy từ biến môi trường để không ghi mật khẩu vào mã nguồn. Mặc định
# tắt để chương trình phần cứng cũ vẫn chạy an toàn trước khi cấu hình broker.
MQTT_ENABLED = os.environ.get("MQTT_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
MQTT_HOST = os.environ.get("MQTT_HOST", "").strip()
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_DEVICE_ID = os.environ.get("MQTT_DEVICE_ID", socket.gethostname()).strip()
# Broker cấp tài khoản riêng cho từng thiết bị, tên đăng nhập = device_id (ACL %u).
MQTT_USERNAME = os.environ.get("MQTT_USERNAME", MQTT_DEVICE_ID).strip()
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")
MQTT_TLS_ENABLED = os.environ.get("MQTT_TLS_ENABLED", "0").strip().lower() in {
    "1", "true", "yes", "on",
}
MQTT_CA_CERT = os.environ.get("MQTT_CA_CERT", "").strip()
MQTT_CLIENT_CERT = os.environ.get("MQTT_CLIENT_CERT", "").strip()
MQTT_CLIENT_KEY = os.environ.get("MQTT_CLIENT_KEY", "").strip()
MQTT_PUBLISH_INTERVAL_S = float(os.environ.get("MQTT_PUBLISH_INTERVAL_S", "1.0"))
MQTT_KEEPALIVE_S = int(os.environ.get("MQTT_KEEPALIVE_S", "30"))
MQTT_OUTBOX_SIZE = int(os.environ.get("MQTT_OUTBOX_SIZE", "200"))

# Ghi PPG thô (RED/IR) của MAX30102 ra logs/ppg_*.csv trong khi hệ thống chạy (nghiên cứu
# nhịp tim, ví dụ đối chiếu nhiễu PPG với lúc đang đi bộ). Mặc định tắt vì file lớn
# (~100 dòng/giây). Thu riêng PPG khi dừng service: dùng record_ppg.py.
PPG_CSV_LOG = os.environ.get("PPG_CSV_LOG", "0").strip().lower() in {"1", "true", "yes", "on"}
