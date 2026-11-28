"""Báo động sau khi phát hiện ngã: có thời gian để người đeo hủy, rồi mới báo động liên tục.

Làm theo cách các đồng hồ thương mại xử lý báo nhầm (Samsung: cảnh báo 60 s rồi gửi SOS;
Apple: nằm yên khoảng 1 phút rồi đếm ngược 30 s). Phát hiện ngã (``processing/fall.py``,
luật ngưỡng, chưa kiểm định) chỉ là bước bắt đầu:

* ``check``: LED đỏ + còi bíp ngắt quãng, màn hình đếm ngược ``cancel_window_s``. Bấm nút
  = người đeo báo ổn (sự kiện ``fall_cancelled``).
* Hết thời gian hủy mà người đeo **nằm yên** (không cử động trong ``immobile_s`` gần nhất)
  → ``alarm``: còi kêu liên tục, gửi ``fall_alarm`` lên web. Bấm nút = tắt (``fall_acknowledged``).
* Hết thời gian hủy nhưng người đeo **đang cử động** (đã đứng dậy, đi lại) → vẫn ``check``,
  chờ bấm nút; nếu sau đó nằm yên đủ ``immobile_s`` thì chuyển ``alarm``.
* Không có mẫu IMU (cảm biến lỗi) thì không chứng minh được là người đeo cử động, nên coi
  như nằm yên: thà báo động thừa còn hơn bỏ sót một cú ngã.

Cử động được nhận ra khi vector gia tốc lệch khỏi trung bình trượt (~1 s) quá
``motion_g``: bắt được cả gia tốc động lẫn xoay cổ tay (đổi hướng trọng lực), và không phụ
thuộc sai số offset của MPU6050 (gyro có thể lệch tới ±20 °/s khi chưa hiệu chuẩn).
"""

import math

IDLE = "idle"
CHECK = "check"
ALARM = "alarm"


class FallAlarm:
    def __init__(self, cancel_window_s: float = 30.0, immobile_s: float = 10.0,
                 motion_g: float = 0.1, beep_period_s: float = 1.0, beep_on_s: float = 0.5,
                 baseline_tau_s: float = 1.0):
        self.cancel_window_s = cancel_window_s
        self.immobile_s = immobile_s
        self.motion_g = motion_g
        self.beep_period_s = beep_period_s
        self.beep_on_s = beep_on_s
        self.baseline_tau_s = baseline_tau_s
        self.state = IDLE
        self.started_at = None
        self.last_motion_at = None
        self._baseline = None
        self._last_sample_at = None

    @property
    def active(self) -> bool:
        return self.state != IDLE

    def start(self, now: float) -> bool:
        """Bắt đầu thời gian hủy; trả False nếu đang báo động rồi (không khởi động lại đồng hồ)."""
        if self.active:
            return False
        self.state = CHECK
        self.started_at = now
        self.last_motion_at = now  # nằm yên được tính từ lúc phát hiện ngã
        return True

    def observe(self, ax: float, ay: float, az: float, t: float) -> None:
        """Nhận từng mẫu gia tốc (g) để biết người đeo có cử động sau cú ngã không."""
        if self._baseline is None or self._last_sample_at is None:
            self._baseline = (ax, ay, az)
            self._last_sample_at = t
            return
        dt = min(max(t - self._last_sample_at, 0.0), 1.0)
        self._last_sample_at = t
        bx, by, bz = self._baseline
        deviation = math.sqrt((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2)
        if self.active and deviation > self.motion_g:
            self.last_motion_at = t
        keep = math.exp(-dt / self.baseline_tau_s)
        self._baseline = (keep * bx + (1 - keep) * ax, keep * by + (1 - keep) * ay, keep * bz + (1 - keep) * az)

    def update(self, now: float) -> bool:
        """Trả True đúng một lần, khi chuyển sang báo động liên tục."""
        if self.state != CHECK:
            return False
        if now - self.started_at >= self.cancel_window_s and now - self.last_motion_at >= self.immobile_s:
            self.state = ALARM
            return True
        return False

    def acknowledge(self) -> str:
        """Người đeo bấm nút: trả pha lúc bấm (``check`` = hủy, ``alarm`` = tắt) rồi về bình thường."""
        phase = self.state
        self.state = IDLE
        self.started_at = None
        self.last_motion_at = None
        return phase

    def buzzer_on(self, now: float) -> bool:
        """Trạng thái chân còi lúc này: bíp ngắt quãng khi chờ hủy, kêu liên tục khi báo động."""
        if self.state == ALARM:
            return True
        if self.state == CHECK:
            return (now - self.started_at) % self.beep_period_s < self.beep_on_s
        return False

    def remaining_s(self, now: float) -> float | None:
        if self.state != CHECK:
            return None
        return max(0.0, self.cancel_window_s - (now - self.started_at))
