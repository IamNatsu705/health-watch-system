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

    def update(self, fall_active: bool = False, sos_active=None) -> bool:
        if sos_active is None:
            sos_active = self.button_pressed
        self.green.value = not (fall_active or sos_active)
        self.red.value = fall_active or sos_active
        self.buzzer.value = not sos_active  # Chỉ SOS bật còi; ngã chỉ bật LED đỏ.
        return sos_active

    def close(self) -> None:
        self.green.value = False
        self.red.value = False
        self.buzzer.value = True
        for pin in (self.button, self.green, self.red, self.buzzer):
            pin.deinit()
