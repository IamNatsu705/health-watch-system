#!/bin/sh
set -eu

: "${MQTT_USERNAME:?MQTT_USERNAME is required}"
: "${MQTT_PASSWORD:?MQTT_PASSWORD is required}"
mosquitto_passwd -b -c /tmp/mosquitto.passwd "$MQTT_USERNAME" "$MQTT_PASSWORD"
chown mosquitto:mosquitto /tmp/mosquitto.passwd
chmod 600 /tmp/mosquitto.passwd
exec mosquitto -c /mosquitto/config/mosquitto.conf
