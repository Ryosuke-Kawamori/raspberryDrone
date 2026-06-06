import argparse
import curses
import json
import socket
import time

from rc_protocol import THROTTLE_MAX, THROTTLE_MIN, clamp, default_rc, sanitize_rc


SEND_HZ = 20
AXIS_STEP = 80
THROTTLE_STEP = 10


def send_rc(sock, address, rc):
    payload = json.dumps(sanitize_rc(rc)).encode("utf-8")
    sock.sendto(payload, address)


def draw(stdscr, rc, pico_ip, pico_port):
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


def run_curses(stdscr, pico_ip, pico_port):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(0)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
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

            send_rc(sock, address, rc)
            draw(stdscr, rc, pico_ip, pico_port)
            time.sleep(period)
    finally:
        panic(rc)
        for _ in range(10):
            send_rc(sock, address, rc)
            time.sleep(period)
        sock.close()


def main():
    parser = argparse.ArgumentParser(description="Keyboard UDP controller for Pico W.")
    parser.add_argument("--ip", required=True, help="Pico W IP address")
    parser.add_argument("--port", type=int, default=5005, help="Pico UDP port")
    args = parser.parse_args()
    curses.wrapper(run_curses, args.ip, args.port)


if __name__ == "__main__":
    main()
