"""How names and words should sound, applied just before text-to-speech.

The text the AI writes (and the screen shows) keeps the real spelling; only the words sent
to the voice change. Sources:
- `pronounce:` on a person in people.yaml: how their first name sounds, e.g. Ami -> "Amy"
- data/pronunciations.yaml for anything else, including nicknames:
  {"Tommi": "Tommy", "Naples": "Nay-pulls"}
"""

import json
import os
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
        # `pronounce` is how the first name sounds. Other names in `called` (nicknames,
        # "your wife") are different words, so they stay as written unless listed in
        # pronunciations.yaml.
        first = str(person.get("name", "")).split()[0] if person.get("name") else ""
        if first and first.lower() != say.lower():
            words[first] = say
    for written, say in (_yaml(data_dir / "pronunciations.yaml") or {}).items():
        words[str(written)] = str(say)
    return words


# Words spelled the same but said differently depending on use (homographs), which the
# voice guesses wrong in Tomo's everyday sentences. Applied for every family, before their
# own pronunciations. "Taylor lives in Dallas" was said "lyvz", like "nine lives".
_PLACE = (r"in|on|at|near|nearby|with|by|alone|there|here|next|close|just|about|outside|"
          r"across|around|over|up|down|far|together|abroad|downtown|upstairs|downstairs|"
          r"somewhere|anywhere|right|still|now|only|mostly")
_AUX = r"does|do|did|to|can|will|would|could|should|might|must|don't|doesn't|didn't"
HOMOGRAPHS = [
    # "lives in / near / with ..." is the verb: livz
    (re.compile(rf"\b(L|l)ives(?=\s+(?:{_PLACE})\b)"), r"\1ivs"),
    # "where does Ami live?", "wants to live" is the verb: liv
    (re.compile(rf"\b((?:{_AUX})\s+(?:[\w']+\s+){{0,1}})(L|l)ive\b", re.IGNORECASE), r"\1\2iv"),
]


# US radio and TV call letters (WHEC, WVIT, KMOX) are spelled out, not read as words
# ("WHEC" came out as "wek"). Optional -TV/-FM/-AM suffixes are spelled too.
CALL_LETTERS = re.compile(r"\b([KW][A-Z]{2,3})(?:-(TV|FM|AM))?\b")


def _spell(match: re.Match) -> str:
    letters = " ".join(match.group(1))
    return f"{letters} {' '.join(match.group(2))}" if match.group(2) else letters


def fix_homographs(text: str) -> str:
    for pattern, replacement in HOMOGRAPHS:
        text = pattern.sub(replacement, text)
    return CALL_LETTERS.sub(_spell, text)


# Words every Tomo should say right. A family's own pronunciations take precedence.
BUILTIN_WORDS = {
    "Tomoshibi": "Toemoe-sheebee",  # toh-moh-shee-bee, not "TAH-muh-shih-buy"
}


class Pronouncer:
    def __init__(self, words: dict[str, str]):
        words = {**BUILTIN_WORDS, **words}
        self.words = {w.lower(): s for w, s in words.items()}
        self._pattern = (re.compile(r"\b(" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
                                    + r")\b", re.IGNORECASE) if words else None)

    def apply(self, text: str) -> str:
        text = fix_homographs(text)
        if not self._pattern:
            return text
        return self._pattern.sub(lambda m: self.words[m.group(0).lower()], text)


# --- Editing, for the setup page's pronunciation tester ------------------------------------
# Edits change single lines so the family's hand-written files keep their comments and
# layout; each result is checked as valid YAML before it replaces the file.


