import pytest

from tomoshibi.intents import reminder_reply


@pytest.mark.parametrize("said,expected", [
    ("OK.", ("ack", 0)),
    ("Okay, thanks.", ("ack", 0)),
    ("Thank you, I took them.", ("ack", 0)),
    ("Got it.", ("ack", 0)),
    ("Remind me in ten minutes.", ("snooze", 10)),
    ("Can you remind me again in 15 minutes?", ("snooze", 15)),
    ("Remind me in an hour.", ("snooze", 60)),
    ("Tell me in half an hour.", ("snooze", 30)),
    ("Remind me in a couple of minutes", ("snooze", 2)),
    ("Not now.", ("snooze", 10)),
    ("Give me a minute.", ("snooze", 10)),
    ("What time is the dentist?", ("other", 0)),
    ("Who is Karen?", ("other", 0)),
])
def test_reminder_replies(said, expected):
    assert reminder_reply(said) == expected
