#!/bin/sh
set -eu

SERVER_URL="${CHARGEPILOT_CONNECTOR_SERVER_URL:-__CHARGEPILOT_SERVER_URL__}"
INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/chargepilot/site-connector"
CONFIG_PATH="$INSTALL_DIR/connector-config.json"
PYTHON="$INSTALL_DIR/.venv/bin/python"
ARCHIVE="${TMPDIR:-/tmp}/chargepilot-site-connector-$$.zip"

if ! command -v python3 >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1 || ! command -v unzip >/dev/null 2>&1; then
    echo "Python 3, curl, and unzip are required." >&2
    exit 1
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'; then
    echo "Python 3.12 or newer is required." >&2
    exit 1
fi
python3 - "$SERVER_URL" <<'PY'
import ipaddress
import sys
from urllib.parse import urlsplit

url = urlsplit(sys.argv[1])
if not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
    raise SystemExit("ChargePilot server URL is invalid.")
if url.scheme == "https":
    raise SystemExit(0)
try:
    is_loopback = url.hostname.lower() == "localhost" or ipaddress.ip_address(url.hostname).is_loopback
except ValueError:
    is_loopback = False
if url.scheme != "http" or not is_loopback:
    raise SystemExit("ChargePilot server URL must use HTTPS; HTTP is allowed only for loopback development.")
PY
SERVER_URL="${SERVER_URL%/}"

mkdir -p "$INSTALL_DIR"
chmod 700 "$INSTALL_DIR"
trap 'rm -f "$ARCHIVE"' EXIT HUP INT TERM

curl --fail --location --silent --show-error "$SERVER_URL/connectors/download" --output "$ARCHIVE"
unzip -oq "$ARCHIVE" -d "$INSTALL_DIR"
rm -f "$ARCHIVE"
trap - EXIT HUP INT TERM

if [ ! -x "$PYTHON" ]; then
    python3 -m venv "$INSTALL_DIR/.venv"
fi
"$PYTHON" -m pip install --disable-pip-version-check --no-cache-dir -r "$INSTALL_DIR/requirements.txt"

if [ ! -f "$CONFIG_PATH" ]; then
    ENROLLMENT_CODE="$(python3 -c 'import getpass; print(getpass.getpass("One-time ChargePilot enrollment code: "))')"
    if [ -z "$ENROLLMENT_CODE" ]; then
        echo "The enrollment code cannot be empty." >&2
        exit 1
    fi
    export CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE="$ENROLLMENT_CODE"
    unset ENROLLMENT_CODE
fi

export CHARGEPILOT_CONNECTOR_CONFIG="$CONFIG_PATH"
cd "$INSTALL_DIR"
exec "$PYTHON" -m connector.chargepilot_connector --server-url "$SERVER_URL"
