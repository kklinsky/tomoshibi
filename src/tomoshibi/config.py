"""Loading config.yaml and secrets.env."""

import os
from pathlib import Path

import yaml

from tomoshibi import paths


def config_path() -> Path:
    if env := os.environ.get("TOMOSHIBI_CONFIG"):
        return Path(env)
    return paths.CONFIG_DIR / "config.yaml"


def load(path: Path | None = None) -> dict:
    path = path or config_path()
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get(config: dict, dotted: str, default=None):
    node = config
    for key in dotted.split("."):
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def seconds(value, default: float) -> float:
    """Durations in config are written like "10s", "5m" or plain numbers of seconds."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower()
    for suffix, scale in (("ms", 0.001), ("s", 1), ("m", 60), ("h", 3600)):
        if text.endswith(suffix):
            return float(text[: -len(suffix)]) * scale
    return float(text)


def load_secrets() -> None:
    """Put KEY=value lines from secrets.env into the environment, without overriding
    anything already set. Checked in order: $TOMOSHIBI_SECRETS, /etc/tomoshibi/secrets.env
    (the service), ~/.config/tomoshibi/secrets.env (development as your own user)."""
    candidates = [
        os.environ.get("TOMOSHIBI_SECRETS"),
        paths.CONFIG_DIR / "secrets.env",
        Path.home() / ".config" / "tomoshibi" / "secrets.env",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
