from datetime import date, datetime, time

import pytest

from tomoshibi.events import Events, Reminder, _parse_time, reminder_words, special_days

YAML = """
events:
  - id: pills
    title: Morning pills
    time: "08:00"
    repeat: daily
    say: "It's time for your morning pills. They're in the blue box by the sink."
    protected: true
  - id: dentist
    title: Dentist
    date: 2026-10-27
    time: "2:30 pm"
    remind_before: [60, 0]
  - id: cards
    title: Card night
    time: "19:00"
    repeat: [tue, fri]
    starts: 2026-10-01
  - id: market
    title: Farmers market
    date: 2026-10-24
"""


@pytest.fixture
def ev(tmp_path):
    (tmp_path / "events.yaml").write_text(YAML, encoding="utf-8")
    return Events(tmp_path)


def test_times_people_type():
    assert _parse_time("08:00") == time(8, 0)
    assert _parse_time("2:30 pm") == time(14, 30)
    assert _parse_time("9am") == time(9, 0)
    assert _parse_time(480) == time(8, 0)  # YAML reads unquoted 08:00 as 480
    with pytest.raises(ValueError):
        _parse_time("half past eight")


def test_schedule_with_repeats_and_all_day(ev):
    # Tue Oct 27 2026: pills, dentist, card night (Tuesday)
    titles = [o.event.title for o in ev.occurrences(date(2026, 10, 27), 1)]
    assert titles == ["Morning pills", "Dentist", "Card night"]
    sat = ev.occurrences(date(2026, 10, 24), 1)
    assert [(o.event.title, o.all_day) for o in sat] == [("Farmers market", True), ("Morning pills", False)]
    assert ev.occurrences(date(2026, 10, 27), 1)[1].describe() == {
        "title": "Dentist", "date": "Tuesday, October 27", "time": "2:30 PM"}


def test_each_lead_time_is_its_own_reminder(ev):
    hour_before = datetime(2026, 10, 27, 13, 30)
    due = [r for r in ev.due(hour_before) if r.occurrence.event.id == "dentist"]
    assert [r.lead for r in due] == [60]
    ev.record(due[0], "acknowledged", hour_before)
    at_time = datetime(2026, 10, 27, 14, 30)
    assert [r.lead for r in ev.due(at_time) if r.occurrence.event.id == "dentist"] == [0]


def test_retries_then_missed(ev):
    t = datetime(2026, 10, 23, 8, 0)
    rem = next(r for r in ev.due(t) if r.occurrence.event.id == "pills")
    assert ev.record(rem, "attempted", t) == "pending"
    assert rem not in ev.due(datetime(2026, 10, 23, 8, 2))       # waits 5 minutes
    assert rem in ev.due(datetime(2026, 10, 23, 8, 5))
    assert ev.record(rem, "attempted", datetime(2026, 10, 23, 8, 5)) == "pending"
    assert ev.record(rem, "attempted", datetime(2026, 10, 23, 8, 10)) == "missed"
    assert rem not in ev.due(datetime(2026, 10, 23, 8, 20))


def test_snooze(ev):
    t = datetime(2026, 10, 23, 8, 0)
    rem = next(r for r in ev.due(t) if r.occurrence.event.id == "pills")
    ev.record(rem, "snoozed", t, snooze_minutes=10)
    assert rem not in ev.due(datetime(2026, 10, 23, 8, 9))
    assert rem in ev.due(datetime(2026, 10, 23, 8, 10))


def test_not_too_early_or_too_late(ev):
    assert not [r for r in ev.due(datetime(2026, 10, 23, 7, 59)) if r.occurrence.event.id == "pills"]
    assert not [r for r in ev.due(datetime(2026, 10, 23, 10, 1)) if r.occurrence.event.id == "pills"]


def test_voice_added_event(ev):
    ev.add("Plumber", date(2026, 10, 29), time(10, 0))
    assert [o.event.title for o in ev.occurrences(date(2026, 10, 29), 1)] == ["Morning pills", "Plumber"]
    assert ev.all()[-1].source == "voice"


def test_reminder_words(ev):
    pills = next(o for o in ev.occurrences(date(2026, 10, 23), 1) if o.event.id == "pills")
    assert reminder_words(Reminder(pills, 0), "Bob").startswith("It's time for your morning pills")
    dentist = next(o for o in ev.occurrences(date(2026, 10, 27), 1) if o.event.id == "dentist")
    heads_up = reminder_words(Reminder(dentist, 60), "Bob", now=datetime(2026, 10, 27, 13, 30))
    assert heads_up == "Bob, just a reminder: Dentist is in about 60 minutes."
    assert reminder_words(Reminder(dentist, 0), "Bob", now=datetime(2026, 10, 27, 14, 30)) == "Bob, it's time for Dentist."


def test_birthdays_and_anniversaries():
    people = [{"id": "bob", "is_subject": True, "born": date(1944, 3, 12)},
              {"id": "karen", "name": "Karen Smith", "called": ["Karen"], "born": date(1970, 9, 30)},
              {"id": "carol", "name": "Carol", "called": ["Carol"], "married": date(1967, 6, 17)},
              {"id": "ruth", "name": "Ruth", "born": date(1941, 9, 30), "died": 2023}]
    assert special_days(people, date(2026, 9, 30), "Bob") == ["Karen's birthday (turning 56)"]
    assert special_days(people, date(2026, 3, 12), "Bob") == ["Your birthday (turning 82)"]
    assert special_days(people, date(2026, 6, 17), "Bob") == ["Wedding anniversary with Carol (59 years)"]


def test_example_family_events_load():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "examples" / "data"
    ev = Events(root, db_path=":memory:")
    assert {e.id for e in ev.all()} == {"morning-pills", "card-night", "dentist"}


def test_expected_times(tmp_path):
    from datetime import timedelta

    from tomoshibi.events import schedule_text

    ev = Events(tmp_path)
    left = datetime(2026, 10, 23, 15, 15)
    ev.expect("Hisako back from the store", left + timedelta(minutes=30), left)
    ten_later = left + timedelta(minutes=10)
    (e,) = ev.expected(ten_later)
    assert (e["at"], e["minutes_left"], e["said_at"]) == ("3:45 PM", 20, "3:15 PM")
    text = schedule_text(ev, [], "Bob", ten_later)
    assert "Expected: Hisako back from the store at 3:45 PM, in about 20 minutes (said at 3:15 PM)." in text
    late = schedule_text(ev, [], "Bob", left + timedelta(minutes=42))
    assert "expected about 12 minutes ago, so a little later than planned" in late
    assert ev.expected(left + timedelta(hours=3)) == []       # dropped after a couple of hours
    # a new estimate replaces the old one; "I'm back" clears it
    ev.expect("Hisako back from the store", left + timedelta(minutes=50), left)
    assert [x["at"] for x in ev.expected(ten_later)] == ["4:05 PM"]
    assert ev.done("hisako") == 1 and ev.expected(ten_later) == []


def test_expected_time_tool(tmp_path):
    import json

    from tomoshibi.events import tools

    ev = Events(tmp_path)
    by_name = {t.name: t for t in tools(ev, [], "Bob")}
    out = json.loads(by_name["note_expected_time"].run({"what": "Carol back from the bank", "minutes_from_now": "45"}))
    assert out["noted"] == "Carol back from the bank"
    assert ev.expected()[0]["minutes_left"] in (44, 45)
    assert json.loads(by_name["clear_expected_time"].run({"what": "Carol"})) == {"cleared": 1}
