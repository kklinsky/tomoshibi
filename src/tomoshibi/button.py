"""The arcade button and its light, wired as in hardware/wiring.md.

The switch connects its pin to ground, so a press is a falling edge with the Pi's internal
pull-up on. The light means one thing: on while Tomo is listening.
"""

import threading
import time
from collections.abc import Callable
from datetime import timedelta

MIN_GAP = 0.3  # seconds between presses, so a shaky press counts once


class PressFilter:
    """Counts a press only if enough time has passed since the last one."""

    def __init__(self, gap: float = MIN_GAP):
        self.gap = gap
        self.last: float | None = None

    def accept(self, now: float) -> bool:
        if self.last is not None and now - self.last < self.gap:
            return False
        self.last = now
        return True


class GpioButton:
    def __init__(self, on_press: Callable[[], None], pin: int = 22, light_pin: int = 23):
        import gpiod
        from gpiod.line import Bias, Direction, Edge, Value

        self.on_press, self.light_pin = on_press, light_pin
        self.low, self.high = Value.INACTIVE, Value.ACTIVE
        self.presses = PressFilter()
        self.lines = gpiod.request_lines(  # gpiochip0 is the Pi 5's header
            "/dev/gpiochip0", consumer="tomoshibi-button",
            config={pin: gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP,
                                            edge_detection=Edge.FALLING,
                                            debounce_period=timedelta(milliseconds=30)),
                    light_pin: gpiod.LineSettings(direction=Direction.OUTPUT,
                                                  output_value=Value.INACTIVE)})
        threading.Thread(target=self._watch, daemon=True).start()

    def _watch(self) -> None:
        while True:
            if self.lines.wait_edge_events(timedelta(seconds=1)):
                self.lines.read_edge_events()
                if self.presses.accept(time.monotonic()):
                    self.on_press()

    def light(self, on: bool) -> None:
        self.lines.set_value(self.light_pin, self.high if on else self.low)
