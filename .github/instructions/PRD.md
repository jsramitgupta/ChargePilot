# Product Requirements Document

## 1. Product vision

ChargePilot is a self-hosted battery automation platform for Windows laptops. It turns local smart switches on and off based on laptop battery thresholds with a local-first architecture that avoids cloud control for routine operations.

The product is designed for users who want their laptop charging or AC power flow to respond to battery state without relying on a vendor-managed cloud service.

## 2. Problem statement

The app addresses a practical need: some users want a laptop or accessory to be powered down when the battery is sufficiently charged, and powered back on when the battery is low enough. The product aims to provide that behavior in a local environment with explicit thresholds and a visible event trail.

The codebase implements that model through:

- telemetry ingestion from a Windows laptop agent
- endpoint-to-device mapping for automation targets
- local Tuya control over the LAN
- hysteresis-based threshold decisions
- auditing of device actions and failures

## 3. Target users

### Primary user

A self-hosting user who owns a Windows laptop and a local Tuya-compatible switch or outlet.

### Secondary users

- home lab or office users
- users who prefer local control over cloud-driven automation
- users who want a lightweight self-hosted automation system without a SaaS account

## 4. Core user goals

1. Send laptop battery telemetry to a local ChargePilot server.
2. Attach a laptop endpoint to a switch or channel.
3. Automatically turn a switch on when the battery drops below the configured level.
4. Automatically turn a switch off when the battery rises above the configured level.
5. Avoid rapid relay chatter with hysteresis and interval guards.
6. Inspect endpoint, device, and event data through the dashboard or API.

## 5. Functional requirements

### 5.1 Telemetry ingestion

- The system accepts authenticated telemetry from a battery agent.
- The telemetry includes hostname, IP, battery percentage, charging state, AC state, switch state, timestamp, and agent version.
- The system records the latest battery information per endpoint.
- The system rejects telemetry that is too old or missing a valid bearer token.

### 5.2 Device management

- The app allows registering a local Tuya switch or plug.
- Device metadata includes name, `device_id`, IP, protocol version, local key, and device type.
- Channel-based device topologies are supported with `DeviceChannel` records and per-channel index values.

### 5.3 Mapping and automation

- A laptop endpoint can be mapped to a device and optionally to a specific channel.
- Each mapping has an `on_threshold`, `off_threshold`, and cooldown window.
- The rule engine decides whether a state command should be sent.
- The app can process both automated and explicit state changes.

### 5.4 State control and automation logging

- A device can be turned on or off manually through the app flow or API.
- Channel-specific switching is supported.
- Every action produces an `AutomationEvent` with state before/after and success/error metadata.

### 5.5 Observability

- The dashboard shows summary data for endpoints, devices, and active mappings.
- Event logs record operational decisions and failures for debugging.

## 6. Non-functional requirements

### Security

- Secrets and local keys must live in environment variables or `.env` rather than source files.
- Telemetry routes require a bearer token.
- The app is intentionally local-only and does not require cloud access for automation.

### Reliability

- Switch calls should fail gracefully and not crash the request path.
- Device state should be recovered from live status checks when possible.
- Database state should remain visible for event troubleshooting.

### Maintainability

- The code should remain modular within a monolith.
- Device-specific logic should be centralized in the TinyTuya layer.
- Rule logic should be isolated from API concerns.

### Performance

- Battery telemetry processing is lightweight and synchronous enough for HTTP request handling.
- No message bus or background worker system is required for the first implementation.

## 7. Constraints and assumptions

- The project is self-hosted, not SaaS.
- Local network access is required for smart switch control.
- The Windows PowerShell agent is a supported part of the system design.
- This is a local prototype and not a multi-tenant platform.

## 8. Success criteria

The implementation is considered successful when:

- a laptop agent can send telemetry reliably
- the server updates endpoint state and evaluates mappings
- a Tuya switch state changes based on thresholds and cooldown rules
- event logs expose the reasoning and outcome of each state change
- the app remains functional in a local LAN environment without cloud automation

## 9. Scope and out-of-scope

### In scope

- battery telemetry ingestion
- threshold-based switching
- local Tuya control
- mapping and event inspection
- dashboard and REST interfaces

### Out of scope for the current codebase

- multi-user SaaS accounts
- mobile app frontend
- advanced scheduling, alerts, or cloud integrations
- distributed orchestration or queueing infrastructure

## 10. Product facts captured from the code

The implemented system currently assumes:

- `switch_state` can be sent from the laptop agent and used as an explicit override
- default charge thresholds are `79` and `99`
- minimum delay between changes is 300 seconds
- local device state may require `dps` extraction and channel awareness
- failure details should be visible in automation events for later diagnosis
