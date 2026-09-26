"""I2C is process-isolated; disk logging uses a bounded nonblocking queue."""
import json
import multiprocessing as mp
import queue
import threading
import time
import math
from dataclasses import asdict, replace
from pathlib import Path

from pi_zero.sensors import BMP581, VL53L4CD, Sample, guarded_read
from pi_zero.estimation import Estimator
from pi_zero.alt_control import AltController
from rc_protocol import default_rc


def sensor_worker(config, name, output, stop):
    """One process per sensor: a wedged BMP transaction cannot starve ToF/CRSF."""
    try:
        sensor = (BMP581 if name == "bmp" else VL53L4CD).open(config)
    except Exception as exc:
        output.put(Sample(name, -1, time.monotonic(), {}, False, str(exc)))
        return
    last_poll = last_ready = time.monotonic()
    while not stop.is_set():
        now = time.monotonic()
        delayed = now-last_poll > config.stale_s
        last_poll = now
        sample = guarded_read(sensor, name)
        if sample is not None:
            last_ready = now
            if delayed or sample.acquisition_s > config.stale_s:
                sample = replace(sample, valid=False, error="acquisition/poll delay; old conversion discarded")
        elif now-last_ready > config.stale_s:
            sample = Sample(name, -1, now, {}, False, "data-ready timeout")
            last_ready = now
        if sample is not None:
            try:
                output.put_nowait(sample)
            except queue.Full:
                pass  # Never block acquisition; timestamp exposes dropped/stale samples.
        stop.wait(0.005)


class SensorProcesses:
    def __init__(self, config):
        ctx = mp.get_context("spawn")
        self.queue = ctx.Queue(maxsize=32)
        self.stop = ctx.Event()
        self.processes = [ctx.Process(target=sensor_worker, args=(config, name, self.queue, self.stop),
                                     daemon=True) for name in ("tof", "bmp")]
        for p in self.processes:
            p.start()

    def drain(self):
        samples = []
        for _ in range(32):
            try:
                samples.append(self.queue.get_nowait())
            except queue.Empty:
                break
        return sorted(samples, key=lambda s: s.at_s)

    def close(self):
        self.stop.set()
        for p in self.processes:
            p.join(.2)
            if p.is_alive():
                p.terminate()
                p.join(.2)
        self.queue.cancel_join_thread()
        self.queue.close()


class AsyncLog:
    def __init__(self, path, config, mode):
        # Fail before UART opens if path cannot be created; writes then occur off-loop.
        self.file = Path(path).open("w", encoding="utf-8")
        self.queue = queue.Queue(maxsize=256)
        self.dropped = 0
        self.error = ""
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._write, daemon=True)
        self.thread.start()
        self.emit({"type": "settings", "config": asdict(config), "mode": mode,
                   "wall_time_unix_s": time.time(), "monotonic_s": time.monotonic()})

    def emit(self, row):
        try:
            self.queue.put_nowait(row)
        except queue.Full:
            self.dropped += 1

    def _write(self):
        try:
            while not self.stopping.is_set() or not self.queue.empty():
                try:
                    row = self.queue.get(timeout=.1)
                except queue.Empty:
                    continue
                self.file.write(json.dumps(json_finite(row), ensure_ascii=False, allow_nan=False)+"\n")
                self.file.flush()
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.file.close()

    def close(self):
        self.stopping.set()
        self.thread.join(.5)  # disk hangs cannot delay shutdown CRSF


def json_finite(value):
    """Invalid raw numbers remain invalid samples; encode them as JSON null."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: json_finite(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_finite(v) for v in value]
    return value


class AltRuntime:
    def __init__(self, config, mode, source, log):
        self.c, self.mode, self.source, self.log = config, mode, source, log
        self.estimator = Estimator(config)
        self.controller = AltController(config, mode)
        self.next_control = 0.0
        self.status = {}
        self.output = default_rc()
        self.pending_samples = []

    def tick(self, now, state, loop_lateness=0.0):
        samples = self.source.drain()
        for sample in samples:
            self.estimator.update(sample, now, state.rc["arm"])
        self.pending_samples.extend(samples)
        estimate = self.estimator.snapshot(now)
        if now < self.next_control and state.rc["arm"] and not state.expired:
            # Manual release and disarm cannot wait for the control deadline.
            if not (self.controller.state == "ALT_HOLD" and not state.hold):
                result = state.rc.copy()
                if self.mode == "live":
                    result["throttle"] = self.output["throttle"]
                    result["arm"] = self.output["arm"]
                return result
        previous = self.controller.state
        input_rc, hold, offset, secure, link_ok = state.rc.copy(), state.hold, state.offset, state.secure, not state.expired
        self.output, control = self.controller.step(now, state.rc, estimate, state.hold,
                                                    state.offset, not state.expired, state.secure)
        self.next_control = now+self.c.control_period_s
        if control["state"] == "FAULT" and previous != "FAULT":
            # Rotate all freshness tokens; new OFF then ON required after failure.
            state.tokens.clear()
            if self.mode == "live" and self.c.loss_policy == "bench-disarm":
                state.failsafe()
        self.status = {**estimate, **control, "mode": self.mode,
                       "loop_lateness_s": loop_lateness, "log_dropped": self.log.dropped,
                       "log_error": self.log.error}
        self.log.emit({"type": "tick", "at_s": now, "samples": [asdict(s) for s in self.pending_samples],
                       "input_rc": input_rc, "hold": hold, "offset_m": offset,
                       "secure": secure, "link_ok": link_ok,
                       "output_rc": self.output.copy(), **self.status})
        self.pending_samples.clear()
        return self.output.copy()


def monitor(config, duration, path):
    log = AsyncLog(path, config, "sensor-monitor")
    source = SensorProcesses(config)
    est = Estimator(config)
    started = time.monotonic()
    try:
        while duration is None or time.monotonic()-started < duration:
            now = time.monotonic()
            samples = source.drain()
            for sample in samples:
                est.update(sample, now, False)
            status = est.snapshot(now)
            log.emit({"type": "tick", "at_s": now, "samples": [asdict(s) for s in samples],
                      "input_rc": default_rc(), "hold": False, "offset_m": 0,
                      "link_ok": True, "secure": False, **status})
            if int((now-started)*5) != int((now-started-config.control_period_s)*5):
                print(json.dumps(status, ensure_ascii=False))
            time.sleep(config.control_period_s)
    except KeyboardInterrupt:
        pass
    finally:
        source.close()
        log.close()
