"""Filesystem locations, overridable with environment variables for development."""

import os
from pathlib import Path

PREFIX = Path(os.environ.get("TOMOSHIBI_PREFIX", "/opt/tomoshibi"))
STATE_DIR = Path(os.environ.get("TOMOSHIBI_STATE_DIR", "/var/lib/tomoshibi"))
CONFIG_DIR = Path(os.environ.get("TOMOSHIBI_CONFIG_DIR", "/etc/tomoshibi"))


def models_dir() -> Path:
    return Path(os.environ.get("TOMOSHIBI_MODELS_DIR", STATE_DIR / "models"))


def data_dir() -> Path:
    return Path(os.environ.get("TOMOSHIBI_DATA_DIR", STATE_DIR / "data"))


def default_models_lock() -> Path:
    """models.lock from the working directory (development) or the installed release."""
    if env := os.environ.get("TOMOSHIBI_MODELS_LOCK"):
        return Path(env)
    for candidate in (Path.cwd() / "models.lock", PREFIX / "current" / "models.lock"):
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return PREFIX / "current" / "models.lock"
