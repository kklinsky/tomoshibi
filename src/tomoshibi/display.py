"""The ST7789 screen over SPI: 240x320 in portrait, wired as in hardware/wiring.md.

Only the rectangle that changed since the last frame is sent, which keeps the SPI bus and CPU
quiet while the face is mostly still.
"""

import os
import struct
import time
from pathlib import Path

import numpy as np

WIDTH, HEIGHT = 240, 320
SPI_DEVICE = "/dev/spidev0.0"
SPI_IOC_WR_MODE, SPI_IOC_WR_MAX_SPEED_HZ = 0x40016B01, 0x40046B04  # from <linux/spi/spidev.h>

# From the panel vendor's sample code for the ER-TFT032IPS-3.2-4334.
INIT = [
    (0x36, [0x00]),  # portrait
    (0x3A, [0x05]),  # 16-bit color
    (0xB2, [0x0C, 0x0C, 0x00, 0x33, 0x33]),
    (0xB7, [0x35]),
    (0xBB, [0x15]),
    (0xC0, [0x2C]),
    (0xC2, [0x01]),
    (0xC3, [0x0B]),
    (0xC4, [0x20]),
    (0xC6, [0x0F]),
    (0xD0, [0xA4, 0xA1]),
    (0x21, []),  # color inversion on, which IPS panels need
    (0xE0, [0xF0, 0x00, 0x04, 0x04, 0x04, 0x05, 0x29, 0x33, 0x3E, 0x38, 0x12, 0x12, 0x28, 0x30]),
    (0xE1, [0xF0, 0x07, 0x0A, 0x0D, 0x0B, 0x07, 0x28, 0x33, 0x3E, 0x36, 0x14, 0x14, 0x29, 0x32]),
]


def to_rgb565(rgb: np.ndarray) -> np.ndarray:
    """H x W x 3 bytes -> H x W big-endian 16-bit pixels, the order the panel reads."""
    r, g, b = rgb[..., 0].astype(np.uint16), rgb[..., 1].astype(np.uint16), rgb[..., 2].astype(np.uint16)
    return (((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)).astype(">u2")


def changed_box(old: np.ndarray | None, new: np.ndarray) -> tuple[int, int, int, int] | None:
    """(x0, y0, x1, y1), inclusive, around what differs; None if nothing does."""
    if old is None:
        return 0, 0, new.shape[1] - 1, new.shape[0] - 1
    diff = old != new
    rows, cols = np.flatnonzero(diff.any(axis=1)), np.flatnonzero(diff.any(axis=0))
    if rows.size == 0:
        return None
    return int(cols[0]), int(rows[0]), int(cols[-1]), int(rows[-1])


class SpiBus:
    """SPI0 plus the data/command and reset pins. Holds the pins for as long as it's open,
    since a released reset pin can drift low and blank the panel."""

    def __init__(self, spi_hz: int = 33_400_000, dc_pin: int = 25, reset_pin: int = 27,
                 backlight_pin: int = 18):
        import fcntl

        import gpiod
        from gpiod.line import Direction, Value

        self.dc_pin, self.reset_pin, self.backlight_pin = dc_pin, reset_pin, backlight_pin
        self.low, self.high = Value.INACTIVE, Value.ACTIVE
        self.pins = gpiod.request_lines(  # gpiochip0 is the Pi 5's header
            "/dev/gpiochip0", consumer="tomoshibi-display",
            config={(dc_pin, reset_pin): gpiod.LineSettings(direction=Direction.OUTPUT,
                                                            output_value=Value.ACTIVE),
                    backlight_pin: gpiod.LineSettings(direction=Direction.OUTPUT,
                                                      output_value=Value.INACTIVE)})
        # Plain file access: the kernel's spidev needs no compiled Python package.
        self.spi = os.open(SPI_DEVICE, os.O_WRONLY)
        fcntl.ioctl(self.spi, SPI_IOC_WR_MODE, struct.pack("B", 0))
        fcntl.ioctl(self.spi, SPI_IOC_WR_MAX_SPEED_HZ, struct.pack("I", spi_hz))
        self.chunk = int(Path("/sys/module/spidev/parameters/bufsiz").read_text())

    def reset(self) -> None:
        self.pins.set_value(self.reset_pin, self.low)
        time.sleep(0.02)
        self.pins.set_value(self.reset_pin, self.high)
        time.sleep(0.15)

    def backlight(self, on: bool) -> None:
        self.pins.set_value(self.backlight_pin, self.high if on else self.low)

    def write(self, command: int, data: bytes = b"") -> None:
        self.pins.set_value(self.dc_pin, self.low)
        os.write(self.spi, bytes((command,)))
        if data:
            self.pins.set_value(self.dc_pin, self.high)
            view = memoryview(data)
            for start in range(0, len(view), self.chunk):
                os.write(self.spi, view[start:start + self.chunk])

    def close(self) -> None:
        os.close(self.spi)
        self.pins.release()


class ST7789:
    def __init__(self, bus):
        self.bus = bus
        self.shown: np.ndarray | None = None
        bus.reset()
        for command, data in INIT:
            bus.write(command, bytes(data))
        bus.write(0x11)  # exit sleep
        time.sleep(0.12)
        bus.write(0x29)  # display on

    def show(self, rgb: np.ndarray) -> bool:
        """Draw a HEIGHT x WIDTH x 3 frame. Returns whether anything had to be sent."""
        pixels = to_rgb565(rgb)
        box = changed_box(self.shown, pixels)
        if box is None:
            return False
        x0, y0, x1, y1 = box
        self.bus.write(0x2A, bytes((x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF)))
        self.bus.write(0x2B, bytes((y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF)))
        self.bus.write(0x2C, pixels[y0:y1 + 1, x0:x1 + 1].tobytes())
        self.shown = pixels
        return True

    def backlight(self, on: bool) -> None:
        self.bus.backlight(on)

    def off(self) -> None:
        self.bus.backlight(False)
        self.bus.write(0x28)
