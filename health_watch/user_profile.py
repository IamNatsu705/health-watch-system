"""Hồ sơ người đeo (chiều cao, cân nặng) và ước tính quãng đường/năng lượng từ số bước.

Không có hồ sơ thật thì không ước tính: quãng đường và kcal là ``None`` và
màn hình/web hiện ``--`` thay vì nhân với một hằng số mẫu.

Công thức (đều là ước tính, ghi rõ trên giao diện):
* Chiều dài bước: giá trị người dùng tự đo (đi 20 bước, đo quãng đường, chia 20)
  nếu có; nếu không thì 0,414 × chiều cao, quy tắc kinh nghiệm phổ biến
  (0,413 nữ / 0,415 nam).
* Năng lượng hoạt động (không gồm chuyển hóa nghỉ) theo phương trình ACSM:
  đi bộ tốn 0,1 mL O2/kg/m, chạy 0,2 mL O2/kg/m, 1 L O2 ≈ 5 kcal
  → 0,5 kcal/kg/km khi đi, 1,0 kcal/kg/km khi chạy (nhịp >= 150 bước/phút).
"""

import math
from dataclasses import dataclass

HEIGHT_RANGE_CM = (100.0, 230.0)
WEIGHT_RANGE_KG = (25.0, 250.0)
STEP_LENGTH_RANGE_M = (0.25, 1.30)
HEIGHT_TO_STEP_RATIO = 0.414
WALK_KCAL_PER_KG_KM = 0.5
RUN_KCAL_PER_KG_KM = 1.0


def _number(value, name: str, limits: tuple[float, float]) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} phải là số")
    if not limits[0] <= float(value) <= limits[1]:
        raise ValueError(f"{name} phải trong khoảng {limits[0]}–{limits[1]}")
    return float(value)


@dataclass(frozen=True)
class UserProfile:
    height_cm: float
    weight_kg: float
    step_length_m: float | None = None
    updated_at: str | None = None

    @classmethod
    def from_dict(cls, document: dict) -> "UserProfile":
        if not isinstance(document, dict):
            raise ValueError("Hồ sơ phải là object")
        step = document.get("step_length_m")
        return cls(
            height_cm=_number(document.get("height_cm"), "height_cm", HEIGHT_RANGE_CM),
            weight_kg=_number(document.get("weight_kg"), "weight_kg", WEIGHT_RANGE_KG),
            step_length_m=None if step is None else _number(step, "step_length_m", STEP_LENGTH_RANGE_M),
            updated_at=document.get("updated_at") if isinstance(document.get("updated_at"), str) else None,
        )

    def to_dict(self) -> dict:
        return {
            "height_cm": self.height_cm,
            "weight_kg": self.weight_kg,
            "step_length_m": self.step_length_m,
            "updated_at": self.updated_at,
        }

    @property
    def effective_step_length_m(self) -> float:
        if self.step_length_m is not None:
            return self.step_length_m
        return round(HEIGHT_TO_STEP_RATIO * self.height_cm / 100.0, 3)

    @property
    def step_length_method(self) -> str:
        return "measured" if self.step_length_m is not None else "height_ratio"


def distance_m(steps: int, profile: UserProfile | None) -> float | None:
    if profile is None:
        return None
    return steps * profile.effective_step_length_m


def active_kcal(steps: int, running_steps: int, profile: UserProfile | None) -> float | None:
    if profile is None:
        return None
    running = max(0, min(running_steps, steps))
    km_per_step = profile.effective_step_length_m / 1000.0
    return profile.weight_kg * km_per_step * (
        WALK_KCAL_PER_KG_KM * (steps - running) + RUN_KCAL_PER_KG_KM * running
    )
