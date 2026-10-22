"""How names and words should sound, applied just before text-to-speech.

The text the AI writes (and the screen shows) keeps the real spelling; only the words sent
to the voice change. Sources:
- `pronounce:` on a person in people.yaml, e.g. Ami -> "Amy"
- data/pronunciations.yaml for anything else: {"Tommi": "Tommy", "Naples": "Nay-pulls"}
"""

import re
from pathlib import Path

import yaml


def _yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load(data_dir: Path) -> dict[str, str]:
    """written word -> how to say it."""
    words: dict[str, str] = {}
    for person in (_yaml(data_dir / "people.yaml").get("people") or []):
        say = person.get("pronounce")
        if not say:
            continue
        first = str(person.get("name", "")).split()[0] if person.get("name") else None
        for written in [first, *(person.get("called") or [])]:
            # Only plain one-word names; "your daughter" etc. are spoken as written.
            if written and " " not in written and written.lower() != say.lower():
                words[written] = say
    for written, say in (_yaml(data_dir / "pronunciations.yaml") or {}).items():
        words[str(written)] = str(say)
    return words


class Pronouncer:
    def __init__(self, words: dict[str, str]):
        self.words = {w.lower(): s for w, s in words.items()}
        self._pattern = (re.compile(r"\b(" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
                                    + r")\b", re.IGNORECASE) if words else None)

    def apply(self, text: str) -> str:
        if not self._pattern:
            return text
        return self._pattern.sub(lambda m: self.words[m.group(0).lower()], text)
