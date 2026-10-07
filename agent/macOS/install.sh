#!/bin/bash
set -eu

SERVER_URL="${1:-http://localhost:8000}"
ENDPOINT_TOKEN="${2:-test-endpoint-token}"
AGENT_VERSION="${3:-1.0.0}"
INSTALL_DIR="$HOME/Library/Application Support/ChargePilot"
SCRIPT_PATH="$INSTALL_DIR/BatteryAgent.sh"
CONFIG_PATH="$INSTALL_DIR/agent-config.json"
PLIST_PATH="$HOME/Library/LaunchAgents/com.chargepilot.agent.plist"

mkdir -p "$INSTALL_DIR"
cp "$(dirname "$0")/BatteryAgent.sh" "$SCRIPT_PATH"
chmod +x "$SCRIPT_PATH"

python3 - "$CONFIG_PATH" "$SERVER_URL" "$ENDPOINT_TOKEN" "$AGENT_VERSION" <<'PY'
import json, sys
from pathlib import Path
config_path = Path(sys.argv[1])
config_path.parent.mkdir(parents=True, exist_ok=True)
config = {
    'serverUrl': sys.argv[2],
    'endpointToken': sys.argv[3],
    'agentVersion': sys.argv[4],
}
config_path.write_text(json.dumps(config, indent=2), encoding='utf-8')
PY

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.chargepilot.agent</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$SCRIPT_PATH</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>300</integer>
</dict>
</plist>
PLIST

launchctl bootout gui/"$(id -u)" "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl bootstrap gui/"$(id -u)" "$PLIST_PATH" >/dev/null 2>&1 || true

printf 'Installed macOS ChargePilot agent.\n'
printf 'Script: %s\n' "$SCRIPT_PATH"
printf 'Config: %s\n' "$CONFIG_PATH"
printf 'Launch agent: %s\n' "$PLIST_PATH"
printf 'Next run: every 5 minutes.\n'
