from machine import UART, Pin
import time

uart = UART(
    0,
    baudrate=420000,
    bits=8,
    parity=None,
    stop=1,
    tx=Pin(0),
    rx=Pin(1),
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
    # 1000us ≒ 192, 1500us ≒ 992, 2000us ≒ 1792
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

# AETR1234:
# CH1 Roll, CH2 Pitch, CH3 Throttle, CH4 Yaw, CH5 AUX1/Arm
base = [1500] * 16
base[0] = 1500   # Roll
base[1] = 1500   # Pitch
base[2] = 1000   # Throttle low
base[3] = 1500   # Yaw
base[4] = 1000   # AUX1 Arm OFF

while True:
    ch = base[:]

    # Pitchだけ動かす
    if (time.ticks_ms() // 1000) % 2 == 0:
        ch[1] = 1560
    else:
        ch[1] = 1440

    send_rc(ch)
    led.toggle()
    time.sleep_ms(20)  # 50Hz