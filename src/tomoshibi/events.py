"""Events and reminders (docs/DESIGN.md §4 use case 2, §7).

Two sources, both on the device so everything works offline:
- data/events.yaml, written by the family (and kept in their private data repo), e.g.

    events:
      - id: morning-pills
        title: Morning pills
        time: "08:00"
        repeat: daily              # daily | weekdays | weekly | monthly | yearly,
                                   # or a list of days: [mon, thu]
        say: "It's time for your morning pills. They're in the blue box by the sink."
        protected: true            # can't be changed or cancelled by voice
      - id: dentist
        title: Dentist
        date: 2026-10-27
        time: "14:00"
        remind_before: [60, 0]     # minutes before; default [0]

- events added by voice, kept in data/tomoshibi.db (SQLite) along with reminder state:
  which occurrences were acknowledged, snoozed or missed.

Birthdays and anniversaries come from people.yaml and appear in the schedule.
"""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path

import yaml

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
RETRY_MINUTES = 5
MAX_ATTEMPTS = 3  # the reminder itself, then two retries


@dataclass(frozen=True)
class Event:
    id: str
    title: str
    at: time | None                 # None for all-day
    start: date                     # first (or only) date
    repeat: str | tuple = "none"    # "none" | "daily" | "weekdays" | "weekly" | "monthly" | "yearly" | days tuple
    say: str = ""
    remind_before: tuple[int, ...] = (0,)
    protected: bool = False
    source: str = "events.yaml"
    end: date | None = None         # last date for repeating events

    def occurs_on(self, day: date) -> bool:
        if day < self.start or (self.end and day > self.end):
            return False
        r = self.repeat
        if r == "none":
            return day == self.start
        if r == "daily":
            return True
        if r == "weekdays":
            return day.weekday() < 5
        if r == "weekly":
            return day.weekday() == self.start.weekday()
        if r == "monthly":
            return day.day == self.start.day
        if r == "yearly":
            return (day.month, day.day) == (self.start.month, self.start.day)
        if isinstance(r, tuple):
            return DAYS[day.weekday()] in r
        return False


@dataclass(frozen=True, order=True)
class Occurrence:
    when: datetime                  # midnight for all-day
    event: Event = field(compare=False)
    all_day: bool = field(default=False, compare=False)

    @property
    def key(self) -> str:
        return f"{self.event.id}@{self.when.isoformat(timespec='minutes')}"

    def describe(self) -> dict:
        d = {"title": self.event.title, "date": self.when.strftime("%A, %B ") + str(self.when.day)}
        if not self.all_day:
            d["time"] = self.when.strftime("%I:%M %p").lstrip("0")
        if self.event.repeat != "none":
            d["repeats"] = self.event.repeat if isinstance(self.event.repeat, str) else ", ".join(self.event.repeat)
        return d


