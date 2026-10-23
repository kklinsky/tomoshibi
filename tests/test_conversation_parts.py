from datetime import date, datetime
from pathlib import Path

import yaml

from tomoshibi import config, keys, prompt
from tomoshibi.sentences import SentenceSplitter
from tomoshibi.vad import Endpointer

ROOT = Path(__file__).resolve().parents[1]


def test_splitter_streams_sentences_and_flushes_the_rest():
    s = SentenceSplitter()
    out = []
    for chunk in ["It's Sat", "urday, Bob. Karen is com", "ing at two! Shall I", " remind you"]:
        out += s.feed(chunk)
    assert out == ["It's Saturday, Bob.", "Karen is coming at two!"]
    assert s.flush() == ["Shall I remind you"]


def test_splitter_cuts_a_long_first_sentence_at_a_comma():
    s = SentenceSplitter()
    text = "Well, that's a lovely question to ask on a sunny afternoon, and I'd be glad to tell you about it. "
    first = s.feed(text)[0]
    assert first.endswith(",") and len(first) < 80


def test_endpointer_starts_then_ends_after_silence():
    ep = Endpointer(end_silence=0.32, wait_for_speech=5)  # 10 frames of silence
    states = [ep.update(p) for p in [0.1, 0.9, 0.9, 0.9] + [0.0] * 10]
    assert states[3] == "speaking"
    assert states[-1] == "done"


def test_endpointer_times_out_without_speech():
    ep = Endpointer(wait_for_speech=0.32)
    assert [ep.update(0.0) for _ in range(10)][-1] == "timeout"


def test_key_event_parsing():
    data = keys.EVENT.pack(0, 0, keys.EV_KEY, keys.KEY_SPACE, keys.PRESSED)
    assert keys.parse(data + b"\0\0") == [(keys.EV_KEY, keys.KEY_SPACE, keys.PRESSED)]


def test_config_seconds():
    assert config.seconds("10s", 0) == 10
    assert config.seconds("5m", 0) == 300
    assert config.seconds("1.5s", 0) == 1.5
    assert config.seconds(None, 7) == 7


def test_stable_prompt_from_example_family():
    conf = yaml.safe_load((ROOT / "config" / "config.example.yaml").read_text(encoding="utf-8"))
    text = prompt.stable_prompt(ROOT / "examples" / "data", conf)
    assert text.startswith("# Rules")
    assert "Karen Smith (called Karen): Bob's child" in text
    assert "Emma Smith: Bob's grandchild (child of Karen)" in text
    assert "Mike Smith: Bob's child-in-law (married to Karen)" in text
    assert "{" not in text


def test_today_context():
    text = prompt.today_context(datetime(2026, 10, 17, 14, 5))
    assert "Saturday, October 17, 2026, 2:05 PM (Saturday afternoon)" in text


def test_people_ages():
    lines = prompt.people_text([{"id": "a", "is_subject": True}, {"id": "b", "name": "Bea", "born": date(2000, 12, 31)}],
                               date(2026, 10, 22))
    assert "Age 25, birthday December 31" in lines


def test_profile_includes_the_persons_own_birthday():
    text = prompt.profile_text({"call_him": "Bob"}, {"id": "bob", "born": date(1944, 3, 12)}, date(2026, 10, 22))
    assert "Birthday: March 12, 1944 (age 82)." in text


def test_siblings_and_half_siblings():
    people = [
        {"id": "bob", "is_subject": True, "parents": ["nate", "ruth"]},
        {"id": "nate", "name": "Nathan", "called": ["your father"]},
        {"id": "ruth", "name": "Ruth"},
        {"id": "sue", "name": "Sue", "parents": ["nate", "ruth"]},
        {"id": "rob", "name": "Roben", "parents": ["nate", "robs_mother"]},
        {"id": "tay", "name": "Taylor", "pronouns": "they/them", "parents": ["sue"], "lives": "Dallas"},
    ]
    text = prompt.people_text(people, date(2026, 10, 22), "Bob")
    assert "Nathan (called your father): Bob's parent" in text
    assert "Sue: Bob's sibling" in text
    assert "Roben: Bob's half-sibling, through Nathan" in text
    assert "They live in Dallas." in text and "pronouns" not in text


def test_relationship_words_follow_pronouns():
    assert prompt._gendered("Bob's grandchild (child of Ami)", "he/him") == "Bob's grandson (child of Ami)"
    assert prompt._gendered("Bob's half-sibling, through Nathan", "she/her") == "Bob's half-sister, through Nathan"
    assert prompt._gendered("Bob's child-in-law (married to Karen)", "he/him") == "Bob's son-in-law (married to Karen)"
    assert prompt._gendered("Bob's grandchild", "they/them") == "Bob's grandchild"
    assert prompt._gendered("Bob's grandchild", None) == "Bob's grandchild"


def test_wiki_is_included_without_source_tags(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "career.md").write_text(
        "---\ntopic: Career\nsensitivity: normal\n---\n## Facts\n- Ran WHEC from 1983. [hof]\n\n"
        "## How to talk about it\nDon't bring up retirement.\n\n## Sources\n- hof: Hall of Fame\n",
        encoding="utf-8")
    (wiki / "loss.md").write_text("---\ntopic: A hard year\nsensitivity: avoid_unless_raised\n---\n- Lost his job.\n",
                                  encoding="utf-8")
    text = prompt.wiki_text(tmp_path, "Bob")
    assert "## Career\nYou may bring this up" in text
    assert "- Ran WHEC from 1983." in text and "[hof]" not in text and "Hall of Fame" not in text
    assert "Don't bring up retirement." in text
    assert "Don't bring this up yourself. Talk about it only if Bob does." in text
    assert prompt.wiki_text(tmp_path / "nothing", "Bob") == ""


def test_example_family_wiki_reaches_the_prompt():
    conf = yaml.safe_load((ROOT / "config" / "config.example.yaml").read_text(encoding="utf-8"))
    text = prompt.stable_prompt(ROOT / "examples" / "data", conf)
    assert "# Their life story" in text and "radioman" in text
    assert "Talk about Bob's life story" in text  # "memories" is now listed as built


def test_death_dates_read_naturally():
    people = [{"id": "bob", "is_subject": True, "parents": ["n", "r"]},
              {"id": "s", "name": "Shelly", "pronouns": "she/her", "parents": ["n", "r"], "died": 2021},
              {"id": "u", "name": "Ruth", "died": date(2023, 4, 10)}]
    text = prompt.people_text(people, date(2026, 10, 22), "Bob")
    assert "Shelly: Bob's sister. She died in 2021." in text
    assert "Died on April 10, 2023." in text
