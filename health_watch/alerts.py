"""Nút SOS, hai LED và còi MH-FMD trên Raspberry Pi."""

import board
import digitalio

from config import BUZZER_GPIO, GREEN_LED_GPIO, RED_LED_GPIO, SOS_BUTTON_GPIO


class AlertOutputs:
    def __init__(self):
        self.green = digitalio.DigitalInOut(getattr(board, f"D{GREEN_LED_GPIO}"))
        self.red = digitalio.DigitalInOut(getattr(board, f"D{RED_LED_GPIO}"))
        self.buzzer = digitalio.DigitalInOut(getattr(board, f"D{BUZZER_GPIO}"))
        self.button = digitalio.DigitalInOut(getattr(board, f"D{SOS_BUTTON_GPIO}"))

        self.green.switch_to_output(value=False)
        self.red.switch_to_output(value=False)
        self.buzzer.switch_to_output(value=True)  # Mức cao = còi tắt.
        self.button.switch_to_input(pull=digitalio.Pull.UP)

    @property
    def button_pressed(self) -> bool:
        return not self.button.value  # Nhấn nối GPIO23 xuống GND.

    def update(self, fall_active: bool = False, sos_active=None, buzzer_active=None) -> bool:
        """``buzzer_active`` = trạng thái chân còi lúc này (main.py bíp ngắt quãng khi báo ngã);
        bỏ trống thì còi theo SOS như check_alerts.py."""
        if sos_active is None:
            sos_active = self.button_pressed
        if buzzer_active is None:
            buzzer_active = sos_active
        self.green.value = not (fall_active or sos_active)
        self.red.value = fall_active or sos_active
        self.buzzer.value = not buzzer_active  # MH-FMD: mức thấp = kêu.
        return sos_active

    def close(self) -> None:
        self.green.value = False
        self.red.value = False
        self.buzzer.value = True
        for pin in (self.button, self.green, self.red, self.buzzer):
            pin.deinit()
