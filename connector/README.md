# ChargePilot site connector

Run one connector on an always-on computer on the same LAN as the Tuya
switches. It uses an outbound WebSocket for command notifications and
authenticated HTTPS for durable command claim/results; no inbound firewall
rule is needed.

Version 0.1.5 and newer reconnects with backoff after network failures,
checks for queued work immediately after connecting, and periodically performs
a safety claim in case a notification was missed. Commands remain durable on
the server, so a WebSocket disconnect does not lose queued work. Older
connector versions continue to use HTTPS polling.

## Docker Compose (Linux)

Create a one-time enrollment code in ChargePilot. The published image and API
URL are already configured; the Docker-managed volume stores the permanent
connector credential on the local Docker host:

```yaml
services:
  chargepilot-connector:
    image: endusercompute/chargepilot-connector:sha-f9c01a016d3a2e706c8a50a12c3aa5ae73da38b2
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

If the image repository is private, ask the ChargePilot operator for Docker
Hub pull access and run `docker login` on the connector host before the first
pull. Do not put the registry token in this Compose file or reuse the
one-time enrollment code as a registry credential.

For an existing installation, update the image reference and redeploy the
service while keeping its `connector-data` volume; the saved credential does
not need to be enrolled again. Authenticate again before a later pull if the
Docker login session has been removed.

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

The published Docker image and Windows executable are the supported connector
distributions. Source archives and the source-based Python installer are not
served by ChargePilot. Use the immutable `sha-<commit>` tag for a pinned
deployment.

## Windows executable

The Windows build is a self-contained executable that installs and manages
the connector as an automatically starting Windows service. Download
`ChargePilotConnector.exe` from the authenticated **Site Connectors** page,
then open PowerShell as Administrator in the download folder:

```powershell
.\ChargePilotConnector.exe install --server-url "https://api.example.com"
```

The installer securely prompts for the one-time enrollment code and does not
accept it as a command-line argument. It stores the connector credential at
`%ProgramData%\ChargePilot\connector-config.json` with access for SYSTEM,
Administrators, and the service identity. The service runs as LocalService
and writes rotating logs under `%ProgramData%\ChargePilot\logs`. It requires
outbound HTTPS/WSS and local Tuya traffic (UDP 6666, 6667, 7000 and TCP 6668).

Use the executable with `status`, `start`, `stop`, or `uninstall` to manage the
service. For updates, stop the service, replace
`%ProgramFiles%\ChargePilot\Connector\ChargePilotConnector.exe` with a newly
downloaded build, and start the service. Uninstall removes local credentials
but does not revoke the server-side connector; revoke it in ChargePilot first
when retiring the host. Builds are unsigned, so Windows SmartScreen may show
an unknown-publisher warning. Source archives and a Python installer are not
served by ChargePilot; use an authorized checkout for source builds.
