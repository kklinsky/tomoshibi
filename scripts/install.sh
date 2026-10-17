#!/usr/bin/env bash
# Tomoshibi installer for Raspberry Pi OS Lite (64-bit) on a Raspberry Pi 5.
#
# Run as your normal user; it asks for your password when it needs sudo.
# Safe to re-run: it repairs an install and never overwrites config or data.
# See docs/DESIGN.md §10a.
#
#   install.sh                 install from GitHub (branch/tag given by --ref)
#   install.sh --source DIR    install from a local checkout (development)

set -euo pipefail

REPO_URL="https://github.com/kklinsky/tomoshibi.git"
UV_VERSION="0.12.2"
PREFIX="/opt/tomoshibi"
STATE_DIR="/var/lib/tomoshibi"
CONFIG_DIR="/etc/tomoshibi"
CACHE_DIR="/var/cache/tomoshibi"
SERVICE_USER="tomoshibi"
KEEP_RELEASES=3

SOURCE_DIR=""
REF="main"   # until there are tagged releases
REBOOT_NEEDED=0

usage() {
    sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
    echo "Options: --source DIR, --ref REF, -h/--help"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --source) SOURCE_DIR="$(cd "$2" && pwd)"; shift 2 ;;
        --ref) REF="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
    esac
done

step() { printf '\n==> %s\n' "$*"; }
ok()   { printf '    %s\n' "$*"; }
die()  { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

[[ $EUID -ne 0 ]] || die "Run this as your normal user, not with sudo. It will ask for your password when needed."
ADMIN_USER="$(id -un)"

# ---------------------------------------------------------------------------
step "Checking this Raspberry Pi"
model="$(tr -d '\0' </proc/device-tree/model 2>/dev/null || true)"
[[ "$model" == "Raspberry Pi 5"* ]] || die "Tomoshibi needs a Raspberry Pi 5 (this is: ${model:-unknown})."
[[ "$(uname -m)" == "aarch64" ]] || die "Tomoshibi needs the 64-bit version of Raspberry Pi OS."
# shellcheck source=/dev/null
. /etc/os-release
case "${VERSION_CODENAME:-}" in
    trixie|bookworm) ;;
    *) die "Unsupported OS: ${PRETTY_NAME:-unknown}. Use Raspberry Pi OS Lite (64-bit)." ;;
esac
avail_gb="$(df --output=avail -BG / | tail -1 | tr -dc '0-9')"
(( avail_gb >= 8 )) || die "Not enough free disk space (${avail_gb} GB free, need 8 GB)."
curl -fsS --max-time 15 -o /dev/null https://github.com || die "Can't reach the internet."
ok "$model"
ok "$PRETTY_NAME, ${avail_gb} GB free"

sudo -v || die "This installer needs sudo."

# ---------------------------------------------------------------------------
step "Installing system packages"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    git curl ca-certificates alsa-utils libportaudio2 libsndfile1 sqlite3 >/dev/null
ok "done"

# ---------------------------------------------------------------------------
step "Enabling SPI (for the screen)"
if [[ "$(sudo raspi-config nonint get_spi)" == "0" ]]; then
    ok "already enabled"
else
    sudo raspi-config nonint do_spi 0
    REBOOT_NEEDED=1
    ok "enabled (takes effect after a reboot)"
fi

# ---------------------------------------------------------------------------
step "Creating the '$SERVICE_USER' service user"
if id "$SERVICE_USER" &>/dev/null; then
    ok "already exists"
else
    sudo useradd --system --home-dir "$STATE_DIR" --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
    ok "created"
fi
for group in audio gpio spi video; do
    getent group "$group" >/dev/null && sudo usermod -aG "$group" "$SERVICE_USER"
done
# Let the admin read models/data and run tools as themselves (after next login).
if ! id -nG "$ADMIN_USER" | tr ' ' '\n' | grep -qx "$SERVICE_USER"; then
    sudo usermod -aG "$SERVICE_USER" "$ADMIN_USER"
    ok "added $ADMIN_USER to the $SERVICE_USER group (log out and back in to use it)"
fi

sudo install -d -m 755 -o root -g root "$PREFIX" "$PREFIX/releases"
sudo install -d -m 750 -o "$SERVICE_USER" -g "$SERVICE_USER" "$STATE_DIR" "$STATE_DIR/models"
sudo install -d -m 750 -o root -g "$SERVICE_USER" "$CONFIG_DIR"
sudo install -d -m 755 -o root -g root "$CACHE_DIR"

# ---------------------------------------------------------------------------
step "Installing uv $UV_VERSION (Python package manager)"
if command -v uv >/dev/null && [[ "$(uv --version | awk '{print $2}')" == "$UV_VERSION" ]]; then
    ok "already installed"
