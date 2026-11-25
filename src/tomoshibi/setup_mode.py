"""Setup mode: the "Tomoshibi-Setup" hotspot and the Wi-Fi part of the setup page (docs/DESIGN.md §10b).

It starts when someone at the device holds the button for 10 seconds and then presses it once
more (button.SetupGesture), or by itself after 5 minutes with no network. The screen then
shows the hotspot's name and password and a one-time 6-digit code; the setup page needs that
code. Setup mode turns itself off after 15 minutes.

A new Wi-Fi network is tried before the old profile is forgotten. If it can't reach the
internet within 2 minutes, its profile is deleted and the hotspot comes back, so a mistyped
password never strands the device.

It runs inside the main `tomoshibi chat` service (which holds the button and the screen), as
the `tomoshibi` user. Wi-Fi changes go through NetworkManager under a narrow polkit rule.
"""

import secrets
import threading
import time
from collections.abc import Callable

from tomoshibi import config as cfg
from tomoshibi import wifi
from tomoshibi.wifi import Network, NmcliError

CODE_DIGITS = 6
WRONG_WAIT = 3.0      # seconds before another code may be tried after a wrong one
MAX_WRONG = 5         # after this many wrong codes in a row the code changes...
LOCKOUT = 60.0        # ...and nobody can try for this long
TICK = 5.0            # seconds between checks (timeout, no network)


def status(text: str) -> None:
    print(f"  [setup mode] {text}", flush=True)


def new_code() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(CODE_DIGITS))


def spaced(code: str) -> str:
    return f"{code[:3]} {code[3:]}"


class CodeGate:
    """The one-time code that unlocks the setup page, with wrong guesses rate-limited.

    A code works once; after that (and after MAX_WRONG wrong guesses) a new one is shown."""

    def __init__(self, make_code: Callable[[], str] = new_code):
        self.make_code = make_code
        self.code = make_code()
        self.wrong = 0
        self.not_before = 0.0

    def check(self, guess: str, now: float) -> str:
        """"ok", "wrong", "wait" (too soon after a wrong one) or "changed" (too many wrong)."""
        if now < self.not_before:
            return "wait"
        guess = "".join(ch for ch in str(guess) if ch.isdigit())
        if secrets.compare_digest(guess.encode(), self.code.encode()):
            self.code, self.wrong = self.make_code(), 0
            return "ok"
        self.wrong += 1
        if self.wrong >= MAX_WRONG:
            self.code, self.wrong, self.not_before = self.make_code(), 0, now + LOCKOUT
            return "changed"
        self.not_before = now + WRONG_WAIT
        return "wrong"


def launch(conf: dict, face=None) -> "SetupMode | None":
    """Setup mode for the main service: watches for a lost network from its own thread and
    is ready for the button's gesture. None if switched off in config."""
    if not cfg.get(conf, "setup.enabled", True):
        return None
    from tomoshibi.setup_page import serve_setup_mode

    mode = SetupMode(conf, wifi.Nmcli(str(cfg.get(conf, "setup.wifi_device", "wlan0"))), face,
                     serve=lambda m: serve_setup_mode(m, conf))
    threading.Thread(target=mode.run_forever, daemon=True).start()
    return mode


