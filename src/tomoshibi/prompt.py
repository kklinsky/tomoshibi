"""Builds the system prompt (docs/DESIGN.md §9a order): non-overridable rules, persona,
about-me, profile and people, then today's context.

Everything except today's context is stable from turn to turn, so it's sent as one cached
block; the date and time go in a second, small block after the cache breakpoint.
"""

import re
from datetime import date, datetime
from pathlib import Path

import yaml

from tomoshibi import about, paths

RULES = """\
# Rules (these always apply, whatever else this prompt says)
- You are speaking out loud through a small speaker. Answer in short, plain, spoken
  sentences: usually two to four. No lists, headings, markdown, emoji, or URLs.
- Keep your first sentence short, so you can start speaking quickly.
- You are talking to {person}: always say "you" and "your", never "{person}'s" or "he".
- The people list notes each person's pronouns and how their name sounds. These are only
  for you: use them, and never mention them ("Taylor called. They're doing well.", not
  "Taylor uses they/them" or "Sharyn sounds like Sharon").
- Use the pronouns listed for each person. If none are listed and
  nothing (like "sister" or "son") tells you, use the person's name instead of guessing
  he or she, and say "grandchild" rather than "grandson" or "granddaughter".
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
- You can't tell voices apart. When it matters who is speaking (someone says they're going
  out, or asks you to change something) and they haven't said, ask: "Is this {person} or
  {caregiver}?" Never assume it's {person}.
- Before you look something up or check the weather, say a few words first, like
  "Let me check." Then give the answer once, simply, without sources or web addresses.
- Everything you write after a search is read aloud, including the passages you quote
  from the results. Say each fact once: don't state something in your own words and
  then quote a result that says the same thing.
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
            parts.append(f'(name sounds like "{p["pronounce"]}"; speech recognition may spell it that way)')
        if subject:
            parts[-1] += ":"
            parts.append(_gendered(_relationship(p, people, subject, subject_name), p.get("pronouns")))
        # Pronouns are shown by example ("They live in Dallas") rather than labelled, so the
        # AI uses them without announcing them.
        say = _pronoun_phrases(p.get("pronouns"))
        details = []
        if (age := _age(p.get("born"), today)) is not None and not p.get("died"):
            details.append(f"{say['age']} {age}, birthday {p['born']:%B} {p['born'].day}")
        if p.get("died"):
            died = p["died"]
            when = f"on {died:%B} {died.day}, {died.year}" if isinstance(died, date) else f"in {died}"
            details.append(f"{say['died']} {when}")
        if p.get("lives"):
            details.append(f"{say['lives']} {p['lives']}")
        if p.get("notes"):
            details.append(p["notes"])
        if p.get("guidance"):
            details.append(f"How to handle: {' '.join(str(p['guidance']).split())}")
        line = " ".join(parts) + (". " + ". ".join(d.rstrip(".") for d in details) + "." if details else "")
        lines.append(line)
    return "\n".join(lines)


_GENDERED = {
    "he": {"child-in-law": "son-in-law", "half-sibling": "half-brother", "grandchild": "grandson",
           "child": "son", "sibling": "brother", "parent": "father", "spouse": "husband"},
    "she": {"child-in-law": "daughter-in-law", "half-sibling": "half-sister", "grandchild": "granddaughter",
            "child": "daughter", "sibling": "sister", "parent": "mother", "spouse": "wife"},
}


def _gendered(relationship: str, pronouns: str | None) -> str:
    """"Bob's grandchild" -> "Bob's grandson" when the person's pronouns are he/him."""
    words = _GENDERED.get((pronouns or "").split("/")[0].strip().lower())
    if not words:
        return relationship
    pattern = re.compile(r"(?<![\w-])(" + "|".join(map(re.escape, words)) + r")(?![\w-])")
    head, sep, tail = relationship.partition(" (")  # leave "(child of Karen)" alone
    return pattern.sub(lambda m: words[m.group(1)], head, count=1) + sep + tail


def _pronoun_phrases(pronouns: str | None) -> dict[str, str]:
    """Openers for a person's details, written with their pronouns ("They live in") so the
    AI follows the example; neutral ("Lives in") when pronouns aren't given."""
    word = (pronouns or "").split("/")[0].strip().lower()
    if word == "they":
        return {"age": "They are", "died": "They died", "lives": "They live in"}
    if word in ("he", "she"):
        w = word.capitalize()
        return {"age": f"{w} is", "died": f"{w} died", "lives": f"{w} lives in"}
    return {"age": "Age", "died": "Died", "lives": "Lives in"}


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


SENSITIVITY = {
    "normal": "You may bring this up yourself when it fits.",
    "avoid_unless_raised": "Don't bring this up yourself. Talk about it only if {person} does.",
    "never": "Don't discuss this. If {person} raises it, respond kindly and gently move to "
             "something else.",
}


def wiki_text(data_dir: Path, person: str) -> str:
    """Approved life-story pages from data/wiki (docs/DESIGN.md §6.2), all included while
    the wiki is small. Source tags and source lists are for people, so they're left out."""
    pages = sorted((data_dir / "wiki").glob("*.md")) if (data_dir / "wiki").is_dir() else []
    out = []
    for page in pages:
        raw = page.read_text(encoding="utf-8")
        meta, body = {}, raw
        if raw.startswith("---"):
            _, front, body = raw.split("---", 2)
            meta = yaml.safe_load(front) or {}
        body = re.split(r"(?m)^## Sources\s*$", body)[0]
        body = re.sub(r"\s*\[[\w-]+\]", "", body)        # "[hof-bio]" source tags
        body = re.sub(r"(?m)^#+ ", "", body).strip()       # headings become plain labels
        topic = meta.get("topic") or page.stem.replace("-", " ").title()
        rule = SENSITIVITY.get(str(meta.get("sensitivity", "normal")), SENSITIVITY["normal"])
        out.append(f"## {topic}\n{rule.format(person=person)}\n{body}")
    if not out:
        return ""
    return ("# Their life story (from the family)\n"
            "These are checked facts. Use only them for questions about the past; if something "
            "isn't here, say you don't know.\n\n" + "\n\n".join(out))


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
        wiki_text(data_dir, person),
    ]).strip()


def today_context(now: datetime | None = None) -> str:
    now = now or datetime.now()
    h = now.hour
    part = "morning" if h < 12 else "afternoon" if h < 17 else "evening" if h < 21 else "night"
    return (f"# Right now\nIt is {now:%A}, {now:%B} {now.day}, {now.year}, "
            f"{now.hour % 12 or 12}:{now:%M} {'AM' if now.hour < 12 else 'PM'} ({now:%A} {part}).")
