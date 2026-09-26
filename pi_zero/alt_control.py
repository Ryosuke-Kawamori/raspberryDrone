"""Pure controller/supervisor. Inputs are RC units, metres, seconds; never newtons."""
from rc_protocol import default_rc


def clip(x, lo, hi):
    return max(lo, min(hi, x))


class PID:
    def __init__(self, c):
        self.c = c
        self.reset()

    def reset(self):
        self.integral = 0.0
        self.terms = {"p": 0.0, "i": 0.0, "d": 0.0, "limited": False}

    def step(self, error, velocity, base, previous, dt):
        c = self.c
        proposed = clip(self.integral + error*dt, -c.integral_limit_m_s, c.integral_limit_m_s)
        p, d = c.kp*error, -c.kd*velocity
        low = max(c.throttle_min, base-c.correction_limit, previous-c.slew_per_s*dt)
        high = min(c.throttle_max, base+c.correction_limit, previous+c.slew_per_s*dt)
        raw = base+p+c.ki*proposed+d
        out = clip(raw, low, high)
        # Conditional integration includes correction, absolute AND slew saturation.
        if c.ki and (raw == out or (raw-out)*error <= 0):
            self.integral = proposed
        raw = base+p+c.ki*self.integral+d
        out = clip(raw, low, high)
        self.terms = {"p": p, "i": c.ki*self.integral, "d": d, "raw": raw,
                      "limited": out != raw, "lower": low, "upper": high}
        return out


class AltController:
    def __init__(self, c, mode="shadow"):
        self.c, self.mode, self.pid = c, mode, PID(c)
        self.state = "DISARMED"
        self.fault = ""
        self.target = None
        self.base = 1000.0
        self.auto = 1000.0
        self.last_at = None
        self.on_previous = False
        self.off_seen = False
        self.offset_at_on = 0.0
        self.capture = None
        self.releasing = False
        self.fault_off_seen = False

    def step(self, now, rc, estimate, hold=False, offset=0.0, link_ok=True, secure=False):
        old = self.state
        dt = now-self.last_at if self.last_at is not None else self.c.control_period_s
        self.last_at = now
        out = rc.copy()
        rising = hold and not self.on_previous
        self.on_previous = hold
        if not hold:
            self.off_seen = True
        # Emergency/disarm/link loss bypasses all smoothing.
        if not link_ok or not rc["arm"]:
            self.pid.reset()
            self.auto = rc["throttle"] if link_ok else 1000
            self.releasing = False
            self.target = None
            if self.state == "FAULT":
                if link_ok and not rc["arm"]:
                    self.fault_off_seen = True
            elif not link_ok:
                self._fault("UDP timeout/failsafe")
            else:
                self.state = "DISARMED"
            out = rc.copy() if link_ok else default_rc()
        else:
            if self.state == "FAULT" and self.fault_off_seen and not hold:
                self.state, self.fault = "MANUAL", ""
                self.fault_off_seen = False
            if self.state == "DISARMED":
                self.state = "MANUAL"
                self.auto = rc["throttle"]
            if self.state == "ALT_HOLD" and not hold:
                self.state = "MANUAL"  # explicit manual release wins over sensor fault
                self.pid.reset()
                self.releasing = True
                self.target = None
            if self.state == "ALT_HOLD":
                if not 0 < dt <= self.c.max_dt_s:
                    self._fault("control dt abnormal")
                elif not estimate["valid"]:
                    self._fault(estimate["quality"])
                else:
                    self.target = clip(self.capture+offset-self.offset_at_on,
                                       self.c.target_min_m, self.c.target_max_m)
                    self.auto = self.pid.step(self.target-estimate["height_m"],
                                              estimate["velocity_m_s"], self.base, self.auto, dt)
            elif self.state == "MANUAL":
                if self.releasing:
                    if not 0 < dt <= self.c.max_dt_s:
                        self._fault("release dt abnormal")
                    else:
                        self.auto += clip(rc["throttle"]-self.auto, -self.c.slew_per_s*dt, self.c.slew_per_s*dt)
                        self.releasing = abs(self.auto-rc["throttle"]) > 0.01
                else:
                    self.auto = rc["throttle"]
                if rising and self.off_seen and not self.releasing:
                    allowed = (estimate["qualified"] and estimate["valid"]
                               and self.c.target_min_m <= estimate["height_m"] <= self.c.target_max_m
                               and abs(estimate["velocity_m_s"]) <= self.c.max_enable_velocity_m_s
                               and (self.mode != "live" or secure))
                    if allowed:
                        self.state, self.fault = "ALT_HOLD", ""
                        self.target = self.capture = estimate["height_m"]
                        self.offset_at_on = offset
                        self.base = self.auto = float(rc["throttle"])
                        self.pid.reset()  # first output EXACTLY manual; derivative next tick is slew limited
                    else:
                        self.fault = "ON rejected: stable/fresh range, low velocity and secure command required"
            if self.mode == "live":
                if self.state == "FAULT":
                    out = default_rc() if self.c.loss_policy == "bench-disarm" else rc.copy()
                elif self.state == "ALT_HOLD" or self.releasing:
                    out["throttle"] = round(self.auto)
            # shadow ALWAYS outputs the original manual RC, including sensor faults.
        return out, {"state": self.state, "transition": old+"->"+self.state if old != self.state else "",
                     "fault": self.fault, "target_m": self.target, "manual_throttle": rc["throttle"],
                     "auto_throttle": self.auto, "output_throttle": out["throttle"],
                     "pid": self.pid.terms.copy(), "control_dt_s": dt, "releasing": self.releasing}

    def _fault(self, reason):
        self.state, self.fault = "FAULT", reason
        self.pid.reset()
        self.target = None
        self.releasing = False
        self.off_seen = False
        self.fault_off_seen = False
