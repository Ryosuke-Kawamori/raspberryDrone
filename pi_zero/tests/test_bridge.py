import json
import socket

import pytest

from crsf import make_rc_frame
from pc_gamepad_ui import rc_payload, read_status
from pi_zero.config import Config
from pi_zero.main import main, run_loop, shutdown
from pi_zero.serial_transport import DryRunTransport, SerialTransport
from pi_zero.udp_receiver import RcState, UdpRcReceiver, decode_command
from rc_protocol import default_rc, rc_to_channels


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeSerial:
    def __init__(self, clock=lambda: 0, **settings):
        self.clock = clock
        self.settings = settings
        self.writes = []
        self.closed = False

    def write(self, frame):
        self.writes.append((self.clock(), bytes(frame)))
        return len(frame)

    def close(self):
        self.closed = True


def command(**values):
    return decode_command(json.dumps(dict(default_rc(), **values)).encode())


def unpack(frame):
    packed = int.from_bytes(frame[3:-1], "little")
    return [(packed >> (11 * index)) & 2047 for index in range(16)]


def assert_safe(rc):
    assert rc["throttle"] == 1000
    assert rc["arm"] is False


def test_crsf_known_frame_and_channels():
    # Independent fixed vector: sixteen centered 11-bit values (992).
    assert make_rc_frame([1500] * 16).hex() == (
        "c81816e0031ff8c0073ef0810f7ce0031ff8c0073ef0810f7cad"
    )
    rc = dict(default_rc(), roll=1000, pitch=2000, throttle=1200, yaw=1500, arm=True)
    frame = make_rc_frame(rc_to_channels(rc))
    assert len(frame) == 26
    assert list(frame[:3]) == [0xC8, 24, 0x16]
    assert unpack(frame) == [192, 1792, 512, 992, 1792, 1792] + [992] * 10


def test_protocol_and_local_throttle_clamp():
    rc = command(roll=999, pitch=2001, yaw=1600, throttle=3000, arm=True).rc
    assert rc == dict(default_rc(), roll=1000, pitch=2000, yaw=1600, throttle=1200, arm=True)
    assert_safe(command(arm=False, throttle=1200).rc)


def test_receiver_test_with_existing_ui_payload():
    data = rc_payload(dict(default_rc(), arm=True, throttle=1200), receiver_test=True)
    rc = decode_command(json.dumps(data).encode()).rc
    assert rc["arm"] is False
    assert rc["throttle"] == 1200
    assert command(arm=True, receiver_test=True).rc["arm"] is False


def test_initial_arm_lock_and_rearm_after_exact_timeout():
    state = RcState()
    state.accept(command(arm=True), 0)
    assert_safe(state.rc)
    state.accept(command(), 0)
    state.accept(command(arm=True), 0)
    assert state.rc["arm"] is True
    state.accept(command(arm=True, throttle=1200), 0)
    state.expire(0.499)
    assert state.rc["arm"] is True
    state.expire(0.500)
    assert_safe(state.rc)
    state.accept(command(arm=True), 0.501)
    assert_safe(state.rc)
    state.accept(command(), 0.502)
    state.accept(command(arm=True), 0.503)
    assert state.rc["arm"] is True


def test_timeout_checked_before_new_packet_and_raw_low_required():
    state = RcState()
    state.accept(command(), 0)
    state.accept(command(arm=True), 0.5)
    assert_safe(state.rc)
    state.accept(command(arm=False, throttle=1200), 0.6)
    state.accept(command(arm=True), 0.7)
    assert_safe(state.rc)
    state.accept(command(), 0.8)
    state.accept(command(arm=True, throttle=1100), 0.9)
    assert_safe(state.rc)


def test_receiver_test_does_not_unlock_arm():
    state = RcState()
    state.accept(command(), 0)
    state.accept(command(receiver_test=True, arm=True, throttle=1200), 0.1)
    assert state.rc["arm"] is False
    state.accept(command(arm=True), 0.2)
    assert_safe(state.rc)


@pytest.mark.parametrize("payload", [
    b"broken", b"[]", b"null", b'"text"', b'{}garbage', b"\xff",
    b'{"arm":true,"throttle":NaN}', b'{"arm":true,"roll":Infinity}',
    b'{"arm":true,"roll":null}', b'{"arm":1}', b'{"arm":"true"}',
    b'{"receiver_test":"true","arm":true}', b'{"roll":true}',
])
def test_invalid_udp_disarms_and_locks(payload):
    receiver = UdpRcReceiver(0)
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        state = RcState()
        state.accept(command(), 0)
        state.accept(command(arm=True), 0)
        client.sendto(payload, ("127.0.0.1", receiver.sock.getsockname()[1]))
        receiver.poll(state, lambda: 0.1)
        assert_safe(state.rc)
        assert not state.arm_ready
        assert receiver.packet_count == 0
    finally:
        client.close()
        receiver.close()


def test_real_udp_ack_compatible_with_gamepad_reader():
    receiver = UdpRcReceiver(0)
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.setblocking(False)
    try:
        state = RcState()
        client.sendto(json.dumps(rc_payload(default_rc())).encode(),
                      ("127.0.0.1", receiver.sock.getsockname()[1]))
        receiver.poll(state, lambda: 1.0)
        receiver.send_status(state.status(1.2, receiver.packet_count))
        status = read_status(client)
        assert status["type"] == "pico_status"
        assert status["packets"] == 1
        assert 199 <= status["link_age_ms"] <= 200
        assert_safe(status["rc"])
    finally:
        client.close()
        receiver.close()


