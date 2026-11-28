"""Nối bộ đếm bước của phiên với số liệu trong ngày, hồ sơ người đeo và màn hình."""

from types import SimpleNamespace

from processing.steps import StepEngine
from storage import DailyStepStore
from user_profile import active_kcal, distance_m


class StepTracker:
    """Nối bộ đếm phiên với số bước trong ngày và hồ sơ người đeo.

    Quãng đường/kcal được cộng dồn theo từng nhóm bước mới với hồ sơ tại thời điểm đó,
    nên đổi hồ sơ giữa chừng không tính lại các bước đã đi trước đó.
    """

    def __init__(self, engine: StepEngine, daily: DailyStepStore, profile):
        self.engine = engine
        self.daily = daily
        self.profile = profile
        self.session_distance_m = 0.0
        self.session_kcal = 0.0
        self._last = (0, 0, 0, 0)

    @property
    def source_key(self) -> str:
        return "ai" if self.engine.gate is not None else "algorithm"

    def sync(self) -> None:
        self.daily.refresh()
        engine = self.engine
        current = (
            engine.steps_algorithm,
            engine.running_steps_algorithm,
            engine.steps_ai or 0,
            engine.running_steps_ai or 0,
        )
        deltas = [now - before for now, before in zip(current, self._last)]
        self._last = current
        if not any(deltas):
            return
        steps, running = (deltas[2], deltas[3]) if self.source_key == "ai" else (deltas[0], deltas[1])
        distance = distance_m(steps, self.profile) or 0.0
        kcal = active_kcal(steps, running, self.profile) or 0.0
        self.session_distance_m += distance
        self.session_kcal += kcal
        self.daily.add(algorithm=deltas[0], algorithm_running=deltas[1], ai=deltas[2], ai_running=deltas[3],
                       distance_m=distance, kcal=kcal)

    def screen_view(self, imu) -> SimpleNamespace:
        counts = self.daily.counts
        has_profile = self.profile is not None
        return SimpleNamespace(
            steps=counts[self.source_key],
            title="BƯỚC HÔM NAY" if self.daily.date_known else "BƯỚC TỪ KHI BẬT",
            source_label="AI" if self.engine.gate is not None else "Thuật toán",
            distance_km=counts["distance_m"] / 1000.0 if has_profile else None,
            calories_kcal=counts["kcal"] if has_profile else None,
            imu_ok=imu.ok,
        )

    def session_estimates(self) -> tuple[float | None, float | None]:
        if self.profile is None:
            return None, None
        return self.session_distance_m, self.session_kcal

    def distance_basis(self) -> dict | None:
        if self.profile is None:
            return None
        return {
            "step_length_m": self.profile.effective_step_length_m,
            "method": self.profile.step_length_method,
        }
