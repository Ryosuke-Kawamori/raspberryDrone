import json
import math
from dataclasses import replace
from types import SimpleNamespace

import pytest

from pi_zero.alt_config import AltConfig
from pi_zero.alt_control import AltController, PID
from pi_zero.alt_runtime import AltRuntime
from pi_zero.estimation import Estimator, Attitude
from pi_zero.experiments import simulate, replay
from pi_zero.sensors import Sample, FakeSensor, guarded_read, BMP581, VL53L4CD
from pi_zero.udp_receiver import RcState, decode_command
from pi_zero.main import run_loop, main
from pi_zero.serial_transport import SerialTransport
from pi_zero.tests.test_bridge import Clock as FakeClock, FakeSerial, unpack
from rc_protocol import default_rc


def estimate(h=.4, v=0, valid=True):
    return dict(height_m=h, velocity_m_s=v, valid=valid, qualified=valid, quality="good" if valid else "ToF stale")


def armed(throttle=1150):
    return dict(default_rc(), arm=True, throttle=throttle)


def enable(mode="live", **kwargs):
    ctl = AltController(replace(AltConfig(), kp=100, kd=30, **kwargs), mode)
    ctl.step(0, armed(), estimate(), False, secure=True)
    out, _ = ctl.step(.02, armed(), estimate(), True, secure=True)
    assert out["throttle"] == 1150
    assert ctl.state == "ALT_HOLD"
    return ctl


def tof(t, distance=.44, seq=None, **kw):
    return Sample("tof", round(t*1000)+1 if seq is None else seq, t, {"distance_m": distance}, **kw)


def test_control_sign_limits_and_anti_windup():
    c = replace(AltConfig(), kp=100, kd=20, ki=10, slew_per_s=10000)
    pid = PID(c)
    assert pid.step(.1, 0, 1150, 1150, .02) > 1150
    pid.reset()
    assert pid.step(0, .2, 1150, 1150, .02) < 1150
    for _ in range(100):
        out = pid.step(10, 0, 1190, 1190, .02)
    assert out == 1200
    assert pid.integral == 0
    assert pid.step(-10, 0, 1010, 1010, .02) == 1000


def test_on_off_continuity_and_emergency_priority():
    ctl = enable()
    out, _ = ctl.step(.04, armed(), estimate(.2), True, secure=True)
    assert abs(out["throttle"]-1150) <= 2
    before = out["throttle"]
    out, state = ctl.step(.06, armed(1050), estimate(valid=False), False, secure=True)
    assert abs(out["throttle"]-before) <= 2
    assert state["state"] == "MANUAL"
    assert ctl.pid.integral == 0
    out, _ = ctl.step(.08, default_rc(), estimate(), True)
    assert out == default_rc()


@pytest.mark.parametrize("mode", ["shadow", "live"])
def test_sensor_fault_and_recovery_requires_off_and_new_hold(mode):
    ctl = enable(mode)
    out, status = ctl.step(.04, armed(), estimate(valid=False), True, secure=True)
    assert status["state"] == "FAULT"
    assert out == (armed() if mode == "shadow" else default_rc())
    for t in (.06, .08):
        ctl.step(t, armed(), estimate(), True, secure=True)
        assert ctl.state == "FAULT"
    ctl.step(.1, default_rc(), estimate(), False, secure=True)
    ctl.step(.12, armed(), estimate(), False, secure=True)
    assert ctl.state == "MANUAL"
    ctl.step(.14, armed(), estimate(), True, secure=True)
    assert ctl.state == "ALT_HOLD"


def test_shadow_and_manual_recover_never_mix_automatic_output():
    ctl = enable("shadow")
    for i in range(2, 15):
        out, _ = ctl.step(i*.02, armed(), estimate(.2), True, secure=True)
        assert out == armed()
    assert ctl.auto != 1150
    ctl = enable(loss_policy="manual-recover")
    out, _ = ctl.step(.04, armed(1080), estimate(valid=False), True, secure=True)
    assert out == armed(1080)
    out, _ = ctl.step(.06, armed(1080), estimate(), True, link_ok=False, secure=True)
    assert out == default_rc()


def test_abnormal_dt_and_target_range():
    ctl = enable()
    ctl.step(.2, armed(), estimate(), True, secure=True)
    assert ctl.state == "FAULT"
    ctl = enable()
    ctl.step(.04, armed(), estimate(), True, offset=5, secure=True)
    assert ctl.target == ctl.c.target_max_m


