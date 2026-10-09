# Current State Summary

This file is the short operational summary for the repository as it stands today.

## Product
ChargePilot is a local-first battery automation platform for Windows laptops. It monitors laptop battery state and toggles local Tuya switches or plugs on the same LAN. The system includes a SmartLife/Tuya QR onboarding flow and a LAN discovery wizard to help import devices and local keys.

## Core runtime stack
- FastAPI
- SQLAlchemy
- PostgreSQL
- TinyTuya
- tuya-device-sharing-sdk
- Jinja2
- qrcode
- pytest

## Current primary workflows
1. PowerShell agent posts telemetry to /api/v1/telemetry.
2. Server validates endpoint token and timestamp.
3. Active mappings are evaluated using battery thresholds and cooldown logic.
4. Local switch state is updated via Tuya control.
5. Device events are logged and exposed in the UI.
6. Users can discover local devices and pair them through SmartLife/Tuya QR login.
7. SmartLife linked devices can be matched to local discovery results to fill IP and local key fields.

## Current important service modules
- app/services/rule_engine.py — threshold logic and hysteresis
- app/services/tuya_service.py — local device control / discovery
- app/services/smartlife_service.py — QR generation and linked-device polling
- app/services/broadcaster.py — SSE updates

## Current known implementation risks
- bearer-token validation remains intentionally minimal
- device payloads vary by Tuya firmware and hardware model
- SmartLife QR tokens may expire or respond invalidly; the system refreshes QR automatically when needed
- local keys and session data are sensitive and should never be committed to source control

## Instructions for future AI builds
Use the special docs under .github/instructions as the canonical source of truth for product, technical design, architecture, and deployment contexts. When rebuilding, do not assume the app is only a battery rule engine; it has a SmartLife/Tuya onboarding architecture as well.
