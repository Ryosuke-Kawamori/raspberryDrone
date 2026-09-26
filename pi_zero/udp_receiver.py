"""Nonblocking input adapter and transport-independent RC safety state."""

import json
import logging
import socket
import math
import secrets
from dataclasses import dataclass

from rc_protocol import default_rc, sanitize_rc
from pi_zero.config import THROTTLE_MAX, THROTTLE_MIN

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Command:
    rc: dict
    receiver_test: bool = False
    disarm_low: bool = False
    hold: bool = False
    offset: float = 0.0
    token: str = ""
    seq: int = -1


def decode_command(payload, throttle_max=THROTTLE_MAX):
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("RC packet must be a JSON object")
    if "arm" not in data or "throttle" not in data:
        raise ValueError("RC packet requires explicit arm and throttle")
    # Reject malformed known fields rather than letting coercion arm the FC.
    for key in ("roll", "pitch", "throttle", "yaw"):
        if key in data and (isinstance(data[key], bool) or
                            not isinstance(data[key], (int, float)) or not math.isfinite(data[key])):
            raise ValueError("invalid numeric RC field: " + key)
    for key in ("arm", "angle", "receiver_test", "alt_hold"):
        if key in data and not isinstance(data[key], bool):
            raise ValueError("invalid boolean RC field: " + key)
    receiver_test = data.get("receiver_test") is True
    rc = sanitize_rc(data, force_throttle_low=not receiver_test)
    rc["throttle"] = max(THROTTLE_MIN, min(throttle_max, rc["throttle"]))
    if receiver_test:
        rc["arm"] = False
    # Inspect raw throttle: sanitize_rc lowers it automatically while disarmed.
    disarm_low = (data.get("arm") is False and
                  data.get("throttle") == THROTTLE_MIN and not receiver_test)
    offset = data.get("alt_offset_m", 0.0)
    if type(offset) not in (int, float) or not math.isfinite(offset) or abs(offset) > 10:
        raise ValueError("invalid altitude offset")
    token, seq = data.get("control_token", ""), data.get("control_seq", -1)
    if not isinstance(token, str) or len(token) > 128 or type(seq) is not int or not -1 <= seq < 2**53:
        raise ValueError("invalid control token/sequence")
    return Command(rc, receiver_test, disarm_low, data.get("alt_hold", False), offset, token, seq)


class RcState:
    def __init__(self, link_timeout_ms=500, require_secure=False, throttle_max=THROTTLE_MAX):
        self.timeout_s = link_timeout_ms / 1000.0
        self.last_packet_at = None
        self.rc = default_rc()
        self.arm_ready = False
        self.require_secure = require_secure
        self.throttle_max = throttle_max
        self.tokens = {}
        self.last_seq = -1
        self.secure_seen = False
        self.secure = False
        self.hold = False
        self.offset = 0.0
        self.expired = True

    def failsafe(self):
        self.rc = default_rc()
        self.arm_ready = False
        self.hold = False
        self.secure = False
        self.tokens.clear()
        self.expired = True

    def expire(self, now):
        if not self.expired and (self.last_packet_at is None or
                                 not 0 <= now - self.last_packet_at < self.timeout_s):
            self.failsafe()

    def accept(self, command, now):
        # Expire before accepting: an ARM packet after a gap cannot re-arm.
        self.expire(now)
        secure = (command.token in self.tokens and
                  0 <= now-self.tokens[command.token] <= 0.4 and command.seq > self.last_seq)
        if (self.require_secure or self.secure_seen or command.token) and not secure:
            # An explicit disarm remains authoritative even when its token expired.
            if not command.rc["arm"]:
                self.failsafe()
            return
        if secure:
            self.last_seq = command.seq
            self.secure_seen = True
        self.secure = secure
        self.last_packet_at = now
        self.expired = False
        rc = command.rc.copy()
        if command.receiver_test:
            self.arm_ready = False
        elif command.disarm_low:
            self.arm_ready = True
        if rc["arm"] and (not self.arm_ready or
                          (not self.rc["arm"] and rc["throttle"] != THROTTLE_MIN)):
            self.failsafe()
            return
        self.rc = rc
        self.hold = command.hold if secure else False
        self.offset = command.offset if secure else 0.0

    def status(self, now, packets):
        self.expire(now)
        self.tokens = {k: v for k, v in self.tokens.items() if now-v <= 0.4}
        token = secrets.token_hex(16)
        self.tokens[token] = now
        return {
            "type": "pico_status",  # Wire compatibility with the existing PC UI.
            "packets": packets,
            "link_age_ms": (int((now - self.last_packet_at) * 1000)
                            if self.last_packet_at is not None else 0),
            "rc": self.rc.copy(),
            "arm_ready": self.arm_ready,
            "control_token": token,
            "control_seq_floor": self.last_seq,
        }


class UdpRcReceiver:
    def __init__(self, port=5005):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.bind(("0.0.0.0", port))
            self.sock.setblocking(False)
        except BaseException:
            self.sock.close()
            raise
        self.last_addr = None
        self.packet_count = 0
        self.bad_packets = 0

    def poll(self, state, clock):
        # Bound work even under UDP flooding so the output deadline is serviced.
        latest = None
        for _ in range(32):
            try:
                payload, addr = self.sock.recvfrom(65535)
            except BlockingIOError:
                if latest is not None:
                    command, addr = latest
                    self.last_addr = addr
                    state.accept(command, clock())
                return
            try:
                command = decode_command(payload, state.throttle_max)
            except (ValueError, TypeError, OverflowError, RecursionError):
                state.failsafe()
                self.bad_packets += 1
                if self.bad_packets == 1 or self.bad_packets % 100 == 0:
                    logger.warning("Invalid UDP packet; disarmed (count=%d)", self.bad_packets)
                return  # Leave this polling pass in the locked safe state.
            self.packet_count += 1
            # Never execute a queued OFF->ON sequence inside one polling pass.
            # Any explicit OFF in this batch takes priority over subsequent ARM.
            if latest is None or latest[0].rc["arm"]:
                latest = command, addr
        # A persistent backlog is not a reliable live control stream.
        state.failsafe()

    def send_status(self, status):
        if self.last_addr is not None:
            try:
                self.sock.sendto(json.dumps(status).encode("utf-8"), self.last_addr)
            except OSError:
                logger.debug("Status ACK could not be sent", exc_info=True)

    def close(self):
        self.sock.close()
