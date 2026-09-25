"""Run from the repository root: python -m pi_zero.main --dry-run."""

import argparse
import logging
import signal
import time

from pi_zero.config import Config, RC_PERIOD_S, SHUTDOWN_FRAMES, STATUS_PERIOD_S
from pi_zero.serial_transport import DryRunTransport, SerialTransport
from pi_zero.udp_receiver import RcState, UdpRcReceiver
from rc_protocol import default_rc

logger = logging.getLogger("pi_zero.main")


def shutdown(transport, clock=time.monotonic, sleep=time.sleep):
    """Attempt all 50 safe frames even if individual UART writes fail."""
    errors = 0
    deadline = clock()
    for _ in range(SHUTDOWN_FRAMES):
        try:
            transport.send(default_rc())
        except Exception:
            errors += 1
        deadline = max(deadline + RC_PERIOD_S, clock())
        sleep(max(0.0, deadline - clock()))
    logger.info("Shutdown: %d safe frames sent, %d failed", SHUTDOWN_FRAMES - errors, errors)
    return errors


def run_loop(receiver, transport, state, should_stop,
             clock=time.monotonic, sleep=time.sleep):
    transport.send(default_rc())
    next_send = clock() + RC_PERIOD_S
    next_status = clock() + STATUS_PERIOD_S
    while not should_stop():
        receiver.poll(state, clock)
        now = clock()
        state.expire(now)
        if now >= next_send:
            transport.send(state.rc.copy())
            next_send += RC_PERIOD_S
            if next_send <= clock():
                # Do not burst old frames after a scheduler/IO delay.
                next_send = clock() + RC_PERIOD_S
        if now >= next_status:
            receiver.send_status(state.status(now, receiver.packet_count))
            next_status = now + STATUS_PERIOD_S
        sleep(max(0.0, min(0.001, next_send - clock())))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Pi Zero W UDP / CRSF bridge (Python 3.11+)")
    parser.add_argument("--uart", default="/dev/serial0")
    parser.add_argument("--baud", type=int, default=420000)
    parser.add_argument("--port", type=int, default=5005)
    parser.add_argument("--link-timeout-ms", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    try:
        return Config(**vars(parser.parse_args(argv)))
    except ValueError as exc:
        parser.error(str(exc))


def main(argv=None):
    config = parse_args(argv)
    package_logger = logging.getLogger("pi_zero")
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    package_logger.addHandler(handler)
    package_logger.setLevel(logging.DEBUG if config.verbose else logging.INFO)
    package_logger.propagate = False
    # __main__ must be a child of the package logger too.
    log = logging.getLogger("pi_zero.main")
    log.info("Settings: %s; UDP listen=0.0.0.0:%d; UART=%s; 8N1; RC=50Hz",
             config, config.port, config.uart)
    stopped = False

    def stop(_signum, _frame):
        nonlocal stopped
        stopped = True

    transport = None
    receiver = None
    previous_handlers = {}
    exit_code = 0
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.signal(signum, stop)
        transport = (DryRunTransport() if config.dry_run else
                     SerialTransport.open(config.uart, config.baud))
        receiver = UdpRcReceiver(config.port)
        run_loop(receiver, transport, RcState(config.link_timeout_ms), lambda: stopped)
    except Exception:
        log.exception("Bridge failed; attempting safe shutdown")
        exit_code = 1
    finally:
        if transport is not None:
            if shutdown(transport):
                exit_code = 1
            try:
                transport.close()
            except Exception:
                log.exception("UART close failed")
                exit_code = 1
        if receiver is not None:
            receiver.close()
        for signum, previous in previous_handlers.items():
            signal.signal(signum, previous)
        package_logger.removeHandler(handler)
        handler.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
