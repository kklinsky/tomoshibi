import json
import threading
from http.server import ThreadingHTTPServer
from importlib import resources

import pytest
from test_setup_mode import FakeNet, make
from test_setup_page import request

from tomoshibi.setup_page import make_handler


class SetupModeApp:
    """What the handler needs from SetupApp in setup mode: no voice, a SetupMode."""

    def __init__(self, setup, data_dir):
        self.conf, self.data_dir, self.setup, self.net = {}, data_dir, setup, setup.net
        self.token, self.session, self.tts = "tok", "", None
        self.html = resources.files("tomoshibi").joinpath("setup_page.html").read_text(encoding="utf-8")


@pytest.fixture
def setup_server(tmp_path):
    mode, *_ = make(FakeNet())
    mode.start("button")
    mode.address = "127.0.0.1"
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(SetupModeApp(mode, tmp_path)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield mode, f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_other_hosts_are_sent_to_the_page(setup_server):
    import urllib.request

    mode, base = setup_server
    req = urllib.request.Request(base + "/generate_204", headers={"Host": "connectivitycheck.gstatic.com"})
    from test_setup_page import NoRedirect

    try:
        urllib.request.build_opener(NoRedirect).open(req)
        status = 200
    except urllib.error.HTTPError as e:
        status, location = e.code, e.headers["Location"]
    assert status == 302 and location == mode.url + "/"


def test_locked_until_the_code_is_entered(setup_server):
    mode, base = setup_server
    status, _, body = request(base + "/")
    assert status == 200 and b"Enter the code" in body  # the page asks for the code itself
    assert json.loads(request(base + "/api/mode")[2]) == {"setup_mode": True, "unlocked": False,
                                                          "pronunciations": False}
    assert request(base + "/api/wifi")[0] == 401
    assert request(base + "/api/wifi/join", {"ssid": "CarolNet", "password": "right horse"})[0] == 401
    wrong = "000000" if mode.gate.code != "000000" else "111111"
    status, _, body = request(base + "/api/unlock", {"code": wrong})
    assert status == 403 and "isn't right" in json.loads(body)["error"]
    status = request(base + "/api/unlock", {"code": mode.gate.code})[0]
    assert status == 403  # still waiting after the wrong one


def unlocked(mode, base):
    mode.gate.not_before = 0
    status, headers, _ = request(base + "/api/unlock", {"code": mode.gate.code})
    assert status == 200 and "SameSite=Strict" in headers["Set-Cookie"]
    return headers["Set-Cookie"].split(";")[0]


def test_wifi_status_scan_and_join(setup_server):
    mode, base = setup_server
    cookie = unlocked(mode, base)
    data = json.loads(request(base + "/api/wifi", cookie=cookie)[2])
    assert data["can_change"] and data["before"]["ssid"] == "CarolNet" and data["minutes_left"] == 15
    assert [n["ssid"] for n in data["networks"]] == ["CarolNet", "Cafe"]
    data = json.loads(request(base + "/api/wifi/scan", {}, cookie)[2])
    assert data["fresh"] is False  # can't scan while it's a hotspot: the earlier list stays
    status, _, body = request(base + "/api/wifi/join", {"ssid": "CarolNet", "password": "short"}, cookie)
    assert status == 400 and "8 to 63" in json.loads(body)["error"]
    assert request(base + "/api/say", {"text": "hi"}, cookie)[0] == 409  # no tester in setup mode


def test_wifi_is_read_only_outside_setup_mode(tmp_path):
    from test_setup_page import FakeApp

    app = FakeApp(tmp_path)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        data = json.loads(request(base + "/api/wifi", cookie="tomo_setup=sess")[2])
        assert data == {"setup_mode": False, "can_change": False, "current": None}
        status, _, body = request(base + "/api/wifi/join", {"ssid": "x", "password": "12345678"},
                                  cookie="tomo_setup=sess")
        assert status == 409 and "setup mode" in json.loads(body)["error"]
    finally:
        srv.shutdown()
