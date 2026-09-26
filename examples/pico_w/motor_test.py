from machine import UART, Pin
import time

uart = UART(
    0,
    baudrate=420000,
    bits=8,
    parity=None,
    stop=1,
    tx=Pin(0),  # GP0 -> FC RX1
    rx=Pin(1),  # GP1 <- FC TX1, 未接続でもOK
)

led = Pin("LED", Pin.OUT)

CRSF_ADDR_FLIGHT_CONTROLLER = 0xC8
CRSF_FRAMETYPE_RC_CHANNELS_PACKED = 0x16

def crc8_dvb_s2(data):
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0xD5) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc

def us_to_crsf(us):
    # Betaflightで見るRC値:
    # 1000us ≒ low, 1500us ≒ center, 2000us ≒ high
    v = int((us - 1500) * 8 / 5 + 992)
    return max(172, min(1811, v))

def pack_channels(ch_us):
    vals = [us_to_crsf(x) for x in ch_us[:16]]
    bitbuf = 0
    bits = 0
    out = bytearray()

    for v in vals:
        bitbuf |= (v & 0x7FF) << bits
        bits += 11
        while bits >= 8:
            out.append(bitbuf & 0xFF)
            bitbuf >>= 8
            bits -= 8

    return bytes(out)

def send_rc(ch_us):
    payload = pack_channels(ch_us)

    frame = bytearray()
    frame.append(CRSF_ADDR_FLIGHT_CONTROLLER)
    frame.append(len(payload) + 2)
    frame.append(CRSF_FRAMETYPE_RC_CHANNELS_PACKED)
    frame.extend(payload)

    crc = crc8_dvb_s2(frame[2:])
    frame.append(crc)

    uart.write(frame)

def make_channels(throttle=1000, arm=False, aux2=1000):
    # AETR1234
    ch = [1500] * 16
    ch[0] = 1500          # Roll
    ch[1] = 1500          # Pitch
    ch[2] = throttle      # Throttle
    ch[3] = 1500          # Yaw
    ch[4] = 2000 if arm else 1000  # AUX1 = Arm
    ch[5] = aux2          # AUX2, Mode用に使うならここ
    return ch

def send_for(seconds, throttle=1000, arm=False, aux2=1000):
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < seconds * 1000:
        send_rc(make_channels(throttle=throttle, arm=arm, aux2=aux2))
        led.toggle()
        time.sleep_ms(20)  # 50Hz

try:
    print("STEP 1: disarm 5 sec")
    send_for(5, throttle=1000, arm=False)

    print("STEP 2: arm, throttle low 5 sec")
    send_for(5, throttle=1000, arm=True)

    print("STEP 3: minimum motor spin test 3 sec")
    send_for(3, throttle=1040, arm=True)

    print("STEP 4: disarm")
    send_for(3, throttle=1000, arm=False)

finally:
    # Ctrl+Cなどで止めても、最後にDisarmを送る
    for _ in range(50):
        send_rc(make_channels(throttle=1000, arm=False))
        time.sleep_ms(20)
    print("DISARM sent")