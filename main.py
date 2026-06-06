"""
from machine import Pin
import time

led = Pin("LED", Pin.OUT)

while True:
    led.toggle()
    print("blink")
    time.sleep(0.5)
"""
#IP address: 192.168.0.112

"""
import network
import time
from machine import Pin

SSID = "Yoshidadorm2.4"
PASSWORD = "nicoshishi"

led = Pin("LED", Pin.OUT)

wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(SSID, PASSWORD)

print("connecting to WiFi...")

for i in range(20):
    if wlan.isconnected():
        break
    led.toggle()
    print("waiting...", i)
    time.sleep(0.5)

if wlan.isconnected():
    print("connected to WiFi")
    print("IP address:", wlan.ifconfig()[0])
else:
    led.off()
    print("failed to connect to WiFi")
"""

"""
import network
import socket
import time
from machine import Pin

SSID = "Yoshidadorm2.4"
PASSWORD = "nicoshishi"

UDP_PORT = 5005

led = Pin("LED", Pin.OUT)

wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(SSID, PASSWORD)

print("connecting to WiFi...")

for i in range(30):
    if wlan.isconnected():
        break
    led.toggle()
    print("waiting...", i)
    time.sleep(0.5)

if wlan.isconnected():
    print("connected to WiFi")
    print("IP address:", wlan.ifconfig()[0])
else:
    led.off()
    print("failed to connect to WiFi")
    raise SystemExit

ip = wlan.ifconfig()[0]
led.on()

print("connected")
print("Pico W IP: ", ip)
print("UDP port: ", UDP_PORT)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", UDP_PORT))
sock.settimeout(1.0)

print("waiting for UDP packets...")

while True:
    try:
        data, addr = sock.recvfrom(1024)
        print("from: ", addr)
        print("data: ", data.decode())
        led.toggle()
    except OSError:
        pass
"""

"""
import network
import socket
import time
import json
from machine import Pin

SSID = "Yoshidadorm2.4"
PASSWORD = "nicoshishi"

UDP_PORT = 5005
TIMEOUT_MS = 500

led = Pin("LED", Pin.OUT)

def clamp(value, min_value, max_value):
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value

def safe_bool(value):
    return True if value is True else False

def default_rc():
    return {
        "roll": 1500,
        "pitch": 1500,
        "throttle": 1000,
        "yaw": 1500,
        "arm": False,
        "angle": True
    }

def sanitize_rc(data):
    rc = default_rc()
    rc["roll"] = clamp(int(data.get("roll", 1500)), 1000, 2000)
    rc["pitch"] = clamp(int(data.get("pitch", 1500)), 1000, 2000)
    rc["throttle"] = clamp(int(data.get("throttle", 1000)), 1000, 1200)
    rc["yaw"] = clamp(int(data.get("yaw", 1500)), 1000, 2000)
    rc["arm"] = safe_bool(data.get("arm", False))
    rc["angle"] = safe_bool(data.get("angle", True))
    if not rc["arm"]:
        rc["throttle"] = 1000
    return rc

def connet_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(SSID, PASSWORD)

    print("connecting to WiFi...")

    for i in range(30):
        if wlan.isconnected():
            break
        led.toggle()
        print("waiting...", i)
        time.sleep(0.5)

    if wlan.isconnected():
        print("connected to WiFi")
        print("IP address:", wlan.ifconfig()[0])
        return wlan
    else:
        led.off()
        print("failed to connect to WiFi")
        raise SystemExit
    
    led.on()
    print("connected")
    print("Pico W IP: ", wlan.ifconfig()[0])
    return(wlan)

def make_udp_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", UDP_PORT))
    sock.settimeout(0.05)
    print("UDP port:", UDP_PORT)
    print("waiting for RC commands...")
    return sock


wlan = connet_wifi()
sock = make_udp_socket()

rc = default_rc()
last_packet_time = time.ticks_ms()

while True:
    try:
        data, addr = sock.recvfrom(1024)
        message = data.decode().strip()

        parsed = json.loads(message)
        rc = sanitize_rc(parsed)
        last_packet_time = time.ticks_ms()

        led.toggle()

        print("from: ", addr)
        print("rc: ", rc)

    except OSError:
        pass
    
    except Exception as e:
        print("bad packet: ", e)
        rc = default_rc()
        rc["arm"] = False
        rc["throttle"] = 1000

    if time.ticks_diff(time.ticks_ms(), last_packet_time) > TIMEOUT_MS:
        rc = default_rc()
        rc["arm"] = False
        rc["throttle"] = 1000
    time.sleep(0.02)
"""

import network
import socket
import time
import json
from machine import Pin, UART

# ===== WiFi設定 =====
SSID = "Yoshidadorm2.4"
PASSWORD = "nicoshishi"

# ===== UDP設定 =====
UDP_PORT = 5005
COMMAND_TIMEOUT_MS = 500

