"""Wi-Fi through NetworkManager's `nmcli` (docs/DESIGN.md §10b).

Everything that touches the system goes through `Nmcli.run`, so tests swap in a fake. The
`tomoshibi` user may manage connections thanks to a narrow polkit rule (deploy/, installed by
install.sh); nothing here runs as root.

The pure decisions (is it time to start the hotspot, keep or revert a new network, which kind
of security a network needs) are plain functions and small classes with no I/O.
"""

import secrets
import socket
import subprocess
from dataclasses import dataclass

HOTSPOT = "Tomoshibi-Setup"        # both the network name and the NetworkManager profile name
TRIAL = "tomoshibi-trial"          # a new network's profile while it's being tried
HOTSPOT_ADDRESS = "10.42.0.1"      # NetworkManager's usual address for a shared connection
TRY_SECONDS = 120                  # a new network must reach the internet within this
NO_WIFI_SECONDS = 300              # this long with no network starts the hotspot by itself
PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o, 1/l/i: it's read off a small screen


class NmcliError(RuntimeError):
    pass


@dataclass
class Network:
    ssid: str
    signal: int
    security: str  # as nmcli shows it: "WPA2", "WPA1 WPA2", "WPA3", "" for open
    in_use: bool = False

    def as_dict(self) -> dict:
        return {"ssid": self.ssid, "signal": self.signal, "security": self.security,
                "open": not key_mgmt(self.security) and is_supported(self.security), "in_use": self.in_use}


# --- pure helpers -------------------------------------------------------------------------
def split_terse(line: str) -> list[str]:
    """One line of `nmcli -t` output: fields split on ':', with '\\:' and '\\\\' unescaped."""
    fields, field, escaped = [], [], False
    for ch in line:
        if escaped:
            field.append(ch)
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == ":":
            fields.append("".join(field))
            field = []
        else:
            field.append(ch)
    fields.append("".join(field))
    return fields


def parse_scan(text: str) -> list[Network]:
    """`nmcli -t -f IN-USE,SSID,SIGNAL,SECURITY dev wifi list` -> the strongest entry per name,
    strongest first. Hidden networks (no name) and our own hotspot are left out."""
    best: dict[str, Network] = {}
    for line in text.splitlines():
        parts = split_terse(line)
        if len(parts) < 4 or not parts[1] or parts[1] == HOTSPOT:
            continue
        security = "" if parts[3].strip() in ("", "--") else parts[3].strip()
        try:
            signal = int(parts[2])
        except ValueError:
            signal = 0
        net = Network(parts[1], signal, security, parts[0].strip() == "*")
        old = best.get(net.ssid)
        if old is not None:
            net.in_use = net.in_use or old.in_use
            if old.signal >= net.signal:
                net.signal, net.security = old.signal, old.security
        best[net.ssid] = net
    return sorted(best.values(), key=lambda n: (-n.in_use, -n.signal, n.ssid.lower()))


def is_supported(security: str) -> bool:
    """WEP and enterprise (802.1X) networks need more than a password field."""
    s = security.upper()
    return "WEP" not in s and "802.1X" not in s


def key_mgmt(security: str) -> str:
    """NetworkManager's key-mgmt for a scanned network: "" (open), "wpa-psk" or "sae" (WPA3 only)."""
    s = security.upper()
    if not s:
        return ""
    if "WPA3" in s and "WPA2" not in s and "WPA1" not in s:
        return "sae"
    return "wpa-psk"


def password_problem(password: str, security: str) -> str:
    """Why this password can't be right for the network, or "" if it might be."""
    if not is_supported(security):
        return "Tomo can't join this kind of network (it needs more than a password)."
    if not key_mgmt(security):
        return ""
    if len(password) == 64 and all(c in "0123456789abcdefABCDEF" for c in password):
        return ""
    if not 8 <= len(password) <= 63:
        return "Wi-Fi passwords are 8 to 63 characters long. Check it and try again."
    return ""


def new_hotspot_password() -> str:
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(8))


def trial_outcome(elapsed: float, activated: bool | None, online: bool, limit: float = TRY_SECONDS) -> str:
    """Keep a new network, revert to the old setup, or keep waiting.

    activated: None while NetworkManager is still connecting, then True or False."""
    if activated is False:
        return "revert"
    if activated and online:
        return "keep"
    if elapsed >= limit:
        return "revert"
    return "wait"


class NoWifiWatch:
    """True once the device has had no network for `limit` seconds in a row."""

    def __init__(self, limit: float = NO_WIFI_SECONDS):
        self.limit = limit
        self.since: float | None = None

    def update(self, now: float, connected: bool) -> bool:
        if connected:
            self.since = None
            return False
        if self.since is None:
            self.since = now
        return now - self.since >= self.limit

    def reset(self) -> None:
        self.since = None


