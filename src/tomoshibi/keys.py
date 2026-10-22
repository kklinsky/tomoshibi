"""The talk button: a keyboard key for now, the arcade button on GPIO later.

Reads Linux input events straight from /dev/input, so no extra packages are needed and it
works whether or not a terminal has focus. The user needs to be in the `input` group.
"""

import glob
import struct
import threading
from collections.abc import Callable

EVENT = struct.Struct("llHHi")  # struct input_event on 64-bit Linux: time, type, code, value
EV_KEY = 1
KEY_SPACE = 57
KEY_ENTER = 28
PRESSED = 1


def keyboard_devices() -> list[str]:
    return sorted(glob.glob("/dev/input/by-id/*-event-kbd"))


def parse(data: bytes) -> list[tuple[int, int, int]]:
    """(type, code, value) for each whole event in `data`."""
    events = []
    for offset in range(0, len(data) - EVENT.size + 1, EVENT.size):
        _sec, _usec, etype, code, value = EVENT.unpack_from(data, offset)
        events.append((etype, code, value))
    return events


class KeyButton:
    """Calls `on_press` when Space or Enter is pressed on any attached keyboard."""

    def __init__(self, on_press: Callable[[], None], codes: tuple[int, ...] = (KEY_SPACE, KEY_ENTER)):
        self.on_press = on_press
        self.codes = codes
        self.devices = keyboard_devices()
        for path in self.devices:
            threading.Thread(target=self._watch, args=(path,), daemon=True).start()

    def _watch(self, path: str) -> None:
        try:
            with open(path, "rb", buffering=0) as f:
                while True:
                    for etype, code, value in parse(f.read(EVENT.size * 16)):
                        if etype == EV_KEY and value == PRESSED and code in self.codes:
                            self.on_press()
        except OSError:
            return
