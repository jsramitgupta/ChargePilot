# Product Requirements Document

## 1. Product vision

ChargePilot is a self-hosted local automation platform for Windows laptops. It monitors battery state, evaluates configurable thresholds, and toggles local smart switches or plugs on the same LAN. The current product is not a cloud service; it is a local-first control system that remains usable even when the device is offline from the internet.

The current product state extends the original battery automation idea with a missing but important layer: discovering and registering local Tuya devices via LAN scan, and optionally linking devices through the SmartLife/Tuya QR login flow when the user needs a local key or wants to import a device that was previously paired via the mobile app.

## 2. Problem statement

Users want an automatic way to keep a laptop or accessory powered in a safe, energy-aware pattern:

- turn on power when the battery is low
- turn off power when the battery is high enough
- keep behavior local to the LAN and avoid cloud dependence for day-to-day automation
- recover device details even when a device is not discoverable by IP alone

The codebase addresses this with:

- telemetry ingestion from a Windows laptop agent
- endpoint-to-device mapping for automation targets
- local Tuya switch discovery and control over the LAN
- SmartLife/Tuya QR login support for retrieving linked devices and local keys
- hysteresis-based threshold decisions and event logging

## 3. Target users

### Primary user

A self-hosting user with a Windows laptop, a local Tuya-compatible smart switch or plug, and a desire to automate charging behavior without depending on a cloud app or SaaS backend.

### Secondary users

- home-lab and office users who want local automation
- users managing multiple switches or plugs on a local network
- users who own devices that are only visible after a SmartLife/Tuya pairing or QR login
- admins who want a lightweight dashboard and event log for troubleshooting

## 4. Core user goals

1. Send laptop battery telemetry to a local ChargePilot server.
2. Identify or import the local switch or plug for a mapped endpoint.
3. Discover devices available on the LAN or recover them from a SmartLife linked-device session.
4. Auto-match discovered devices with SmartLife session state to populate local keys and IP addresses.
5. Automatically turn a switch on or off based on battery thresholds and cooldown rules.
6. Inspect endpoint, device, mapping, and event state from the dashboard or API.

## 5. Current product scope

### 5.1 Telemetry ingestion

- The system accepts authenticated telemetry from the PowerShell agent.
- Payload includes hostname, IP, battery percentage, charging status, AC status, switch state, timestamp, and agent version.
- The app records the latest battery state per endpoint and uses it to evaluate mappings.
- Stale telemetry is rejected, and invalid bearer tokens are rejected.

### 5.2 Local discovery and switch registration

- Users can run a LAN scan to discover Tuya devices on the local network.
- Discovered devices are shown in a device wizard for manual review and addition.
- Device forms accept name, device ID, IP, protocol version, channel count, and local key.
- Users can bulk auto-match local keys and IPs from the SmartLife session.

### 5.3 SmartLife/Tuya QR login flow

- Users can enter a SmartLife user ID and choose a QR scheme such as SmartLife or TuyaSmart.
- The app generates a QR image and returns it to the client.
- The user scans it in the SmartLife app.
- The app polls for linked devices and matches them to LAN-discovered devices.
- If the QR token is expired or invalid immediately, the server refreshes the QR automatically and returns the new payload without requiring the user to click retry manually.

### 5.4 Device mapping and automation

- An endpoint can be mapped to a device and optionally a specific channel.
- Each mapping carries `on_threshold`, `off_threshold`, and a cooldown interval.
- The rule engine makes a state decision based on the battery and the last state-change timestamp.
- Both direct switch actions and battery-driven automation are supported.

### 5.5 Operational visibility

- A dashboard plus Jinja pages show devices, endpoints, mappings, and events.
- Event logs capture decision reasons and success/failure status.
- SSE streaming is available for real-time update pushes to UI clients.

## 6. Functional requirements

### 6.1 Authentication and safety

- The app requires a bearer token for endpoint telemetry.
- The backend validates bearer data before accepting telemetry.
- Device actions should fail gracefully and leave an event trail even when control fails.

### 6.2 Local-control requirements

- Tuya state changes are performed by local-device access, not by cloud automation.
- The app supports channel-specific operations and nested DPS extraction.
- Device keys, IPs, and protocol metadata are required for local control to work reliably.

### 6.3 SmartLife credentials and device import

- QR generation must support PNG-first output with SVG fallback.
- QR payloads must embed the correct app-visible scheme (for example `smartlife--qrLogin?token=` or `tuyaSmart--qrLogin?token=`).
- The flow must persist session state long enough to match linked devices after scanning.
- The frontend should surface success/error info without blocking the user with browser alerts.

### 6.4 UX requirements

- The device wizard must support scanning, SmartLife login, device matching, and add-switch flows in one interface.
- AJAX responses should allow the UI to render refreshed QR payloads and update state without complete page reloads.
- Toasts should communicate status, warnings, and refresh actions clearly.

## 7. Non-functional requirements

### Security

- Secrets and local keys must be stored outside source control, ideally in environment variables or a local `.env` file.
- The SmartLife session should not be committed to source control.
- The app should not assume network trust beyond the local environment.

### Reliability

- Device discovery and control should be tolerant of missing metadata and transient API issues.
- The QR flow must degrade gracefully when the provider response is partial or expired.
- Telemetry should continue to work even if the battery agent is restarted or the network changes.

### Maintainability

- Core battery logic should remain separate from local-Tuya integration logic.
- SmartLife-specific code should stay isolated in a service layer.
- Dashboard behavior should remain simple enough to reason about without a separate frontend framework.

### Performance

- Battery telemetry processing is lightweight and synchronous enough for a local app.
- Discovery and QR polling are simple polling loops that operate within bounded timeout windows.

## 8. Constraints and assumptions

- This is a self-hosted, local-first system rather than a SaaS product.
- LAN access is required for device discovery and state changes.
- Local Tuya control depends on correct device IP, protocol version, and local key metadata.
- SmartLife QR login relies on the mobile app flow and provider TTL values, which can vary by response.
- The app currently favors a modular monolith instead of a microservice architecture.

## 9. Success criteria

The product is considered successful when:

- a Windows laptop sends telemetry to the app reliably
- the server updates endpoint state and evaluates mappings
- a smart switch toggles according to battery thresholds with hysteresis and cooldown rules
- a user can discover a device locally and add it from the wizard
- a user can log in via SmartLife QR, fetch linked devices, and auto-fill local key and IP values
- future rebuilds can recreate the same architecture without reverse-engineering the app

## 10. Key findings captured from the implementation

The current implementation shows that the project has matured from a basic battery rule engine into a hybrid product:

- it is still fundamentally a local battery automation engine
- it now also includes a LAN-discovery and SmartLife metadata onboarding path
- the main risk is device-specific behavior, especially QR expiry, local key extraction, and Tuya protocol variations
- operational UX matters: a user should be able to scan a QR, fetch devices, and auto-match them without manual debugging

This is the product model that future Claude-driven rebuilds should preserve.
