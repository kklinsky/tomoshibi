from pathlib import Path

from tomoshibi import models

LOCK = Path(__file__).resolve().parents[1] / "models.lock"


def test_lock_parses_and_has_one_of_each_kind():
    specs = models.load_lock(LOCK)
    assert models.first_of_kind(specs, "stt")
    assert models.first_of_kind(specs, "tts")
    for spec in specs:
        assert len(spec.revision) == 40, f"{spec.name} must be pinned to a commit"


def test_piper_model_path_points_at_onnx(tmp_path):
    spec = models.first_of_kind(models.load_lock(LOCK), "tts")
    assert models.piper_model_path(spec, tmp_path).suffix == ".onnx"