class SetupMode:
    def __init__(self, conf: dict, net: wifi.Nmcli, face=None, log: Callable[..., None] | None = None,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
                 serve: Callable[["SetupMode"], object] | None = None):
        self.net, self.face, self.clock, self.sleep = net, face, clock, sleep
        self.log = log or (lambda *a, **k: None)
        self.serve = serve  # starts the web page; returns something with .shutdown()
        self.minutes = float(cfg.get(conf, "setup.minutes", 15))
        self.auto_start = bool(cfg.get(conf, "setup.auto_start", True))
        self.watch = wifi.NoWifiWatch(cfg.seconds(cfg.get(conf, "setup.no_network_after"), wifi.NO_WIFI_SECONDS))
        self.lock = threading.RLock()
        self.active = False
        self.reason = ""
        self.ends = 0.0
        self.password = ""
        self.gate: CodeGate | None = None
        self.sessions: set[str] = set()
        self.networks: list[Network] = []
        self.before: Network | None = None  # the network the device was on when setup mode started
        self.trying: str = ""               # the network being tried, if any
        self.result: dict | None = None     # how the last try went, for the page
        self.server = None
        self.address = wifi.HOTSPOT_ADDRESS
        self.port = int(cfg.get(conf, "setup.port", 80))

    # --- starting and stopping ------------------------------------------------------------
    def start(self, reason: str) -> None:
        with self.lock:
            if self.active:
                self.ends = self.clock() + self.minutes * 60  # a second gesture just restarts the clock
                self._show()
                return
            status(f"starting ({reason})")
            self._cleanup()
            try:
                self.before = self.net.current()
            except NmcliError:
                self.before = None
            self._scan(rescan=True)  # before the hotspot: the radio can't scan well while it's one
            self.password = wifi.new_hotspot_password()
            self.gate = CodeGate()
            self.sessions.clear()
            self.result = None
            self.reason = reason
            self.active = True
            self.ends = self.clock() + self.minutes * 60
            self._hotspot_up()

    def stop(self, note: str = "") -> None:
        with self.lock:
            if not self.active:
                return
            status(f"stopping{': ' + note if note else ''}")
            self.active = False
            self.sessions.clear()
            self.gate = None
            self._serve_off()
            self.net.stop_hotspot()
            self.watch.reset()
            self._card(None)

    def _hotspot_up(self) -> None:
        try:
            self.net.start_hotspot(self.password)
        except NmcliError as e:
            status(f"couldn't start the hotspot: {e}")
            self.active = False
            self._card(None)
            return
        self._serve_on()
        self._show()
        status(f"hotspot {wifi.HOTSPOT} is up; page at {self.url}")

    def _cleanup(self) -> None:
        """Leftovers from a run that was cut short (a crash or power cut mid-try)."""
        self.net.delete(wifi.TRIAL)
        self.net.delete(wifi.HOTSPOT)

    def _serve_on(self) -> None:
        if self.serve and self.server is None:
            try:
                self.server = self.serve(self)
            except OSError as e:
                status(f"couldn't start the setup page: {e}")

    def _serve_off(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server = None

    @property
    def url(self) -> str:
        return f"http://{self.address}" + ("" if self.port == 80 else f":{self.port}")

    # --- the periodic check -----------------------------------------------------------------
    def tick(self) -> None:
        now = self.clock()
        with self.lock:
            if self.active:
                if not self.trying and now >= self.ends:
                    self.stop("time's up")
                elif not self.trying:
                    self._show()  # the minutes left
                return
        if not self.auto_start:
            return
        try:
            connected = self.net.connected()
        except NmcliError:
            connected = True  # no NetworkManager here: nothing to fix
        if self.watch.update(now, connected):
            self.start("no network")

    def run_forever(self) -> None:
        self._cleanup()  # a hotspot left up by a crash would keep the device off its network
        while True:
            try:
                self.tick()
            except Exception as e:  # noqa: BLE001 - never let a hiccup end the watch for good
                status(f"check failed: {e}")
            self.sleep(TICK)

    # --- the screen -------------------------------------------------------------------------
    def _card(self, rows) -> None:
        if self.face is None:
            return
        from tomoshibi.face import info_card

        self.face.card(info_card(rows) if rows else None)

    def _show(self) -> None:
        if not self.active or not self.gate:
            return
        left = max(1, round((self.ends - self.clock()) / 60))
        rows = [("Setup mode", "title"),
                ("Join Wi-Fi", "label"), (wifi.HOTSPOT, "value"),
                ("Password", "label"), (self.password, "big"),
                ("Then open", "label"), (self.url.removeprefix("http://"), "value"),
                ("Code", "label"), (spaced(self.gate.code), "big")]
        if self.result and not self.result.get("ok"):
            rows.append((f"Couldn't join {self.result['ssid']}", "warn"))
        rows.append((f"Ends in {left} min", "note"))
        self._card(rows)

    # --- the page's side ------------------------------------------------------------------
    def unlock(self, code: str) -> tuple[str, str]:
        """(session, "") if the code is right, else ("", why not)."""
        with self.lock:
            if not self.active or not self.gate:
                return "", "Setup mode is off. Start it on the device."
            outcome = self.gate.check(code, self.clock())
            if outcome != "wrong":
                self._show()  # the code on the screen changed
            if outcome == "ok":
                session = secrets.token_urlsafe(24)
                self.sessions.add(session)
                return session, ""
            return "", {"wrong": "That code isn't right. Check the screen and try again.",
                        "wait": "Please wait a moment before trying again.",
                        "changed": "Too many wrong codes. A new code is on the screen; "
                                   "try again in a minute."}[outcome]

    def authed(self, session: str) -> bool:
        with self.lock:
            return self.active and any(secrets.compare_digest(session, s) for s in self.sessions)

    def _scan(self, rescan: bool) -> bool:
        try:
            self.networks = self.net.scan(rescan=rescan)
            return True
        except NmcliError as e:
            status(f"scan failed: {e}")
            return False

    def rescan(self) -> bool:
        """While the radio is a hotspot a fresh scan may not work; the list from just before
        the hotspot started is kept then. True if the list is fresh."""
        with self.lock:
            return self._scan(rescan=True)

    def wifi_status(self) -> dict:
        with self.lock:
            return {
                "setup_mode": self.active,
                "before": self.before.as_dict() if self.before else None,
                "networks": [n.as_dict() for n in self.networks],
                "trying": self.trying,
                "result": self.result,
                "minutes_left": max(0, round((self.ends - self.clock()) / 60)) if self.active else 0,
            }

    def join(self, ssid: str, password: str, hidden: bool = False, client: str = "",
             background: bool = True) -> str:
        """Start trying a network. Returns "" once started, or why it can't be."""
        ssid = ssid.strip()
        with self.lock:
            if not self.active:
                return "Setup mode is off. Start it on the device."
            if self.trying:
                return f"Tomo is already trying {self.trying}."
            if not ssid or len(ssid.encode()) > 32:
                return "Pick a network, or type its name (up to 32 characters)."
            seen = next((n for n in self.networks if n.ssid == ssid), None)
            # A network that isn't in the list is typed by hand: assume WPA2, as most are.
            security = seen.security if seen else ("WPA2" if password else "")
            problem = wifi.password_problem(password, security)
            if problem:
                return problem
            self.trying = ssid
        args = (ssid, password, security, hidden or seen is None, client)
        if background:
            threading.Thread(target=self.run_trial, args=args, daemon=True).start()
        else:
            self.run_trial(*args)
        return ""

    def run_trial(self, ssid: str, password: str, security: str, hidden: bool, client: str) -> None:
        start = self.clock()
        status(f"trying {ssid}")
        self._card([("Trying", "title"), (ssid, "value"),
                    ("This takes up to 2 minutes. The setup Wi-Fi is off meanwhile.", "note")])
        with self.lock:
            self._serve_off()
            self.net.stop_hotspot()
        try:
            old = [uuid for uuid, name in self.net.wifi_profiles() if name == ssid]
            self.net.add_trial(ssid, password, security, hidden)
            activated = self.net.up(wifi.TRIAL, wait=wifi.TRY_SECONDS - 10)
        except NmcliError as e:
            status(f"couldn't set up {ssid}: {e}")
            old, activated = [], False
        while True:
            online = bool(activated) and self.net.online()
            decision = wifi.trial_outcome(self.clock() - start, activated, online)
            if decision != "wait":
                break
            self.sleep(5)

        if decision == "keep":
            try:
                self.net.keep_trial(ssid, old)
            except NmcliError as e:  # it works now, but may not come back after a restart
                status(f"connected, but couldn't save it cleanly: {e}")
            self.log(client, "wifi changed", ssid=ssid, replaced=len(old))
            status(f"joined {ssid}; setup mode done")
            with self.lock:
                self.result = {"ssid": ssid, "ok": True}
                self.trying = ""
                self.active = False
                self.sessions.clear()
                self.gate = None
                self.watch.reset()
            self._card([("Connected", "title"), (ssid, "value"), ("Tomo is back online.", "note")])
            self.sleep(20)
            with self.lock:
                if not self.active:
                    self._card(None)
            return

        self.net.delete(wifi.TRIAL)
        why = ("Couldn't connect. The password may be wrong." if not activated
               else "Connected, but couldn't reach the internet.")
        self.log(client, "wifi try reverted", ssid=ssid, why=why)
        status(f"{ssid} didn't work ({why}); back to the setup hotspot")
        with self.lock:
            self.result = {"ssid": ssid, "ok": False, "why": why}
            self.trying = ""
            if self.active:
                self.ends = self.clock() + self.minutes * 60
                self._hotspot_up()
