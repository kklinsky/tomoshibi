"""Voice activity detection with Silero VAD (ONNX), and end-of-speech detection."""

from pathlib import Path

import numpy as np

from tomoshibi.audio import FRAME, MIC_RATE

CONTEXT = 64  # Silero v5 prepends the previous 64 samples to each 512-sample frame


class SileroVAD:
    def __init__(self, model_path: Path):
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        self._session = ort.InferenceSession(str(model_path), sess_options=opts)
        self.reset()

    def reset(self) -> None:
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, CONTEXT), dtype=np.float32)

    def probability(self, frame: np.ndarray) -> float:
        """Speech probability (0-1) for one FRAME-sample, 16 kHz frame."""
        x = np.concatenate([self._context, frame.reshape(1, -1).astype(np.float32)], axis=1)
        out, self._state = self._session.run(
            None, {"input": x, "state": self._state, "sr": np.array(MIC_RATE, dtype=np.int64)}
        )
        self._context = x[:, -CONTEXT:]
        return float(out[0][0])


class Endpointer:
    """Decides when a turn has started and when it has ended.

    Speech starts after `start_frames` consecutive speechy frames. It ends after
    `end_silence` seconds without speech; the silence window is long on purpose, since
    older speakers often pause mid-sentence. `wait_for_speech` limits how long to wait
    for anything at all.
    """

    FRAME_SECONDS = FRAME / MIC_RATE

    def __init__(self, end_silence: float = 1.5, wait_for_speech: float = 8.0,
                 max_utterance: float = 30.0, threshold: float = 0.5, start_frames: int = 3):
        self.end_frames = int(end_silence / self.FRAME_SECONDS)
        self.wait_frames = int(wait_for_speech / self.FRAME_SECONDS)
        self.max_frames = int(max_utterance / self.FRAME_SECONDS)
        self.threshold = threshold
        self.start_frames = start_frames
        self.frames = 0
        self.speech_run = 0
        self.silence_run = 0
        self.started = False

    def update(self, prob: float) -> str:
        """Feed one frame's probability. Returns "waiting", "speaking", "done" or "timeout"."""
        self.frames += 1
        speechy = prob >= self.threshold
        if not self.started:
            self.speech_run = self.speech_run + 1 if speechy else 0
            if self.speech_run >= self.start_frames:
                self.started = True
                self.silence_run = 0
                return "speaking"
            return "timeout" if self.frames >= self.wait_frames else "waiting"
        self.silence_run = 0 if speechy else self.silence_run + 1
        if self.silence_run >= self.end_frames or self.frames >= self.max_frames:
            return "done"
        return "speaking"
