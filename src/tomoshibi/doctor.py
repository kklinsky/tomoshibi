"""`tomoshibi doctor`: plain-language checks of the device setup."""

import platform
import sys
from pathlib import Path

from tomoshibi import __version__, models, paths


def _line(ok: bool | str | None, label: str, detail: str = "") -> None:
    mark = {True: "OK  ", False: "FAIL", "warn": "WARN", None: "--  "}[ok]
    print(f"[{mark}] {label}{': ' + detail if detail else ''}")


def _read(path: str) -> str:
    try:
        return Path(path).read_text(errors="replace").replace("\0", "").strip()
    except OSError:
        return ""


def run(lock_path: Path) -> int:
    print(f"Tomoshibi {__version__} on Python {platform.python_version()}\n")
    failures = warnings = 0

    board = _read("/proc/device-tree/model")
    _line(board.startswith("Raspberry Pi 5") if board else None, "Board", board or "not a Pi")

    try:
        specs = models.load_lock(lock_path)
        _line(True, "models.lock", str(lock_path))
    except OSError as e:
        _line(False, "models.lock", str(e))
        specs, failures = [], failures + 1
    for spec in specs:
        present = spec.is_present()
        failures += not present
        _line(present, f"Model {spec.name}", str(spec.local_dir()) if present else "missing")

    cards = _read("/proc/asound/cards")
    usb_audio = "USB" in cards
    warnings += bool(cards) and not usb_audio
    _line((usb_audio or "warn") if cards else None, "USB speakerphone",
          "found" if usb_audio else "not found (plug in the Jabra)")

    spi = sorted(str(p) for p in Path("/dev").glob("spidev*"))
    _line(bool(spi) if board else None, "SPI (screen)",
          ", ".join(spi) if spi else "not enabled (needs reboot after install)")

    for name in ("config.yaml", "secrets.env"):
        path = paths.CONFIG_DIR / name
        _line(path.exists() or None, name, str(path) if path.exists() else "not found")

    data = paths.data_dir()
    _line(data.is_dir() or None, "Data directory", str(data))

    print()
    if failures or warnings:
        print(f"{failures} problem(s), {warnings} warning(s).")
    else:
        print("No problems found.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run(paths.default_models_lock()))
