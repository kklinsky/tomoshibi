"""Model downloads pinned by models.lock."""

import posixpath
import tomllib
from dataclasses import dataclass
from pathlib import Path

from tomoshibi import paths

# Engine used when a models.lock entry does not name one.
DEFAULT_ENGINE = {"stt": "whisper", "tts": "piper"}


@dataclass(frozen=True)
class ModelSpec:
    name: str
    kind: str
    repo: str
    revision: str
    files: tuple[str, ...]
    engine: str = "whisper"  # which STT/TTS class reads this model; see DEFAULT_ENGINE
    arch: str | None = None  # engine-specific model architecture, e.g. Moonshine's "base"
    voice: str | None = None  # default voice for multi-voice TTS models, e.g. Kokoro's

    def local_dir(self, models_dir: Path | None = None) -> Path:
        return (models_dir or paths.models_dir()) / self.name

    def is_present(self, models_dir: Path | None = None) -> bool:
        root = self.local_dir(models_dir)
        return all((root / f).is_file() for f in self.files)

    def files_dir(self, models_dir: Path | None = None) -> Path:
        """The deepest directory holding all of this model's files."""
        common = posixpath.commonpath([posixpath.dirname(f) for f in self.files])
        return self.local_dir(models_dir) / common


def load_lock(path: Path) -> list[ModelSpec]:
    with path.open("rb") as f:
        data = tomllib.load(f)
    return [
        ModelSpec(
            name=name,
            kind=entry["kind"],
            repo=entry["repo"],
            revision=entry["revision"],
            files=tuple(entry["files"]),
            engine=entry.get("engine", DEFAULT_ENGINE.get(entry["kind"], "whisper")),
            arch=entry.get("arch"),
            voice=entry.get("voice"),
        )
        for name, entry in data.get("models", {}).items()
    ]


def find(specs: list[ModelSpec], name: str) -> ModelSpec:
    for spec in specs:
        if spec.name == name:
            return spec
    raise KeyError(f"No model named {name!r} in models.lock")


def first_of_kind(specs: list[ModelSpec], kind: str) -> ModelSpec:
    for spec in specs:
        if spec.kind == kind:
            return spec
    raise KeyError(f"No {kind} model in models.lock")


def fetch(spec: ModelSpec, models_dir: Path | None = None) -> Path:
    from huggingface_hub import snapshot_download

    target = spec.local_dir(models_dir)
    snapshot_download(
        repo_id=spec.repo,
        revision=spec.revision,
        allow_patterns=list(spec.files),
        local_dir=target,
    )
    return target


def piper_model_path(spec: ModelSpec, models_dir: Path | None = None) -> Path:
    onnx = next(f for f in spec.files if f.endswith(".onnx"))
    return spec.local_dir(models_dir) / onnx
