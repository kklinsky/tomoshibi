import time

from tomoshibi.button import Blinker, PressFilter


def test_blinker_alternates_and_never_switches_after_stop():
    seen = []
    blink = Blinker(seen.append, period=0.02).start()
    time.sleep(0.1)
    blink.stop()
    count = len(seen)
    time.sleep(0.05)
    assert len(seen) == count  # nothing after stop
    assert seen[:4] == [True, False, True, False]


def test_a_shaky_press_counts_once():
    presses = PressFilter(gap=0.3)
    assert presses.accept(10.0)
    assert not presses.accept(10.1)
    assert not presses.accept(10.29)
    assert presses.accept(10.31)
