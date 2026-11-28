#!/bin/sh
# Tạo tài khoản + ACL cho Mosquitto từ biến môi trường mỗi lần container khởi động.
# - Backend (MQTT_USERNAME): chỉ ĐỌC dữ liệu thiết bị, chỉ GHI commands/config.
# - Mỗi Pi trong MQTT_DEVICES (id:mat_khau,...): chỉ GHI dữ liệu của CHÍNH NÓ,
#   chỉ ĐỌC commands/config của chính nó. Không client nào ghi được dữ liệu
#   thay cho thiết bị khác, nên dữ liệu giả không thể đi vào DB qua broker.
set -eu

: "${MQTT_USERNAME:?MQTT_USERNAME is required}"
: "${MQTT_PASSWORD:?MQTT_PASSWORD is required}"
: "${MQTT_DEVICES:?MQTT_DEVICES is required, ví dụ pi-watch-001:mat_khau_rieng}"

PASSWD=/tmp/mosquitto.passwd
ACL=/tmp/mosquitto.acl
rm -f "$PASSWD" "$ACL"
mosquitto_passwd -b -c "$PASSWD" "$MQTT_USERNAME" "$MQTT_PASSWORD"
cat > "$ACL" <<ACL_EOF
user $MQTT_USERNAME
topic read health/v1/devices/+/telemetry
topic read health/v1/devices/+/events
topic read health/v1/devices/+/status
topic read health/v1/devices/+/alert-state
topic write health/v1/devices/+/commands
topic write health/v1/devices/+/config

ACL_EOF

count=0
old_ifs=$IFS
IFS=,
for entry in $MQTT_DEVICES; do
    IFS=$old_ifs
    entry=$(printf '%s' "$entry" | sed 's/^ *//;s/ *$//')
    if [ -z "$entry" ]; then IFS=,; continue; fi
    device_id=${entry%%:*}
    device_password=${entry#*:}
    case "$device_id" in
        ""|*[!A-Za-z0-9._-]*) echo "ID thiết bị không hợp lệ: '$device_id'" >&2; exit 1 ;;
    esac
    if [ "$device_password" = "$entry" ] || [ -z "$device_password" ]; then
        echo "Thiếu mật khẩu cho thiết bị $device_id (định dạng id:mat_khau)" >&2
        exit 1
    fi
    if [ "$device_id" = "$MQTT_USERNAME" ]; then
        echo "ID thiết bị không được trùng tài khoản backend" >&2
        exit 1
    fi
    mosquitto_passwd -b "$PASSWD" "$device_id" "$device_password"
    cat >> "$ACL" <<ACL_EOF
user $device_id
topic write health/v1/devices/$device_id/telemetry
topic write health/v1/devices/$device_id/events
topic write health/v1/devices/$device_id/status
topic write health/v1/devices/$device_id/alert-state
topic read health/v1/devices/$device_id/commands
topic read health/v1/devices/$device_id/config

ACL_EOF
    count=$((count + 1))
    IFS=,
done
IFS=$old_ifs
if [ "$count" -eq 0 ]; then
    echo "MQTT_DEVICES không có thiết bị nào" >&2
    exit 1
fi

chown mosquitto:mosquitto "$PASSWD" "$ACL"
chmod 600 "$PASSWD" "$ACL"
echo "Mosquitto: 1 tài khoản backend, $count thiết bị"
exec mosquitto -c /mosquitto/config/mosquitto.conf
