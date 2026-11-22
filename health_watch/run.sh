#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

if [[ ! -f .env ]]; then
    echo "Thiếu $APP_DIR/.env. Hãy copy .env.example thành .env rồi cấu hình MQTT." >&2
    exit 1
fi
if [[ ! -x .venv/bin/python ]]; then
    echo "Thiếu .venv. Hãy chạy: bash deploy/pi/setup.sh" >&2
    exit 1
fi

set -a
# shellcheck disable=SC1091
source ./.env
set +a

export PYTHONUNBUFFERED=1
exec .venv/bin/python main.py
