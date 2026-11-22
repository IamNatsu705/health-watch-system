"""Phát hiện ngã thử nghiệm bằng chuỗi rơi/va chạm, đổi hướng và nằm yên."""

import math


class FallDetector:
    FREE_FALL_G = 0.65
    IMPACT_G = 2.05
    HARD_IMPACT_G = 2.75
    MIN_FREE_FALL_S = 0.06
    MAX_FREE_FALL_S = 0.9
    TILT_TIMEOUT_S = 1.8
    STILL_TIME_S = 1.8
    CHECK_TIMEOUT_S = 6.0
    MIN_DIRECTION_CHANGE_DEG = 50.0
    MAX_STILL_GYRO_DPS = 49.0

    def __init__(self):
        self.state = "normal"
        self.state_since = 0.0
        self.free_since = 0.0
        self.still_since = None
        self.baseline = None
        self.before_impact = None
        self.magnitude_g = 0.0
        self.direction_change_deg = 0.0

    @property
    def confirmed(self) -> bool:
        return self.state == "confirmed"

    def clear(self) -> None:
        self.state = "normal"
        self.still_since = None
        self.before_impact = None
        self.direction_change_deg = 0.0

    def _begin_impact(self, now: float) -> None:
        self.state = "impact"
        self.state_since = now
        self.still_since = None
        self.before_impact = self.baseline
        self.direction_change_deg = 0.0

    def update(self, motion, now: float) -> bool:
        vector = (motion.ax, motion.ay, motion.az)
        magnitude = math.sqrt(sum(axis * axis for axis in vector))
        gyro = math.sqrt(motion.gx**2 + motion.gy**2 + motion.gz**2)
        self.magnitude_g = magnitude

        if self.confirmed:
            return True

        if self.state == "normal":
            if 0.8 <= magnitude <= 1.2 and gyro < self.MAX_STILL_GYRO_DPS:
                if self.baseline is None:
                    self.baseline = vector
                else:
                    self.baseline = tuple(0.9 * old + 0.1 * new for old, new in zip(self.baseline, vector))
            if magnitude < self.FREE_FALL_G:
                self.state = "free"
                self.free_since = now
            elif magnitude > self.HARD_IMPACT_G:
                self._begin_impact(now)

        elif self.state == "free":
            elapsed = now - self.free_since
            if self.MIN_FREE_FALL_S <= elapsed <= self.MAX_FREE_FALL_S and magnitude > self.IMPACT_G:
                self._begin_impact(now)
            elif elapsed > self.MAX_FREE_FALL_S:
                self.clear()

        elif self.state in ("impact", "still"):
            if self.before_impact is not None and magnitude > 0.01:
                old = self.before_impact
                old_mag = math.sqrt(sum(axis * axis for axis in old))
                if old_mag > 0.01:
                    cosine = sum(a * b for a, b in zip(old, vector)) / (old_mag * magnitude)
                    self.direction_change_deg = math.degrees(math.acos(max(-1.0, min(1.0, cosine))))

            if self.state == "impact":
                if (0.65 <= magnitude <= 1.35 and
                        self.direction_change_deg >= self.MIN_DIRECTION_CHANGE_DEG):
                    self.state = "still"
                    self.state_since = now
                    self.still_since = None
                elif now - self.state_since > self.TILT_TIMEOUT_S:
                    self.clear()
            else:
                stable = (self.direction_change_deg >= self.MIN_DIRECTION_CHANGE_DEG
                          and 0.65 <= magnitude <= 1.35
                          and gyro < self.MAX_STILL_GYRO_DPS)
                if stable:
                    if self.still_since is None:
                        self.still_since = now
                    elif now - self.still_since >= self.STILL_TIME_S:
                        self.state = "confirmed"
                else:
                    self.still_since = None
                if not self.confirmed and now - self.state_since > self.CHECK_TIMEOUT_S:
                    self.clear()

        return self.confirmed
