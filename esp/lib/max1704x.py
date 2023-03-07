# Base driver for MAX1704x fuel gauge
# Copyright (c) 2023 Petr Kracik
# Copyright (c) 2023 OctopusLAB

from struct import unpack

__version__ = "0.0.1"
__license__ = "MIT"
__author__ = "Petr Kracik"


class MAX1704x:
    ADDRESS = 0x36
    REG_VCELL = 0x02
    REG_SOC = 0x04
    REG_MODE = 0x06
    REG_VER = 0x08

    REG_CRATE = 0x16

    REG_STATUS = 0x1A
    REG_CMD = 0xFE


    def __init__(self, i2c):
        self._i2c = i2c


    @property
    def vcell(self):
        return unpack(">H", self._i2c.readfrom_mem(self.ADDRESS, self.REG_VCELL, 2))[0] * 78.125 / 1_000_000


    @property
    def crate(self):
        return unpack(">h", self._i2c.readfrom_mem(self.ADDRESS, self.REG_CRATE, 2))[0] * 0.208


    @property
    def soc(self):
        return unpack(">H", self._i2c.readfrom_mem(self.ADDRESS, self.REG_SOC, 2))[0] / 256.0


    @property
    def version(self):
        return unpack(">H", self._i2c.readfrom_mem(self.ADDRESS, self.REG_VER, 2))[0] - 0x0010


    def reset(self):
        try:
            self._i2c.writeto_mem(self.ADDRESS, self.REG_CMD, b'\x54\x00')
        except:
            print("Reset NACK!")
            pass
