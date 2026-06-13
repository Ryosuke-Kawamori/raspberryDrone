import time
from machine import Pin, UART

from crsf import CrsfRcSender
from pico_udp import UdpRcReceiver, connect_wifi, start_access_point
from rc_protocol import default_rc, rc_to_channels

try:
    from wifi_config import AP_PASSWORD, AP_SSID, WIFI_MODE
except ImportError:
    AP_SSID = "pico-drone"
    AP_PASSWORD = "drone12345"
    WIFI_MODE = "ap"

try:
    from wifi_config import STA_PASSWORD, STA_SSID
except ImportError:
    STA_SSID = ""
    STA_PASSWORD = ""


UDP_PORT = 5005
LINK_TIMEOUT_MS = 500
RC_PERIOD_MS = 20
STATUS_PERIOD_MS = 200

UART_ID = 0
UART_TX_PIN = 0  # GP0 -> FC RX
UART_RX_PIN = 1  # GP1 <- FC TX, optional


def make_uart():
    return UART(
        UART_ID,
        baudrate=420000,
        bits=8,
        parity=None,
        stop=1,
        tx=Pin(UART_TX_PIN),
        rx=Pin(UART_RX_PIN),
    )


def main():
    led = Pin("LED", Pin.OUT)
    if WIFI_MODE == "sta":
        connect_wifi(STA_SSID, STA_PASSWORD, led=led)
    else:
        start_access_point(AP_SSID, AP_PASSWORD, led=led)

    receiver = UdpRcReceiver(UDP_PORT)
    crsf = CrsfRcSender(make_uart())

    rc = default_rc()
    last_packet_ms = time.ticks_ms()
    last_send_ms = time.ticks_ms()
    last_status_ms = time.ticks_ms()

    print("ready: UDP port", UDP_PORT)

    while True:
        received = receiver.receive()
        if received is not None:
            rc = received
            last_packet_ms = time.ticks_ms()
            led.toggle()

        if time.ticks_diff(time.ticks_ms(), last_packet_ms) > LINK_TIMEOUT_MS:
            rc = default_rc()

        now = time.ticks_ms()
        if time.ticks_diff(now, last_send_ms) >= RC_PERIOD_MS:
            crsf.send_channels(rc_to_channels(rc))
            last_send_ms = now

        if time.ticks_diff(now, last_status_ms) >= STATUS_PERIOD_MS:
            receiver.send_status(
                {
                    "type": "pico_status",
                    "packets": receiver.packet_count,
                    "link_age_ms": time.ticks_diff(now, last_packet_ms),
                    "rc": rc,
                }
            )
            last_status_ms = now

        time.sleep_ms(1)


try:
    main()
finally:
    uart = make_uart()
    crsf = CrsfRcSender(uart)
    safe = rc_to_channels(default_rc())
    for _ in range(50):
        crsf.send_channels(safe)
        time.sleep_ms(20)
