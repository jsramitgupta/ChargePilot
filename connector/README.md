# ChargePilot site connector

Run one connector on an always-on computer on the same LAN as the Tuya
switches. It uses outbound HTTPS; no inbound firewall rule is needed.

## Docker Compose (Linux)

Create a one-time enrollment code in ChargePilot. The published image and API
URL are already configured; the Docker-managed volume stores the permanent
connector credential on the local Docker host:

```yaml
services:
  chargepilot-connector:
    image: endusercompute/chargepilot-connector:sha-922f4aac9cef35276eef7814620f38d674720f73
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
      CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE: ${CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE:-}
      CHARGEPILOT_CONNECTOR_CONFIG: /data/connector-config.json
    volumes:
      - connector-data:/data

volumes:
  connector-data:
```

Pass the code only for first enrollment and start the published image:

```sh
read -rsp 'One-time ChargePilot code: ' CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE && echo && export CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE && docker compose up -d && unset CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE
```

Compose uses host networking for LAN discovery and stores the permanent
connector credential in its automatically created `connector-data` volume;
no host directory or ownership setup is required. The one-time code is
not included in shell history, but is available in Docker container metadata
while configured. After the connector is online, you can remove it from the
container configuration with `docker compose up -d --force-recreate` (without
setting the environment variable); the saved connector credential remains in
the volume. Permit outbound HTTPS and local Tuya traffic (UDP 6666, 6667, 7000
and TCP 6668).

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
