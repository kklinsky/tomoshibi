import itertools

from tomoshibi import setup_mode, wifi
from tomoshibi.button import SetupGesture
from tomoshibi.setup_mode import LOCKOUT, MAX_WRONG, WRONG_WAIT, CodeGate, SetupMode
from tomoshibi.wifi import Network, NmcliError


# --- the button gesture ------------------------------------------------------------------
def test_hold_ten_seconds_then_press_starts_setup():
    g = SetupGesture(hold=10, confirm=5)
    assert g.down(0) == "press"
    assert not g.held_long(9.9) and g.held_long(10)
    g.up(10.5)
    assert g.waiting(12)
    assert g.down(14) == "setup"
    assert not g.waiting(14.1)
    assert g.down(20) == "press"  # back to normal


def test_a_short_hold_or_a_slow_confirm_is_just_a_press():
    g = SetupGesture(hold=10, confirm=5)
    g.down(0)
    g.up(9)  # not long enough
    assert g.down(10) == "press"
    g.up(21)  # held 11 s
    assert g.down(26.5) == "press"  # 5.5 s later: too slow


# --- the code ----------------------------------------------------------------------------
def codes():
    return iter(f"{n:06d}" for n in itertools.count(111111, 111111))


def test_code_works_once_and_ignores_spaces():
    gen = codes()
    gate = CodeGate(lambda: next(gen))
    assert gate.code == "111111"
    assert gate.check("111 111", 0) == "ok"
    assert gate.code == "222222"
    assert gate.check("111111", 1) == "wrong"


def test_wrong_codes_are_rate_limited_and_change_the_code():
    gen = codes()
    gate = CodeGate(lambda: next(gen))
    now = 0.0
    assert gate.check("000000", now) == "wrong"
    assert gate.check("111111", now + 1) == "wait"  # even the right one, too soon
    for _ in range(MAX_WRONG - 2):
        now += WRONG_WAIT
        assert gate.check("000000", now) == "wrong"
    now += WRONG_WAIT
    assert gate.check("000000", now) == "changed"
    assert gate.code == "222222"
    assert gate.check("222222", now + LOCKOUT - 1) == "wait"
    assert gate.check("222222", now + LOCKOUT) == "ok"


# --- setup mode with a fake NetworkManager ------------------------------------------------
class FakeNet:
    def __init__(self, good_password="right horse", internet=True):
        self.good, self.internet = good_password, internet
        self.hotspot = False
        self.profiles = [("uuid-old", "CarolNet")]
        self.trial = None
        self.active_trial = False
        self.log = []
        self.has_network = True

    def scan(self, rescan=True):
        if rescan and self.hotspot:
            raise NmcliError("can't scan in AP mode")
        return [Network("CarolNet", 70, "WPA2", True), Network("Cafe", 30, "")]

    def current(self):
        return Network("CarolNet", 70, "WPA2", True)

    def connected(self):
        return self.has_network

    def start_hotspot(self, password):
        self.hotspot = True
        self.log.append("hotspot up")

    def stop_hotspot(self):
        self.hotspot = False
        self.log.append("hotspot down")

    def delete(self, name):
        if name == wifi.TRIAL:
            self.trial = None
            self.active_trial = False
        self.profiles = [p for p in self.profiles if p[0] != name]
        self.log.append(f"delete {name}")

    def wifi_profiles(self):
        return list(self.profiles)

    def add_trial(self, ssid, password, security, hidden):
        self.trial = (ssid, password, security, hidden)

    def up(self, name, wait):
        self.active_trial = self.trial is not None and (not self.trial[2] or self.trial[1] == self.good)
        return self.active_trial

    def online(self):
        return self.active_trial and self.internet

    def keep_trial(self, ssid, old):
        for uuid in old:
            self.delete(uuid)
        self.profiles.append(("uuid-new", ssid))
        self.log.append(f"keep {ssid}")


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


class FakeFace:
    def __init__(self):
        self.cards = []

    def card(self, image):
        self.cards.append(image)


class FakeServer:
    def __init__(self, servers):
        servers.append(self)
        self.down = False

    def shutdown(self):
        self.down = True


def make(net=None, conf=None):
    clock, face, servers = Clock(), FakeFace(), []
    mode = SetupMode(conf or {}, net or FakeNet(), face, clock=clock, sleep=clock.sleep,
                     serve=lambda m: FakeServer(servers))
    logged = []
    mode.log = lambda client, action, **d: logged.append((action, d))
    return mode, clock, face, servers, logged


def test_start_shows_the_card_and_serves_the_page():
    mode, _clock, face, servers, _ = make()
    mode.start("button")
    assert mode.active and mode.net.hotspot and len(servers) == 1
    assert face.cards[-1] is not None and face.cards[-1].size == (240, 320)
    assert [n.ssid for n in mode.networks] == ["CarolNet", "Cafe"]  # scanned before the hotspot
    assert mode.before.ssid == "CarolNet"


