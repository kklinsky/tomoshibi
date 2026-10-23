"""The setup page (docs/DESIGN.md §10b). First version: only the pronunciation tester.

    tomoshibi setup-page [--host 0.0.0.0] [--port 8080]

For now it listens on the home network (not yet only on the setup hotspot and Tailscale,
as the design says). Access needs the one-time link printed at startup: opening it sets a
cookie, and every other request needs that cookie. The cookie is SameSite=Strict and the
API only accepts JSON, so other web pages can't use it on your behalf.
"""

import io
import json
import secrets
import threading
import time
import wave
from datetime import datetime
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path

import numpy as np
import yaml

from tomoshibi import audio, models, paths, pronunciation
from tomoshibi import config as cfg
from tomoshibi import tts as tts_mod

COOKIE = "tomo_setup"
MAX_TEXT = 300


def in_quiet_hours(conf: dict, now: datetime | None = None) -> bool:
    start = cfg.get(conf, "quiet_hours.start")
    end = cfg.get(conf, "quiet_hours.end")
    if not start or not end:
        return False
    now = now or datetime.now()
    minutes = now.hour * 60 + now.minute
    s = int(start[:2]) * 60 + int(start[3:5])
    e = int(end[:2]) * 60 + int(end[3:5])
    return s <= minutes < e if s <= e else minutes >= s or minutes < e


def wav_bytes(pcm: np.ndarray, rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.astype(np.int16).tobytes())
    return buf.getvalue()


class SetupApp:
    def __init__(self, conf: dict, lock_path: Path, data_dir: Path):
        self.conf = conf
        self.data_dir = data_dir
        self.token = secrets.token_urlsafe(12)
        self.session = secrets.token_urlsafe(24)
        specs = models.load_lock(lock_path)
        name = cfg.get(conf, "speech.tts_model")
        spec = models.find(specs, name) if name else models.first_of_kind(specs, "tts")
        self.tts = tts_mod.load(spec, length_scale=float(cfg.get(conf, "speech.tts_speed", 1.1)),
                                voice=cfg.get(conf, "speech.tts_voice"))
        self.tts_lock = threading.Lock()
        self.device = cfg.get(conf, "audio.device", audio.DEFAULT_DEVICE)
        self.html = resources.files("tomoshibi").joinpath("setup_page.html").read_text(encoding="utf-8")

    def speak(self, text: str, word: str = "", say: str = "") -> tuple[np.ndarray, int]:
        words = pronunciation.load(self.data_dir)
        if word and say:
            words[word] = say
        with self.tts_lock:
            return self.tts.synthesize(pronunciation.Pronouncer(words).apply(text))

    def log_change(self, client: str, action: str, **details) -> None:
        entry = {"when": datetime.now().isoformat(timespec="seconds"), "from": client,
                 "action": action, **details}
        with (self.data_dir / "changes.log").open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


