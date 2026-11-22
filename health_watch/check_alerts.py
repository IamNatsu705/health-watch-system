"""Thử nút SOS, LED xanh/đỏ và còi, không cần cảm biến hay màn hình."""

import time

from alerts import AlertOutputs


alerts = AlertOutputs()
last_state = None
print("Nhan nut SOS: LED do + coi bat; tha nut: LED xanh bat. Ctrl+C de dung.")
try:
    while True:
        pressed = alerts.update()
        if pressed != last_state:
            print("SOS: DANG NHAN" if pressed else "SOS: DA THA")
            last_state = pressed
        time.sleep(0.03)
except KeyboardInterrupt:
    print("Da dung thu nut/den/coi.")
finally:
    alerts.close()
