import subprocess

from tomoshibi.volume import Volume, card_from_device, parse

SGET = """Simple mixer control 'PCM',0
  Capabilities: pvolume pvolume-joined pswitch pswitch-joined
  Playback channels: Mono
  Limits: Playback 0 - 11
  Mono: Playback {level} [{pct}%] [-20.00dB] [{sw}]
"""


class FakeMixer:
    def __init__(self, level=4, on=True):
        self.level, self.on, self.calls = level, on, []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        if cmd[3] == "sset":
            self.level, self.on = int(cmd[5]), True
        out = SGET.format(level=self.level, pct=round(self.level * 100 / 11), sw="on" if self.on else "off")
        return subprocess.CompletedProcess(cmd, 0, stdout=out)


def test_card_and_parse():
    assert card_from_device("plughw:CARD=USB") == "USB"
    assert card_from_device("plughw:2,0") == "2"
    assert parse(SGET.format(level=4, pct=36, sw="on")) == (4, 0, 11, True)
    assert parse(SGET.format(level=4, pct=36, sw="off"))[3] is False


def test_louder_quieter_and_the_floor(tmp_path, monkeypatch):
    monkeypatch.setattr("tomoshibi.volume.state_file", lambda: tmp_path / "state.json")
    mixer = FakeMixer(level=4, on=False)
    v = Volume("plughw:CARD=USB", floor_percent=25, run=mixer)
    assert v.change("louder")["level"] == 5
    assert mixer.calls[-1][-1] == "unmute"
    assert v.change("much_louder")["level"] == 8
    assert v.change("loudest") == {"level": 11, "percent": 100, "at_loudest": True, "at_quietest_allowed": False}
    assert v.change("quietest")["level"] == 3          # 25% floor of 0-11, rounded up
    assert v.change("much_quieter")["level"] == 3      # never below the floor
    assert '"volume_level": 3' in (tmp_path / "state.json").read_text()


def test_restore(tmp_path, monkeypatch):
    (tmp_path / "state.json").write_text('{"volume_level": 7}')
    monkeypatch.setattr("tomoshibi.volume.state_file", lambda: tmp_path / "state.json")
    mixer = FakeMixer(level=4)
    Volume("plughw:CARD=USB", run=mixer).restore()
    assert mixer.level == 7