def make_handler(app: SetupApp):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Tomoshibi"

        def log_message(self, fmt, *args):  # quieter than the default, and never logs the link code
            line = (fmt % args).replace(app.token, "...")
            print(f"  [setup page] {self.address_string()} {line}", flush=True)

        # --- helpers --------------------------------------------------------------
        def _authed(self) -> bool:
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            return COOKIE in cookie and secrets.compare_digest(cookie[COOKIE].value, app.session)

        def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, data) -> None:
            self._send(status, json.dumps(data).encode(), "application/json")

        def _body(self) -> dict | None:
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return None
            length = min(int(self.headers.get("Content-Length", 0) or 0), 10_000)
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return None
            return data if isinstance(data, dict) else None

        # --- routes ---------------------------------------------------------------
        def do_GET(self):
            path, _, query = self.path.partition("?")
            if path == "/" and query.startswith("t="):
                if secrets.compare_digest(query[2:], app.token):
                    self._send(HTTPStatus.SEE_OTHER, b"", "text/plain", {
                        "Location": "/",
                        "Set-Cookie": f"{COOKIE}={app.session}; HttpOnly; SameSite=Strict; Path=/",
                    })
                else:
                    self._send(HTTPStatus.FORBIDDEN, b"That link has expired. Use the one shown on the device.",
                               "text/plain; charset=utf-8")
                return
            if not self._authed():
                self._send(HTTPStatus.UNAUTHORIZED,
                           b"Open the link shown where the setup page was started.", "text/plain; charset=utf-8")
                return
            if path == "/":
                self._send(HTTPStatus.OK, app.html.encode(), "text/html; charset=utf-8")
            elif path == "/api/pronunciations":
                self._json(HTTPStatus.OK, {"entries": pronunciation.entries(app.data_dir),
                                           "person": _person_name(app.data_dir)})
            else:
                self._send(HTTPStatus.NOT_FOUND, b"Not found", "text/plain")

        def do_POST(self):
            if not self._authed():
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "Open the link shown where the setup page was started."})
                return
            data = self._body()
            if data is None:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "Expected a JSON request."})
                return
            client = self.client_address[0]
            if self.path == "/api/say":
                text = str(data.get("text", "")).strip()[:MAX_TEXT]
                if not text:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "Type something to say."})
                    return
                pcm, rate = app.speak(text, str(data.get("word", "")).strip(), str(data.get("say", "")).strip())
                if data.get("where") == "device":
                    if in_quiet_hours(app.conf):
                        self._json(HTTPStatus.CONFLICT, {"error": "It's quiet hours, so Tomo won't speak out loud."
                                                         " Listen in your browser instead."})
                        return
                    ok = _play_on_device(app.device, pcm, rate)
                    self._json(HTTPStatus.OK if ok else HTTPStatus.CONFLICT, {"played": ok} if ok else {
                        "error": "The speaker is busy (Tomo may be talking). Try again, or listen here."})
                    return
                self._send(HTTPStatus.OK, wav_bytes(pcm, rate), "audio/wav")
            elif self.path == "/api/pronunciations":
                word, say = str(data.get("word", "")), str(data.get("say", ""))
                try:
                    where = pronunciation.save(app.data_dir, word, say)
                except (ValueError, OSError, yaml.YAMLError) as e:  # bad input, or an edit that would break the file
                    self._json(HTTPStatus.BAD_REQUEST, {"error": f"Couldn't save: {e}"})
                    return
                app.log_change(client, "pronunciation saved", word=word.strip(), say=say.strip(), file=where)
                self._json(HTTPStatus.OK, {"saved": where})
            elif self.path == "/api/pronunciations/delete":
                word = str(data.get("word", ""))
                if pronunciation.remove(app.data_dir, word):
                    app.log_change(client, "pronunciation removed", word=word.strip())
                    self._json(HTTPStatus.OK, {"removed": True})
                else:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "No pronunciation for that word."})
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    return Handler


def _person_name(data_dir: Path) -> str:
    profile = pronunciation._yaml(data_dir / "profile.yaml")
    return str(profile.get("call_him") or profile.get("name") or "")


def _play_on_device(device: str, pcm: np.ndarray, rate: int) -> bool:
    import subprocess

    try:
        proc = subprocess.run(["aplay", "-q", "-D", device, "-f", "S16_LE", "-r", str(rate), "-c", "1", "-t", "raw"],
                              input=pcm.astype(np.int16).tobytes(), timeout=60, capture_output=True, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def serve(conf: dict, lock_path: Path, host: str = "0.0.0.0", port: int = 8080) -> None:
    data_dir = paths.data_dir()
    print(f"  [loading voice for the setup page; data in {data_dir}]", flush=True)
    app = SetupApp(conf, lock_path, data_dir)
    server = ThreadingHTTPServer((host, port), make_handler(app))
    shown = _lan_address() if host in ("0.0.0.0", "") else host
    print(f"\n  Setup page ready. Open this link (it works for this run only):\n"
          f"    http://{shown}:{port}/?t={app.token}\n", flush=True)
    started = time.time()
    try:
        server.serve_forever()
    finally:
        print(f"  [setup page stopped after {time.time() - started:.0f} s]")


def _lan_address() -> str:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "localhost"
