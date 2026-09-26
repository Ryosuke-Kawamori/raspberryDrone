"""Drivers return only fresh conversions. Hardware imports occur in the worker."""
import math
import time
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Sample:
    sensor: str
    seq: int
    at_s: float
    values: dict
    valid: bool = True
    error: str = ""
    status: int | None = None
    acquisition_s: float = 0.0


class Sensor(Protocol):
    def read(self) -> Sample | None: ...


class FakeSensor:
    def __init__(self, samples=()):
        self.samples = iter(samples)

    def read(self):
        value = next(self.samples, None)
        if isinstance(value, Exception):
            raise value
        return value


class SmbusAdapter:
    """Qwiic I2C interface, with explicit bus selection and unsuppressed IO errors.

    SparkFun's Linux backend auto-selects its bus; this small adapter avoids that.
    """
    def __init__(self, bus):
        self.bus = bus

    def isDeviceConnected(self, address):
        self.bus.read_byte(address)
        return True

    def read_byte(self, address, register):
        return self.bus.read_byte_data(address, register)

    def read_block(self, address, register, length):
        return self.bus.read_i2c_block_data(address, register, length)

    def write_byte(self, address, register, value):
        self.bus.write_byte_data(address, register, value)

    def write_block(self, address, register, values):
        self.bus.write_i2c_block_data(address, register, list(values))


class BMP581:
    def __init__(self, device, clock=time.monotonic, period_s=0.0):
        self.device, self.clock, self.seq = device, clock, 0
        self.period_s = period_s

    @classmethod
    def open(cls, c):
        import qwiic_bmp581 as bmp
        from smbus2 import SMBus
        dev = bmp.QwiicBMP581(c.bmp_address, SmbusAdapter(SMBus(c.i2c_bus)))
        if not dev.begin():
            raise OSError("BMP581 initialization/chip ID failed")
        odr = {0.025: dev.kOdr40Hz, 0.05: dev.kOdr20Hz,
               0.1: dev.kOdr10Hz, 0.2: dev.kOdr05Hz}[c.bmp_period_s]
        dev.set_power_mode(dev.kPowerModeStandby)
        dev.set_odr_frequency(odr)
        source = bmp.intSourceSelect()
        source.intDrdy = dev.kEnable
        dev.int_source_select(source)
        dev.set_power_mode(dev.kPowerModeNormal)
        dev.get_interrupt_status()  # discard initialization conversion/read-to-clear
        return cls(dev, period_s=c.bmp_period_s)

    def read(self):
        started = self.clock()
        if not self.device.get_interrupt_status() & self.device.kIntAssertedDrdy:
            return None
        data = self.device.get_sensor_data()
        # SparkFun 2.0.0 decodes temperature as unsigned 24-bit; signed Q16 correction.
        temp = data.temperature - 256 if data.temperature >= 128 else data.temperature
        valid = (math.isfinite(data.pressure) and 30000 <= data.pressure <= 125000
                 and math.isfinite(temp) and -40 <= temp <= 85)
        self.seq += 1
        return Sample("bmp", self.seq, started-self.period_s,
                      {"pressure_pa": data.pressure, "temperature_c": temp}, valid,
                      "" if valid else "invalid pressure/temperature", acquisition_s=self.clock()-started)


class VL53L4CD:
    def __init__(self, device, clock=time.monotonic, period_s=0.0):
        self.device, self.clock, self.seq = device, clock, 0
        self.period_s = period_s

    @classmethod
    def open(cls, c):
        from adafruit_extended_bus import ExtendedI2C
        from adafruit_vl53l4cd import VL53L4CD as Driver
        dev = Driver(ExtendedI2C(c.i2c_bus), address=c.tof_address)
        dev.timing_budget = c.tof_budget_ms
        dev.inter_measurement = round(c.tof_period_s * 1000)
        dev.start_ranging()
        return cls(dev, period_s=c.tof_period_s)

    def read(self):
        started = self.clock()
        if not self.device.data_ready:
            return None
        status = self.device.range_status
        distance = self.device.distance / 100.0
        self.device.clear_interrupt()  # never publish if consumption failed
        self.seq += 1
        valid = status == 0 and math.isfinite(distance) and 0 < distance < 1.2
        return Sample("tof", self.seq, started-self.period_s, {"distance_m": distance}, valid,
                      "" if valid else "range status/value invalid", status, self.clock()-started)


def guarded_read(sensor, name, clock=time.monotonic):
    try:
        return sensor.read()
    except Exception as exc:
        return Sample(name, -1, clock(), {}, False, type(exc).__name__ + ": " + str(exc))