else
    curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" \
        | sudo env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh >/dev/null
    ok "installed $(uv --version)"
fi

# ---------------------------------------------------------------------------
step "Installing Tomoshibi"
staging="$(mktemp -d)"
trap 'rm -rf "$staging"' EXIT
if [[ -n "$SOURCE_DIR" ]]; then
    tar -C "$SOURCE_DIR" \
        --exclude=./.git --exclude=./.venv --exclude=./data --exclude=./sources --exclude=./review \
        --exclude=__pycache__ --exclude=.pytest_cache --exclude=.ruff_cache \
        -cf - . | tar -C "$staging" -xf -
    version="dev-$(date +%Y%m%d-%H%M%S)"
    ok "from local source $SOURCE_DIR"
else
    git clone --quiet --depth 1 --branch "$REF" "$REPO_URL" "$staging/src"
    version="$(git -C "$staging/src" describe --tags --always)"
    rm -rf "$staging/src/.git"
    staging="$staging/src"
    ok "from $REPO_URL ($REF)"
fi

release="$PREFIX/releases/$version"
if [[ -d "$release" ]]; then
    ok "release $version already installed"
else
    sudo cp -a "$staging/." "$release"
    sudo chown -R root:root "$release"
    sudo chmod -R u=rwX,go=rX "$release"
    ok "release $version"
fi

ok "installing Python and dependencies (first run takes a few minutes)"
sudo env \
    UV_PYTHON_INSTALL_DIR="$PREFIX/python" \
    UV_PYTHON_PREFERENCE=only-managed \
    UV_CACHE_DIR="$CACHE_DIR/uv" \
    uv sync --quiet --frozen --no-dev --no-editable --project "$release"

previous="$(readlink "$PREFIX/current" 2>/dev/null || true)"
sudo ln -sfn "$release" "$PREFIX/current"
sudo ln -sfn "$PREFIX/current/.venv/bin/tomoshibi" /usr/local/bin/tomoshibi
ok "current -> $version${previous:+ (previous: $(basename "$previous"))}"

# Keep the newest releases for rollback; never remove the current one.
mapfile -t old < <(ls -1dt "$PREFIX"/releases/* | tail -n +$((KEEP_RELEASES + 1)))
for dir in "${old[@]}"; do
    [[ "$dir" == "$(readlink -f "$PREFIX/current")" ]] || sudo rm -rf "$dir"
done

# ---------------------------------------------------------------------------
step "Config and data"
if [[ -f "$CONFIG_DIR/config.yaml" ]]; then
    ok "config.yaml exists, leaving it alone"
else
    sudo install -m 640 -o root -g "$SERVICE_USER" "$release/config/config.example.yaml" "$CONFIG_DIR/config.yaml"
    ok "created $CONFIG_DIR/config.yaml"
fi
if sudo test -f "$CONFIG_DIR/secrets.env"; then
    ok "secrets.env exists, leaving it alone"
else
    printf '# API keys and tokens. Readable only by the %s service.\n# ANTHROPIC_API_KEY=\n' "$SERVICE_USER" \
        | sudo tee "$CONFIG_DIR/secrets.env" >/dev/null
    sudo chown "$SERVICE_USER:$SERVICE_USER" "$CONFIG_DIR/secrets.env"
    sudo chmod 600 "$CONFIG_DIR/secrets.env"
    ok "created $CONFIG_DIR/secrets.env (empty)"
fi
if sudo test -d "$STATE_DIR/data"; then
    ok "data directory exists, leaving it alone"
else
    sudo cp -a "$release/examples/data" "$STATE_DIR/data"
    sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$STATE_DIR/data"
    ok "seeded $STATE_DIR/data with the fictional example family"
fi

# ---------------------------------------------------------------------------
step "Downloading speech models"
cd /   # the service user can't read the admin's home directory
sudo -u "$SERVICE_USER" env HF_HOME="$STATE_DIR/.cache/huggingface" HF_HUB_DISABLE_TELEMETRY=1 \
    /usr/local/bin/tomoshibi --lock "$release/models.lock" models fetch | sed 's/^/    /'

# ---------------------------------------------------------------------------
step "Self-test"
sudo -u "$SERVICE_USER" /usr/local/bin/tomoshibi --lock "$release/models.lock" doctor | sed 's/^/    /' || true

step "Finished"
ok "Not installed yet: the background service (there is no voice app to run yet)."
if (( REBOOT_NEEDED )); then
    ok "Please reboot to finish enabling SPI:  sudo reboot"
fi
