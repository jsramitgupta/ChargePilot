#!/bin/bash
set -u

SERVER_URL="${SERVER_URL:-http://localhost:8000}"
ENDPOINT_TOKEN="${ENDPOINT_TOKEN:-test-endpoint-token}"
AGENT_VERSION="${AGENT_VERSION:-1.0.0}"
CONFIG_PATH="${CONFIG_PATH:-$HOME/Library/Application Support/ChargePilot/agent-config.json}"
STATE_PATH="${STATE_PATH:-$HOME/Library/Application Support/ChargePilot/switch-state.json}"

if [ -f "$CONFIG_PATH" ]; then
  SERVER_URL="$(python3 - "$CONFIG_PATH" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
except Exception:
    data = {}
print(str(data.get('serverUrl') or data.get('server_url') or 'http://localhost:8000'))
PY
)"
  ENDPOINT_TOKEN="$(python3 - "$CONFIG_PATH" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
except Exception:
    data = {}
print(str(data.get('endpointToken') or data.get('endpoint_token') or 'test-endpoint-token'))
PY
)"
  AGENT_VERSION="$(python3 - "$CONFIG_PATH" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
except Exception:
    data = {}
print(str(data.get('agentVersion') or data.get('agent_version') or '1.0.0'))
PY
)"
fi

mkdir -p "$(dirname "$CONFIG_PATH")"
mkdir -p "$(dirname "$STATE_PATH")"

read_battery_details() {
  local raw
  raw="$(pmset -g batt 2>/dev/null || true)"

  if ! printf '%s\n' "$raw" | grep -qi 'Battery'; then
    printf '100\nfalse\nfalse\n'
    return 0
  fi

  python3 - "$raw" <<'PY'
import re, sys
text = sys.argv[1] or ""
text_l = text.lower()
match = re.search(r'(\d{1,3})\s*%', text)
percent = int(match.group(1)) if match else 100
charging = 'charging' in text_l or 'ac power' in text_l or 'charged' in text_l
ac_connected = 'ac power' in text_l or 'charging' in text_l or 'charged' in text_l
print(percent)
print('true' if charging else 'false')
print('true' if ac_connected else 'false')
PY
}

read_ip_address() {
  ipconfig getifaddr en0 2>/dev/null || \
  ipconfig getifaddr en1 2>/dev/null || \
  ifconfig 2>/dev/null | awk '/inet / && $2 != "127.0.0.1" {print $2; exit}' || \
  echo "0.0.0.0"
}

read_last_switch_state() {
  if [ -f "$STATE_PATH" ]; then
    python3 - "$STATE_PATH" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
except Exception:
    data = {}
value = data.get('switchState')
print('true' if str(value).lower() == 'true' else 'false')
PY
  else
    echo "false"
  fi
}

save_switch_state() {
  local state="$1"
  python3 - "$STATE_PATH" "$state" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
state = sys.argv[2].lower() == 'true'
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps({'switchState': state}), encoding='utf-8')
PY
}

get_switch_state() {
  local battery_percent="$1"
  local current_state="$2"

  if [ "$battery_percent" -le 30 ]; then
    echo "true"
    return 0
  fi

  if [ "$battery_percent" -ge 90 ]; then
    echo "false"
    return 0
  fi

  echo "$current_state"
}

BATTERY_INFO="$(read_battery_details)"
BATTERY_PERCENT="$(printf '%s\n' "$BATTERY_INFO" | sed -n '1p')"
BATTERY_CHARGING="$(printf '%s\n' "$BATTERY_INFO" | sed -n '2p')"
BATTERY_AC_CONNECTED="$(printf '%s\n' "$BATTERY_INFO" | sed -n '3p')"
HOSTNAME="$(hostname -s)"
IP_ADDRESS="$(read_ip_address)"
LAST_STATE="$(read_last_switch_state)"
SWITCH_STATE="$(get_switch_state "$BATTERY_PERCENT" "$LAST_STATE")"
save_switch_state "$SWITCH_STATE"

TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

python3 - "$SERVER_URL" "$ENDPOINT_TOKEN" "$HOSTNAME" "$IP_ADDRESS" "$BATTERY_PERCENT" "$BATTERY_CHARGING" "$BATTERY_AC_CONNECTED" "$SWITCH_STATE" "$TIMESTAMP" "$AGENT_VERSION" <<'PY'
import json, os, sys, urllib.request
server_url, endpoint_token, hostname, ip_address, battery_percent, charging, ac_connected, switch_state, timestamp, agent_version = sys.argv[1:]
payload = {
    'hostname': hostname,
    'ip_address': ip_address,
    'battery_percentage': int(battery_percent),
    'charging': charging.lower() == 'true',
    'ac_connected': ac_connected.lower() == 'true',
    'switch_state': switch_state.lower() == 'true',
    'timestamp': timestamp,
    'agent_version': agent_version,
}
body = json.dumps(payload).encode('utf-8')
url = f"{server_url.rstrip('/')}/api/v1/telemetry"
req = urllib.request.Request(url, data=body, headers={
    'Authorization': f'Bearer {endpoint_token}',
    'Content-Type': 'application/json',
}, method='POST')
try:
    with urllib.request.urlopen(req, timeout=30) as response:
        print(f"Telemetry sent successfully: {response.status}")
except Exception as exc:
    print(f"Failed to send telemetry: {exc}")
PY
