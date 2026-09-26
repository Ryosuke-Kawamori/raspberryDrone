import argparse
import curses
import json
import socket
import time

from rc_protocol import THROTTLE_MAX, THROTTLE_MIN, clamp, default_rc, sanitize_rc
from pc.altitude import AltitudeClient
from pc.gamepad_ui import read_status


SEND_HZ = 20
AXIS_STEP = 80
THROTTLE_STEP = 10


def send_rc(sock, address, rc, altitude=None):
    data = sanitize_rc(rc)
    payload = json.dumps(altitude.decorate(data) if altitude else data).encode("utf-8")
    sock.sendto(payload, address)


def draw(stdscr, rc, pico_ip, pico_port, altitude=None):
    stdscr.erase()
    stdscr.addstr(0, 0, "Pico Drone UDP Control")
    stdscr.addstr(2, 0, "target: {}:{}".format(pico_ip, pico_port))
    stdscr.addstr(4, 0, "W/S pitch  A/D roll  Q/E yaw  R/F throttle")
    stdscr.addstr(5, 0, "M arm toggle  G angle toggle  Space center  P panic  X quit")
    stdscr.addstr(7, 0, "roll:     {}".format(rc["roll"]))
    stdscr.addstr(8, 0, "pitch:    {}".format(rc["pitch"]))
    stdscr.addstr(9, 0, "throttle: {}".format(rc["throttle"]))
    stdscr.addstr(10, 0, "yaw:      {}".format(rc["yaw"]))
    stdscr.addstr(11, 0, "arm:      {}".format(rc["arm"]))
    stdscr.addstr(12, 0, "angle:    {}".format(rc["angle"]))
    if altitude:
        height, width = stdscr.getmaxyx()
        for row, line in enumerate(["H hold ON/OFF  [ / ] target -/+0.02m"]+altitude.lines(), 14):
            if row < height-1:
                stdscr.addnstr(row, 0, line, max(1, width-1))
    stdscr.refresh()


def center_sticks(rc):
    rc["roll"] = 1500
    rc["pitch"] = 1500
    rc["yaw"] = 1500


def panic(rc):
    center_sticks(rc)
    rc["throttle"] = THROTTLE_MIN
    rc["arm"] = False


def apply_key(rc, key):
    if key in (ord("a"), ord("A")):
        rc["roll"] = 1500 - AXIS_STEP
    elif key in (ord("d"), ord("D")):
        rc["roll"] = 1500 + AXIS_STEP
    elif key in (ord("w"), ord("W")):
        rc["pitch"] = 1500 + AXIS_STEP
    elif key in (ord("s"), ord("S")):
        rc["pitch"] = 1500 - AXIS_STEP
    elif key in (ord("q"), ord("Q")):
        rc["yaw"] = 1500 - AXIS_STEP
    elif key in (ord("e"), ord("E")):
        rc["yaw"] = 1500 + AXIS_STEP
    elif key in (ord("r"), ord("R")):
        rc["throttle"] = clamp(rc["throttle"] + THROTTLE_STEP, THROTTLE_MIN, THROTTLE_MAX)
    elif key in (ord("f"), ord("F")):
        rc["throttle"] = clamp(rc["throttle"] - THROTTLE_STEP, THROTTLE_MIN, THROTTLE_MAX)
    elif key in (ord("m"), ord("M")):
        rc["arm"] = not rc["arm"]
    elif key in (ord("g"), ord("G")):
        rc["angle"] = not rc["angle"]
    elif key == ord(" "):
        center_sticks(rc)
    elif key in (ord("p"), ord("P")):
        panic(rc)


def run_curses(stdscr, pico_ip, pico_port, use_altitude=False):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(0)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    altitude = AltitudeClient() if use_altitude else None
    address = (pico_ip, pico_port)
    rc = default_rc()
    period = 1.0 / SEND_HZ

    try:
        while True:
            key = stdscr.getch()
            if key in (ord("x"), ord("X")):
                break
            if key != -1:
                apply_key(rc, key)
                if altitude:
                    if key in (ord("h"), ord("H")):
                        altitude.hold = not altitude.hold
                    elif key in (ord("["), ord("]")):
                        altitude.step(.02 if key == ord("]") else -.02)

            status = read_status(sock)
            if altitude and status is not None:
                altitude.receive(status)
            send_rc(sock, address, rc, altitude)
            draw(stdscr, rc, pico_ip, pico_port, altitude)
            time.sleep(period)
    finally:
        panic(rc)
        for _ in range(10):
            send_rc(sock, address, rc, altitude)
            time.sleep(period)
        sock.close()


def main():
    parser = argparse.ArgumentParser(description="Keyboard UDP controller for Pico W.")
    parser.add_argument("--ip", required=True, help="Pico W IP address")
    parser.add_argument("--port", type=int, default=5005, help="Pico UDP port")
    parser.add_argument("--altitude", action="store_true", help="Enable Pi altitude protocol and H/[ / ] controls")
    args = parser.parse_args()
    curses.wrapper(run_curses, args.ip, args.port, args.altitude)


if __name__ == "__main__":
    main()
