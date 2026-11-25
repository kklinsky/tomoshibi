"""Tomo doesn't listen or answer while setup mode (the Wi-Fi hotspot) is on."""

from types import SimpleNamespace

from tomoshibi.conversation import Conversation


class Quiet:
    def __getattr__(self, name):
        return lambda *a, **k: None


def bare(setup_active=False, heard=("hello",)):
    talk = Conversation.__new__(Conversation)
    talk.face, talk.speaker = Quiet(), Quiet()
    talk.first_wait = talk.follow_up = 10
    talk.setup = SimpleNamespace(active=setup_active)
    talk.setup_starting = False
    talk.answered = []
    heard = list(heard)
    talk.listen = lambda wait: heard.pop(0) if heard else ""
    talk.respond = lambda text, note="": talk.answered.append(text) or False
    return talk


def test_no_conversation_while_setup_mode_is_on():
    talk = bare(setup_active=True)
    talk.session()
    assert talk.answered == []


def test_setup_mode_starting_mid_conversation_ends_it():
    talk = bare(heard=("first", "second"))

    def respond(text, note=""):
        talk.answered.append(text)
        talk.setup_starting = True  # the gesture is done while Tomo answers
        return False

    talk.respond = respond
    talk.session()
    assert talk.answered == ["first"]


def test_setup_on_covers_starting_and_running():
    talk = bare()
    assert not talk.setup_on()
    talk.setup_starting = True
    assert talk.setup_on()
    talk.setup_starting = False
    talk.setup.active = True
    assert talk.setup_on()
    talk.setup = None
    assert not talk.setup_on()
