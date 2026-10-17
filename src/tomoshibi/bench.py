"""Speech pipeline benchmark: Piper speaks each phrase, Whisper transcribes it back.

Synthetic speech is far cleaner than a real older voice, so the accuracy here is a
best case. This checks that the pipeline works and how fast it is on the Pi; the real
accuracy test uses recordings of the person (see docs/DESIGN.md §5).
"""

import re
import tempfile
import time
from pathlib import Path

from tomoshibi import models
from tomoshibi.stt import WhisperSTT
from tomoshibi.tts import PiperTTS

PHRASES = [
    "What day is it today?",
    "When is Karen coming to visit?",
    "Did the Tigers win last night?",
    "Remind me to take my pills at eight o'clock.",
    "Who is Emma again?",
    "What's the weather going to be like tomorrow?",
    "Tell Kevin I said hello.",
    "Where did I work after the Navy?",
]


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref, hyp = _words(reference), _words(hypothesis)
    # Levenshtein distance over words.
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, start=1):
        cur = [i]
        for j, h in enumerate(hyp, start=1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h)))
        prev = cur
    return prev[-1] / max(len(ref), 1)


def _words(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9' ]", " ", text.lower()).split()


def _wav_seconds(path: Path) -> float:
    import wave

    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def run(specs: list[models.ModelSpec], stt_names: list[str] | None = None) -> None:
    tts_spec = models.first_of_kind(specs, "tts")
    stt_specs = [s for s in specs if s.kind == "stt" and (not stt_names or s.name in stt_names)]

    t0 = time.perf_counter()
    tts = PiperTTS(models.piper_model_path(tts_spec))
    print(f"Loaded {tts_spec.name} in {time.perf_counter() - t0:.1f} s")

    with tempfile.TemporaryDirectory() as tmp:
        clips = []
        print(f"\nText-to-speech ({tts_spec.name})")
        print(f"{'synth s':>8} {'audio s':>8} {'RTF':>6}  phrase")
        for i, phrase in enumerate(PHRASES):
            wav = Path(tmp) / f"{i}.wav"
            t0 = time.perf_counter()
            tts.synthesize_to_wav(phrase, wav)
            took, audio = time.perf_counter() - t0, _wav_seconds(wav)
            clips.append((phrase, wav, audio))
            print(f"{took:8.2f} {audio:8.2f} {took / audio:6.2f}  {phrase}")

        for spec in stt_specs:
            t0 = time.perf_counter()
            stt = WhisperSTT(spec.local_dir())
            print(f"\nSpeech-to-text ({spec.name}, loaded in {time.perf_counter() - t0:.1f} s)")
            print(f"{'stt s':>8} {'RTF':>6} {'WER':>5}  heard")
            total_time = total_audio = total_wer = 0.0
            for phrase, wav, audio in clips:
                t0 = time.perf_counter()
                heard = stt.transcribe(wav)
                took = time.perf_counter() - t0
                wer = word_error_rate(phrase, heard)
                total_time, total_audio, total_wer = total_time + took, total_audio + audio, total_wer + wer
                print(f"{took:8.2f} {took / audio:6.2f} {wer:5.0%}  {heard}")
            n = len(clips)
            print(
                f"{'avg':>8} {total_time / total_audio:6.2f} {total_wer / n:5.0%}"
                f"  ({total_time / n:.2f} s per phrase)"
            )
    print("\nRTF = processing time / audio length (below 1.0 is faster than real time).")