def _parse_time(value) -> time | None:
    if value in (None, ""):
        return None
    if isinstance(value, int):  # YAML reads 08:00 unquoted as minutes since midnight
        return time(value // 60, value % 60)
    text = str(value).strip().lower().replace(".", "")
    for fmt in ("%H:%M", "%I:%M %p", "%I %p", "%I:%M%p", "%I%p"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"can't read the time {value!r}; use e.g. \"08:00\" or \"2:30 pm\"")


def _parse_repeat(value):
    if value in (None, "", "none", "once"):
        return "none"
    if isinstance(value, list):
        days = tuple(str(d).strip().lower()[:3] for d in value)
        bad = [d for d in days if d not in DAYS]
        if bad:
            raise ValueError(f"unknown day(s) {bad}; use mon, tue, wed, thu, fri, sat, sun")
        return days
    value = str(value).strip().lower()
    if value not in ("daily", "weekdays", "weekly", "monthly", "yearly"):
        raise ValueError(f"unknown repeat {value!r}")
    return value


def _event_from(entry: dict, source: str, today: date) -> Event:
    when = entry.get("date") or entry.get("starts")
    start = when if isinstance(when, date) else (date.fromisoformat(str(when)) if when else today)
    end = entry.get("until")
    return Event(
        id=str(entry["id"]),
        title=str(entry.get("title") or entry["id"]),
        at=_parse_time(entry.get("time")),
        start=start,
        repeat=_parse_repeat(entry.get("repeat")),
        say=str(entry.get("say") or "").strip(),
        remind_before=tuple(int(m) for m in (entry.get("remind_before") or [0])),
        protected=bool(entry.get("protected")),
        source=source,
        end=end if isinstance(end, date) else (date.fromisoformat(str(end)) if end else None),
    )


class Events:
    def __init__(self, data_dir: Path, db_path: Path | None = None):
        self.data_dir = data_dir
        self.db = sqlite3.connect(db_path or data_dir / "tomoshibi.db", check_same_thread=False)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS voice_events (id TEXT PRIMARY KEY, data TEXT NOT NULL,
                created TEXT NOT NULL, cancelled INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS reminders (key TEXT PRIMARY KEY, state TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0, last_attempt TEXT, snooze_until TEXT,
                updated TEXT NOT NULL);
        """)
        self.db.commit()

    # --- events ------------------------------------------------------------------------
    def all(self, today: date | None = None) -> list[Event]:
        today = today or date.today()
        events = []
        path = self.data_dir / "events.yaml"
        if path.is_file():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for entry in data.get("events") or []:
                events.append(_event_from(entry, "events.yaml", today))
        for (data,) in self.db.execute("SELECT data FROM voice_events WHERE cancelled = 0"):
            events.append(_event_from(json.loads(data), "voice", today))
        return events

    def add(self, title: str, day: date, at: time | None, repeat="none", say: str = "",
            remind_before=(0,)) -> Event:
        base = "".join(c if c.isalnum() else "-" for c in title.lower()).strip("-")[:30] or "event"
        event_id = f"voice-{base}-{day.isoformat()}"
        entry = {"id": event_id, "title": title, "date": day.isoformat(),
                 "time": at.strftime("%H:%M") if at else None,
                 "repeat": list(repeat) if isinstance(repeat, tuple) else repeat,
                 "say": say, "remind_before": list(remind_before)}
        event = _event_from(entry, "voice", day)  # validates
        self.db.execute("INSERT OR REPLACE INTO voice_events (id, data, created) VALUES (?, ?, ?)",
                        (event_id, json.dumps(entry), datetime.now().isoformat(timespec="seconds")))
        self.db.commit()
        return event

    # --- schedule ----------------------------------------------------------------------
    def occurrences(self, start: date, days: int, today: date | None = None) -> list[Occurrence]:
        out = []
        events = self.all(today)
        for n in range(days):
            day = start + timedelta(days=n)
            for e in events:
                if e.occurs_on(day):
                    out.append(Occurrence(datetime.combine(day, e.at or time(0)), e, all_day=e.at is None))
        return sorted(out)

    def schedule(self, start: date, days: int, people: list[dict] | None = None,
                 person: str = "") -> list[dict]:
        """Events plus birthdays and anniversaries, for the AI to read."""
        items = [o.describe() for o in self.occurrences(start, days)]
        for day_offset in range(days):
            day = start + timedelta(days=day_offset)
            for note in special_days(people or [], day, person):
                items.append({"title": note, "date": day.strftime("%A, %B ") + str(day.day)})
        return items

    # --- reminders -----------------------------------------------------------------------
    # Each lead time is its own reminder: with remind_before [60, 0], "OK" to the heads-up an
    # hour before doesn't cancel the one at the time. Only the at-the-time reminder retries.
    def due(self, now: datetime) -> list["Reminder"]:
        """Reminders that should be given now, including retries and finished snoozes."""
        out = []
        for occ in self.occurrences(now.date() - timedelta(days=1), 2):
            if occ.all_day:
                continue
            for lead in sorted(set(occ.event.remind_before), reverse=True):
                rem = Reminder(occ, lead)
                fire_at = occ.when - timedelta(minutes=lead)
                last_chance = occ.when + timedelta(hours=2) if lead == 0 else occ.when
                if not (fire_at <= now <= last_chance):
                    continue
                state, attempts, last, snooze = self._row(rem.key)
                if state in ("acknowledged", "missed"):
                    continue
                if state == "snoozed":
                    if snooze and now >= datetime.fromisoformat(snooze):
                        out.append(rem)
                    continue
                limit = MAX_ATTEMPTS if lead == 0 else 1
                if attempts >= limit:
                    continue
                if attempts and last and now < datetime.fromisoformat(last) + timedelta(minutes=RETRY_MINUTES):
                    continue
                out.append(rem)
        return sorted(out, key=lambda r: (r.occurrence.when, -r.lead))

    def _row(self, key: str):
        row = self.db.execute("SELECT state, attempts, last_attempt, snooze_until FROM reminders "
                              "WHERE key = ?", (key,)).fetchone()
        return row if row else ("pending", 0, None, None)

    def record(self, rem: "Reminder", state: str, now: datetime, snooze_minutes: int = 0) -> str:
        """state: "attempted" (spoken, no reply yet), "acknowledged" or "snoozed".
        Returns the stored state ("missed" once the last retry goes unanswered)."""
        _, attempts, _, _ = self._row(rem.key)
        if state == "attempted":
            attempts += 1
            limit = MAX_ATTEMPTS if rem.lead == 0 else 1
            state = "missed" if attempts >= limit else "pending"
        snooze = (now + timedelta(minutes=snooze_minutes)).isoformat() if state == "snoozed" else None
        self.db.execute(
            "INSERT INTO reminders (key, state, attempts, last_attempt, snooze_until, updated) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET state=excluded.state, "
            "attempts=excluded.attempts, last_attempt=excluded.last_attempt, "
            "snooze_until=excluded.snooze_until, updated=excluded.updated",
            (rem.key, state, attempts, now.isoformat(), snooze, now.isoformat()))
        self.db.commit()
        return state

    def state(self, rem: "Reminder") -> str:
        return self._row(rem.key)[0]


@dataclass(frozen=True)
class Reminder:
    occurrence: Occurrence
    lead: int  # minutes before the event

    @property
    def key(self) -> str:
        return f"{self.occurrence.key}#{self.lead}"

def special_days(people: list[dict], day: date, person: str) -> list[str]:
    """Birthdays and wedding anniversaries on `day`, from people.yaml."""
    notes = []
    for p in people:
        name = (p.get("called") or [None])[0] or str(p.get("name", "")).split(" ")[0]
        born = p.get("born")
        if isinstance(born, date) and (born.month, born.day) == (day.month, day.day) and not p.get("died"):
            whose = "your" if p.get("is_subject") else f"{name}'s"
            notes.append(f"{whose.capitalize() if whose == 'your' else whose} birthday "
                         f"(turning {day.year - born.year})")
        married = p.get("married")
        if isinstance(married, date) and (married.month, married.day) == (day.month, day.day):
            notes.append(f"Wedding anniversary with {name} ({day.year - married.year} years)")
    return notes


def reminder_words(rem: Reminder, person: str, now: datetime | None = None) -> str:
    """What to say. Fixed words (not the AI's), so reminders work offline. An event's own
    `say` text is used at the time itself; heads-ups say how long until it."""
    occ, now = rem.occurrence, now or datetime.now()
    at = occ.when.strftime("%I:%M %p").lstrip("0")
    minutes = round((occ.when - now).total_seconds() / 60)
    if rem.lead > 0 and minutes > 2:
        soon = f"in about {minutes} minutes" if minutes < 90 else f"at {at}"
        return f"{person}, just a reminder: {occ.event.title} is {soon}."
    if occ.event.say:
        return occ.event.say
    return f"{person}, it's time for {occ.event.title}."


def tools(events: "Events", people: list[dict], person: str):
    """get_schedule and add_event for the AI (docs/DESIGN.md §8)."""
    from tomoshibi.tools import Tool

    def get_schedule(args: dict) -> str:
        start = date.fromisoformat(args["from_date"]) if args.get("from_date") else date.today()
        days = max(1, min(int(args.get("days") or 1), 31))
        return json.dumps({"from": start.isoformat(), "days": days,
                           "items": events.schedule(start, days, people, person)})

    def add_event(args: dict) -> str:
        try:
            day = date.fromisoformat(args["date"])
            at = _parse_time(args.get("time")) if args.get("time") else None
            repeat = _parse_repeat(args.get("repeat") or "none")
            before = int(args.get("remind_minutes_before") or 0)
            event = events.add(args["title"].strip(), day, at, repeat,
                               remind_before=tuple(sorted({before, 0}, reverse=True)))
        except (KeyError, ValueError) as e:
            return json.dumps({"error": f"Couldn't add it: {e}"})
        first = next((o for o in events.occurrences(day, 1) if o.event.id == event.id), None)
        return json.dumps({"added": first.describe() if first else event.title})

    return [
        Tool(
            name="get_schedule",
            description=("The family calendar: appointments, visits, reminders, birthdays and "
                         "anniversaries for a range of days. Today and tomorrow are already in "
                         "your context; use this for other days or longer ranges."),
            input_schema={"type": "object", "properties": {
                "from_date": {"type": "string", "description": "YYYY-MM-DD; default today"},
                "days": {"type": "string", "description": "how many days, 1-31; default 1"},
            }, "required": [], "additionalProperties": False},
            run=get_schedule,
        ),
        Tool(
            name="add_event",
            description=("Add an appointment, visit or reminder to the calendar, so you can remind "
                         f"{person} at the time. Only after reading the details back in plain words "
                         "(what, day, date, time) and hearing a clear yes. Never guess a date or time: "
                         "ask. Medication reminders are set up by the family, not by voice."),
            input_schema={"type": "object", "properties": {
                "title": {"type": "string", "description": "short, e.g. 'Dentist' or 'Karen visits'"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "time": {"type": "string", "description": "e.g. '14:30'; leave out for all day"},
                "repeat": {"type": "string", "enum": ["none", "daily", "weekdays", "weekly", "monthly", "yearly"]},
                "remind_minutes_before": {"type": "string", "description": "extra heads-up, e.g. '60'"},
            }, "required": ["title", "date"], "additionalProperties": False},
            run=add_event,
        ),
    ]


def schedule_text(events: "Events", people: list[dict], person: str, now: datetime | None = None) -> str:
    """Today's and tomorrow's plans, for the date/time part of the prompt."""
    now = now or datetime.now()
    lines = []
    for offset, label in ((0, "Today"), (1, "Tomorrow")):
        items = events.schedule(now.date() + timedelta(days=offset), 1, people, person)
        if not items:
            lines.append(f"{label}: nothing on the calendar.")
            continue
        parts = [f"{i['title']} at {i['time']}" if i.get("time") else i["title"] for i in items]
        lines.append(f"{label}: " + "; ".join(parts) + ".")
    return "# The calendar\n" + "\n".join(lines)