def test_estimator_stale_duplicates_range_jump_and_freeze():
    est = Estimator(AltConfig())
    est.update(tof(0), 0)
    est.update(tof(.05, .45), .05)
    assert est.snapshot(.05)["velocity_m_s"] > 0
    est.update(tof(.1, 1.2), .1)
    assert not est.snapshot(.1)["valid"]
    est.update(tof(.15), .15)
    est.update(tof(.2, .85), .2)
    assert "jump" in est.snapshot(.2)["quality"]
    est.update(tof(.25), .25)
    est.update(tof(.25), .4)
    assert est.at == .25
    assert not est.snapshot(.5)["valid"]
    est = Estimator(AltConfig())
    for i in range(50):
        est.update(tof(i*.05), i*.05, True)
    assert "freeze" in est.snapshot(2.45)["quality"]


def test_baro_calibration_disarmed_ground_only_never_rezeros_in_flight():
    est = Estimator(AltConfig())
    for i in range(50):
        now = i*.05
        est.update(tof(now, .04), now)
        est.update(Sample("bmp", i, now, {"pressure_pa": 101325, "temperature_c": 20}), now)
    assert est.p0 == 101325
    est.update(Sample("bmp", 100, 2.5, {"pressure_pa": 101300, "temperature_c": 20}), 2.5, True)
    assert est.baro_height > 0
    assert est.p0 == 101325
    assert not est.snapshot(3)["valid"]  # barometer cannot rescue stale ToF
    est2 = Estimator(AltConfig())
    for i in range(60):
        est2.update(Sample("bmp", i, i*.05, {"pressure_pa": 101325, "temperature_c": 20}), i*.05, True)
    assert est2.p0 is None


def test_attitude_is_optional_but_not_fabricated():
    est = Estimator(AltConfig())
    est.update(tof(0, .5), 0, attitude=Attitude(.2, 0, 0))
    assert est.height == pytest.approx(.5*math.cos(.2)-.04)
    est.update(tof(.05, .5), .05)
    assert est.tilt.startswith("unmeasured")


def test_driver_new_data_units_status_and_i2c_exception():
    class ToFDevice:
        data_ready = True
        range_status = 0
        distance = 44
        def clear_interrupt(self):
            self.data_ready = False
    d = ToFDevice()
    sensor = VL53L4CD(d, lambda: 1)
    assert sensor.read().values["distance_m"] == .44
    assert sensor.read() is None
    d.data_ready, d.range_status = True, 4
    assert not sensor.read().valid
    class BmpDevice:
        kIntAssertedDrdy = 1
        ready = 1
        def get_interrupt_status(self):
            ready, self.ready = self.ready, 0
            return ready
        def get_sensor_data(self):
            return SimpleNamespace(pressure=101325, temperature=251)
    sensor = BMP581(BmpDevice(), lambda: 1)
    assert sensor.read().values["temperature_c"] == -5
    assert sensor.read() is None
    result = guarded_read(FakeSensor([OSError("I2C disconnected")]), "tof", lambda: 1)
    assert not result.valid and "I2C" in result.error


def command(state, now, **kw):
    token = state.status(now, 0)["control_token"]
    raw = dict(default_rc(), control_token=token, control_seq=state.last_seq+1, **kw)
    return decode_command(json.dumps(raw).encode())


def test_secure_timeout_replay_old_arm_and_recovery():
    s = RcState(require_secure=True)
    s.accept(command(s, 0), 0)
    s.accept(command(s, .01, arm=True), .01)
    assert s.rc["arm"]
    old = command(s, .02, arm=True)
    s.expire(.6)
    s.accept(old, .61)
    assert not s.rc["arm"]
    s.accept(command(s, .62, arm=True), .62)
    assert not s.rc["arm"]
    s.accept(command(s, .63), .63)
    s.accept(command(s, .64, arm=True), .64)
    assert s.rc["arm"]
    last = s.last_packet_at
    s.accept(old, .65)
    assert s.last_packet_at == last


class MemoryLog:
    dropped = 0
    error = ""
    def __init__(self):
        self.rows = []
    def emit(self, row):
        self.rows.append(row)


def test_stopped_sensor_worker_does_not_stop_serial_or_udp_failsafe():
    clock, serial = FakeClock(), FakeSerial()
    state = RcState()
    source = SimpleNamespace(drain=lambda: [])  # worker blocked forever; main never calls its read
    state.alt_runtime = AltRuntime(AltConfig(), "shadow", source, MemoryLog())
    class Receiver:
        packet_count = 0
        def poll(self, s, now):
            if self.packet_count == 0:
                for rc in (default_rc(), armed(1000), armed()):
                    s.accept(decode_command(json.dumps(rc).encode()), now())
                self.packet_count = 3
        def send_status(self, status):
            pass
    serial.clock = clock
    run_loop(Receiver(), SerialTransport(serial), state, lambda: clock() >= .56, clock, clock.sleep)
    assert len(serial.writes) >= 28
    assert all(unpack(frame)[4] == 192 for at, frame in serial.writes if at >= .5)


