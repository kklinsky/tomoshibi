import json
import threading
import urllib.error
import urllib.request
from datetime import datetime
from http.server import ThreadingHTTPServer
from importlib import resources
from pathlib import Path

import numpy as np
import pytest

from tomoshibi import pronunciation
from tomoshibi.setup_page import in_quiet_hours, make_handler


class FakeApp:
    def __init__(self, data_dir: Path):
        self.conf, self.data_dir, self.device = {}, data_dir, "none"
        self.token, self.session = "tok", "sess"
        self.html = resources.files("tomoshibi").joinpath("setup_page.html").read_text(encoding="utf-8")
        self.spoken = []

    def speak(self, text, word="", say=""):
        words = pronunciation.load(self.data_dir)
        if word and say:
            words[word] = say
        self.spoken.append(pronunciation.Pronouncer(words).apply(text))
        return np.zeros(100, dtype=np.int16), 24000

    def log_change(self, client, action, **details):
        (self.data_dir / "changes.log").open("a").write(json.dumps({"action": action, **details}) + "\n")


@pytest.fixture
def server(tmp_path):
    (tmp_path / "people.yaml").write_text('people:\n  - id: ami\n    name: "Ami Stevens"\n', encoding="utf-8")
    (tmp_path / "profile.yaml").write_text("call_him: Arnold\n", encoding="utf-8")
    app = FakeApp(tmp_path)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield app, f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def request(url, data=None, cookie=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json", **({"Cookie": cookie} if cookie else {})})
    try:
        with urllib.request.build_opener(NoRedirect).open(req) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def test_needs_the_link_first(server):
    _app, base = server
    assert request(base + "/")[0] == 401
    assert request(base + "/api/pronunciations")[0] == 401
    assert request(base + "/api/say", {"text": "hi"})[0] == 401
    assert request(base + "/?t=wrong")[0] == 403
    status, headers, _ = request(base + "/?t=tok")
    assert status == 303 and "tomo_setup=sess" in headers["Set-Cookie"] and "SameSite=Strict" in headers["Set-Cookie"]


def test_try_save_and_list(server):
    app, base = server
    cookie = "tomo_setup=sess"
    assert request(base + "/", cookie=cookie)[0] == 200
    status, headers, body = request(base + "/api/say", {"text": "Ami called, Arnold.", "word": "Ami", "say": "Amy"}, cookie)
    assert status == 200 and headers["Content-Type"] == "audio/wav" and body[:4] == b"RIFF"
    assert app.spoken[-1] == "Amy called, Arnold."
    assert request(base + "/api/pronunciations", {"word": "Ami", "say": "Amy"}, cookie)[0] == 200
    _, _, body = request(base + "/api/pronunciations", cookie=cookie)
    data = json.loads(body)
    assert data["person"] == "Arnold" and data["entries"][0]["say"] == "Amy"
    request(base + "/api/say", {"text": "Ami called."}, cookie)
    assert app.spoken[-1] == "Amy called."  # saved pronunciation is used from now on
    assert "pronunciation saved" in (app.data_dir / "changes.log").read_text()
    assert request(base + "/api/pronunciations/delete", {"word": "Ami"}, cookie)[0] == 200


def test_quiet_hours():
    conf = {"quiet_hours": {"start": "00:00", "end": "07:00"}}
    assert in_quiet_hours(conf, datetime(2026, 10, 22, 3, 0))
    assert not in_quiet_hours(conf, datetime(2026, 10, 22, 7, 0))
    overnight = {"quiet_hours": {"start": "22:00", "end": "07:00"}}
    assert in_quiet_hours(overnight, datetime(2026, 10, 22, 23, 30))
    assert not in_quiet_hours(overnight, datetime(2026, 10, 22, 12, 0))
