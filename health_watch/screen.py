"""Giao diện đồng hồ sức khỏe dạng thẻ trên TFT ST7789V3 240x280."""

from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import DISPLAY_HEIGHT, DISPLAY_ROTATION, DISPLAY_WIDTH, DISPLAY_Y_OFFSET


BACKGROUND = (3, 10, 17)
CARD = (7, 19, 28)
WHITE = (235, 244, 248)
MUTED = (137, 162, 175)
CYAN = (35, 202, 237)
RED = (255, 76, 91)
GREEN = (82, 229, 78)


def _font(size: int, bold: bool = False):
    filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    candidates = (
        Path("/usr/share/fonts/truetype/dejavu") / filename,
        Path("C:/Windows/Fonts") / ("arialbd.ttf" if bold else "arial.ttf"),
    )
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


FONT_SMALL = _font(10)
FONT_LABEL = _font(12, True)
FONT_TITLE = _font(16, True)
FONT_VALUE = _font(30, True)
FONT_STATUS = _font(15, True)


def _centered(draw, y: int, text: str, font, color) -> None:
    bounds = draw.textbbox((0, 0), text, font=font)
    width = bounds[2] - bounds[0]
    draw.text(((DISPLAY_WIDTH - width) // 2, y), text, font=font, fill=color)


def _pulse_trace(draw, pulse) -> None:
    x0, x1, y0, y1 = 153, 219, 75, 98
    draw.line((x0, 87, x1, 87), fill=(35, 66, 72), width=1)
    # Không có ngón tay: chỉ hiện đường nền, tránh phóng đại nhiễu IR thành sóng tim.
    if not pulse.finger_present:
        return
    values = list(pulse.ir_history)[-45:]
    if len(values) < 3:
        return
    low, high = min(values), max(values)
    spread = max(1, high - low)
    points = [
        (x0 + round(i * (x1 - x0) / (len(values) - 1)),
         y1 - round((value - low) * (y1 - y0) / spread))
        for i, value in enumerate(values)
    ]
    draw.line(points, fill=RED, width=2)


def render_dashboard(steps, pulse, alert_state: str, now=None):
    """Tạo ảnh bằng Pillow; chạy được cả trên PC để kiểm tra bố cục."""
    now = now or datetime.now()
    image = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle((2, 2, 237, 277), radius=18, outline=(36, 64, 78), width=2)
    draw.text((13, 9), now.strftime("%H:%M:%S"), font=FONT_LABEL, fill=WHITE)
    draw.rounded_rectangle((174, 8, 223, 27), radius=8, outline=GREEN, width=1)
    draw.ellipse((181, 14, 187, 20), fill=GREEN)
    draw.text((191, 12), "LIVE", font=FONT_SMALL, fill=GREEN)

    draw.rounded_rectangle((9, 43, 230, 114), radius=10, fill=CARD, outline=CYAN, width=2)
    draw.ellipse((20, 66, 48, 94), outline=RED, width=2)
    draw.text((27, 67), "♥", font=FONT_TITLE, fill=RED)
    draw.text((57, 51), "NHỊP TIM", font=FONT_LABEL, fill=WHITE)
    bpm = str(pulse.bpm) if pulse.bpm is not None else "--"
    draw.text((55, 69), bpm, font=FONT_VALUE, fill=RED)
    draw.text((113, 89), "BPM~", font=FONT_SMALL, fill=MUTED)
    _pulse_trace(draw, pulse)
    if not pulse.finger_present:
        pulse_status = "Đặt tay"
    elif len(pulse.ir_history) < pulse.sample_rate * 5:
        pulse_status = "Lấy mẫu"
    elif pulse.bpm is None:
        pulse_status = "Chưa rõ"
    else:
        pulse_status = "Đang đo"
    draw.text(
        (155, 99), pulse_status,
        font=FONT_SMALL, fill=GREEN if pulse.bpm is not None else MUTED,
    )

    draw.rounded_rectangle((9, 130, 230, 201), radius=10, fill=CARD, outline=CYAN, width=2)
    draw.ellipse((22, 154, 31, 161), fill=CYAN)
    draw.ellipse((31, 160, 40, 167), fill=CYAN)
    draw.rounded_rectangle((21, 162, 29, 176), radius=3, fill=CYAN)
    draw.rounded_rectangle((31, 168, 39, 182), radius=3, fill=CYAN)
    draw.text((55, 137), "BƯỚC CHÂN", font=FONT_LABEL, fill=WHITE)
    draw.text((55, 156), str(steps.steps), font=FONT_VALUE, fill=CYAN)
    draw.text((160, 164), "bước", font=FONT_SMALL, fill=MUTED)
    draw.line((55, 186, 218, 186), fill=(34, 70, 82), width=1)
    draw.text((55, 188), f"{steps.distance_km:.3f} km", font=FONT_SMALL, fill=WHITE)
    draw.text((150, 188), f"{steps.calories_kcal:.2f} kcal~", font=FONT_SMALL, fill=GREEN)

    accent = RED if alert_state else GREEN
    draw.rounded_rectangle((9, 223, 230, 266), radius=10, fill=CARD, outline=accent, width=2)
    draw.ellipse((20, 233, 44, 257), outline=accent, width=2)
    draw.ellipse((28, 242, 32, 246), fill=accent)
    draw.ellipse((35, 242, 39, 246), fill=accent)
    draw.arc((26, 243, 40, 253), 15 if alert_state else 0, 165 if alert_state else 180, fill=accent, width=2)
    title = "PHÁT HIỆN NGÃ" if alert_state == "fall" else ("SOS ĐANG BẬT" if alert_state == "sos" else "BÌNH THƯỜNG")
    detail = "Nhấn nút để xác nhận" if alert_state == "fall" else ("LED đỏ + còi" if alert_state == "sos" else "Nhấn nút để thử SOS")
    draw.text((52, 229), title, font=FONT_STATUS, fill=accent)
    draw.text((53, 249), detail, font=FONT_SMALL, fill=MUTED)
    return image


class Screen:
    def __init__(self):
        import board
        import digitalio
        from adafruit_rgb_display import st7789

        spi = board.SPI()
        dc = digitalio.DigitalInOut(board.D25)
        reset = digitalio.DigitalInOut(board.D24)
        # CE0 do /dev/spidev0.0 điều khiển, tránh giữ GPIO8 lần hai.
        self.display = st7789.ST7789(
            spi, cs=None, dc=dc, rst=reset,
            width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT,
            x_offset=0, y_offset=DISPLAY_Y_OFFSET,
            rotation=0, baudrate=8_000_000,
        )

    def _send(self, image) -> None:
        self.display.image(image.rotate(DISPLAY_ROTATION))

    def status(self, title: str, detail: str = "") -> None:
        image = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), BACKGROUND)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((9, 9, 230, 270), radius=12, outline=CYAN, width=2)
        _centered(draw, 98, title, FONT_TITLE, WHITE)
        _centered(draw, 131, detail, FONT_SMALL, MUTED)
        self._send(image)

    def update(self, steps, pulse, alert_state: str) -> None:
        self._send(render_dashboard(steps, pulse, alert_state))
