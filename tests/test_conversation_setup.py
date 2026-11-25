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
    talk.heard_full = False
    talk.longest_turn = 20
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


def tv_on_after_first_turn(talk, first_full=False):
    """The first turn (after a press) waits 8 s; follow-ups wait 10 s and hear only the TV."""
    talk.first_wait, talk.follow_up = 8, 10

    def listen(wait):
        talk.heard_full = first_full if wait == 8 else True
        return "what's the weather" if wait == 8 else "the TV"

    talk.listen = listen


def test_a_follow_up_that_never_pauses_ends_the_conversation():
    talk = bare()
    tv_on_after_first_turn(talk)
    talk.session()
    assert talk.answered == ["what's the weather"]


def test_a_pressed_turn_that_never_pauses_is_answered_with_a_tv_note():
    talk = bare()
    tv_on_after_first_turn(talk, first_full=True)
    notes = []
    talk.respond = lambda text, note="": notes.append(note) or False
    talk.session()
    assert len(notes) == 1 and "TV or radio" in notes[0]


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
