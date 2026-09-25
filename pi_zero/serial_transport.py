"""CRSF output with an injectable pyserial-compatible writer."""

import logging
import time

from crsf import make_rc_frame
from rc_protocol import rc_to_channels

logger = logging.getLogger(__name__)


class SerialTransport:
    def __init__(self, serial):
        self.serial = serial

    @classmethod
    def open(cls, device, baud, serial_factory=None):
        if serial_factory is None:
            import serial  # Optional in dry-run and unit tests.
            serial_factory = serial.Serial
        return cls(serial_factory(
            port=device, baudrate=baud, bytesize=8, parity="N", stopbits=1,
            timeout=0, write_timeout=0.020, xonxoff=False, rtscts=False,
            dsrdtr=False, exclusive=True,
        ))

    def send(self, rc):
        frame = bytes(make_rc_frame(rc_to_channels(rc)))
        if self.serial.write(frame) != len(frame):
            raise OSError("Incomplete CRSF UART write")

    def close(self):
        self.serial.close()


class DryRunTransport:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.next_log = 0.0

    def send(self, rc):
        now = self.clock()
        if now >= self.next_log:
            logger.info("dry-run rc=%s crsf=%s", rc,
                        bytes(make_rc_frame(rc_to_channels(rc))).hex())
            self.next_log = now + 1.0

    def close(self):
        pass
