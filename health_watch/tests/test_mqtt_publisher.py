"""Kiểm tra publisher chạy nền mà không cần broker thật."""

import json
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
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
        self.on_message = None
        self.published = []
        self.connected_to = None
        self.subscriptions = []

    def username_pw_set(self, username, password):
        self.credentials = (username, password)

    def tls_set(self, **kwargs):
        self.tls = kwargs

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

    def subscribe(self, topic, qos):
        self.subscriptions.append((topic, qos))
        return (0, 1)

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
        self.assertIn(("health/v1/devices/pi-test/commands", 1), fake.subscriptions)
        self.assertIn(("health/v1/devices/pi-test/config", 1), fake.subscriptions)

    def test_accepts_fresh_remote_alert_once(self):
        fake = FakeClient()
        with patch("mqtt_publisher.mqtt.Client", return_value=fake):
            publisher = MqttPublisher(
                self.settings(), {"state": "online"}, {"state": "offline"}
            )
        command = {
            "schema_version": 1,
            "command_id": str(uuid4()),
            "device_id": "pi-test",
            "command_type": "remote_alert",
            "active": True,
            "duration_s": 10,
            "issued_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        message = SimpleNamespace(payload=json.dumps(command).encode("utf-8"))
        publisher._on_message(None, None, message)
        publisher._on_message(None, None, message)

        commands = publisher.pop_commands()
        self.assertEqual(len(commands), 1)
        self.assertTrue(commands[0]["active"])
        self.assertEqual(commands[0]["duration_s"], 10)

    def test_rejects_stale_remote_alert(self):
        fake = FakeClient()
        with patch("mqtt_publisher.mqtt.Client", return_value=fake):
            publisher = MqttPublisher(
                self.settings(), {"state": "online"}, {"state": "offline"}
            )
        command = {
            "schema_version": 1,
            "command_id": str(uuid4()),
            "device_id": "pi-test",
            "command_type": "remote_alert",
            "active": True,
            "duration_s": 10,
            "issued_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
        }
        publisher._on_message(
            None, None, SimpleNamespace(payload=json.dumps(command).encode("utf-8"))
        )
        self.assertEqual(publisher.pop_commands(), [])

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

    def test_aws_tls_uses_client_certificate_without_password(self):
        fake = FakeClient()
        settings = BrokerSettings(
            host="example-ats.iot.ap-southeast-2.amazonaws.com",
            port=8883,
            username="",
            password="",
            device_id="pi-test",
            tls_enabled=True,
            ca_cert="/certs/AmazonRootCA1.pem",
            client_cert="/certs/device.cert.pem",
            client_key="/certs/device.private.key",
        )
        with patch("mqtt_publisher.mqtt.Client", return_value=fake):
            MqttPublisher(settings, {"state": "online"}, {"state": "offline"})

        self.assertEqual(fake.tls, {
            "ca_certs": "/certs/AmazonRootCA1.pem",
            "certfile": "/certs/device.cert.pem",
            "keyfile": "/certs/device.private.key",
        })
        self.assertFalse(hasattr(fake, "credentials"))

    def test_aws_tls_rejects_missing_certificate_path(self):
        settings = BrokerSettings(
            host="example-ats.iot.ap-southeast-2.amazonaws.com",
            port=8883,
            username="",
            password="",
            device_id="pi-test",
            tls_enabled=True,
            ca_cert="/certs/AmazonRootCA1.pem",
            client_cert="/certs/device.cert.pem",
            client_key="",
        )
        with self.assertRaises(ValueError):
            settings.validate()

    def test_alert_state_is_retained_and_latest_state_wins(self):
        fake = FakeClient()
        with patch("mqtt_publisher.mqtt.Client", return_value=fake):
            publisher = MqttPublisher(
                self.settings(), {"state": "online"}, {"state": "offline"}
            )
            publisher._started = True
            publisher.publish_alert_state({"buzzer_active": True})
            publisher.publish_alert_state({"buzzer_active": False})

        states = [item for item in publisher._outbox if item.kind == "state"]
        self.assertEqual(len(states), 1)
        self.assertFalse(states[0].document["buzzer_active"])
        self.assertTrue(states[0].retain)


class ProfileConfigTests(unittest.TestCase):
    def publisher(self):
        fake = FakeClient()
        settings = BrokerSettings(host="broker", port=1883, username="pi-test", password="secret",
                                  device_id="pi-test", outbox_size=10)
        with patch("mqtt_publisher.mqtt.Client", return_value=fake):
            return MqttPublisher(settings, {"state": "online"}, {"state": "offline"}), fake

    def config_message(self, document):
        return SimpleNamespace(topic="health/v1/devices/pi-test/config",
                               payload=json.dumps(document).encode("utf-8"))

    def test_valid_profile_is_queued(self):
        publisher, _ = self.publisher()
        publisher._on_message(None, None, self.config_message({
            "schema_version": 1, "device_id": "pi-test", "updated_at": "2026-11-28T00:00:00Z",
            "profile": {"height_cm": 168, "weight_kg": 58.5, "step_length_m": None},
        }))
        updates = publisher.pop_profile_updates()
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0]["profile"].weight_kg, 58.5)
        self.assertEqual(publisher.pop_commands(), [])

    def test_cleared_profile_and_invalid_profile(self):
        publisher, _ = self.publisher()
        base = {"schema_version": 1, "device_id": "pi-test", "updated_at": "2026-11-28T00:00:00Z"}
        publisher._on_message(None, None, self.config_message({**base, "profile": None}))
        publisher._on_message(None, None, self.config_message({**base, "profile": {"height_cm": 5, "weight_kg": 60}}))
        publisher._on_message(None, None, self.config_message({**base, "device_id": "other", "profile": None}))
        updates = publisher.pop_profile_updates()
        self.assertEqual(len(updates), 1)
        self.assertIsNone(updates[0]["profile"])

    def test_stop_flushes_pending_messages_first(self):
        publisher, fake = self.publisher()
        publisher.start()
        for sequence in range(5):
            publisher.publish_telemetry({"sequence": sequence})
        publisher.stop()
        telemetry = [item for item in fake.published if item[0].endswith("/telemetry")]
        self.assertEqual(len(telemetry), 5)
        self.assertTrue(fake.published[-1][0].endswith("/status"))
        publisher.publish_telemetry({"sequence": 99})
        self.assertEqual(len([i for i in fake.published if i[0].endswith("/telemetry")]), 5)


if __name__ == "__main__":
    unittest.main()
