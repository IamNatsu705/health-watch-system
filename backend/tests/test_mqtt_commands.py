"""Command state prevents duplicate remote buzzer activation."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from backend.api.mqtt_commands import CommandConflict, MqttCommandPublisher


class FakePublishInfo:
    rc = 0

    def wait_for_publish(self, timeout=None):
        return None

    def is_published(self):
        return True


class FakeClient:
    def username_pw_set(self, username, password): pass
    def reconnect_delay_set(self, min_delay, max_delay): pass
    def subscribe(self, topic, qos): return (0, 1)
    def publish(self, topic, payload, qos, retain): return FakePublishInfo()
    def connect_async(self, host, port, keepalive): pass
    def loop_start(self): pass
    def disconnect(self): pass
    def loop_stop(self): pass


class CommandStateTests(unittest.TestCase):
    def make_publisher(self):
        with patch("backend.api.mqtt_commands.mqtt.Client", return_value=FakeClient()):
            publisher = MqttCommandPublisher()
        publisher._connected.set()
        return publisher

    def report(self, publisher, active, command_id=None):
        document = {
            "schema_version": 1,
            "device_id": "pi-test",
            "boot_id": str(uuid4()),
            "buzzer_active": active,
            "red_led_active": active,
            "source": "remote" if active else "normal",
            "last_command_id": command_id,
            "expires_at": None,
            "reported_at": "2026-11-22T07:00:00Z",
        }
        publisher._on_message(
            None,
            None,
            SimpleNamespace(
                topic="health/v1/devices/pi-test/alert-state",
                payload=json.dumps(document).encode(),
            ),
        )

    def command(self, active):
        return {
            "command_id": str(uuid4()),
            "active": active,
        }

    def test_state_acknowledges_command_and_blocks_duplicate_start(self):
        publisher = self.make_publisher()
        self.report(publisher, False)
        command = self.command(True)
        pending = publisher.publish("pi-test", command)
        self.assertTrue(pending["pending"])

        self.report(publisher, True, command["command_id"])
        state = publisher.state_view("pi-test")
        self.assertTrue(state["buzzer_active"])
        self.assertFalse(state["pending"])
        with self.assertRaises(CommandConflict):
            publisher.publish("pi-test", self.command(True))

    def test_unknown_state_blocks_start_but_allows_safe_stop(self):
        publisher = self.make_publisher()
        with self.assertRaises(CommandConflict):
            publisher.publish("pi-test", self.command(True))
        state = publisher.publish("pi-test", self.command(False))
        self.assertTrue(state["pending"])


if __name__ == "__main__":
    unittest.main()
