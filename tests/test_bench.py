from tomoshibi.bench import word_error_rate


def test_wer_ignores_case_and_punctuation():
    assert word_error_rate("What day is it?", "what day is it") == 0


def test_wer_counts_substitutions():
    assert word_error_rate("tell kevin hello", "tell evan hello") == 1 / 3


def test_load_wav_resamples_to_16k(tmp_path):
    import wave

    import numpy as np

    from tomoshibi.stt import WHISPER_RATE, load_wav

    path = tmp_path / "tone.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes((np.sin(np.arange(22050) / 10) * 10000).astype(np.int16).tobytes())
    audio = load_wav(path)
    assert audio.dtype == np.float32
    assert len(audio) == WHISPER_RATE
