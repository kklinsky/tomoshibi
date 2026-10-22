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
