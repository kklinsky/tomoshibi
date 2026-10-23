from pathlib import Path

import yaml

from tomoshibi.pronunciation import Pronouncer, load


def test_people_pronunciations(tmp_path: Path):
    (tmp_path / "people.yaml").write_text(yaml.safe_dump({"people": [
        {"id": "ami", "name": "Ami Stevens", "called": ["Ami", "your daughter"], "pronounce": "Amy"},
        {"id": "bob", "name": "Bob"},
        {"id": "hisako", "name": "Hisako", "called": ["Hisako", "Tommi"], "pronounce": "Hee-sah-ko"},
    ]}), encoding="utf-8")
    (tmp_path / "pronunciations.yaml").write_text("Tommi: Tommy\n", encoding="utf-8")
    p = Pronouncer(load(tmp_path))
    assert p.apply("Ami is coming. Tell ami and Tommi hello, Bob.") == "Amy is coming. Tell Amy and Tommy hello, Bob."
    assert p.apply("Miami is warm.") == "Miami is warm."  # whole words only
    # A person's pronunciation covers their first name, not their nicknames.
    assert p.apply("Hisako, also called Tommi.") == "Hee-sah-ko, also called Tommy."


def test_no_pronunciations_is_a_no_op(tmp_path: Path):
    assert Pronouncer(load(tmp_path)).apply("Hello there.") == "Hello there."


PEOPLE = """\
# Family tree. Comments must survive edits.
people:
  - id: ami
    name: "Ami Stevens"
    called: ["Ami", "your daughter"]   # keep me
    parents: [dad]

  - id: meryl
    name: "Meryl Stevens"
    pronounce: "Meryl"
"""


def test_save_to_person_keeps_comments(tmp_path: Path):
    from tomoshibi.pronunciation import entries, save

    (tmp_path / "people.yaml").write_text(PEOPLE, encoding="utf-8")
    assert save(tmp_path, "Ami", "Amy") == "people.yaml"
    assert save(tmp_path, "meryl", "Meril") == "people.yaml"
    text = (tmp_path / "people.yaml").read_text(encoding="utf-8")
    assert "# keep me" in text and "Comments must survive" in text
    assert '    called: ["Ami", "your daughter"]   # keep me\n    pronounce: "Amy"' in text
    assert text.count("pronounce:") == 2 and 'pronounce: "Meril"' in text
    assert {e["word"]: e["say"] for e in entries(tmp_path)} == {"Ami": "Amy", "Meryl": "Meril"}


def test_save_and_remove_other_words(tmp_path: Path):
    from tomoshibi.pronunciation import entries, remove, save

    (tmp_path / "pronunciations.yaml").write_text("# words\nTommi: Tommy  # nickname\n", encoding="utf-8")
    assert save(tmp_path, "Naples", "Nay-pulls") == "pronunciations.yaml"
    assert save(tmp_path, "tommi", "Tah-mee") == "pronunciations.yaml"
    assert {e["word"].lower(): e["say"] for e in entries(tmp_path)} == {"naples": "Nay-pulls", "tommi": "Tah-mee"}
    assert remove(tmp_path, "Naples") and not remove(tmp_path, "Naples")
    assert "# words" in (tmp_path / "pronunciations.yaml").read_text(encoding="utf-8")


def test_remove_from_person(tmp_path: Path):
    from tomoshibi.pronunciation import entries, remove

    (tmp_path / "people.yaml").write_text(PEOPLE, encoding="utf-8")
    assert remove(tmp_path, "Meryl")
    assert entries(tmp_path) == []


def test_homographs_lives_and_live():
    from tomoshibi.pronunciation import fix_homographs as f

    assert f("Taylor lives in Dallas, Texas.") == "Taylor livs in Dallas, Texas."
    assert f("Meryl lives nearby, and Simon lives with Ami.") == "Meryl livs nearby, and Simon livs with Ami."
    assert f("Lives in Atlanta.") == "Livs in Atlanta."
    assert f("Where does Ami live?") == "Where does Ami liv?"
    assert f("Ami wants to live there.") == "Ami wants to liv there."
    assert f("We watched it live.") == "We watched it live."
    assert f("Did they watch it live?") == "Did they watch it live?"
    assert f("Cats have nine lives.") == "Cats have nine lives."   # the noun is left alone
    assert f("We watched the game live.") == "We watched the game live."
    assert f("She delivers.") == "She delivers."
