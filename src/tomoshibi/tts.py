"""Local text-to-speech with Piper."""

import wave
from pathlib import Path


class PiperTTS:
    def __init__(self, model_path: Path, length_scale: float = 1.0):
        from piper import PiperVoice, SynthesisConfig

        self._voice = PiperVoice.load(str(model_path))
        # length_scale > 1.0 speaks more slowly.
        self._config = SynthesisConfig(length_scale=length_scale)

    def synthesize_to_wav(self, text: str, out_path: Path) -> None:
        with wave.open(str(out_path), "wb") as wav_file:
            self._voice.synthesize_wav(text, wav_file, syn_config=self._config)
