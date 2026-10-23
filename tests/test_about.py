from pathlib import Path

import yaml

from tomoshibi import about

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "data"
CONFIG = yaml.safe_load((ROOT / "config" / "config.example.yaml").read_text(encoding="utf-8"))


ALL_BUILT = frozenset({"conversation", "people", "calendar", "reminders", "memories",
                       "web_search", "weather", "news", "messaging"})


def render(config=CONFIG, built=ALL_BUILT):
    return about.render(
        yaml.safe_load((EXAMPLES / "persona.yaml").read_text(encoding="utf-8")),
        yaml.safe_load((EXAMPLES / "profile.yaml").read_text(encoding="utf-8")),
        yaml.safe_load((EXAMPLES / "people.yaml").read_text(encoding="utf-8"))["people"],
        config,
        built,
    )


def test_fills_names_from_family_files():
    text = render()
    assert "I'm Tomo, a helper your son David made for you." in text
    assert "David made you for Bob" in text
    assert "## Your full introduction" in text and "Hello, Bob. I'm Tomo." in text
    assert "Helping Carol" in text
    assert "{" not in text and "}" not in text, "unfilled placeholder"


def test_capabilities_follow_config():
    on = render()
    assert "Look things up on the internet" in on.split("## What you cannot do")[0]
    assert "Send short messages to Karen and David" in on
    off = dict(CONFIG, internet={"web_search": {"enabled": False}}, messaging={"enabled": False})
    text = render(off)
    can, cannot = text.split("## What you cannot do")
    assert "Look things up on the internet" not in can.split("## What you can do")[1]
    assert "Look things up on the internet" in cannot
    assert "Send messages to anyone." in cannot


def test_privacy_mentions_summaries_only_when_enabled():
    assert "don't send the family summaries" in render()
    on = dict(CONFIG, privacy={"daily_summary": True})
    assert "Once a day the family gets a short summary" in render(on)


def test_template_has_no_family_names():
    template = (ROOT / "src" / "tomoshibi" / "prompts" / "about_me.md").read_text(encoding="utf-8")
    for name in ("Bob", "Carol", "David", "Karen", "Mike", "Emma"):
        assert name not in template


def test_never_claims_features_that_are_not_built():
    text = render(built=frozenset({"conversation", "people"}))
    can, cannot = text.split("## What you can do")[1].split("## What you cannot do")
    for claim in ("weather", "internet", "reminders", "messages to"):
        assert claim not in can.lower(), claim
    assert "Check the weather." in cannot
    assert "Send messages to anyone." in cannot


def test_name_meaning():
    text = render()
    assert "My name is short for Tomoshibi. It's a Japanese word for lamplight" in text
    assert "## Your name\n\"Tomo\" is short for Tomoshibi" in text and "a warm light that's always there for Bob" in text
    persona = yaml.safe_load((EXAMPLES / "persona.yaml").read_text(encoding="utf-8"))
    other = about.render({**persona, "name": "Sunny"},
                         yaml.safe_load((EXAMPLES / "profile.yaml").read_text(encoding="utf-8")),
                         yaml.safe_load((EXAMPLES / "people.yaml").read_text(encoding="utf-8"))["people"], CONFIG)
    assert "Tomoshibi" not in other and "## Your name" not in other and "{" not in other
    own = about.render({**persona, "name": "Sunny", "name_meaning": "I'm named after the sunshine."},
                       yaml.safe_load((EXAMPLES / "profile.yaml").read_text(encoding="utf-8")),
                       yaml.safe_load((EXAMPLES / "people.yaml").read_text(encoding="utf-8"))["people"], CONFIG)
    assert 'Then: "I\'m named after the sunshine."' in own
