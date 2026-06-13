import argparse
import json
import socket
import sys
import time

from rc_protocol import THROTTLE_MAX, THROTTLE_MIN, clamp, default_rc, sanitize_rc


SEND_HZ = 30
STATUS_TIMEOUT_S = 1.0


def load_pygame():
    try:
        import pygame
    except ImportError:
        print("pygame is required for gamepad input.")
        print("Install it with: python3 -m pip install pygame")
        raise SystemExit(1)
    return pygame


def axis_value(joystick, axis, fallback=0.0):
    if axis < 0 or axis >= joystick.get_numaxes():
        return fallback
    value = joystick.get_axis(axis)
    if abs(value) < 0.06:
        return 0.0
    return value


def button_pressed(joystick, button):
    if button < 0 or button >= joystick.get_numbuttons():
        return False
    return joystick.get_button(button) == 1


def stick_to_channel(value, center=1500, span=400, invert=False):
    if invert:
        value = -value
    return int(clamp(center + value * span, 1000, 2000))


def throttle_from_axis(value, invert=False):
    if invert:
        value = -value
    normalized = (value + 1.0) / 2.0
    return int(clamp(THROTTLE_MIN + normalized * (THROTTLE_MAX - THROTTLE_MIN), THROTTLE_MIN, THROTTLE_MAX))


def read_status(sock):
    latest = None
    while True:
        try:
            data, _addr = sock.recvfrom(2048)
        except BlockingIOError:
            return latest
        except OSError:
            return latest

        try:
            latest = json.loads(data.decode())
        except Exception:
            pass


def send_rc(sock, address, rc):
    payload = json.dumps(sanitize_rc(rc)).encode("utf-8")
    sock.sendto(payload, address)


def print_overview(joystick):
    print("Controller:", joystick.get_name())
    print("Axes:", joystick.get_numaxes(), "Buttons:", joystick.get_numbuttons())
    print("Default mapping: left X=roll axis0, left Y=pitch axis1, right X=yaw axis2")
    print("Buttons: throttle up button5, throttle down button4, arm button7, angle button6, panic button1")
    print("Press Ctrl+C to stop. Stop sends disarm/throttle-low packets.")


def main():
    parser = argparse.ArgumentParser(description="Gamepad UDP controller for Pico W drone.")
    parser.add_argument("--ip", required=True, help="Pico W IP address")
    parser.add_argument("--port", type=int, default=5005, help="Pico UDP port")
    parser.add_argument("--index", type=int, default=0, help="Gamepad index")
    parser.add_argument("--roll-axis", type=int, default=0)
    parser.add_argument("--pitch-axis", type=int, default=1)
    parser.add_argument("--yaw-axis", type=int, default=2)
    parser.add_argument("--throttle-axis", type=int, default=-1)
    parser.add_argument("--invert-roll", action="store_true")
    parser.add_argument("--invert-pitch", action="store_true")
    parser.add_argument("--invert-yaw", action="store_true")
    parser.add_argument("--invert-throttle", action="store_true")
    parser.add_argument("--arm-button", type=int, default=7)
    parser.add_argument("--angle-button", type=int, default=6)
    parser.add_argument("--panic-button", type=int, default=1)
    parser.add_argument("--throttle-up-button", type=int, default=5)
    parser.add_argument("--throttle-down-button", type=int, default=4)
    args = parser.parse_args()

    pygame = load_pygame()
    pygame.init()
    pygame.joystick.init()

    if pygame.joystick.get_count() <= args.index:
        print("No gamepad found at index", args.index)
        raise SystemExit(1)

    joystick = pygame.joystick.Joystick(args.index)
    joystick.init()
    print_overview(joystick)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    address = (args.ip, args.port)

    rc = default_rc()
    last_status = None
    last_status_at = 0.0
    prev_arm_pressed = False
    prev_angle_pressed = False
    period = 1.0 / SEND_HZ

    try:
        while True:
            pygame.event.pump()

            arm_pressed = button_pressed(joystick, args.arm_button)
            angle_pressed = button_pressed(joystick, args.angle_button)
            if arm_pressed and not prev_arm_pressed:
                rc["arm"] = not rc["arm"]
            if angle_pressed and not prev_angle_pressed:
                rc["angle"] = not rc["angle"]
            prev_arm_pressed = arm_pressed
            prev_angle_pressed = angle_pressed

            if button_pressed(joystick, args.panic_button):
                rc = default_rc()
            else:
                rc["roll"] = stick_to_channel(axis_value(joystick, args.roll_axis), invert=args.invert_roll)
                rc["pitch"] = stick_to_channel(axis_value(joystick, args.pitch_axis), invert=not args.invert_pitch)
                rc["yaw"] = stick_to_channel(axis_value(joystick, args.yaw_axis), invert=args.invert_yaw)
                if args.throttle_axis >= 0:
                    rc["throttle"] = throttle_from_axis(
                        axis_value(joystick, args.throttle_axis, fallback=-1.0),
                        invert=args.invert_throttle,
                    )
                else:
                    if button_pressed(joystick, args.throttle_up_button):
                        rc["throttle"] = clamp(rc["throttle"] + 2, THROTTLE_MIN, THROTTLE_MAX)
                    if button_pressed(joystick, args.throttle_down_button):
                        rc["throttle"] = clamp(rc["throttle"] - 4, THROTTLE_MIN, THROTTLE_MAX)

            send_rc(sock, address, rc)

            status = read_status(sock)
            if status is not None:
                last_status = status
                last_status_at = time.time()

            link = "NO ACK"
            if last_status is not None and time.time() - last_status_at < STATUS_TIMEOUT_S:
                link = "ACK packets={} age={}ms".format(
                    last_status.get("packets", "?"),
                    last_status.get("link_age_ms", "?"),
                )

            line = (
                "roll={roll:4d} pitch={pitch:4d} thr={throttle:4d} yaw={yaw:4d} "
                "arm={arm} angle={angle} | {link}"
            ).format(link=link, **sanitize_rc(rc))
            sys.stdout.write("\r" + line[:120])
            sys.stdout.flush()
            time.sleep(period)

    except KeyboardInterrupt:
        pass
    finally:
        safe = default_rc()
        for _ in range(10):
            send_rc(sock, address, safe)
            time.sleep(period)
        sock.close()
        pygame.quit()
        print("\nStopped. Disarm packets sent.")


if __name__ == "__main__":
    main()
