from tomoshibi.button import PressFilter


def test_a_shaky_press_counts_once():
    presses = PressFilter(gap=0.3)
    assert presses.accept(10.0)
    assert not presses.accept(10.1)
    assert not presses.accept(10.29)
    assert presses.accept(10.31)
