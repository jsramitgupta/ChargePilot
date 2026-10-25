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
    image: endusercompute/chargepilot-connector:sha-6056b0205cd2e3927b279d68a95f56fbe008bef3
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

The published Docker image is the supported connector distribution. Source
archives and the source-based Python installer are not served by ChargePilot.
To build or modify the connector, use an authorized checkout of the private
repository.
