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


def start_access_point(ssid, password, led=None, channel=6):
    sta = network.WLAN(network.STA_IF)
    sta.active(False)

    ap = network.WLAN(network.AP_IF)
    ap.active(True)

    if password:
        ap.config(essid=ssid, password=password, channel=channel)
    else:
        ap.config(essid=ssid, channel=channel)

    while not ap.active():
        if led is not None:
            led.toggle()
        time.sleep_ms(100)

    if led is not None:
        led.on()

    print("Pico AP started")
    print("SSID:", ssid)
    print("IP address:", ap.ifconfig()[0])
    return ap


class UdpRcReceiver:
    def __init__(self, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", port))
        self.sock.settimeout(0.0)
        self.last_addr = None
        self.packet_count = 0
        print("UDP port:", port)

    def receive(self):
        try:
            data, addr = self.sock.recvfrom(1024)
        except OSError:
            return None

        try:
            message = data.decode().strip()
            parsed = json.loads(message)
            self.last_addr = addr
            self.packet_count += 1
            if parsed.get("receiver_test") is True:
                parsed["arm"] = False
                return sanitize_rc(parsed, force_throttle_low=False)
            return sanitize_rc(parsed)
        except Exception as exc:
            print("bad packet:", exc)
            return default_rc()

    def send_status(self, status):
        if self.last_addr is None:
            return
        try:
            payload = json.dumps(status).encode()
            self.sock.sendto(payload, self.last_addr)
        except OSError:
            pass
