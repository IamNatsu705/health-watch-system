"""Configuration shared by local backend processes."""

import os


DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://health_watch:health_watch@localhost:5432/health_watch"
)
MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USERNAME = os.environ.get("MQTT_USERNAME", "health_watch")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")
