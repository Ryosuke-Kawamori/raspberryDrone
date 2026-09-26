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
            runtime = getattr(state, "alt_runtime", None)
            output = runtime.tick(now, state, max(0.0, now-next_send)) if runtime else state.rc.copy()
            transport.send(output)
            next_send += RC_PERIOD_S
            if next_send <= clock():
                # Do not burst old frames after a scheduler/IO delay.
                next_send = clock() + RC_PERIOD_S
        if now >= next_status:
            status = state.status(now, receiver.packet_count)
            if getattr(state, "alt_runtime", None):
                status["altitude"] = state.alt_runtime.status
            receiver.send_status(status)
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
    parser.add_argument("--mode", choices=("dry-run", "manual", "sensor-monitor", "shadow", "live", "simulation", "replay"), default="dry-run")
    parser.add_argument("--alt-config")
    parser.add_argument("--log", default="altitude.jsonl")
    parser.add_argument("--duration", type=float)
    parser.add_argument("--replay")
    parser.add_argument("--enable-live", action="store_true")
    try:
        return Config(**vars(parser.parse_args(argv)))
    except ValueError as exc:
        parser.error(str(exc))


def main(argv=None):
    config = parse_args(argv)
    from pi_zero.alt_config import load_config
    try:
        alt_config = load_config(config.alt_config)
        if config.mode == "live":
            if not config.enable_live or config.dry_run:
                raise ValueError("live requires --enable-live and cannot use --dry-run")
            alt_config.validate_live()
        if config.mode == "replay" and not config.replay:
            raise ValueError("replay requires --replay PATH")
    except (ValueError, TypeError, OSError) as exc:
        print(str(exc))
        return 2
    if config.mode == "sensor-monitor":
        from pi_zero.alt_runtime import monitor
        monitor(alt_config, config.duration, config.log)
        return 0
    if config.mode in ("simulation", "replay"):
        from pi_zero.experiments import simulate, replay
        print(simulate(alt_config, config.log) if config.mode == "simulation" else
              replay(alt_config if config.alt_config else None, config.replay, config.log))
        return 0
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
    source = log_writer = None
    started = time.monotonic()
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.signal(signum, stop)
        runtime = None
        if config.mode in ("shadow", "live"):
            from pi_zero.alt_runtime import SensorProcesses, AsyncLog, AltRuntime
            log_writer = AsyncLog(config.log, alt_config, config.mode)
            source = SensorProcesses(alt_config)
            runtime = AltRuntime(alt_config, config.mode, source, log_writer)
        transport = (DryRunTransport() if config.dry_run or config.mode == "dry-run" else
                     SerialTransport.open(config.uart, config.baud))
        receiver = UdpRcReceiver(config.port)
        state = RcState(config.link_timeout_ms, require_secure=config.mode == "live",
                        throttle_max=alt_config.throttle_max)
        state.alt_runtime = runtime
        run_loop(receiver, transport, state, lambda: stopped or (
            config.duration is not None and time.monotonic()-started >= config.duration))
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
        if source is not None:
            source.close()
        if log_writer is not None:
            log_writer.close()
        for signum, previous in previous_handlers.items():
            signal.signal(signum, previous)
        package_logger.removeHandler(handler)
        handler.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
