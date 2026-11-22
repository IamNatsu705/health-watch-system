"""Cấu hình cho mạch Raspberry Pi 4 của nhóm."""

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
BUZZER_GPIO = 17  # MH-FMD kích mức thấp.
SOS_BUTTON_GPIO = 23  # Nút nối GPIO23 với GND, dùng pull-up nội bộ.

# Chỉ là giá trị mẫu cho phần ước tính vận động; sửa theo người thử.
STEP_LENGTH_M = 0.70
WEIGHT_KG = 70.0

SAMPLE_INTERVAL_S = 0.04
SCREEN_INTERVAL_S = 0.5
I2C_READ_ATTEMPTS = 3