def test_turns_off_after_fifteen_minutes():
    mode, clock, face, servers, _ = make()
    mode.start("button")
    clock.t += 14 * 60
    mode.tick()
    assert mode.active
    clock.t += 60
    mode.tick()
    assert not mode.active and not mode.net.hotspot
    assert servers[0].down and face.cards[-1] is None


def test_starts_by_itself_after_five_minutes_without_a_network():
    net = FakeNet()
    net.has_network = False
    mode, clock, *_ = make(net)
    mode.tick()
    clock.t += 299
    mode.tick()
    assert not mode.active
    clock.t += 1
    mode.tick()
    assert mode.active and mode.reason == "no network"


def test_auto_start_can_be_switched_off():
    net = FakeNet()
    net.has_network = False
    mode, clock, *_ = make(net, {"setup": {"auto_start": False}})
    mode.tick()
    clock.t += 3600
    mode.tick()
    assert not mode.active


def test_page_needs_the_code():
    mode, *_ = make()
    assert mode.unlock("123456")[1]  # setup mode is off
    mode.start("button")
    session, error = mode.unlock("000000" if mode.gate.code != "000000" else "111111")
    assert not session and "isn't right" in error
    assert not mode.authed("anything")


def test_a_good_password_replaces_the_old_profile():
    mode, _clock, face, _, logged = make()
    mode.start("button")
    session, _ = mode.unlock(mode.gate.code)
    assert mode.authed(session)
    assert mode.join("CarolNet", "right horse", client="10.42.0.5", background=False) == ""
    net = mode.net
    assert net.log.index("hotspot down") < net.log.index("delete uuid-old")  # tried before forgetting
    assert ("uuid-new", "CarolNet") in net.profiles and ("uuid-old", "CarolNet") not in net.profiles
    assert not mode.active and not net.hotspot and not mode.authed(session)
    assert logged == [("wifi changed", {"ssid": "CarolNet", "replaced": 1})]
    assert "right horse" not in repr(logged)  # passwords are never logged
    assert face.cards[-1] is None  # back to the face after "Connected"


def test_a_wrong_password_reverts_and_brings_the_hotspot_back():
    mode, clock, *_ = make()
    mode.start("button")
    started = clock.t
    assert mode.join("CarolNet", "wrong horse", background=False) == ""
    net = mode.net
    assert ("uuid-old", "CarolNet") in net.profiles and net.trial is None
    assert mode.active and net.hotspot
    assert mode.result == {"ssid": "CarolNet", "ok": False, "why": "Couldn't connect. The password may be wrong."}
    assert clock.t - started < 5  # NetworkManager said no: no need to wait out the 2 minutes


def test_no_internet_within_two_minutes_reverts():
    mode, clock, *_ = make(FakeNet(internet=False))
    mode.start("button")
    started = clock.t
    mode.join("CarolNet", "right horse", background=False)
    assert clock.t - started >= wifi.TRY_SECONDS
    assert mode.result["why"] == "Connected, but couldn't reach the internet."
    assert ("uuid-old", "CarolNet") in mode.net.profiles and mode.net.hotspot


def test_join_rejects_bad_input_before_touching_the_network():
    mode, *_ = make()
    assert "off" in mode.join("CarolNet", "right horse")
    mode.start("button")
    assert "8 to 63" in mode.join("CarolNet", "short")
    assert mode.join("", "right horse")
    assert mode.net.hotspot and not mode.trying


def test_open_and_hand_typed_networks():
    mode, *_ = make()
    mode.start("button")
    assert mode.join("Cafe", "", background=False) == ""
    assert mode.net.profiles[-1] == ("uuid-new", "Cafe")
    mode.start("button")
    mode.join("Hidden Place", "right horse", background=False)
    assert mode.net.profiles[-1] == ("uuid-new", "Hidden Place")


def test_crash_leftovers_are_cleaned_up_on_start():
    mode, *_ = make()
    mode.start("button")
    assert f"delete {wifi.TRIAL}" in mode.net.log and f"delete {wifi.HOTSPOT}" in mode.net.log


def test_spaced_code():
    assert setup_mode.spaced("123456") == "123 456"


def test_a_bounce_right_after_the_press_doesnt_cancel_the_hold():
    from tomoshibi.button import ButtonTracker

    t = ButtonTracker(SetupGesture(hold=10, confirm=5))
    assert t.pressed(0.0) == "press"
    assert t.pressed(0.01) == ""          # the bounce's second falling edge
    for now in (0.2, 5.0, 9.8):
        assert t.level(now, down=True) == ""
        assert not t.hint(now)
    assert "held 10 s" in t.level(10.0, down=True)
    assert t.hint(10.0)
    assert "waiting 5 s" in t.level(11.0, down=False)
    assert t.hint(13.0)
    assert t.pressed(14.0) == "setup"
    assert not t.hint(14.1)


def test_a_short_press_lets_go_by_level():
    from tomoshibi.button import ButtonTracker

    t = ButtonTracker(SetupGesture(hold=10, confirm=5))
    t.pressed(0.0)
    assert t.level(0.4, down=False) == ""  # let go: no hold any more
    assert not t.hint(20.0)
    assert t.pressed(20.0) == "press"
