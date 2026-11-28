#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "$(id -u)" -eq 0 ]]; then
    echo "Hãy chạy script bằng user Pi bình thường, không chạy 'sudo bash'. Script sẽ tự gọi sudo khi cần." >&2
    exit 1
fi

APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
PI_USER="$(id -un)"

echo "Cài gói hệ thống cho $PI_USER tại $APP_DIR"
if command -v raspi-config >/dev/null 2>&1; then
    sudo raspi-config nonint do_i2c 0
    sudo raspi-config nonint do_spi 0
fi

sudo apt update
sudo apt install -y \
    python3-venv python3-pip python3-spidev python3-libgpiod python3-numpy \
    i2c-tools fonts-dejavu-core

# Số bước "hôm nay" trên TFT chia ngày theo giờ địa phương của Pi; phải khớp
# LOCAL_TIMEZONE của backend (mặc định Asia/Ho_Chi_Minh).
PI_TIMEZONE="${PI_TIMEZONE:-Asia/Ho_Chi_Minh}"
if command -v timedatectl >/dev/null 2>&1; then
    sudo timedatectl set-timezone "$PI_TIMEZONE"
    sudo timedatectl set-ntp true || true
fi

for group in i2c spi gpio; do
    if getent group "$group" >/dev/null 2>&1; then
        sudo usermod -aG "$group" "$PI_USER"
    fi
done

cd "$APP_DIR"
if [[ ! -d .venv ]]; then
    python3 -m venv .venv --system-site-packages
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
chmod +x run.sh deploy/pi/setup.sh deploy/pi/install_service.sh

echo
echo "Cài đặt xong. Kiểm tra thiết bị:"
echo "  ls -l /dev/i2c-1 /dev/spidev0.0"
echo "  .venv/bin/python check_i2c.py"
echo "Nếu vừa bật I2C/SPI hoặc thêm group, hãy reboot Pi trước khi thử phần cứng."
