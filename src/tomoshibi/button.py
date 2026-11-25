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
SETUP_HOLD = 10.0  # hold this long, let go...
SETUP_CONFIRM = 5.0  # ...and press again within this to start setup mode (docs/DESIGN.md §10b)
FAST_BLINK = 0.3  # "now press once more"


class SetupGesture:
    """Hold the button for SETUP_HOLD seconds, let go, then press once more within
    SETUP_CONFIRM seconds. Times are in seconds; presses here are already debounced.

    `down` says what a press means: "press" (an ordinary press, passed on), "setup" (the
    confirming press, which isn't passed on) or "" (ignored)."""

    def __init__(self, hold: float = SETUP_HOLD, confirm: float = SETUP_CONFIRM):
        self.hold, self.confirm = hold, confirm
        self.pressed_at: float | None = None
        self.confirm_until: float | None = None

    def down(self, now: float) -> str:
        armed = self.confirm_until is not None and now <= self.confirm_until
        self.confirm_until = None
        if armed:
            self.pressed_at = None
            return "setup"
        self.pressed_at = now
        return "press"

    def up(self, now: float) -> None:
        if self.pressed_at is not None and now - self.pressed_at >= self.hold:
            self.confirm_until = now + self.confirm
        self.pressed_at = None

    def held_long(self, now: float) -> bool:
        """Still held, and long enough: time to show that a confirming press is wanted."""
        return self.pressed_at is not None and now - self.pressed_at >= self.hold

    def waiting(self, now: float) -> bool:
        """Between letting go and the confirming press."""
        return self.confirm_until is not None and now <= self.confirm_until


POLL = 0.2  # seconds between looks at the button's level


class ButtonTracker:
    """Debounced presses (falling edges) and regular looks at the line's level, turned into
    what they mean. Only the level ends a hold, so a bouncy switch can't cut one short."""

    def __init__(self, gesture: SetupGesture | None = None, presses: "PressFilter | None" = None):
        self.gesture = gesture or SetupGesture()
        self.presses = presses or PressFilter()
        self.told_hold = False

    def pressed(self, now: float) -> str:
        """A falling edge: "press", "setup" or "" (a bounce)."""
        if not self.presses.accept(now):
            return ""
        return self.gesture.down(now)

    def level(self, now: float, down: bool) -> str:
        """The button is held (down) or not right now. Returns something worth logging, or ""."""
        g = self.gesture
        if down:
            if g.held_long(now) and not self.told_hold:
                self.told_hold = True
                return "held 10 s: let go, then press once more to start setup mode"
            return ""
        if g.pressed_at is None:
            return ""
        g.up(now)
        if self.told_hold:
            self.told_hold = False
            return "let go after a long hold: waiting 5 s for the confirming press"
        return ""

    def hint(self, now: float) -> bool:
        """Blink fast: the hold is long enough, or the confirming press is awaited."""
        return self.gesture.held_long(now) or self.gesture.waiting(now)


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
        self.on_setup: Callable[[], None] = lambda: None  # the setup-mode gesture
        self.light_pin = light_pin
        self.blinker: Blinker | None = None
        self.low, self.high = Value.INACTIVE, Value.ACTIVE
        self.pin = pin
        self.tracker = ButtonTracker()
        self.lines = gpiod.request_lines(  # gpiochip0 is the Pi 5's header
            "/dev/gpiochip0", consumer="tomoshibi-button",
            config={pin: gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP,
                                            edge_detection=Edge.FALLING,
                                            debounce_period=timedelta(milliseconds=30)),
                    light_pin: gpiod.LineSettings(direction=Direction.OUTPUT,
                                                  output_value=Value.INACTIVE)})
        threading.Thread(target=self._watch, daemon=True).start()

    def _watch(self) -> None:
        hinting = False  # fast-blinking: "now press once more"
        while True:
            if self.lines.wait_edge_events(timedelta(seconds=POLL)):
                for _ in self.lines.read_edge_events():
                    meaning = self.tracker.pressed(time.monotonic())
                    if meaning == "setup":
                        print("  [button: setup gesture done, starting setup mode]", flush=True)
                        self.on_setup()
                    elif meaning == "press":
                        self.on_press()
            now = time.monotonic()
            # The level, not edge events, says when it's let go: a bounce can't end a hold.
            note = self.tracker.level(now, down=self.lines.get_value(self.pin) == self.low)
            if note:
                print(f"  [button: {note}]", flush=True)
            want = self.tracker.hint(now)
            if want and self.blinker is None:  # (re)start it: a conversation may have set the light
                self.blink(FAST_BLINK)
            elif hinting and not want:
                self.light(False)
            hinting = want

    def _set(self, on: bool) -> None:
        self.lines.set_value(self.light_pin, self.high if on else self.low)

    def blink(self, period: float = BLINK_PERIOD) -> None:
        """Blink until light() is next called: slowly while Tomo starts up, fast for the
        setup gesture."""
        if self.blinker:
            self.blinker.stop()
        self.blinker = Blinker(self._set, period).start()

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
