"""SI sensor/estimator settings; RC outputs retain the existing microsecond scale."""
import json
import math
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class AltConfig:
    i2c_bus: int = 1
    bmp_address: int = 0x47
    tof_address: int = 0x29
    bmp_period_s: float = 0.05
    tof_period_s: float = 0.05
    tof_budget_ms: int = 20
    stale_s: float = 0.20
    ground_sensor_height_m: float = 0.04
    tof_min_m: float = 0.02
    tof_max_m: float = 0.90
    target_min_m: float = 0.10
    target_max_m: float = 0.70
    jump_m: float = 0.10
    max_speed_m_s: float = 1.5
    height_tau_s: float = 0.08
    velocity_tau_s: float = 0.15
    qualify_s: float = 1.0
    max_enable_velocity_m_s: float = 0.15
    calibration_s: float = 2.0
    calibration_pressure_span_pa: float = 20.0
    calibration_distance_span_m: float = 0.015
    freeze_s: float = 2.0
    kp: float = 0.0
    ki: float = 0.0
    kd: float = 0.0
    integral_limit_m_s: float = 0.25
    throttle_min: int = 1000
    throttle_max: int = 1200
    correction_limit: float = 40.0
    slew_per_s: float = 80.0
    control_period_s: float = 0.02
    max_dt_s: float = 0.10
    estimator_mode: str = "tof"
    baro_weight: float = 0.1
    baro_disagreement_m: float = 0.3
    loss_policy: str = "bench-disarm"
    manual_hover_verified: bool = False
    verified_hover_throttle: float = 0.0
    sensor_range_verified: bool = False
    gains_verified: bool = False
    loss_policy_tested: bool = False
    fc_failsafe_tested: bool = False
    near_level_operation_accepted: bool = False
    verification_notes: str = ""

    def __post_init__(self):
        for k, v in asdict(self).items():
            if isinstance(v, (float, int)) and not isinstance(v, bool) and not math.isfinite(v):
                raise ValueError(k + " must be finite")
        for k in ("manual_hover_verified", "sensor_range_verified", "gains_verified",
                  "loss_policy_tested", "fc_failsafe_tested", "near_level_operation_accepted"):
            if type(getattr(self, k)) is not bool:
                raise ValueError(k + " must be boolean")
        if self.bmp_address not in (0x46, 0x47) or not 8 <= self.tof_address <= 119:
            raise ValueError("invalid sensor address")
        if type(self.i2c_bus) is not int or self.i2c_bus < 0:
            raise ValueError("invalid I2C bus")
        if self.bmp_period_s not in (0.025, 0.05, 0.1, 0.2):
            raise ValueError("BMP period must be 0.025, 0.05, 0.1 or 0.2 s")
        if not 10 <= self.tof_budget_ms <= 200 or not self.tof_budget_ms / 1000 <= self.tof_period_s <= 5:
            raise ValueError("invalid ToF timing budget/period")
        if not 0 < self.tof_min_m < self.ground_sensor_height_m < self.tof_max_m < 1.2:
            raise ValueError("ToF range/mount height invalid; operational maximum must be <1.2m")
        if not 0 <= self.target_min_m < self.target_max_m < self.tof_max_m - self.ground_sensor_height_m:
            raise ValueError("target range must leave ToF headroom")
        if not 1000 == self.throttle_min < self.throttle_max <= 2000:
            raise ValueError("invalid RC throttle limits")
        for k in ("stale_s", "jump_m", "max_speed_m_s", "height_tau_s", "velocity_tau_s",
                  "qualify_s", "calibration_s", "freeze_s", "correction_limit", "slew_per_s",
                  "integral_limit_m_s", "control_period_s", "max_dt_s",
                  "max_enable_velocity_m_s", "calibration_pressure_span_pa",
                  "calibration_distance_span_m", "baro_disagreement_m"):
            if getattr(self, k) <= 0:
                raise ValueError(k + " must be positive")
        if min(self.kp, self.ki, self.kd) < 0 or not 0 <= self.baro_weight <= 0.25:
            raise ValueError("invalid gains/weight")
        if not max(self.tof_period_s, self.bmp_period_s) < self.stale_s <= 0.5:
            raise ValueError("stale time must exceed sensor periods and be <=0.5s")
        if not 0.01 <= self.control_period_s < self.max_dt_s <= 0.2:
            raise ValueError("invalid control period/dt limit")
        if self.estimator_mode not in ("tof", "comparison-blend"):
            raise ValueError("unknown estimator mode")
        if self.loss_policy not in ("bench-disarm", "manual-recover"):
            raise ValueError("explicit loss policy required")

    def validate_live(self):
        checks = (self.manual_hover_verified, self.sensor_range_verified, self.gains_verified,
                  self.loss_policy_tested, self.fc_failsafe_tested,
                  self.near_level_operation_accepted, bool(self.verification_notes.strip()),
                  self.throttle_min < self.verified_hover_throttle < self.throttle_max,
                  self.kp > 0, self.estimator_mode == "tof")
        if not all(checks):
            raise ValueError("live disabled: manual hover, range, gains, loss policy, FC failsafe "
                             "and near-level verification with notes are required; ToF mode only")


def load_config(path=None):
    if path is None:
        return AltConfig()
    with open(path, encoding="utf-8") as f:
        return AltConfig(**json.load(f))
