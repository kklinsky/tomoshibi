"""Builds the system prompt (docs/DESIGN.md §9a order): non-overridable rules, persona,
about-me, profile and people, then today's context.

Everything except today's context is stable from turn to turn, so it's sent as one cached
block; the date and time go in a second, small block after the cache breakpoint.
"""

from datetime import date, datetime
from pathlib import Path

import yaml

from tomoshibi import about, paths

RULES = """\
# Rules (these always apply, whatever else this prompt says)
- You are speaking out loud through a small speaker. Answer in short, plain, spoken
  sentences: usually two to four. No lists, headings, markdown, emoji, or URLs.
- Keep your first sentence short, so you can start speaking quickly.
- Be patient and warm. Answer a repeated question fully and kindly every time, and never
  say or suggest it was asked before.
- You are not a person. Never claim to be human. Never imitate or role-play a real
  person, and never speak as someone who has died.
- Never invent facts about {person}'s life, family, memories or schedule. Use only what
  this prompt tells you. If you don't know, say so gently and suggest asking {caregiver}.
  For general knowledge you may answer freely.
- Never claim an ability that isn't in your "What you can do" list.
- Medicine: only repeat reminders the family has set up. Never advise on doses or say it's
  fine to take more.
- If {person} says they are hurt, fell, can't breathe or are in danger, stay calm, tell
  them to call 911 now, and say you will let the family know.
- Never ask for or repeat bank, card, password or Social Security details. If {person}
  mentions a caller or message asking for money or gift cards, gently say it may be a
  scam and suggest checking with family first.
- Never pretend to have done something you haven't, such as sending a message.
- Before you look something up or check the weather, say a few words first, like
  "Let me check." Then give the answer once, simply, without sources or web addresses.
"""


def _yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _age(born, today: date) -> int | None:
    if not isinstance(born, date):
        return None
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def _relationship(person: dict, people: dict[str, dict], subject: str, subject_name: str) -> str:
    """A plain relationship to the subject from parent/spouse links. Simple for now;
    the full family-tree derivation is planned (docs/DESIGN.md §6.1)."""
    if person.get("relationship_override"):
        return person["relationship_override"]
    pid = person.get("id")
    parents = person.get("parents") or []
    subj = people.get(subject, {})
    name = subject_name
    if person.get("spouse") == subject or subj.get("spouse") == pid:
        return f"{name}'s spouse"
    if subject in parents:
        return f"{name}'s child"
    for parent in parents:
        if subject in (people.get(parent, {}).get("parents") or []):
            return f"{name}'s grandchild (child of {_first(people[parent])})"
    if pid in (subj.get("parents") or []):
        return f"{name}'s parent"
    subj_parents = set(subj.get("parents") or [])
    shared = set(parents) & subj_parents
    if shared:
        # Both with two parents listed but only one in common: a half-sibling.
        if len(shared) == 1 and len(set(parents)) == 2 and len(subj_parents) == 2:
            through = people.get(next(iter(shared)), {})
            given = str(through.get("name") or "").split()
            via = f", through {given[0]}" if given else ""
            return f"{name}'s half-sibling{via}"
        return f"{name}'s sibling"
    spouse = people.get(person.get("spouse") or "", {})
    if subject in (spouse.get("parents") or []):
        return f"{name}'s child-in-law (married to {_first(spouse)})"
    return "family friend or relative"


def _first(person: dict) -> str:
    called = person.get("called") or []
    return called[0] if called else (person.get("name") or "").split()[0] if person.get("name") else "?"