# --- talking to NetworkManager ------------------------------------------------------------
class Nmcli:
    """A small wrapper around the `nmcli` commands Tomo needs."""

    def __init__(self, ifname: str = "wlan0"):
        self.ifname = ifname

    def run(self, *args: str, timeout: float = 30) -> str:
        try:
            proc = subprocess.run(["nmcli", *args], capture_output=True, text=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise NmcliError(str(e)) from e
        if proc.returncode != 0:
            raise NmcliError((proc.stderr or proc.stdout).strip() or f"nmcli exited {proc.returncode}")
        return proc.stdout

    # reading
    def scan(self, rescan: bool = True) -> list[Network]:
        return parse_scan(self.run("-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "dev", "wifi", "list",
                                   "ifname", self.ifname, "--rescan", "yes" if rescan else "no", timeout=45))

    def active(self) -> list[tuple[str, str, str]]:
        """Active connections as (name, type, device)."""
        rows = [split_terse(line) for line in self.run("-t", "-f", "NAME,TYPE,DEVICE", "con", "show",
                                                       "--active").splitlines() if line]
        return [(r[0], r[1], r[2]) for r in rows if len(r) >= 3]

    def connected(self) -> bool:
        """On some network other than our own hotspot: Wi-Fi or a cable."""
        return any(name != HOTSPOT and ctype in ("802-11-wireless", "802-3-ethernet")
                   for name, ctype, _ in self.active())

    def current(self) -> Network | None:
        """The Wi-Fi network the device is on now, if any (never the hotspot)."""
        for net in self.scan(rescan=False):
            if net.in_use:
                return net
        return None

    def wifi_profiles(self) -> list[tuple[str, str]]:
        """Saved Wi-Fi profiles as (uuid, ssid), leaving out our own two."""
        out = []
        for line in self.run("-t", "-f", "NAME,UUID,TYPE", "con", "show").splitlines():
            parts = split_terse(line)
            if len(parts) >= 3 and parts[2] == "802-11-wireless" and parts[0] not in (HOTSPOT, TRIAL):
                ssid = self.run("-g", "802-11-wireless.ssid", "con", "show", "uuid", parts[1]).strip()
                out.append((parts[1], ssid))
        return out

    def online(self) -> bool:
        """Can reach the internet: NetworkManager's own check, or else a plain connection."""
        try:
            state = self.run("networking", "connectivity", "check", timeout=20).strip()
        except NmcliError:
            state = "unknown"
        if state == "full":
            return True
        if state in ("none", "portal", "limited"):
            return False
        try:  # the check is switched off on this system: try for ourselves
            with socket.create_connection(("one.one.one.one", 443), timeout=5):
                return True
        except OSError:
            return False

    # changing
    def delete(self, name_or_uuid: str) -> None:
        try:
            self.run("con", "delete", name_or_uuid)
        except NmcliError:
            pass  # already gone

    def start_hotspot(self, password: str) -> None:
        self.delete(HOTSPOT)
        # proto/pairwise/group pinned to WPA2-CCMP: the Pi's Wi-Fi chip is picky as an access point.
        self.run("con", "add", "type", "wifi", "ifname", self.ifname, "con-name", HOTSPOT,
                 "autoconnect", "no", "ssid", HOTSPOT,
                 "802-11-wireless.mode", "ap", "802-11-wireless.band", "bg",
                 "ipv4.method", "shared", "ipv4.addresses", f"{HOTSPOT_ADDRESS}/24", "ipv6.method", "disabled",
                 "wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.proto", "rsn", "wifi-sec.pairwise", "ccmp",
                 "wifi-sec.group", "ccmp", "wifi-sec.pmf", "disable", "wifi-sec.psk", password)
        self.run("con", "up", HOTSPOT, timeout=45)

    def stop_hotspot(self) -> None:
        self.delete(HOTSPOT)  # deleting also takes it down; NetworkManager then rejoins known networks

    def add_trial(self, ssid: str, password: str, security: str, hidden: bool) -> None:
        """A profile for a network being tried. It doesn't connect by itself until it's kept."""
        self.delete(TRIAL)
        args = ["con", "add", "type", "wifi", "ifname", self.ifname, "con-name", TRIAL,
                "autoconnect", "no", "ssid", ssid]
        if hidden:
            args += ["802-11-wireless.hidden", "yes"]
        mgmt = key_mgmt(security)
        if mgmt:
            args += ["wifi-sec.key-mgmt", mgmt, "wifi-sec.psk", password]
        self.run(*args)

    def up(self, name: str, wait: float) -> bool:
        try:
            self.run("--wait", str(int(wait)), "con", "up", name, timeout=wait + 15)
            return True
        except NmcliError:
            return False

    def keep_trial(self, ssid: str, old_uuids: list[str]) -> None:
        """The new network works: forget the old profiles for that name and keep the new one."""
        for uuid in old_uuids:
            self.delete(uuid)
        self.run("con", "modify", TRIAL, "connection.id", ssid, "connection.autoconnect", "yes",
                 "connection.autoconnect-priority", "10")