# ===== UART / IBUS設定 =====
# Pico W GP0 = UART0 TX
# Pico W GP1 = UART0 RX
uart = UART(0, baudrate=115200, tx=Pin(0), rx=Pin(1))

led = Pin("LED", Pin.OUT)


def clamp(value, min_value, max_value):
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value


def default_channels():
    """
    IBUSは通常14ch分を送れる。
    Betaflight側ではCH1〜CH8あたりを使う。
    """
    ch = [1500] * 14

    # AETR想定
    ch[0] = 1500  # CH1 Roll
    ch[1] = 1500  # CH2 Pitch
    ch[2] = 1000  # CH3 Throttle
    ch[3] = 1500  # CH4 Yaw

    ch[4] = 1000  # CH5 ARM AUX1
    ch[5] = 2000  # CH6 ANGLE AUX2
    ch[6] = 1000  # CH7 AUTO_TRACK AUX3
    ch[7] = 1000  # CH8 reserved

    return ch


def sanitize_rc(data):
    ch = default_channels()

    roll = clamp(int(data.get("roll", 1500)), 1000, 2000)
    pitch = clamp(int(data.get("pitch", 1500)), 1000, 2000)

    # 初期安全上限。FC接続前でも、最初は低くしておく
    throttle = clamp(int(data.get("throttle", 1000)), 1000, 1200)

    yaw = clamp(int(data.get("yaw", 1500)), 1000, 2000)

    arm = True if data.get("arm", False) is True else False
    angle = True if data.get("angle", True) is True else False
    auto_track = True if data.get("auto_track", False) is True else False

    # arm=falseなら必ずスロットル最小
    if not arm:
        throttle = 1000

    ch[0] = roll
    ch[1] = pitch
    ch[2] = throttle
    ch[3] = yaw
    ch[4] = 2000 if arm else 1000
    ch[5] = 2000 if angle else 1000
    ch[6] = 2000 if auto_track else 1000

    return ch


def make_ibus_frame(channels):
    """
    FlySky IBUS RC frame:
    32 bytes
    byte0: 0x20 = length 32
    byte1: 0x40 = command
    byte2-29: 14 channels, little-endian uint16
    byte30-31: checksum, little-endian
    checksum = 0xFFFF - sum(bytes[0:30])
    """
    frame = bytearray(32)
    frame[0] = 0x20
    frame[1] = 0x40

    for i in range(14):
        value = int(channels[i])
        frame[2 + i * 2] = value & 0xFF
        frame[3 + i * 2] = (value >> 8) & 0xFF

    checksum = 0xFFFF
    for i in range(30):
        checksum -= frame[i]

    frame[30] = checksum & 0xFF
    frame[31] = (checksum >> 8) & 0xFF

    return frame


def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(SSID, PASSWORD)

    print("connecting to WiFi...")

    for i in range(30):
        if wlan.isconnected():
            break
        led.toggle()
        print("waiting...", i)
        time.sleep(0.5)

    if not wlan.isconnected():
        led.off()
        print("wifi connection failed")
        raise SystemExit

    led.on()
    print("connected")
    print("Pico W IP:", wlan.ifconfig()[0])
    return wlan


def make_udp_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", UDP_PORT))
    sock.settimeout(0.001)
    print("UDP port:", UDP_PORT)
    return sock


# ===== 起動 =====
wlan = connect_wifi()
sock = make_udp_socket()

channels = default_channels()
last_packet_ms = time.ticks_ms()
last_print_ms = time.ticks_ms()

print("IBUS output started on GP0 / UART0 TX")
print("waiting for UDP RC commands...")

while True:
    now = time.ticks_ms()

    # UDP受信
    try:
        data, addr = sock.recvfrom(1024)
        message = data.decode().strip()
        parsed = json.loads(message)

        channels = sanitize_rc(parsed)
        last_packet_ms = time.ticks_ms()
        led.toggle()

    except OSError:
        # UDP受信なし
        pass

    except Exception as e:
        print("bad packet:", e)
        channels = default_channels()
        channels[2] = 1000  # throttle
        channels[4] = 1000  # arm off

    # 通信断フェイルセーフ
    if time.ticks_diff(now, last_packet_ms) > COMMAND_TIMEOUT_MS:
        channels = default_channels()
        channels[2] = 1000  # throttle
        channels[4] = 1000  # arm off

    # IBUSを継続送信
    frame = make_ibus_frame(channels)
    uart.write(frame)

    # たまに状態表示
    if time.ticks_diff(now, last_print_ms) > 1000:
        print(
            "CH1 roll:",
            channels[0],
            "CH2 pitch:",
            channels[1],
            "CH3 thr:",
            channels[2],
            "CH4 yaw:",
            channels[3],
            "CH5 arm:",
            channels[4],
            "CH6 angle:",
            channels[5],
        )
        last_print_ms = now

    # IBUSは数ms周期で送る。まずは約7ms
    time.sleep_ms(7)