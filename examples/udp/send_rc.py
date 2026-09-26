import socket
import json
import time

PICO_IP = "192.168.0.112"  # Pico WのIPに変更
PICO_PORT = 5005

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

cmd = {
    "roll": 1500,
    "pitch": 1500,
    "throttle": 1000,
    "yaw": 1600,
    "arm": False,
    "angle": True,
}

while True:
    message = json.dumps(cmd).encode()
    sock.sendto(message, (PICO_IP, PICO_PORT))
    time.sleep(0.05)  # 20Hz