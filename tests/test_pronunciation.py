from pathlib import Path

import yaml

from tomoshibi.pronunciation import Pronouncer, load


def test_people_pronunciations(tmp_path: Path):
    (tmp_path / "people.yaml").write_text(yaml.safe_dump({"people": [
        {"id": "ami", "name": "Ami Stevens", "called": ["Ami", "your daughter"], "pronounce": "Amy"},
        {"id": "bob", "name": "Bob"},
    ]}), encoding="utf-8")
    (tmp_path / "pronunciations.yaml").write_text("Tommi: Tommy\n", encoding="utf-8")
    p = Pronouncer(load(tmp_path))
    assert p.apply("Ami is coming. Tell ami and Tommi hello, Bob.") == "Amy is coming. Tell Amy and Tommy hello, Bob."
    assert p.apply("Miami is warm.") == "Miami is warm."  # whole words only


def test_no_pronunciations_is_a_no_op(tmp_path: Path):
    assert Pronouncer(load(tmp_path)).apply("Hello there.") == "Hello there."
