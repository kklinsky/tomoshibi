"""Microphone and speaker I/O through ALSA's arecord/aplay.

Subprocesses keep this simple and robust: ALSA's `plughw` device converts sample rates,
so the Jabra (16 or 48 kHz) can play Kokoro's 24 kHz and Piper's 22.05 kHz audio as is.
"""

import queue
import subprocess
import threading
from typing import Self

import numpy as np

MIC_RATE = 16_000
FRAME = 512  # samples per frame at 16 kHz (32 ms), what Silero VAD expects
DEFAULT_DEVICE = "plughw:CARD=USB"


class Microphone:
    """Streams 16 kHz mono float32 frames from the speakerphone."""

    def __init__(self, device: str = DEFAULT_DEVICE):
        self.device = device
        self._proc: subprocess.Popen | None = None

    def __enter__(self) -> Self:
        self._proc = subprocess.Popen(
            ["arecord", "-q", "-D", self.device, "-f", "S16_LE", "-r", str(MIC_RATE),
             "-c", "1", "-t", "raw"],
            stdout=subprocess.PIPE,
        )
        return self

    def __exit__(self, *exc) -> None:
        if self._proc:
            self._proc.terminate()
            self._proc.wait(timeout=2)
            self._proc = None

    def read(self) -> np.ndarray:
        """One frame of FRAME samples in [-1, 1]. Blocks for about 32 ms."""
        data = self._proc.stdout.read(FRAME * 2)
        if len(data) < FRAME * 2:
            raise OSError("microphone stopped")
        return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


class Speaker:
    """Plays clips one after another in the background; stop() cuts off at once."""

    def __init__(self, device: str = DEFAULT_DEVICE):
        self.device = device
        self._queue: queue.Queue = queue.Queue()
        self._current: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._idle = threading.Event()
        self._idle.set()
        self._stopped = False
        threading.Thread(target=self._run, daemon=True).start()

    def play(self, audio: np.ndarray, rate: int) -> None:
        """Queue int16 mono audio."""
        self._idle.clear()
        self._queue.put((audio, rate))

    def finish(self) -> None:
        """Mark the end of the current reply, so wait() knows when everything has played."""
        self._queue.put(None)

    def wait(self) -> None:
        self._idle.wait()

    @property
    def busy(self) -> bool:
        return not self._idle.is_set()

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
            if self._current:
                self._current.kill()
        self._queue.put(None)

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                with self._lock:
                    self._stopped = False
                if self._queue.empty():
                    self._idle.set()
                continue
            audio, rate = item
            with self._lock:
                if self._stopped:
                    continue
                self._current = subprocess.Popen(
                    ["aplay", "-q", "-D", self.device, "-f", "S16_LE", "-r", str(rate),
                     "-c", "1", "-t", "raw"],
                    stdin=subprocess.PIPE,
                )
            try:
                self._current.stdin.write(audio.astype(np.int16).tobytes())
                self._current.stdin.close()
            except (BrokenPipeError, ValueError):
                pass
            self._current.wait()
            with self._lock:
                self._current = None


def chime(rate: int = 24_000, pitch: float = 880.0, seconds: float = 0.18) -> np.ndarray:
    """A soft two-note chime played when the button is pressed."""
    out = []
    for f in (pitch, pitch * 1.5):
        t = np.arange(int(rate * seconds / 2)) / rate
        envelope = np.sin(np.pi * t / t[-1]) ** 2
        out.append(np.sin(2 * np.pi * f * t) * envelope * 0.25)
    return (np.concatenate(out) * 32767).astype(np.int16)


# --- the reminder tune ---------------------------------------------------------------------
# An original short melody in the spirit of Japanese railway platform chimes: bright,
# bell-like and over in a few seconds. Composed for Tomoshibi, so it can be shared freely.
# A family can use their own sound instead (reminders.tune in config).

_NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# (note, beats). One beat = 0.24 s. Rises, turns, and settles on the home note.
STATION_TUNE = [
    ("D6", 1), ("F#6", 1), ("A6", 1), ("B6", 2), ("A6", 1), ("F#6", 1),
    ("E6", 2), ("A5", 1), ("C#6", 1), ("E6", 1), ("D6", 5),
]


def _freq(note: str) -> float:
    name, octave = note[:-1], int(note[-1])
    semitone = _NOTE[name[0]] + (1 if name.endswith("#") else -1 if name.endswith("b") else 0)
    return 440.0 * 2 ** ((semitone - 9) / 12 + (octave - 4))


def _bell(freq: float, seconds: float, rate: int) -> np.ndarray:
    """A glockenspiel-like strike: a bright attack and inharmonic overtones that fade."""
    t = np.arange(int(rate * seconds)) / rate
    tone = np.zeros_like(t)
    for ratio, level, decay in ((1.0, 1.0, 2.2), (2.76, 0.35, 4.5), (5.40, 0.12, 8.0), (2.0, 0.15, 3.0)):
        if freq * ratio < rate / 2:
            tone += level * np.sin(2 * np.pi * freq * ratio * t) * np.exp(-decay * t)
    attack = np.minimum(1.0, t / 0.004)  # 4 ms, so the strike doesn't click
    return tone * attack


def station_tune(rate: int = 24_000, beat: float = 0.24, volume: float = 0.3) -> np.ndarray:
    """The built-in reminder tune as int16 mono samples."""
    ring = 1.6  # each note keeps ringing under the next, like a real bell
    total = sum(b for _, b in STATION_TUNE) * beat + ring
    out = np.zeros(int(rate * total))
    pos = 0.0
    for note, beats in STATION_TUNE:
        start = int(rate * pos)
        bell = _bell(_freq(note), beats * beat + ring, rate)
        out[start:start + len(bell)] += bell[: len(out) - start]
        pos += beats * beat
    out *= volume / max(1e-9, np.abs(out).max())
    fade = int(rate * 0.3)
    out[-fade:] *= np.linspace(1, 0, fade)
    return (out * 32767).astype(np.int16)


def load_tune(path) -> tuple[np.ndarray, int]:
    """A family's own reminder sound: a 16-bit WAV file (mono or stereo)."""
    import wave

    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"{path}: needs to be a 16-bit WAV file")
        rate, channels = w.getframerate(), w.getnchannels()
        samples = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return samples.reshape(-1, channels).mean(axis=1).astype(np.int16), rate

