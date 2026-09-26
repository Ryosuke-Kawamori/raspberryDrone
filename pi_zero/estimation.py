"""ToF relative height; barometric comparison never supplies a ToF outage."""
import math
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class Attitude:
    roll_rad: float
    pitch_rad: float
    at_s: float


class Estimator:
    def __init__(self, config):
        self.c = config
        self.last_seq = {}
        self.raw = {}
        self.height = None
        self.velocity = 0.0
        self.at = None
        self.good_since = None
        self.error = "waiting for ToF"
        self.last_distance = None
        self.same_since = None
        self.baro_height = None
        self.baro_at = None
        self.baro_error = "uncalibrated"
        self.p0 = None
        self.t0_k = None
        self.calibration = deque()
        self.ground = deque()
        self.bias = None
        self.tilt = "unmeasured: near-level only"

    def reject(self, reason):
        self.error = reason
        self.good_since = None

    def update(self, sample, now, armed=False, attitude=None):
        c = self.c
        self.raw[sample.sensor] = sample
        if sample.sensor not in ("tof", "bmp"):
            return
        if (not sample.valid or not math.isfinite(sample.at_s) or
                not 0 <= now - sample.at_s <= c.stale_s):
            reason = sample.error or "stale/future sample"
            if sample.sensor == "tof":
                self.reject(reason)
            else:
                self.baro_error = reason
                self.calibration.clear()
            return
        previous = self.last_seq.get(sample.sensor)
        if previous and (sample.seq <= previous[0] or sample.at_s <= previous[1]):
            return  # duplicates cannot refresh age or qualification
        self.last_seq[sample.sensor] = (sample.seq, sample.at_s)
        if sample.sensor == "bmp":
            self._barometer(sample, armed)
            return
        d = sample.values.get("distance_m", float("nan"))
        if sample.status not in (None, 0) or not math.isfinite(d) or not c.tof_min_m <= d < c.tof_max_m:
            self.reject("ToF status/out of operational range")
            return
        if attitude is not None:
            if (not 0 <= now - attitude.at_s <= c.stale_s or
                    not all(math.isfinite(x) and abs(x) <= math.radians(20)
                            for x in (attitude.roll_rad, attitude.pitch_rad))):
                self.reject("attitude stale/tilt too large")
                return
            d *= math.cos(attitude.roll_rad) * math.cos(attitude.pitch_rad)
            self.tilt = "corrected: horizontal floor assumed"
        else:
            self.tilt = "unmeasured: near-level only"
        dt = sample.at_s - self.at if self.at is not None else None
        if self.last_distance is not None and dt and dt <= c.stale_s:
            if abs(d - self.last_distance) > c.jump_m + c.max_speed_m_s * dt:
                self.reject("ToF jump")
                return
        if self.last_distance != d or self.same_since is None or not armed:
            self.same_since = sample.at_s
        elif sample.at_s - self.same_since > c.freeze_s:
            self.reject("ToF constant-value freeze suspected")
            return
        self.last_distance = d
        z = d - c.ground_sensor_height_m
        if not armed:
            self.ground.append((sample.at_s, d))
            while self.ground and sample.at_s-self.ground[0][0] > c.calibration_s + c.stale_s:
                self.ground.popleft()
        else:
            self.ground.clear()
            self.calibration.clear()
        if c.estimator_mode == "comparison-blend":
            if self.baro_height is None or self.baro_at is None or sample.at_s-self.baro_at > c.stale_s or self.baro_error:
                self.reject("comparison blend requires both sensors")
                return
            if self.bias is None:
                self.bias = z - self.baro_height  # one fixed common-frame bias per process
            aligned = self.baro_height + self.bias
            if abs(aligned-z) > c.baro_disagreement_m:
                self.reject("barometer/ToF disagreement")
                return
            z = (1-c.baro_weight)*z + c.baro_weight*aligned
        if dt is None or dt > c.stale_s or self.height is None or self.error:
            self.height, self.velocity = z, 0.0
            self.good_since = sample.at_s
        else:
            old = self.height
            self.height += dt / (c.height_tau_s + dt) * (z-self.height)
            self.velocity += dt / (c.velocity_tau_s + dt) * ((self.height-old)/dt-self.velocity)
        self.at = sample.at_s
        self.error = ""

    def _barometer(self, s, armed):
        p, t = s.values.get("pressure_pa", 0), s.values.get("temperature_c", float("nan"))
        if not math.isfinite(p) or not 30000 <= p <= 125000 or not math.isfinite(t) or not -40 <= t <= 85:
            self.baro_error = "invalid pressure/temperature"
            self.calibration.clear()
            return
        c = self.c
        if armed:
            self.calibration.clear()
        if self.p0 is None and not armed:
            self.calibration.append((s.at_s, p, t))
            while self.calibration and s.at_s-self.calibration[0][0] > c.calibration_s + c.stale_s:
                self.calibration.popleft()
            rows = list(self.calibration)
            ground = list(self.ground)
            stationary = (len(ground) >= 2 and ground[-1][0]-ground[0][0] >= c.calibration_s
                          and abs(ground[-1][1]-c.ground_sensor_height_m) <= c.calibration_distance_span_m
                          and max(x[1] for x in ground)-min(x[1] for x in ground) <= c.calibration_distance_span_m
                          and max(b[0]-a[0] for a,b in zip(ground, ground[1:])) <= c.stale_s
                          and s.at_s-ground[-1][0] <= c.stale_s)
            if (len(rows) >= 2 and rows[-1][0]-rows[0][0] >= c.calibration_s and stationary
                    and max(x[1] for x in rows)-min(x[1] for x in rows) <= c.calibration_pressure_span_pa
                    and max(b[0]-a[0] for a,b in zip(rows, rows[1:])) <= c.stale_s):
                self.p0 = sum(x[1] for x in rows)/len(rows)
                self.t0_k = sum(x[2] for x in rows)/len(rows) + 273.15
        if self.p0 is not None:
            self.baro_height = 287.05*self.t0_k/9.80665*math.log(self.p0/p)
            self.baro_at = s.at_s
            self.baro_error = ""

    def snapshot(self, now):
        age = now-self.at if self.at is not None else None
        valid = not self.error and age is not None and 0 <= age <= self.c.stale_s
        if not valid:
            self.good_since = None
        return {"height_m": self.height, "velocity_m_s": self.velocity, "age_s": age,
                "valid": valid, "quality": "good" if valid else (self.error or "ToF stale"),
                "qualified": valid and self.good_since is not None and now-self.good_since >= self.c.qualify_s,
                "baro_height_m": self.baro_height, "baro_age_s": None if self.baro_at is None else now-self.baro_at,
                "baro_error": self.baro_error, "p0_pa": self.p0, "tilt": self.tilt,
                "height_filter_delay_s": self.c.height_tau_s,
                "velocity_filter_delay_s": self.c.height_tau_s+self.c.velocity_tau_s,
                "blend_bias_m": self.bias}
