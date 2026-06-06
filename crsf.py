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
    value = int((us - 1500) * 8 / 5 + 992)
    return max(172, min(1811, value))


def pack_channels(ch_us):
    vals = [us_to_crsf(x) for x in ch_us[:16]]
    bitbuf = 0
    bits = 0
    out = bytearray()

    for value in vals:
        bitbuf |= (value & 0x7FF) << bits
        bits += 11
        while bits >= 8:
            out.append(bitbuf & 0xFF)
            bitbuf >>= 8
            bits -= 8

    return bytes(out)


def make_rc_frame(ch_us):
    payload = pack_channels(ch_us)
    frame = bytearray()
    frame.append(CRSF_ADDR_FLIGHT_CONTROLLER)
    frame.append(len(payload) + 2)
    frame.append(CRSF_FRAMETYPE_RC_CHANNELS_PACKED)
    frame.extend(payload)
    frame.append(crc8_dvb_s2(frame[2:]))
    return frame


class CrsfRcSender:
    def __init__(self, uart):
        self.uart = uart

    def send_channels(self, ch_us):
        self.uart.write(make_rc_frame(ch_us))
