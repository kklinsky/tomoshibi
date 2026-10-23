"""Speaker volume, through ALSA's mixer on the speakerphone ("louder, please").

Exposed to the AI as the `adjust_volume` tool. The level never goes below a floor, so a
misheard "quieter" can't make Tomo silent, and it's saved so it survives a restart.
"""

import json
import re
import subprocess
from pathlib import Path

from tomoshibi import paths
from tomoshibi.tools import Tool

CONTROL = "PCM"
STEPS = {"louder": 1, "much_louder": 3, "quieter": -1, "much_quieter": -3}


def card_from_device(device: str) -> str:
    """"plughw:CARD=USB" -> "USB"; "plughw:2,0" -> "2"."""
    if m := re.search(r"CARD=([^,]+)", device):
        return m.group(1)
    if m := re.search(r":(\d+)", device):
        return m.group(1)
    return "default"


def parse(amixer_output: str) -> tuple[int, int, int, bool]:
    """(level, min, max, switched_on) from `amixer sget` output."""
    lo, hi = (int(x) for x in re.search(r"Limits: Playback (\d+) - (\d+)", amixer_output).groups())
    level = int(re.search(r"Playback (\d+) \[\d+%\]", amixer_output).group(1))
    on = "[off]" not in amixer_output
    return level, lo, hi, on


def state_file() -> Path:
    """Where the chosen level is remembered: the service's state dir, or (running as
    yourself during development) ~/.local/state/tomoshibi."""
    for base in (paths.STATE_DIR, Path.home() / ".local" / "state" / "tomoshibi"):
        try:
            base.mkdir(parents=True, exist_ok=True)
            probe = base / "device-state.json"
            probe.touch(exist_ok=True)
            return probe
        except OSError:
            continue
    return Path("device-state.json")


class Volume:
    def __init__(self, device: str, floor_percent: int = 25, run=subprocess.run):
        self.card = card_from_device(device)
        self.floor_percent = floor_percent
        self._run = run

    def _amixer(self, *args: str) -> str:
        out = self._run(["amixer", "-c", self.card, *args], capture_output=True, text=True, check=True)
        return out.stdout

    def read(self) -> tuple[int, int, int, bool]:
        return parse(self._amixer("sget", CONTROL))

    def percent(self, level: int, lo: int, hi: int) -> int:
        return round(100 * (level - lo) / (hi - lo)) if hi > lo else 100

    def _floor(self, lo: int, hi: int) -> int:
        return lo + -(-(hi - lo) * self.floor_percent // 100)  # ceiling division

    def set_level(self, level: int) -> dict:
        _, lo, hi, _ = self.read()
        level = max(self._floor(lo, hi), min(hi, level))
        self._amixer("sset", CONTROL, str(level), "unmute")
        self._remember(level)
        return {"level": level, "percent": self.percent(level, lo, hi),
                "at_loudest": level == hi, "at_quietest_allowed": level == self._floor(lo, hi)}

    def change(self, how: str) -> dict:
        level, lo, hi, _ = self.read()
        if how == "loudest":
            target = hi
        elif how == "quietest":
            target = self._floor(lo, hi)
        else:
            target = level + STEPS[how]
        return self.set_level(target)

    def restore(self) -> None:
        """Put back the level chosen last time, if one was saved."""
        try:
            saved = json.loads(state_file().read_text() or "{}").get("volume_level")
        except (OSError, ValueError):
            return
        if isinstance(saved, int):
            self.set_level(saved)

    def _remember(self, level: int) -> None:
        path = state_file()
        try:
            data = json.loads(path.read_text() or "{}")
        except (OSError, ValueError):
            data = {}
        data["volume_level"] = level
        try:
            path.write_text(json.dumps(data))
        except OSError:
            pass

    def tool(self) -> Tool:
        def run(args: dict) -> str:
            try:
                return json.dumps(self.change(args["change"]))
            except (OSError, subprocess.CalledProcessError, AttributeError, ValueError) as e:
                return json.dumps({"error": f"Couldn't change the volume ({e})."})

        return Tool(
            name="adjust_volume",
            description=(
                "Make your voice louder or quieter. Use it when someone asks you to speak up, "
                "turn it up or down, or says they can't hear you. 'much_' is for 'a lot'. "
                "After changing it, say something short so they can hear the new level."
            ),
            input_schema={
                "type": "object",
                "properties": {"change": {"type": "string", "enum": [
                    "louder", "much_louder", "quieter", "much_quieter", "loudest", "quietest"]}},
                "required": ["change"],
                "additionalProperties": False,
            },
            run=run,
        )
