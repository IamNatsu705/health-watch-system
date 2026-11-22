"""Bộ đếm bước thử nghiệm dựa trên đỉnh gia tốc."""

import math


class StepCounter:
    def __init__(self, step_length_m: float, weight_kg: float):
        self.step_length_m = step_length_m
        self.weight_kg = weight_kg
        self.steps = 0
        self.gravity = 1.0
        self.filtered = 0.0
        self.previous = 0.0
        self.before_previous = 0.0
        self.last_step_time = float("-inf")

    def update(self, motion, now: float) -> None:
        magnitude = math.sqrt(motion.ax**2 + motion.ay**2 + motion.az**2)
        self.gravity = 0.95 * self.gravity + 0.05 * magnitude
        self.filtered = 0.6 * self.filtered + 0.4 * (magnitude - self.gravity)

        is_peak = (
            self.previous > 0.12
            and self.previous > self.before_previous
            and self.previous >= self.filtered
        )
        interval = now - self.last_step_time
        if is_peak and 0.35 <= interval and magnitude < 3.0:
            self.steps += 1
            self.last_step_time = now

        self.before_previous = self.previous
        self.previous = self.filtered

    @property
    def distance_km(self) -> float:
        return self.steps * self.step_length_m / 1000.0

    @property
    def calories_kcal(self) -> float:
        # Quy ước minh họa: 0,75 kcal cho mỗi kg cơ thể trên 1 km đi bộ.
        return self.distance_km * self.weight_kg * 0.75
