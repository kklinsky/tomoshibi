import random
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from tomoshibi import face
from tomoshibi.display import HEIGHT, ST7789, WIDTH, changed_box, to_rgb565
from tomoshibi.face import Face, load_parts, mouth_for, strip_lines

ASSETS = Path(__file__).parent.parent / "assets"


@pytest.fixture
def the_face(monkeypatch):
    monkeypatch.setenv("TOMOSHIBI_ASSETS", str(ASSETS))
    return Face(load_parts(ASSETS / "faces" / "tomoshibi"), rng=random.Random(1))


class FakeBus:
    def __init__(self):
        self.writes = []

    def reset(self):
        pass

    def write(self, command, data=b""):
        self.writes.append((command, data))


def test_parts_fit_the_square_face_area():
    parts = load_parts(ASSETS / "faces" / "tomoshibi")
    assert all(p.size == (240, 240) for n, p in parts.items() if n != "mini_face")


def test_strip_lines():
    assert strip_lines(datetime(2026, 11, 7, 14, 15)) == ("Saturday", "afternoon · 2:15")
    assert strip_lines(datetime(2026, 11, 7, 0, 5)) == ("Saturday", "morning · 12:05")
    assert strip_lines(datetime(2026, 11, 7, 21, 0))[1] == "night · 9:00"


def test_mouth_opens_with_loudness():
    assert [mouth_for(x) for x in (0, 0.3, 0.6, 0.9)] == [
        "mouth_closed", "mouth_open_1", "mouth_open_2", "mouth_open_3"]
    assert mouth_for(0.5, oo=True) == "mouth_oo"


@pytest.mark.parametrize("mode", face.MODES)
@pytest.mark.parametrize("expression", face.EXPRESSIONS)
def test_every_mode_and_expression_draws(the_face, mode, expression):
    the_face.mode, the_face.expression = mode, expression
    assert the_face.frame(1.0).size == (WIDTH, HEIGHT)


@pytest.mark.parametrize("name", face.TRANSITIONS)
def test_transitions_draw_and_end_in_their_mode(the_face, name):
    seconds, ends_in = face.TRANSITIONS[name]
    the_face.play(name, 0.0)
    for t in (0.0, seconds / 2):
        the_face.frame(t)
    the_face.frame(seconds + 0.01)
    assert the_face.mode == ends_in and the_face.transition is None


def test_sleeping_is_dimmer_than_idle(the_face):
    awake = np.asarray(the_face.frame(0.0)).mean()
    the_face.mode = "sleeping"
    assert np.asarray(the_face.frame(0.0)).mean() < awake * 0.7


def test_listening_looks_different_from_idle(the_face):
    idle = np.asarray(the_face.frame(0.0)).astype(int)
    the_face.mode = "listening"
    assert np.abs(idle - np.asarray(the_face.frame(0.0)).astype(int)).sum() > 0


def test_it_blinks(the_face):
    eyes = {the_face.pose(t / 20).eyes for t in range(20 * 12)}
    assert "eyes_closed" in eyes


def test_missing_parts_are_left_out(the_face):
    the_face.parts.pop("thinking_dots_1", None)
    the_face.parts.pop("brows_neutral")
    the_face.mode = "thinking"
    assert the_face.frame(0.0).size == (WIDTH, HEIGHT)


def test_preview_sheet(the_face):
    assert isinstance(face.preview_sheet(the_face), Image.Image)


def test_rgb565():
    pixels = to_rgb565(np.array([[[255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 255]]], np.uint8))
    assert pixels.tobytes() == bytes((0xF8, 0, 0x07, 0xE0, 0, 0x1F, 0xFF, 0xFF))


def test_changed_box():
    old = np.zeros((10, 8), ">u2")
    assert changed_box(None, old) == (0, 0, 7, 9)
    assert changed_box(old, old.copy()) is None
    new = old.copy()
    new[2, 3] = new[5, 6] = 1
    assert changed_box(old, new) == (3, 2, 6, 5)


def test_screen_sends_only_what_changed():
    bus = FakeBus()
    screen = ST7789(bus)
    frame = np.zeros((HEIGHT, WIDTH, 3), np.uint8)
    assert screen.show(frame)
    bus.writes.clear()
    assert not screen.show(frame)
    assert bus.writes == []

    frame = frame.copy()
    frame[10, 20] = 255
    assert screen.show(frame)
    assert bus.writes == [(0x2A, bytes((0, 20, 0, 20))), (0x2B, bytes((0, 10, 0, 10))),
                          (0x2C, bytes((0xFF, 0xFF)))]
