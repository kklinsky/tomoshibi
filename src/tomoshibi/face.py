"""The animated face: layers the face pack's parts and moves them, as designed in DESIGN.md §3.

The motion matches tools/face-previewer/index.html, so a face that looks right there looks
right here. Parts that haven't been drawn yet (thinking dots, for now) are simply left out.
"""

import math
import random
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont

from tomoshibi import paths
from tomoshibi.display import HEIGHT, WIDTH

FACE_H = 240  # a square face area, with the day and time strip below it
STRIP_H = HEIGHT - FACE_H
BACKGROUND = (0x1E, 0x1B, 0x2E)
FPS = 20

MODES = ("idle", "listening", "thinking", "speaking", "sleeping")
EXPRESSIONS = ("none", "happy", "concerned", "curious", "lookup")
# name: (seconds, the mode it ends in)
TRANSITIONS = {
    "wake": (1.0, "idle"),
    "sleep": (1.3, "sleeping"),
    "notice": (0.45, "listening"),
    "ahem": (0.9, "speaking"),
    "settle": (0.7, "idle"),
}
# Where extras sit on the face; they're centered on these points.
ANCHOR = {"dots": (190, 42), "z": (184, 58), "magnifier": (194, 46)}


def ease(t: float) -> float:
    return 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2


def mouth_for(level: float, oo: bool = False) -> str:
    """Mouth shape from how loud the voice is right now, 0 to 1."""
    if level < 0.12:
        return "mouth_closed"
    if oo and level < 0.75:
        return "mouth_oo"
    if level < 0.4:
        return "mouth_open_1"
    if level < 0.72:
        return "mouth_open_2"
    return "mouth_open_3"


def strip_lines(now: datetime) -> tuple[str, str]:
    """("Saturday", "afternoon · 2:15")."""
    hour = now.hour
    part = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening" if hour < 21 else "night"
    clock = now.hour % 12 or 12
    return now.strftime("%A"), f"{part} · {clock}:{now.minute:02d}"


@dataclass
class Pose:
    eyes: str = "eyes_open"
    pupils: bool = True
    pupil: tuple[float, float] = (0, 0)
    brows: str = "brows_neutral"
    mouth: str = "mouth_smile"
    extras: list = field(default_factory=list)  # (part name, x, y, alpha)
    dy: float = 0
    tilt: float = 0
    scale: float = 1
    dim: float = 0


def font(size: int, weight: int) -> ImageFont.FreeTypeFont:
    """Fredoka at a size and weight; it's bundled, so it works offline."""
    loaded = ImageFont.truetype(paths.assets_dir() / "fonts/fredoka/Fredoka[wdth,wght].ttf", size)
    loaded.set_variation_by_axes([weight if a["name"] == b"Weight" else 100
                                  for a in loaded.get_variation_axes()])
    return loaded


def boot_frame() -> Image.Image:
    """The startup screen: the wordmark in lamplight on night (docs/brand.md)."""
    frame = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(frame)
    draw.text((WIDTH / 2, HEIGHT / 2 - 8), "tomo", fill="#f2b45a", font=font(72, 600), anchor="mm")
    draw.text((WIDTH / 2, HEIGHT / 2 + 50), "Starting up…", fill="#a99fb6", font=font(18, 500), anchor="mm")
    return frame


def load_parts(folder: Path | None = None) -> dict[str, Image.Image]:
    folder = folder or paths.assets_dir() / "faces" / "tomoshibi"
    parts = {f.stem: Image.open(f).convert("RGBA") for f in sorted(folder.glob("*.png"))}
    if "eyes_open" not in parts:
        raise FileNotFoundError(f"no face parts found in {folder}")
    return parts


