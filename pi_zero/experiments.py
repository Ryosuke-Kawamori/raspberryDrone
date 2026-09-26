"""Deterministic replay and illustrative 1D plant; not a flight qualification."""
import json
import random
from collections import deque
from dataclasses import asdict, replace
from pathlib import Path

from pi_zero.alt_control import AltController, clip
from pi_zero.alt_config import AltConfig
from pi_zero.estimation import Estimator
from pi_zero.sensors import Sample
from rc_protocol import default_rc


def replay(config, input_path, output_path):
    if Path(input_path).resolve() == Path(output_path).resolve():
        raise ValueError("replay output must differ from input")
    est = ctl = None
    count, last = 0, None
    with open(input_path, encoding="utf-8") as src, open(output_path, "w", encoding="utf-8") as dst:
        for line in src:
            row = json.loads(line)
            if row.get("type") == "settings" and config is None:
                config = AltConfig(**row["config"])
            if row.get("type") != "tick":
                continue
            if est is None:
                config = config or AltConfig()
                est, ctl = Estimator(config), AltController(config, "shadow")
            now = row["at_s"]
            if last is not None and now <= last:
                raise ValueError("replay timestamps must increase")
            last = now
            rc = row.get("input_rc", default_rc())
            for raw in row.get("samples", []):
                est.update(Sample(**raw), now, rc["arm"])
            estimate = est.snapshot(now)
            out, control = ctl.step(now, rc, estimate, row.get("hold", False), row.get("offset_m", 0),
                                    row.get("link_ok", True), row.get("secure", False))
            dst.write(json.dumps({"at_s": now, **estimate, **control, "output_rc": out})+"\n")
            count += 1
    return {"replayed_ticks": count, "output": str(output_path), "uart_opened": False}


def simulate(config, path, seed=7):
    # Explicitly synthetic gains/hover/plant, unrelated to Meteor85 tuning.
    c = replace(config, kp=110, kd=65, ki=0, throttle_max=1600, correction_limit=100,
                slew_per_s=200, freeze_s=5)
    est, ctl, rng = Estimator(c), AltController(c, "live"), random.Random(seed)
    z, v, thrust, peak, final = .4, 0.0, 0.0, 0.0, 0.0
    pending = deque()
    saturated = 0
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "settings", "config": asdict(c), "mode": "synthetic-only"})+"\n")
        for i in range(1000):
            now = i*.02
            if i % 3 == 0:
                s = Sample("tof", i+1, now, {"distance_m": z+c.ground_sensor_height_m+rng.gauss(0, .003)}, status=0)
                pending.append((now+.06, s))
            samples = []
            while pending and pending[0][0] <= now:
                s = pending.popleft()[1]
                samples.append(s)
                est.update(s, now, True)
            rc = dict(default_rc(), arm=True, throttle=1400)
            out, status = ctl.step(now, rc, est.snapshot(now), now >= 2, .05 if now >= 6 else 0,
                                   secure=True)
            demanded = clip((out["throttle"]-1400)*.018, -.45, .45)
            saturated += abs((out["throttle"]-1400)*.018) > .45
            thrust += .02/(.12+.02)*(demanded-thrust)
            disturbance = -.7 if 8 <= now < 9 else 0
            v += (thrust-.6*v+disturbance)*.02
            z = max(0, z+v*.02)
            target = status["target_m"] or .4
            peak = max(peak, abs(z-target))
            final = abs(z-target)
            f.write(json.dumps({"type": "tick", "at_s": now, "samples": [asdict(s) for s in samples],
                                "input_rc": rc, "hold": now >= 2, "offset_m": .05 if now >= 6 else 0,
                                "link_ok": True, "secure": True, "true_height_m": z,
                                "true_velocity_m_s": v, "plant_accel_m_s2": demanded,
                                **est.snapshot(now), **status})+"\n")
    return {"peak_error_m": peak, "final_error_m": final, "plant_saturated_ticks": saturated,
            "final_state": ctl.state, "seed": seed, "flight_validated": False}
