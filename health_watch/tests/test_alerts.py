"""Kiểm tra khác biệt giữa cảnh báo ngã và SOS trên GPIO giả."""

import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FakePin:
    def __init__(self, number):
        self.number = number
        self.value = True

    def switch_to_output(self, value):
        self.value = value

    def switch_to_input(self, pull):
        self.value = True

    def deinit(self):
        pass


class AlertOutputTests(unittest.TestCase):
    def test_fall_is_red_without_buzzer_but_sos_uses_buzzer(self):
        board = types.SimpleNamespace(D22=22, D27=27, D17=17, D23=23)
        digitalio = types.SimpleNamespace(DigitalInOut=FakePin, Pull=types.SimpleNamespace(UP=object()))
        with patch.dict(sys.modules, {"board": board, "digitalio": digitalio}):
            sys.modules.pop("alerts", None)
            from alerts import AlertOutputs

            outputs = AlertOutputs()
            outputs.update(fall_active=True, sos_active=False)
            self.assertFalse(outputs.green.value)
            self.assertTrue(outputs.red.value)
            self.assertTrue(outputs.buzzer.value)  # MH-FMD mức cao là tắt.

            outputs.update(fall_active=False, sos_active=True)
            self.assertTrue(outputs.red.value)
            self.assertFalse(outputs.buzzer.value)
            outputs.close()


if __name__ == "__main__":
    unittest.main()
