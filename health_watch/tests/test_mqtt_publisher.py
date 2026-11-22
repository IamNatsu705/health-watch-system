"""Kiểm tra publisher chạy nền mà không cần broker thật."""

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mqtt_publisher import BrokerSettings, MqttPublisher


class FakeReasonCode:
    is_failure = False

    def __str__(self):
        return "Success"


class FakePublishInfo:
    rc = 0

    def wait_for_publish(self, timeout=None):
        return None

    def is_published(self):
        return True


class FakeClient:
    def __init__(self):
        self.on_connect = None
        self.on_disconnect = None
        self.published = []
        self.connected_to = None

    def username_pw_set(self, username, password):
        self.credentials = (username, password)

    def reconnect_delay_set(self, min_delay, max_delay):
        pass

    def max_inflight_messages_set(self, count):
        pass

    def will_set(self, topic, payload, qos, retain):
        self.will = (topic, payload, qos, retain)

    def connect_async(self, host, port, keepalive):
        self.connected_to = (host, port, keepalive)

    def loop_start(self):
        self.on_connect(self, None, None, FakeReasonCode(), None)

    def publish(self, topic, payload, qos, retain):
        self.published.append((topic, payload, qos, retain))
        return FakePublishInfo()

    def disconnect(self):
        return None

    def loop_stop(self):
        return None


class MqttPublisherTests(unittest.TestCase):
    def settings(self):
        return BrokerSettings(
            host="broker", port=1883, username="device", password="secret",
            device_id="pi-test", outbox_size=10,
        )

    def test_background_publish_and_graceful_status(self):
        fake = FakeClient()
        with patch("mqtt_publisher.mqtt.Client", return_value=fake):
            publisher = MqttPublisher(
                self.settings(),
                online_status={"state": "online"},
                offline_status={"state": "offline"},
            )
            publisher.start()
            publisher.publish_telemetry({"sequence": 1})
            deadline = time.monotonic() + 1
            while len(fake.published) < 2 and time.monotonic() < deadline:
                time.sleep(0.01)
            publisher.stop()

        topics = [item[0] for item in fake.published]
        self.assertEqual(fake.connected_to, ("broker", 1883, 30))
        self.assertIn("health/v1/devices/pi-test/telemetry", topics)
        self.assertEqual(topics.count("health/v1/devices/pi-test/status"), 2)
        self.assertEqual(fake.will[0], "health/v1/devices/pi-test/status")

    def test_full_outbox_keeps_events_over_telemetry(self):
        fake = FakeClient()
        with patch("mqtt_publisher.mqtt.Client", return_value=fake):
            publisher = MqttPublisher(
                self.settings(), {"state": "online"}, {"state": "offline"}
            )
            publisher._started = True
            for sequence in range(10):
                publisher.publish_event({"sequence": sequence})
            publisher.publish_telemetry({"sequence": 10})
            self.assertEqual(len(publisher._outbox), 10)
            self.assertTrue(all(item.kind == "event" for item in publisher._outbox))

    def test_rejects_missing_credentials(self):
        settings = BrokerSettings(
            host="broker", port=1883, username="device", password="",
            device_id="pi-test",
        )
        with self.assertRaises(ValueError):
            settings.validate()


if __name__ == "__main__":
    unittest.main()
