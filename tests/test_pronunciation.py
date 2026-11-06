from pathlib import Path

import yaml

from tomoshibi.pronunciation import Pronouncer, load


def test_people_pronunciations(tmp_path: Path):
    (tmp_path / "people.yaml").write_text(yaml.safe_dump({"people": [
        {"id": "niamh", "name": "Niamh Smith", "called": ["Niamh", "your daughter"], "pronounce": "Neev"},
        {"id": "bob", "name": "Bob"},
        {"id": "siobhan", "name": "Carol", "called": ["Carol", "Gigi"], "pronounce": "Shiv-awn"},
    ]}), encoding="utf-8")
    (tmp_path / "pronunciations.yaml").write_text("Gigi: Jee-jee\n", encoding="utf-8")
    p = Pronouncer(load(tmp_path))
    assert p.apply("Niamh is coming. Tell niamh and Gigi hello, Bob.") == "Neev is coming. Tell Neev and Jee-jee hello, Bob."
    assert p.apply("Miami is warm.") == "Miami is warm."  # whole words only
    # A person's pronunciation covers their first name, not their nicknames.
    assert p.apply("Carol, also called Gigi.") == "Shiv-awn, also called Jee-jee."


def test_no_pronunciations_is_a_no_op(tmp_path: Path):
    assert Pronouncer(load(tmp_path)).apply("Hello there.") == "Hello there."


def test_builtin_words():
    assert Pronouncer({}).apply("Short for Tomoshibi.") == "Short for Toemoe-sheebee."
    assert Pronouncer({"Tomoshibi": "Tomo-shee-bee"}).apply("Tomoshibi") == "Tomo-shee-bee"  # family wins


PEOPLE = """\
# Family tree. Comments must survive edits.
people:
  - id: niamh
    name: "Niamh Smith"
    called: ["Niamh", "your daughter"]   # keep me
    parents: [dad]

  - id: emma
    name: "Emma Smith"
    pronounce: "Emma"
"""


def test_save_to_person_keeps_comments(tmp_path: Path):
    from tomoshibi.pronunciation import entries, save

    (tmp_path / "people.yaml").write_text(PEOPLE, encoding="utf-8")
    assert save(tmp_path, "Niamh", "Neev") == "people.yaml"
    assert save(tmp_path, "emma", "Emmah") == "people.yaml"
    text = (tmp_path / "people.yaml").read_text(encoding="utf-8")
    assert "# keep me" in text and "Comments must survive" in text
    assert '    called: ["Niamh", "your daughter"]   # keep me\n    pronounce: "Neev"' in text
    assert text.count("pronounce:") == 2 and 'pronounce: "Emmah"' in text
    assert {e["word"]: e["say"] for e in entries(tmp_path)} == {"Niamh": "Neev", "Emma": "Emmah"}


def test_save_and_remove_other_words(tmp_path: Path):
    from tomoshibi.pronunciation import entries, remove, save

    (tmp_path / "pronunciations.yaml").write_text("# words\nTommi: Jee-jee  # nickname\n", encoding="utf-8")
    assert save(tmp_path, "Naples", "Nay-pulls") == "pronunciations.yaml"
    assert save(tmp_path, "gigi", "Gee-gee") == "pronunciations.yaml"
    assert {e["word"].lower(): e["say"] for e in entries(tmp_path)} == {"naples": "Nay-pulls", "gigi": "Gee-gee"}
    assert remove(tmp_path, "Naples") and not remove(tmp_path, "Naples")
    assert "# words" in (tmp_path / "pronunciations.yaml").read_text(encoding="utf-8")


def test_remove_from_person(tmp_path: Path):
    from tomoshibi.pronunciation import entries, remove

    (tmp_path / "people.yaml").write_text(PEOPLE, encoding="utf-8")
    assert remove(tmp_path, "Emma")
    assert entries(tmp_path) == []


def test_homographs_lives_and_live():
    from tomoshibi.pronunciation import fix_homographs as f

    assert f("Mike lives in Denver, Colorado.") == "Mike livs in Denver, Colorado."
    assert f("Emma lives nearby, and David lives with Niamh.") == "Emma livs nearby, and David livs with Niamh."
    assert f("Lives in Boston.") == "Livs in Boston."
    assert f("Where does Niamh live?") == "Where does Niamh liv?"
    assert f("Niamh wants to live there.") == "Niamh wants to liv there."
    assert f("We watched it live.") == "We watched it live."
    assert f("Did they watch it live?") == "Did they watch it live?"
    assert f("Cats have nine lives.") == "Cats have nine lives."   # the noun is left alone
    assert f("We watched the game live.") == "We watched the game live."
    assert f("She delivers.") == "She delivers."


def test_call_letters_are_spelled_out():
    from tomoshibi.pronunciation import fix_homographs as f

    assert f("You ran WKRP in Cincinnati.") == "You ran W K R P in Cincinnati."
    assert f("WXYZ and KMOX-AM.") == "W X Y Z and K M O X A M."
    assert f("NBC and ABC.") == "NBC and ABC."          # the voice already spells these
    assert f("We won the Emmy.") == "We won the Emmy."  # ordinary words are left alone
