#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
PI_USER="${SUDO_USER:-$USER}"
PI_GROUP="$(id -gn "$PI_USER")"
SERVICE_NAME="health-watch.service"
TEMPLATE="$APP_DIR/deploy/pi/health-watch.service.template"

if [[ "$PI_USER" == "root" ]]; then
    echo "Không xác định được user chạy phần cứng. Hãy đăng nhập bằng user Pi rồi chạy script." >&2
    exit 1
fi
if [[ ! -f "$APP_DIR/.env" ]]; then
    echo "Thiếu $APP_DIR/.env; chưa cài service." >&2
    exit 1
fi
if [[ ! -x "$APP_DIR/.venv/bin/python" ]]; then
    echo "Thiếu .venv; hãy chạy bash deploy/pi/setup.sh trước." >&2
    exit 1
fi
if [[ ! -f "$TEMPLATE" ]]; then
    echo "Thiếu template service: $TEMPLATE" >&2
    exit 1
fi

escaped_app_dir="${APP_DIR//&/\\&}"
escaped_user="${PI_USER//&/\\&}"
escaped_group="${PI_GROUP//&/\\&}"
temp_service="$(mktemp)"
trap 'rm -f "$temp_service"' EXIT
sed \
    -e "s|@@APP_DIR@@|$escaped_app_dir|g" \
    -e "s|@@PI_USER@@|$escaped_user|g" \
    -e "s|@@PI_GROUP@@|$escaped_group|g" \
    "$TEMPLATE" > "$temp_service"

chmod 600 "$APP_DIR/.env"
sudo install -m 0644 "$temp_service" "/etc/systemd/system/$SERVICE_NAME"
sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"
sleep 2

if ! sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "Service không chạy được. Log gần nhất:" >&2
    sudo journalctl -u "$SERVICE_NAME" -n 40 --no-pager >&2
    exit 1
fi

sudo systemctl status "$SERVICE_NAME" --no-pager
echo "Đã cài và bật tự khởi động $SERVICE_NAME"
