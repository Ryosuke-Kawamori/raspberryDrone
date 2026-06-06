import json
import socket
import time

import network

from rc_protocol import default_rc, sanitize_rc


def connect_wifi(ssid, password, led=None, timeout_s=15):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)

    print("connecting to WiFi...")
    start = time.ticks_ms()
    while not wlan.isconnected():
        if led is not None:
            led.toggle()
        if time.ticks_diff(time.ticks_ms(), start) > timeout_s * 1000:
            if led is not None:
                led.off()
            raise RuntimeError("WiFi connection timeout")
        time.sleep_ms(250)

    if led is not None:
        led.on()

    print("connected to WiFi")
    print("IP address:", wlan.ifconfig()[0])
    return wlan


class UdpRcReceiver:
    def __init__(self, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", port))
        self.sock.settimeout(0.0)
        print("UDP port:", port)

    def receive(self):
        try:
            data, _addr = self.sock.recvfrom(1024)
        except OSError:
            return None

        try:
            message = data.decode().strip()
            parsed = json.loads(message)
            return sanitize_rc(parsed)
        except Exception as exc:
            print("bad packet:", exc)
            return default_rc()
