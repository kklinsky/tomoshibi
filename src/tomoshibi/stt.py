"""Local speech-to-text with faster-whisper or Moonshine."""

import wave
from pathlib import Path

import numpy as np

from tomoshibi.models import ModelSpec

WHISPER_RATE = 16_000


def load_wav(path: Path) -> np.ndarray:
    """Read a 16-bit PCM WAV as mono float32 at 16 kHz, the format Whisper expects.

    We decode ourselves rather than letting faster-whisper use PyAV: live audio will
    arrive as raw samples anyway, and it avoids PyAV version incompatibilities.
    """
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"{path}: expected 16-bit PCM, got {8 * w.getsampwidth()}-bit")
        rate, channels = w.getframerate(), w.getnchannels()
        samples = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    audio = samples.reshape(-1, channels).mean(axis=1).astype(np.float32) / 32768.0
    return resample(audio, rate, WHISPER_RATE)


def resample(audio: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
    if from_rate == to_rate:
        return audio
    duration = len(audio) / from_rate
    target = np.linspace(0, duration, int(duration * to_rate), endpoint=False)
    source = np.arange(len(audio)) / from_rate
    return np.interp(target, source, audio).astype(np.float32)


class WhisperSTT:
    def __init__(self, model_dir: Path, compute_type: str = "int8", cpu_threads: int = 4):
        from faster_whisper import WhisperModel

        self._model = WhisperModel(
            str(model_dir), device="cpu", compute_type=compute_type, cpu_threads=cpu_threads
        )

    def transcribe(self, audio: Path | np.ndarray) -> str:
        """Transcribe a WAV file, or mono float32 samples at 16 kHz."""
        if isinstance(audio, Path):
            audio = load_wav(audio)
        segments, _info = self._model.transcribe(audio, language="en", beam_size=1)
        return " ".join(segment.text.strip() for segment in segments).strip()


class MoonshineSTT:
    """Moonshine via moonshine-voice. Unlike Whisper it encodes only the audio it is given,
    so short phrases are fast instead of paying for a fixed 30 s window."""

    def __init__(self, model_dir: Path, arch: str):
        from moonshine_voice.moonshine_api import string_to_model_arch
        from moonshine_voice.transcriber import Transcriber

        self._transcriber = Transcriber(str(model_dir), model_arch=string_to_model_arch(arch))

    def transcribe(self, audio: Path | np.ndarray) -> str:
        """Transcribe a WAV file, or mono float32 samples at 16 kHz."""
        if isinstance(audio, Path):
            audio = load_wav(audio)
        transcript = self._transcriber.transcribe_without_streaming(audio.tolist(), WHISPER_RATE)
        return " ".join(line.text.strip() for line in transcript.lines).strip()


def load(spec: ModelSpec, models_dir: Path | None = None) -> WhisperSTT | MoonshineSTT:
    """Create the STT engine that a models.lock entry names."""
    if spec.engine == "whisper":
        return WhisperSTT(spec.local_dir(models_dir))
    if spec.engine == "moonshine":
        if not spec.arch:
            raise ValueError(f"{spec.name}: Moonshine models need an `arch` in models.lock")
        return MoonshineSTT(spec.files_dir(models_dir), spec.arch)
    raise ValueError(f"{spec.name}: unknown STT engine {spec.engine!r}")
