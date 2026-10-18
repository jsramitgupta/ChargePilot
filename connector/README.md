# ChargePilot site connector

Run one connector on an always-on computer on the same LAN as the Tuya
switches. It uses outbound HTTPS; no inbound firewall rule is needed.

## Docker Compose (Linux)

Create a one-time enrollment code in ChargePilot, then save it in
`enrollment-code.txt` beside this Compose file. The published image and API
URL are already configured:

```yaml
services:
  chargepilot-connector:
    image: endusercompute/chargepilot-connector:sha-6c647c97e88c1b0078bf9a7c000e36f76a52e86b
    container_name: chargepilot-connector
    network_mode: host
    restart: unless-stopped
    read_only: true
    tmpfs:
      - /tmp:rw,noexec,nosuid,size=16m
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    environment:
      CHARGEPILOT_CONNECTOR_SERVER_URL: https://api-chargepilot.endusercompute.in
      CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE_FILE: /run/secrets/enrollment_code
      CHARGEPILOT_CONNECTOR_CONFIG: /data/connector-config.json
    secrets:
      - enrollment_code
    volumes:
      - ./connector-data:/data

secrets:
  enrollment_code:
    file: ./enrollment-code.txt
```

Restrict the code file, prepare persistent storage, and start the published
image:

```sh
sudo chown 10001:10001 enrollment-code.txt
sudo chmod 0400 enrollment-code.txt
mkdir -p connector-data
sudo chown 10001:10001 connector-data
docker compose up -d
```

Compose uses host networking for LAN discovery and saves the permanent
connector credential under `connector-data`. Keep that directory private.
Permit outbound HTTPS and local Tuya traffic (UDP 6666, 6667, 7000 and TCP
6668).

## Python (Linux or macOS)

Install Python 3.12+, `curl`, and `unzip`. Create an enrollment code in
ChargePilot, then run this command from a terminal on the switch LAN:

```sh
curl -fsSL https://api-chargepilot.endusercompute.in/connectors/install.sh | sh
```

Enter the one-time code when prompted. The installer fetches the current
connector package, creates a private Python virtual environment, and saves the
permanent credential under
`~/.local/share/chargepilot/site-connector/connector-config.json`. Keep the
process running; use your operating system's service manager to start it at
boot. The command runs an installer served by ChargePilot; use it only if you
trust that HTTPS server. Set `CHARGEPILOT_CONNECTOR_SERVER_URL` first if using
a different ChargePilot API URL.

The source package is also available at
`https://api-chargepilot.endusercompute.in/connectors/download`.
Downloads contain code only; enrollment credentials are never included.

On Windows, download and extract the source package, then run:

```powershell
python -m pip install -r requirements.txt
python -m connector.chargepilot_connector --server-url "https://api-chargepilot.endusercompute.in"
```

Enter the one-time code when prompted. The connector saves its credential
under `%ProgramData%\ChargePilot`; run it under the same Windows account to
reconnect.
