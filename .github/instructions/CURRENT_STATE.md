# Current State Summary

This file is the short operational summary for the repository as it stands today.

## Product
ChargePilot is a cloud-capable, local-first battery automation platform for Windows laptops. It monitors laptop battery state and controls local Tuya switches through an outbound-HTTPS site connector on each device LAN. The system includes SmartLife/Tuya QR onboarding and connector-based LAN discovery.

## Core runtime stack
- FastAPI
- SQLAlchemy
- PostgreSQL
- TinyTuya
- HTTPS-polling site connector with PostgreSQL-backed commands
- tuya-device-sharing-sdk
- Jinja2
- qrcode
- pytest

## Current primary workflows
1. PowerShell agent posts telemetry to /api/v1/telemetry.
2. Server validates endpoint token and timestamp.
3. Active mappings are evaluated using battery thresholds and cooldown logic.
4. A durable desired-state command is routed to the switch's assigned connector.
5. The connector controls the device locally and acknowledges; resulting events/state are exposed in the UI.
6. Users can discover LAN devices through a connector and pair them through SmartLife/Tuya QR login.
7. SmartLife linked devices can be matched to connector discovery results to fill IP and local key fields.

## Current important service modules
- app/services/rule_engine.py — threshold logic and hysteresis
- app/services/tuya_service.py — local device control / discovery
- app/services/smartlife_service.py — QR generation and linked-device polling
- app/services/broadcaster.py — SSE updates
- app/services/connector_service.py — connector identity, command queue, lease, and result handling
- connector/chargepilot_connector.py — site-side TinyTuya runtime

## Current known implementation risks
- bearer-token validation remains intentionally minimal
- device payloads vary by Tuya firmware and hardware model
- SmartLife QR tokens may expire or respond invalidly; the system refreshes QR automatically when needed
- local keys and session data are sensitive and should never be committed to source control
- keep `CHARGEPILOT_ENCRYPTION_KEY` stable and backed up; it protects stored device local keys
- the cloud server does not scan or route to private device LANs; use a healthy connector and explicit device assignment

The full connector design, operational contract, and deployment plan is
documented in [CLOUD_CONNECTOR_ARCHITECTURE.md](CLOUD_CONNECTOR_ARCHITECTURE.md).

## Instructions for future AI builds
Use the special docs under .github/instructions as the canonical source of truth for product, technical design, architecture, and deployment contexts. When rebuilding, do not assume the app is only a battery rule engine; it has a SmartLife/Tuya onboarding architecture as well.
