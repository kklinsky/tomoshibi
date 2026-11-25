import pytest

from tomoshibi import wifi
from tomoshibi.wifi import (
    Nmcli,
    NmcliError,
    NoWifiWatch,
    parse_scan,
    password_problem,
    split_terse,
    trial_outcome,
)


def test_terse_fields_unescape_colons():
    assert split_terse(r"*:Bob\:s Wi-Fi:72:WPA2") == ["*", "Bob:s Wi-Fi", "72", "WPA2"]
    assert split_terse(r"a\\b:") == ["a\\b", ""]


def test_scan_keeps_the_strongest_of_each_name_and_skips_hidden_and_hotspot():
    lines = [
        " :CarolNet:40:WPA2",
        "*:CarolNet:81:WPA2",
        " :Neighbors:90:WPA1 WPA2",
        " ::70:WPA2",                     # hidden
        " :Tomoshibi-Setup:99:WPA2",      # our own
        " :Cafe:30:--",
        " :Old:20:WEP",
    ]
    text = "\n".join(lines)
    nets = parse_scan(text)
    assert [n.ssid for n in nets] == ["CarolNet", "Neighbors", "Cafe", "Old"]  # in use first
    assert nets[0].signal == 81 and nets[0].in_use
    cafe = nets[2].as_dict()
    assert cafe["open"] and cafe["security"] == ""
    assert not nets[3].as_dict()["open"]  # WEP isn't "open", it's unsupported


def test_security_and_password_checks():
    assert wifi.key_mgmt("") == ""
    assert wifi.key_mgmt("WPA2") == "wpa-psk"
    assert wifi.key_mgmt("WPA2 WPA3") == "wpa-psk"
    assert wifi.key_mgmt("WPA3") == "sae"
    assert password_problem("short", "WPA2")
    assert password_problem("x" * 64, "WPA2")  # 64 characters must be a hex key
    assert password_problem("a" * 64, "WPA2") == ""
    assert password_problem("right horse", "WPA2") == ""
    assert password_problem("", "") == ""
    assert "can't join" in password_problem("whatever1", "WPA2 802.1X")


def test_hotspot_password_is_readable_and_long_enough():
    pw = wifi.new_hotspot_password()
    assert len(pw) == 8 and not set(pw) & set("0o1li")


@pytest.mark.parametrize("elapsed, activated, online, expected", [
    (5, None, False, "wait"),       # still connecting
    (5, False, False, "revert"),    # wrong password: NetworkManager gave up
    (30, True, True, "keep"),
    (60, True, False, "wait"),      # joined, no internet yet
    (120, True, False, "revert"),   # joined but never got online
    (119, True, True, "keep"),
])
def test_trial_outcome(elapsed, activated, online, expected):
    assert trial_outcome(elapsed, activated, online, limit=120) == expected


def test_no_wifi_watch_needs_five_unbroken_minutes():
    watch = NoWifiWatch(limit=300)
    assert not watch.update(0, False)
    assert not watch.update(299, False)
    assert not watch.update(200 + 100, True)  # back online resets it
    assert not watch.update(400, False)
    assert not watch.update(699, False)
    assert watch.update(700, False)


class Recorder(Nmcli):
    def __init__(self, replies=None):
        super().__init__("wlan0")
        self.calls, self.replies = [], replies or {}

    def run(self, *args, timeout=30):
        self.calls.append(args)
        for key, reply in self.replies.items():
            if key in " ".join(args):
                if isinstance(reply, Exception):
                    raise reply
                return reply
        return ""


def test_hotspot_is_wpa2_shared_and_never_autoconnects():
    net = Recorder()
    net.start_hotspot("abcdefgh")
    add = next(c for c in net.calls if c[:2] == ("con", "add"))
    joined = " ".join(add)
    assert "802-11-wireless.mode ap" in joined and "ipv4.method shared" in joined
    assert "autoconnect no" in joined and "wifi-sec.key-mgmt wpa-psk" in joined
    assert net.calls[-1] == ("con", "up", "Tomoshibi-Setup")


def test_trial_profile_waits_to_be_kept():
    net = Recorder()
    net.add_trial("CarolNet", "right horse", "WPA2", hidden=False)
    add = " ".join(net.calls[-1])
    assert "con-name tomoshibi-trial" in add and "autoconnect no" in add and "hidden" not in add
    net.add_trial("Cafe", "", "", hidden=True)
    add = " ".join(net.calls[-1])
    assert "wifi-sec" not in add and "802-11-wireless.hidden yes" in add
    net.keep_trial("CarolNet", ["uuid-old"])
    assert ("con", "delete", "uuid-old") in net.calls
    assert net.calls[-1][:3] == ("con", "modify", "tomoshibi-trial")
    assert "CarolNet" in net.calls[-1]


def test_connected_ignores_the_hotspot():
    assert not Recorder({"--active": "Tomoshibi-Setup:802-11-wireless:wlan0\nlo:loopback:lo\n"}).connected()
    assert Recorder({"--active": "CarolNet:802-11-wireless:wlan0\n"}).connected()
    assert Recorder({"--active": "Wired:802-3-ethernet:eth0\n"}).connected()


def test_up_reports_failure_instead_of_raising():
    assert not Recorder({"con up": NmcliError("Secrets were required")}).up("tomoshibi-trial", 60)
    assert Recorder().up("tomoshibi-trial", 60)


def test_online_trusts_networkmanager_when_it_knows():
    assert Recorder({"connectivity": "full\n"}).online()
    assert not Recorder({"connectivity": "limited\n"}).online()
