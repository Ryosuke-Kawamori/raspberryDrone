"""Nonblocking input adapter and transport-independent RC safety state."""

import json
import logging
import socket
from dataclasses import dataclass

from rc_protocol import default_rc, sanitize_rc
from pi_zero.config import THROTTLE_MAX, THROTTLE_MIN

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Command:
    rc: dict
    receiver_test: bool = False
    disarm_low: bool = False


def decode_command(payload):
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("RC packet must be a JSON object")
    # Reject malformed known fields rather than letting coercion arm the FC.
    for key in ("roll", "pitch", "throttle", "yaw"):
        if key in data and (isinstance(data[key], bool) or
                            not isinstance(data[key], (int, float))):
            raise ValueError("invalid numeric RC field: " + key)
    for key in ("arm", "angle", "receiver_test"):
        if key in data and not isinstance(data[key], bool):
            raise ValueError("invalid boolean RC field: " + key)
    receiver_test = data.get("receiver_test") is True
    rc = sanitize_rc(data, force_throttle_low=not receiver_test)
    rc["throttle"] = max(THROTTLE_MIN, min(THROTTLE_MAX, rc["throttle"]))
    if receiver_test:
        rc["arm"] = False
    # Inspect raw throttle: sanitize_rc lowers it automatically while disarmed.
    disarm_low = (data.get("arm") is False and
                  data.get("throttle") == THROTTLE_MIN and not receiver_test)
    return Command(rc, receiver_test, disarm_low)


class RcState:
    def __init__(self, link_timeout_ms=500):
        self.timeout_s = link_timeout_ms / 1000.0
        self.last_packet_at = None
        self.rc = default_rc()
        self.arm_ready = False

    def failsafe(self):
        self.rc = default_rc()
        self.arm_ready = False

    def expire(self, now):
        if self.last_packet_at is None or now - self.last_packet_at >= self.timeout_s:
            self.failsafe()

    def accept(self, command, now):
        # Expire before accepting: an ARM packet after a gap cannot re-arm.
        self.expire(now)
        self.last_packet_at = now
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

    def status(self, now, packets):
        self.expire(now)
        return {
            "type": "pico_status",  # Wire compatibility with the existing PC UI.
            "packets": packets,
            "link_age_ms": (int((now - self.last_packet_at) * 1000)
                            if self.last_packet_at is not None else 0),
            "rc": self.rc.copy(),
            "arm_ready": self.arm_ready,
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
        for _ in range(32):
            try:
                payload, addr = self.sock.recvfrom(65535)
            except BlockingIOError:
                return
            try:
                command = decode_command(payload)
            except (ValueError, TypeError, OverflowError, RecursionError):
                state.failsafe()
                self.bad_packets += 1
                if self.bad_packets == 1 or self.bad_packets % 100 == 0:
                    logger.warning("Invalid UDP packet; disarmed (count=%d)", self.bad_packets)
                return  # Leave this polling pass in the locked safe state.
            self.last_addr = addr
            self.packet_count += 1
            state.accept(command, clock())
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