def entries(data_dir: Path) -> list[dict]:
    """Current pronunciations: {"word", "say", "where": "people.yaml"|"pronunciations.yaml"}."""
    out = []
    for person in (_yaml(data_dir / "people.yaml").get("people") or []):
        if person.get("pronounce") and person.get("name"):
            out.append({"word": str(person["name"]).split()[0], "say": str(person["pronounce"]),
                        "where": "people.yaml", "person": person.get("name")})
    for word, say in (_yaml(data_dir / "pronunciations.yaml") or {}).items():
        out.append({"word": str(word), "say": str(say), "where": "pronunciations.yaml"})
    return sorted(out, key=lambda e: e["word"].lower())


def _write_checked(path: Path, text: str) -> None:
    yaml.safe_load(text)  # raises if the edit broke the file; nothing is written then
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    if path.exists():
        path.with_suffix(path.suffix + ".bak").write_bytes(path.read_bytes())
    os.replace(tmp, path)


def _person_block(lines: list[str], word: str) -> tuple[int, int] | None:
    """Line range of the people.yaml entry whose first name is `word`."""
    starts = [i for i, line in enumerate(lines) if line.lstrip().startswith("- id:")]
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        for line in lines[start:end]:
            stripped = line.strip()
            if stripped.startswith("name:"):
                name = yaml.safe_load(stripped[len("name:"):]) or ""
                if str(name).split() and str(name).split()[0].lower() == word.lower():
                    return start, end
    return None


def save(data_dir: Path, word: str, say: str) -> str:
    """Set how `word` sounds. Returns the file it was saved in."""
    word, say = word.strip(), say.strip()
    if not word or not say or "\n" in word + say:
        raise ValueError("word and pronunciation must be filled in, on one line")
    people_path = data_dir / "people.yaml"
    if people_path.is_file():
        lines = people_path.read_text(encoding="utf-8").splitlines()
        block = _person_block(lines, word)
        if block:
            start, end = block
            line = f"    pronounce: {json.dumps(say)}"
            for i in range(start, end):
                if lines[i].strip().startswith("pronounce:"):
                    lines[i] = line
                    break
            else:
                # Insert after `called:` if there is one, otherwise after `name:`.
                keys = {lines[i].strip().split(":", 1)[0]: i for i in range(start, end)}
                lines.insert(keys.get("called", keys["name"]) + 1, line)
            _write_checked(people_path, "\n".join(lines) + "\n")
            return "people.yaml"
    path = data_dir / "pronunciations.yaml"
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else [
        "# How words should sound when Tomo speaks them. One per line:  written: how it sounds"]
    entry = f"{json.dumps(word)}: {json.dumps(say)}"
    for i, line in enumerate(lines):
        if not line.lstrip().startswith("#") and ":" in line:
            key = yaml.safe_load(line.split("#", 1)[0] or "{}") or {}
            if isinstance(key, dict) and str(next(iter(key), "")).lower() == word.lower():
                lines[i] = entry
                break
    else:
        lines.append(entry)
    _write_checked(path, "\n".join(lines) + "\n")
    return "pronunciations.yaml"


def remove(data_dir: Path, word: str) -> bool:
    """Remove a pronunciation (from either file). Returns whether one was found."""
    found = False
    people_path = data_dir / "people.yaml"
    if people_path.is_file():
        lines = people_path.read_text(encoding="utf-8").splitlines()
        block = _person_block(lines, word)
        if block:
            kept = [line for i, line in enumerate(lines)
                    if not (block[0] <= i < block[1] and line.strip().startswith("pronounce:"))]
            if len(kept) != len(lines):
                _write_checked(people_path, "\n".join(kept) + "\n")
                found = True
    path = data_dir / "pronunciations.yaml"
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()
        kept = []
        for line in lines:
            key = None
            if not line.lstrip().startswith("#") and ":" in line:
                parsed = yaml.safe_load(line.split("#", 1)[0] or "{}")
                key = str(next(iter(parsed), "")) if isinstance(parsed, dict) else None
            if key is not None and key.lower() == word.lower():
                found = True
                continue
            kept.append(line)
        if len(kept) != len(lines):
            _write_checked(path, "\n".join(kept) + "\n")
    return found
