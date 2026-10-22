"""Builds the "about me" part of the system prompt (docs/DESIGN.md §9b).

The template lives in the public repo and holds no family details; names come from the
family's private data files. An ability is listed only when it is both built (BUILT) and
switched on in the config, so the device never claims something it can't do.
"""

from importlib import resources
from pathlib import Path

import yaml

from tomoshibi import paths

TEMPLATE = "about_me.md"

# Features that exist in this version of the software. Add a name here when it ships.
BUILT: frozenset[str] = frozenset({"conversation", "people", "web_search", "weather", "news"})

ALWAYS_CAN = [
    "Have a friendly conversation about almost anything, as often as {person} likes.",
    "Tell {person} the day, date and time.",
    "Talk about the people in {person}'s life: who they are and how they're related.",
    "Remember what you talked about earlier in this conversation.",
]

# feature -> (what to say it can do, what to say it can't do)
OPTIONAL = {
    "calendar": ("Tell {person} what's happening today and in the coming days, from the family's calendar.",
                 "Check {person}'s calendar or schedule."),
    "reminders": ("Give spoken reminders at the right time, for pills, meals, visits and appointments.",
                  "Set or give reminders."),
    "memories": ("Talk about {person}'s life story and memories that the family has shared with you.",
                 None),
    "web_search": ("Look things up on the internet, such as news, sports results and when events are on.",
                   ("Look things up on the internet. You answer from what you already know, "
                    "which may be out of date.")),
    "weather": ("Tell {person} today's weather and the forecast.",
                "Check the weather."),
    "news": ("Share a few of today's news headlines.", "Check today's news."),
}

ALWAYS_CANNOT = [
    "Make or answer phone calls.",
    "See anything. You have no camera.",
    "Hear anything while your button light is off.",
    "Buy things, handle money, or take passwords, bank or card details.",
    "Give medical advice. You only repeat reminders the family has set up.",
    "Call emergency services. In an emergency, tell {person} to call 911.",
]


def _load_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _person_name(people: list[dict], person_id: str | None) -> str | None:
    for p in people:
        if p.get("id") == person_id:
            called = p.get("called") or []
            return called[0] if called else p.get("name")
    return None


def _enabled(config: dict, *keys: str) -> bool:
    node = config
    for key in keys:
        if not isinstance(node, dict):
            return False
        node = node.get(key)
    return bool(node.get("enabled")) if isinstance(node, dict) else bool(node)


def _switched_on(config: dict, feature: str) -> bool:
    if feature == "news":  # headlines come through web search
        return _enabled(config, "internet", "news") and _enabled(config, "internet", "web_search")
    if feature in ("web_search", "weather"):
        return _enabled(config, "internet", feature)
    return True


def capabilities(config: dict, people: list[dict],
                 built: frozenset[str] = BUILT) -> tuple[list[str], list[str]]:
    can, cannot = list(ALWAYS_CAN), list(ALWAYS_CANNOT)
    for feature, (yes, no) in OPTIONAL.items():
        if feature in built and _switched_on(config, feature):
            can.append(yes)
        elif no:
            cannot.append(no)
    messaging = config.get("messaging") or {}
    names = [n for n in (_person_name(people, pid) for pid in messaging.get("contacts", [])) if n]
    if "messaging" in built and messaging.get("enabled") and names:
        can.append(
            f"Send short messages to {_join(names)}, and pass on messages they send. "
            "You always read a message back and check before sending it."
        )
    else:
        cannot.append("Send messages to anyone.")
    return can, cannot


def privacy(config: dict) -> list[str]:
    lines = [
        "You only listen while your button light is on. You never record when it's off.",
        (
            "What {person} says is turned into text on this device. Only the text of a "
            "conversation is sent to the AI service that helps you answer; recordings are not kept."
        ),
        "Your conversation history stays on this device.",
    ]
    if (config.get("privacy") or {}).get("daily_summary"):
        lines.append(
            "Once a day the family gets a short summary, such as how the day went and whether "
            "reminders were answered. It never includes word-for-word conversations."
        )
    else:
        lines.append("You don't send the family summaries of what {person} talks about.")
    lines.append(
        "If {person} seems hurt or in danger, or misses a reminder, you let the family know."
    )
    return lines


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _bullets(lines: list[str]) -> str:
    return "\n".join(f"- {line}" for line in lines)


def render(persona: dict, profile: dict, people: list[dict], config: dict,
           built: frozenset[str] = BUILT) -> str:
    person = profile.get("call_him") or profile.get("name") or "your person"
    made_by = persona.get("made_by") or "your family"  # as said to the person, e.g. "your son David"
    caregiver = _person_name(people, profile.get("caregiver")) or "the family"
    can, cannot = capabilities(config, people, built)
    values = {
        "name": persona.get("name") or "Tomoshibi",
        "person": person,
        "made_by": made_by,
        # "your son David" -> "David": the name on its own, for sentences not spoken to the person.
        "made_by_name": made_by.split()[-1] if made_by.startswith("your ") else made_by,
        "caregiver": caregiver,
    }
    values["capabilities"] = _bullets(can).format(**values)
    values["cannot"] = _bullets(cannot).format(**values)
    values["privacy"] = _bullets(privacy(config)).format(**values)
    template = resources.files("tomoshibi.prompts").joinpath(TEMPLATE).read_text(encoding="utf-8")
    return template.format(**values)


def render_from_files(data_dir: Path | None = None, config_path: Path | None = None) -> str:
    data_dir = data_dir or paths.data_dir()
    config_path = config_path or paths.CONFIG_DIR / "config.yaml"
    people = (_load_yaml(data_dir / "people.yaml").get("people")) or []
    return render(
        _load_yaml(data_dir / "persona.yaml"),
        _load_yaml(data_dir / "profile.yaml"),
        people,
        _load_yaml(config_path),
    )