def test_default_and_monitor_do_not_open_uart(monkeypatch):
    monkeypatch.setattr(SerialTransport, "open", lambda *_: pytest.fail("UART opened"))
    assert main(["--duration", "0"]) == 0
    monkeypatch.setattr("pi_zero.alt_runtime.monitor", lambda *args: None)
    assert main(["--mode", "sensor-monitor"]) == 0
    assert main(["--mode", "live", "--enable-live"]) == 2


@pytest.mark.parametrize("kw", [{"kp": float("nan")}, {"target_max_m": 1.5},
                                  {"manual_hover_verified": "true"}, {"tof_max_m": 1.2}])
def test_invalid_settings(kw):
    with pytest.raises(ValueError):
        AltConfig(**kw)


def test_blend_requires_both_sensors_and_is_forbidden_live():
    c = replace(AltConfig(), estimator_mode="comparison-blend")
    est = Estimator(c)
    est.update(tof(0), 0)
    assert not est.snapshot(0)["valid"]
    with pytest.raises(ValueError):
        c.validate_live()


def test_log_backpressure_and_invalid_raw_values(tmp_path):
    from pi_zero.alt_runtime import AsyncLog
    log = AsyncLog(tmp_path/"log.jsonl", AltConfig(), "shadow")
    log.emit({"raw": float("nan"), "valid": False})
    log.close()
    rows = [json.loads(s) for s in (tmp_path/"log.jsonl").read_text().splitlines()]
    assert rows[-1] == {"raw": None, "valid": False}
    # No consumer: same nonblocking emit path used when the disk writer hangs.
    import queue
    log.queue = queue.Queue(maxsize=1)
    log.emit({"a": 1})
    log.emit({"b": 2})
    assert log.dropped == 1


def test_secure_old_off_cannot_unlock_after_fault_and_invalid_fields_do_not_refresh():
    s = RcState(require_secure=True)
    off = command(s, 0)
    s.accept(off, 0)
    s.accept(command(s, .01, arm=True), .01)
    s.failsafe()
    s.accept(off, .02)
    assert not s.arm_ready
    s.accept(command(s, .03, arm=True), .03)
    assert not s.rc["arm"]
    for field in ({"alt_hold": "true"}, {"alt_offset_m": float("nan")}, {"control_seq": True}):
        with pytest.raises(ValueError):
            decode_command(json.dumps(dict(default_rc(), **field)).encode())


def test_queued_off_on_batch_cannot_arm():
    import socket
    from pi_zero.udp_receiver import UdpRcReceiver
    receiver = UdpRcReceiver(0)
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    state = RcState()
    try:
        address = ("127.0.0.1", receiver.sock.getsockname()[1])
        for rc in (default_rc(), armed(1000)):
            client.sendto(json.dumps(rc).encode(), address)
        receiver.poll(state, lambda: 0)
        assert not state.rc["arm"]
    finally:
        receiver.close()
        client.close()


def test_optional_pc_payload_and_repeat_offset():
    from pc_altitude import AltitudeClient
    client = AltitudeClient()
    client.receive({"control_token": "abc", "control_seq_floor": 10})
    client.hold = True
    client.step(.02)
    a, b = client.decorate(armed()), client.decorate(armed())
    assert b["control_seq"] > a["control_seq"] > 10
    assert a["alt_offset_m"] == b["alt_offset_m"] == .02
    assert client.decorate(default_rc())["alt_hold"] is False


def test_noise_delay_saturation_simulation_and_replay(tmp_path):
    log = tmp_path/"simulation.jsonl"
    result = simulate(AltConfig(), log)
    assert result["final_state"] == "ALT_HOLD"
    assert result["final_error_m"] < .10
    assert result["plant_saturated_ticks"] > 0
    assert result["flight_validated"] is False
    result = replay(None, log, tmp_path/"replay.jsonl")
    assert result["replayed_ticks"] == 1000
    rows = [json.loads(line) for line in (tmp_path/"replay.jsonl").read_text().splitlines()]
    assert any(abs(row["pid"]["p"]) > 0 for row in rows)
    with pytest.raises(ValueError):
        replay(AltConfig(), log, log)
