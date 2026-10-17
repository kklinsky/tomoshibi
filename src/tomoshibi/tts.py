"""Local text-to-speech with Piper or Kokoro."""

import wave
from pathlib import Path

import numpy as np

from tomoshibi.models import ModelSpec


class PiperTTS:
    def __init__(self, model_path: Path, length_scale: float = 1.0):
        from piper import PiperVoice, SynthesisConfig

        self._voice = PiperVoice.load(str(model_path))
        # length_scale > 1.0 speaks more slowly.
        self._config = SynthesisConfig(length_scale=length_scale)

    def synthesize_to_wav(self, text: str, out_path: Path) -> None:
        with wave.open(str(out_path), "wb") as wav_file:
            self._voice.synthesize_wav(text, wav_file, syn_config=self._config)


class KokoroTTS:
    """Kokoro-82M via kokoro-onnx. More natural than Piper, and slower.

    Voices are the raw float32 style tables from onnx-community's export, one
    (510, 1, 256) array per voice.
    """

    STYLE_DIM = 256

    def __init__(self, model_path: Path, voice_path: Path, length_scale: float = 1.0):
        from kokoro_onnx import Kokoro

        # kokoro-onnx insists on loading a voices .npz; we pass the style ourselves, so
        # an empty archive next to the model satisfies it.
        empty_voices = model_path.with_name("no-voices.npz")
        if not empty_voices.exists():
            np.savez(empty_voices)
        self._kokoro = Kokoro(str(model_path), str(empty_voices))
        self._style = np.fromfile(voice_path, dtype=np.float32).reshape(-1, 1, self.STYLE_DIM)
        # Same meaning as Piper's length_scale: > 1.0 speaks more slowly.
        self._speed = 1.0 / length_scale

    def synthesize_to_wav(self, text: str, out_path: Path) -> None:
        audio, rate = self._kokoro.create(text, voice=self._style, speed=self._speed)
        pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
        with wave.open(str(out_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(rate)
            wav_file.writeframes(pcm.tobytes())


def load(
    spec: ModelSpec,
    models_dir: Path | None = None,
    length_scale: float = 1.0,
    voice: str | None = None,
) -> PiperTTS | KokoroTTS:
    """Create the TTS engine that a models.lock entry names."""
    root = spec.local_dir(models_dir)
    onnx = next(f for f in spec.files if f.endswith(".onnx"))
    if spec.engine == "piper":
        return PiperTTS(root / onnx, length_scale=length_scale)
    if spec.engine == "kokoro":
        voice = voice or spec.voice
        if not voice:
            raise ValueError(f"{spec.name}: Kokoro models need a `voice` in models.lock")
        voice_file = f"voices/{voice}.bin"
        if voice_file not in spec.files:
            raise ValueError(f"{spec.name}: voice {voice!r} is not in its models.lock files")
        return KokoroTTS(root / onnx, root / voice_file, length_scale=length_scale)
    raise ValueError(f"{spec.name}: unknown TTS engine {spec.engine!r}")
