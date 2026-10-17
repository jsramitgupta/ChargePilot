# ChargePilot site connector

The connector discovers and controls Tuya switches on the local network where
it runs. It communicates with ChargePilot using outbound HTTPS. No inbound
firewall rule is needed.

## Docker deployment (Linux, amd64 or arm64)

Use this option for an always-on Linux host such as a server, NAS, or Raspberry
Pi. Docker selects the matching `linux/amd64` or `linux/arm64` image
automatically.

1. Download and extract the connector package from **Connectors** in
   ChargePilot.
2. Copy `.env.example` to `.env`. For a local build, set
   `CHARGEPILOT_CONNECTOR_IMAGE=chargepilot-connector:local`; also set the
   HTTPS ChargePilot URL, enrollment-code file path, and persistent data
   directory. To use a published image instead, set the image to the immutable
   digest reference reported in the successful connector image workflow.
3. Create the enrollment code file at the path set in
   `CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE_FILE`. Paste the one-time code from
   the ChargePilot **Connectors** page into it. The connector runs as UID
   `10001`, so let that user read the secret while keeping it private:

   ```sh
   sudo chown 10001:10001 enrollment-code.txt
   sudo chmod 0400 enrollment-code.txt
   ```

   It is read only when the connector has no saved credential.
4. Make the persistent directory and let the container's unprivileged UID
   `10001` access it. For example:

   ```sh
   mkdir -p connector-data
   sudo chown 10001:10001 connector-data
   ```

5. For a local build, build the image and start the connector:

   ```sh
   docker build -f connector/Dockerfile -t chargepilot-connector:local .
   docker compose up -d
   docker compose logs -f chargepilot-connector
   ```

   If using a published image, pull its configured digest before starting:

   ```sh
   docker compose pull
   docker compose up -d
   ```

   The connector exchanges the one-time code for its permanent credential and
   saves it in `connector-data/connector-config.json`. The credential remains
   there across container recreation; back up and protect this directory.
6. Confirm the connector is online in ChargePilot. Select it as the scan
   location and assign discovered switches to it.

This Compose service uses Linux host networking so TinyTuya UDP discovery
reaches the local LAN. Permit outbound HTTPS to ChargePilot and local Tuya
traffic (commonly UDP 6666, 6667, 7000 and TCP 6668). Do not publish the
enrollment code, permanent credential, or data directory.

To deploy a newer published connector build, update the image digest in `.env`
to the reference reported by the successful GitHub Actions workflow, then run:

```sh
docker compose pull
docker compose up -d
```

## Python deployment (Windows, Linux, or macOS)

Install Python 3.12 or newer, extract the package, and open a terminal in the
extracted directory:

```powershell
python -m pip install -r requirements.txt
python -m connector.chargepilot_connector --server-url "https://YOUR-CHARGEPILOT-HOST"
```

Create an enrollment code on the ChargePilot **Connectors** page. When prompted
on the connector host, enter the one-time code. The connector saves its
permanent credential outside the extracted folder. Run it again under the same
host account to reconnect. Use the operating system's service manager to start
it at boot.

## Troubleshooting

- Keep the host online and connected to the same LAN as the switches.
- Verify outbound HTTPS connectivity to ChargePilot and local Tuya discovery
  traffic through the host firewall.
- If the connector is offline, inspect `docker compose logs
  chargepilot-connector` or the Python process logs.
- If discovery finds no switches, confirm LAN reachability and UDP ports 6666,
  6667, and 7000 plus TCP port 6668.
- Use an HTTPS server URL. HTTP is permitted only for loopback development.

Never commit or share the enrollment code, `connector-config.json`, or the
persistent connector data directory.