def test_50hz_fake_serial_and_shutdown():
    clock = Clock()
    serial = FakeSerial(clock)
    transport = SerialTransport(serial)
    receiver = UdpRcReceiver(0)
    try:
        run_loop(receiver, transport, RcState(), lambda: clock() >= 0.101,
                 clock, clock.sleep)
    finally:
        receiver.close()
    assert [t for t, _ in serial.writes] == pytest.approx([0, .02, .04, .06, .08, .1])
    serial.writes.clear()
    assert shutdown(transport, clock, clock.sleep) == 0
    assert len(serial.writes) == 50
    for index, (t, frame) in enumerate(serial.writes):
        assert t == pytest.approx(.101 + index * .02)
        assert unpack(frame)[2:5:2] == [192, 192]


def test_shutdown_continues_after_write_failure():
    clock = Clock()
    class FailingSerial(FakeSerial):
        def write(self, frame):
            super().write(frame)
            raise OSError("disconnected")
    serial = FailingSerial(clock)
    assert shutdown(SerialTransport(serial), clock, clock.sleep) == 50
    assert len(serial.writes) == 50


def test_serial_settings_and_short_write():
    transport = SerialTransport.open("fake", 420000, FakeSerial)
    assert transport.serial.settings == dict(
        port="fake", baudrate=420000, bytesize=8, parity="N", stopbits=1,
        timeout=0, write_timeout=.02, xonxoff=False, rtscts=False, dsrdtr=False,
        exclusive=True)
    transport.serial.write = lambda frame: len(frame) - 1
    with pytest.raises(OSError):
        transport.send(default_rc())


def test_uart_open_failure_exits_before_receiver(monkeypatch):
    def fail(*args):
        raise OSError("UART unavailable")
    monkeypatch.setattr(SerialTransport, "open", fail)
    monkeypatch.setattr("pi_zero.main.UdpRcReceiver", lambda *_: pytest.fail("receiver opened"))
    assert main([]) == 1


@pytest.mark.parametrize("signum", [2, 15])
def test_signal_safe_shutdown(monkeypatch, signum):
    import signal
    import pi_zero.main as app
    clock = Clock()
    serial = FakeSerial(clock)
    monkeypatch.setattr(SerialTransport, "open", lambda *_: SerialTransport(serial))
    def loop(receiver, transport, state, should_stop):
        signal.getsignal(signum)(signum, None)
        assert should_stop()
    monkeypatch.setattr(app, "run_loop", loop)
    monkeypatch.setattr(app, "shutdown", lambda t: shutdown(t, clock, clock.sleep))
    assert main([]) == 0
    assert serial.closed
    assert len(serial.writes) == 50
    assert all(unpack(f)[2:5:2] == [192, 192] for _, f in serial.writes)


def test_loop_exception_safe_shutdown(monkeypatch):
    import pi_zero.main as app
    clock = Clock()
    serial = FakeSerial(clock)
    monkeypatch.setattr(SerialTransport, "open", lambda *_: SerialTransport(serial))
    def fail(*args):
        raise RuntimeError("input failure")
    monkeypatch.setattr(app, "run_loop", fail)
    monkeypatch.setattr(app, "shutdown", lambda t: shutdown(t, clock, clock.sleep))
    assert main([]) == 1
    assert serial.closed
    assert len(serial.writes) == 50


def test_dry_run_logs_once_per_second(caplog):
    clock = Clock()
    transport = DryRunTransport(clock)
    with caplog.at_level("INFO", logger="pi_zero.serial_transport"):
        for _ in range(100):
            transport.send(default_rc())
            clock.sleep(.02)
    assert len(caplog.records) == 2
    assert "crsf=" in caplog.text


def test_dry_run_main_never_opens_uart(monkeypatch):
    import signal
    import pi_zero.main as app
    clock = Clock()
    monkeypatch.setattr(SerialTransport, "open", lambda *_: pytest.fail("UART opened"))
    monkeypatch.setattr(app, "UdpRcReceiver", lambda _: UdpRcReceiver(0))
    real_loop = run_loop
    def loop(receiver, transport, state, should_stop):
        assert isinstance(transport, DryRunTransport)
        def sleep(seconds):
            clock.sleep(seconds)
            if clock() >= .05:
                signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        real_loop(receiver, transport, state, should_stop, clock, sleep)
    monkeypatch.setattr(app, "run_loop", loop)
    monkeypatch.setattr(app, "shutdown", lambda t: shutdown(t, clock, clock.sleep))
    assert main(["--dry-run"]) == 0


def test_loop_sends_failsafe_after_packet_loss():
    clock = Clock()
    serial = FakeSerial(clock)
    class OneShotReceiver:
        packet_count = 0
        def poll(self, state, now):
            if self.packet_count == 0:
                state.accept(command(), now())
                state.accept(command(arm=True), now())
                state.accept(command(arm=True, throttle=1200), now())
                self.packet_count = 3
        def send_status(self, status):
            pass
    run_loop(OneShotReceiver(), SerialTransport(serial), RcState(),
             lambda: clock() >= .55, clock, clock.sleep)
    assert any(unpack(frame)[4] == 1792 for _, frame in serial.writes)
    after_loss = [frame for t, frame in serial.writes if t >= .5]
    assert after_loss
    assert all(unpack(frame)[2:5:2] == [192, 192] for frame in after_loss)


@pytest.mark.parametrize("kwargs", [{"port": 0}, {"port": 65536}, {"baud": 0}, {"link_timeout_ms": 0}])
def test_config_validation(kwargs):
    with pytest.raises(ValueError):
        Config(**kwargs)
