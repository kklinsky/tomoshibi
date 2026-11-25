"""The arcade button and its light, wired as in hardware/wiring.md.

The switch connects its pin to ground, so a press is a falling edge with the Pi's internal
pull-up on. The light means one thing once Tomo is ready: on while Tomo is listening. Before
that, it shows Tomo starting up: solid while the Pi boots (gpio= in the Pi's boot config, set
by install.sh), then a slow blink while Tomo loads.
"""

import threading
import time
from collections.abc import Callable
from datetime import timedelta

MIN_GAP = 0.3  # seconds between presses, so a shaky press counts once
BLINK_PERIOD = 1.2  # seconds for one on-off cycle while starting up: slow reads as "wait"


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


class Blinker:
    """Blinks a light from its own thread until stopped. `set_light(on)` does the switching."""

    def __init__(self, set_light: Callable[[bool], None], period: float = BLINK_PERIOD):
        self.set_light, self.period = set_light, period
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> "Blinker":
        self.thread.start()
        return self

    def _run(self) -> None:
        on = True
        while True:
            with self.lock:  # a stop can't land between the check and the switch
                if self.stopped.is_set():
                    return
                self.set_light(on)
            on = not on
            self.stopped.wait(self.period / 2)

    def stop(self) -> None:
        """After this returns, the blinker never touches the light again."""
        with self.lock:
            self.stopped.set()


class GpioButton:
    def __init__(self, on_press: Callable[[], None] | None = None, pin: int = 22, light_pin: int = 23):
        import gpiod
        from gpiod.line import Bias, Direction, Edge, Value

        self.on_press = on_press or (lambda: None)  # presses while starting up do nothing
        self.light_pin = light_pin
        self.blinker: Blinker | None = None
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

    def _set(self, on: bool) -> None:
        self.lines.set_value(self.light_pin, self.high if on else self.low)

    def blink(self) -> None:
        """Blink slowly until light() is next called: Tomo is starting up."""
        if not self.blinker:
            self.blinker = Blinker(self._set).start()

    def light(self, on: bool) -> None:
        if self.blinker:
            self.blinker.stop()
            self.blinker = None
        self._set(on)


def open_button(conf: dict) -> GpioButton | None:
    """The arcade button, with its light blinking until Tomo is ready. None if there isn't one."""
    from tomoshibi import config

    try:
        button = GpioButton(pin=int(config.get(conf, "button.pin", 22)),
                            light_pin=int(config.get(conf, "button.light_pin", 23)))
    except (ImportError, OSError) as e:
        print(f"  [no talk button: {e}]", flush=True)
        return None
    button.blink()
    return button