class Face:
    """Works out the pose for each moment and draws it. Times are in seconds."""

    def __init__(self, parts: dict[str, Image.Image], rng: random.Random | None = None):
        self.parts, self.rng = parts, rng or random.Random()
        self.mode, self.expression = "idle", "none"
        self.transition: tuple[str, float] | None = None
        self.voice_level, self.pretend_voice = 0.0, False
        self.blink_at, self.blink_start = self.rng.uniform(3, 7), None
        self.pupil, self.pupil_target, self.drift_at = [0.0, 0.0], (0.0, 0.0), 0.0
        self.syllable = (0.0, 0.0, 0.0, False)  # start, end, peak, oo
        self.smoothed_level = 0.0
        self.layers: OrderedDict = OrderedDict()  # recent poses, so repeats cost nothing
        self.strip_key, self.strip = None, None
        self.fonts = [font(24, 600), font(18, 500)]

    def play(self, name: str, now: float) -> None:
        self.transition = (name, now)

    def _pretend_level(self, now: float) -> tuple[float, bool]:
        """Syllables of random loudness with short gaps, for demos with no voice playing."""
        start, end, peak, oo = self.syllable
        if now > end:
            gap = self.rng.random() < 0.18
            start, end = now, now + (self.rng.uniform(.12, .32) if gap else self.rng.uniform(.11, .23))
            peak, oo = (0.0 if gap else self.rng.uniform(.35, 1)), (not gap and self.rng.random() < .12)
            self.syllable = (start, end, peak, oo)
        return peak * math.sin(math.pi * min(1, (now - start) / (end - start))), oo

    def _drift(self, now: float) -> None:
        if now > self.drift_at:
            still = self.rng.random() < 0.35
            self.pupil_target = (0, 0) if still else (self.rng.uniform(-7, 7), self.rng.uniform(-4, 4))
            self.drift_at = now + self.rng.uniform(1.8, 4.8)
        self.pupil[0] += (self.pupil_target[0] - self.pupil[0]) * 0.08
        self.pupil[1] += (self.pupil_target[1] - self.pupil[1]) * 0.08

    def pose(self, now: float) -> Pose:
        if self.transition and now - self.transition[1] >= TRANSITIONS[self.transition[0]][0]:
            self.mode, self.transition = TRANSITIONS[self.transition[0]][1], None
        self._drift(now)
        mode, expression, p = self.mode, self.expression, Pose()

        if mode == "idle":
            p.dy, p.pupil = math.sin(now * math.tau / 4) * 2, tuple(self.pupil)
        elif mode == "listening":
            p.eyes, p.brows, p.mouth, p.scale = "eyes_wide", "brows_raised", "mouth_closed", 1.03
            p.dy = math.sin(now * math.tau / 3)
        elif mode == "thinking":
            p.mouth, p.pupil = "mouth_closed", (7, -6)
            p.extras.append((f"thinking_dots_{1 + int(now * 2.5) % 3}", *ANCHOR["dots"], 1))
        elif mode == "speaking":
            level, oo = self._pretend_level(now) if self.pretend_voice else (self.voice_level, False)
            self.smoothed_level += (level - self.smoothed_level) * 0.6
            p.mouth = mouth_for(self.smoothed_level, oo)
            p.dy = math.sin(now * math.tau / 4) * 1.5
            p.pupil = (self.pupil[0] * 0.4, self.pupil[1] * 0.4)
        elif mode == "sleeping":
            p.eyes, p.pupils, p.mouth, p.dim = "eyes_closed", False, "mouth_closed", 0.5
            p.dy = math.sin(now * math.tau / 6) * 2.5
            t = (now % 3.2) / 3.2
            p.extras.append(("sleep_z", ANCHOR["z"][0] + t * 14, ANCHOR["z"][1] - t * 26, math.sin(math.pi * t)))

        if expression == "happy":
            p.eyes, p.pupils = "eyes_happy", False
            if mode != "speaking":
                p.mouth = "mouth_smile"
        elif expression == "concerned":
            p.eyes, p.brows, p.pupil = "eyes_sympathetic", "brows_soft", (0, 2)
            if mode != "speaking":
                p.mouth = "mouth_closed"
        elif expression == "curious":
            p.tilt, p.brows = -6, "brows_raised"
            if mode == "idle":
                p.mouth = "mouth_closed"
        elif expression == "lookup":
            p.pupil = (9, -2)
            if mode != "speaking":
                p.mouth = "mouth_closed"
            x, y = ANCHOR["magnifier"]
            p.extras.append(("magnifier", x, y + math.sin(now * 3) * 3, 1))
        if mode == "sleeping":
            p.eyes, p.pupils = "eyes_closed", False

        if self.transition:
            self._transition(p, now)
        elif mode != "sleeping" and p.eyes in ("eyes_open", "eyes_wide", "eyes_sympathetic"):
            self._blink(p, now, mode)
        return p

    def _transition(self, p: Pose, now: float) -> None:
        name, start = self.transition
        t = min(1, (now - start) / TRANSITIONS[name][0])
        p.extras = []
        if name == "wake":
            p.eyes = "eyes_closed" if t < .35 else "eyes_half" if t < .6 else "eyes_open"
            p.pupils = t >= .6
            p.scale, p.dim = 1 + 0.045 * math.sin(math.pi * t), 0.5 * (1 - ease(t))
            p.mouth = "mouth_closed" if t < .6 else "mouth_smile"
        elif name == "sleep":
            p.eyes = "eyes_open" if t < .4 else "eyes_half" if t < .75 else "eyes_closed"
            p.pupils = t < .4
            p.dy, p.dim, p.mouth = 3 * ease(t), 0.5 * ease(t), "mouth_closed"
        elif name == "notice":
            p.eyes = "eyes_closed" if t < .2 else "eyes_half" if t < .35 else "eyes_wide"
            p.pupils, p.pupil = t >= .35, (0, 0)
            p.brows, p.mouth, p.scale = "brows_raised", "mouth_closed", 1 + 0.03 * ease(t)
        elif name == "ahem":
            p.eyes, p.brows, p.pupil = "eyes_wide" if t < .5 else "eyes_open", "brows_raised", (0, 0)
            p.dy, p.mouth = -3 * math.sin(math.pi * t), "mouth_closed"
        elif name == "settle":
            p.eyes, p.brows, p.dy = "eyes_open", "brows_neutral", 4 * math.sin(math.pi * t)
            p.mouth = "mouth_closed" if t < .5 else "mouth_smile"

    def _blink(self, p: Pose, now: float, mode: str) -> None:
        if self.blink_start is None and now >= self.blink_at:
            self.blink_start = now
        if self.blink_start is None:
            return
        drawn = all(f"blink_{i}" in self.parts for i in (1, 2, 3, 4))
        steps = [f"blink_{i}" for i in (1, 2, 3, 4)] if drawn else ["eyes_half", "eyes_closed", "eyes_half"]
        step = int((now - self.blink_start) / 0.055)
        if step < len(steps):
            p.eyes, p.pupils = steps[step], False
        else:
            self.blink_start = None
            self.blink_at = now + (self.rng.uniform(6, 10) if mode == "listening" else self.rng.uniform(3, 7))

    def _layer(self, p: Pose) -> Image.Image:
        """The face itself, transparent around the edges."""
        dx, dy = round(p.pupil[0]), round(p.pupil[1])
        extras = tuple((n, round(x), round(y), round(a, 1)) for n, x, y, a in p.extras if n in self.parts)
        key = (p.eyes, p.pupils, dx, dy, p.brows, p.mouth, extras, p.tilt, round(p.scale, 3))
        if key in self.layers:
            self.layers.move_to_end(key)
            return self.layers[key]

        layer = Image.new("RGBA", (WIDTH, FACE_H), (0, 0, 0, 0))
        if "face_base" in self.parts:
            layer.alpha_composite(self.parts["face_base"])
        layer.alpha_composite(self._eyes(p.eyes, p.pupils, dx, dy))
        for name in (p.brows, p.mouth):
            if name in self.parts:
                layer.alpha_composite(self.parts[name])
        for name, x, y, alpha in extras:
            part = self.parts[name]
            if alpha < 1:
                part = part.copy()
                part.putalpha(part.getchannel("A").point(lambda v, a=alpha: int(v * a)))
            layer.alpha_composite(part, (x - part.width // 2, y - part.height // 2))

        if p.tilt or p.scale != 1:
            layer = self._turned(layer, p.tilt, p.scale)
        self.layers[key] = layer
        if len(self.layers) > 48:
            self.layers.popitem(last=False)
        return layer

    def _eyes(self, name: str, show_pupils: bool, dx: int, dy: int) -> Image.Image:
        eyes, pupils = self.parts[name], self.parts.get("pupils")
        if pupils is None:
            moved = Image.new("RGBA", eyes.size, (0, 0, 0, 0))
            moved.paste(eyes, (dx // 2, dy // 2))
            return moved
        if not show_pupils:
            return eyes
        # Pupils slide around but stay clipped to the shape of the eye.
        moved = Image.new("RGBA", eyes.size, (0, 0, 0, 0))
        moved.paste(pupils, (dx, dy))
        moved.putalpha(ImageChops.multiply(moved.getchannel("A"), eyes.getchannel("A")))
        result = eyes.copy()
        result.alpha_composite(moved)
        return result

    @staticmethod
    def _turned(layer: Image.Image, tilt: float, scale: float) -> Image.Image:
        cx, cy = WIDTH / 2, FACE_H / 2
        angle = math.radians(tilt)
        a, b = math.cos(angle) / scale, math.sin(angle) / scale
        matrix = (a, b, cx - a * cx - b * cy, -b, a, cy + b * cx - a * cy)
        return layer.transform(layer.size, Image.Transform.AFFINE, matrix, Image.Resampling.BILINEAR)

    def _strip(self, now: datetime) -> Image.Image:
        lines = strip_lines(now)
        if lines != self.strip_key:
            strip = Image.new("RGB", (WIDTH, STRIP_H), tuple(int(c + (255 - c) * 0.06) for c in BACKGROUND))
            draw = ImageDraw.Draw(strip)
            draw.text((WIDTH / 2, 27), lines[0], fill="#f1e7d6", font=self.fonts[0], anchor="mm")
            draw.text((WIDTH / 2, 56), lines[1], fill="#cbbfd8", font=self.fonts[1], anchor="mm")
            self.strip_key, self.strip = lines, strip
        return self.strip

    def frame(self, now: float, clock: datetime | None = None) -> Image.Image:
        p = self.pose(now)
        layer = self._layer(p)
        frame = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
        frame.paste(layer, (0, round(p.dy)), layer)
        frame.paste(self._strip(clock or datetime.now()), (0, FACE_H))
        if p.dim:
            frame = Image.blend(frame, Image.new("RGB", frame.size, (0, 0, 0)), p.dim)
        return frame


class FaceScreen:
    """Keeps the face moving on the screen from its own thread, so speech never waits on it."""

    def __init__(self, face: Face, screen):
        self.face, self.screen = face, screen
        self.frames, self.sent, self.busy = 0, 0, 0.0
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def _run(self) -> None:
        origin = time.monotonic()
        while not self.stopping.is_set():
            started = time.monotonic()
            rgb = np.asarray(self.face.frame(started - origin))
            self.sent += bool(self.screen.show(rgb))
            if self.frames == 0:
                self.screen.backlight(True)  # only once there's a picture to light
            self.frames += 1
            self.busy += time.monotonic() - started
            self.stopping.wait(max(0.0, 1 / FPS - (time.monotonic() - started)))

    def stop(self) -> None:
        self.stopping.set()
        self.thread.join()


DEMO = [
    ("idle", "none", None, 4), (None, None, "notice", 3), ("thinking", "none", None, 2),
    ("speaking", "none", None, 4), ("speaking", "happy", None, 3), ("listening", "concerned", None, 3),
    ("listening", "curious", None, 3), ("thinking", "lookup", None, 3), (None, "none", "settle", 3),
    (None, None, "sleep", 5), (None, None, "wake", 3),
]


def run_demo(face: Face, runner: FaceScreen, end: float) -> None:
    origin = time.monotonic()
    while time.monotonic() < end:
        for mode, expression, transition, seconds in DEMO:
            if mode:
                face.mode = mode
            if expression:
                face.expression = expression
            if transition:
                face.play(transition, time.monotonic() - origin)
            time.sleep(min(seconds, max(0, end - time.monotonic())))


SHEET = [
    ("Idle", "idle", "none"), ("Listening", "listening", "none"), ("Thinking", "thinking", "none"),
    ("Speaking", "speaking", "none"), ("Sleeping", "sleeping", "none"), ("Happy", "idle", "happy"),
    ("Concerned", "listening", "concerned"), ("Curious", "listening", "curious"),
]


def preview_sheet(face: Face) -> Image.Image:
    """Every state side by side, for checking the art without a screen."""
    columns, gap = 4, 16
    rows = math.ceil(len(SHEET) / columns)
    sheet = Image.new("RGB", (columns * (WIDTH + gap) + gap, rows * (HEIGHT + 30 + gap) + gap), "#15121c")
    draw = ImageDraw.Draw(sheet)
    face.voice_level, face.smoothed_level = 0.6, 0.6
    clock = datetime(2026, 11, 7, 14, 15)
    for i, (label, mode, expression) in enumerate(SHEET):
        face.mode, face.expression = mode, expression
        x, y = gap + (i % columns) * (WIDTH + gap), gap + (i // columns) * (HEIGHT + 30 + gap)
        sheet.paste(face.frame(0.0, clock), (x, y))
        draw.text((x, y + HEIGHT + 6), label, fill="#f1e7d6", font=face.fonts[1])
    return sheet
