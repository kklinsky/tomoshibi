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


def test_stt_entries_name_a_known_engine():
    for spec in models.load_lock(LOCK):
        if spec.kind == "stt":
            assert spec.engine in ("whisper", "moonshine"), spec.name
            if spec.engine == "moonshine":
                assert spec.arch, f"{spec.name} needs an arch"


def test_files_dir_is_the_common_parent(tmp_path):
    spec = models.find(models.load_lock(LOCK), "moonshine-base-en")
    assert spec.files_dir(tmp_path) == tmp_path / spec.name / "model/base-en/quantized/base-en"
    whisper = models.find(models.load_lock(LOCK), "whisper-base-en")
    assert whisper.files_dir(tmp_path) == whisper.local_dir(tmp_path)