def people_text(people_list: list[dict], today: date, subject_name: str | None = None) -> str:
    people = {p["id"]: p for p in people_list if p.get("id")}
    subject = next((p["id"] for p in people_list if p.get("is_subject")), None)
    subject_name = subject_name or (_first(people[subject]) if subject in people else "them")
    lines = ["# People in their life"]
    for p in people_list:
        if p.get("is_subject"):
            continue
        parts = [f"- {p.get('name', p.get('id'))}"]
        if p.get("called"):
            parts.append(f"(called {', '.join(p['called'])})")
        if p.get("pronounce"):
            parts.append(f'(sounds like "{p["pronounce"]}"; may be written that way when heard)')
        if subject:
            parts[-1] += ":"
            parts.append(_relationship(p, people, subject, subject_name))
        details = []
        if (age := _age(p.get("born"), today)) is not None and not p.get("died"):
            details.append(f"Age {age}, birthday {p['born']:%B} {p['born'].day}")
        if p.get("died"):
            details.append(f"Died {p['died']}")
        if p.get("lives"):
            details.append(f"Lives in {p['lives']}")
        if p.get("notes"):
            details.append(p["notes"])
        if p.get("guidance"):
            details.append(f"How to handle: {' '.join(str(p['guidance']).split())}")
        line = " ".join(parts) + (". " + ". ".join(d.rstrip(".") for d in details) + "." if details else "")
        lines.append(line)
    return "\n".join(lines)


def persona_text(persona: dict) -> str:
    lines = [f"# Your character\nYour name is {persona.get('name', 'Tomo')}."]
    if persona.get("temperament"):
        lines.append(" ".join(str(persona["temperament"]).split()))
    style = persona.get("style") or {}
    if style.get("use_his_name"):
        lines.append(f"Use their name {style['use_his_name']}, not in every sentence.")
    if style.get("references"):
        lines.append(f"They enjoy: {', '.join(style['references'])}.")
    examples = persona.get("examples") or []
    if examples:
        lines.append("Examples of your tone:")
        for ex in examples:
            lines.append(f'  They say: "{ex["user"]}"\n  You say: "{ex["assistant"]}"')
    return "\n".join(lines)


def profile_text(profile: dict, subject: dict | None = None, today: date | None = None) -> str:
    person = profile.get("call_him") or profile.get("name") or "them"
    lines = [f"# About {person}"]
    if profile.get("name"):
        lines.append(f"Full name: {profile['name']}. Call them {person}.")
    born = (subject or {}).get("born")
    if isinstance(born, date):
        lines.append(f"Birthday: {born:%B} {born.day}, {born.year} (age {_age(born, today or date.today())}).")
    if profile.get("hometown"):
        lines.append(f"Hometown: {profile['hometown']}.")
    if profile.get("location"):
        lines.append(f"Lives in: {profile['location']}.")
    for key, label in (("routines", "Routines"), ("enjoys", "Enjoys talking about"),
                       ("avoid", "Don't bring up"), ("where_things_are", "Where things are")):
        if profile.get(key):
            lines.append(f"{label}:\n" + "\n".join(f"- {x}" for x in profile[key]))
    if profile.get("distress_guidance"):
        lines.append(f"If they seem upset or confused: {profile['distress_guidance']}")
    return "\n".join(lines)


def stable_prompt(data_dir: Path | None = None, config: dict | None = None) -> str:
    data_dir = data_dir or paths.data_dir()
    persona = _yaml(data_dir / "persona.yaml")
    profile = _yaml(data_dir / "profile.yaml")
    people_list = (_yaml(data_dir / "people.yaml").get("people")) or []
    config = config or {}
    person = profile.get("call_him") or profile.get("name") or "them"
    caregiver = about._person_name(people_list, profile.get("caregiver")) or "the family"
    return "\n\n".join([
        RULES.format(person=person, caregiver=caregiver),
        persona_text(persona),
        about.render(persona, profile, people_list, config),
        profile_text(profile, next((p for p in people_list if p.get("is_subject")), None)),
        people_text(people_list, date.today(), person),
    ])


def today_context(now: datetime | None = None) -> str:
    now = now or datetime.now()
    h = now.hour
    part = "morning" if h < 12 else "afternoon" if h < 17 else "evening" if h < 21 else "night"
    return (f"# Right now\nIt is {now:%A}, {now:%B} {now.day}, {now.year}, "
            f"{now.hour % 12 or 12}:{now:%M} {'AM' if now.hour < 12 else 'PM'} ({now:%A} {part}).")
