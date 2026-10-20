# iOS Agent Architecture

## 1. Core architecture

A native SwiftUI app reads battery state and uploads it after a platform-aware
backend schema and per-install enrollment flow are enabled. It does not make
automation decisions or claim to run continuously while suspended.

## 2. Components

- Battery state reader: reads `UIDevice` battery state and level
- Identity manager: stores a random installation ID; server enrollment binds
  it to one endpoint and tenant
- Upload service: uses HTTPS with a revocable per-install credential
- Scheduler: supports foreground and opportunistic upload behavior
- Status UI: shows last success, failure, and report freshness

## 3. Key design decisions

- the app should be explicit about the limits of background behavior
- telemetry must remain distinguishable from the backend's Windows behavior
- the app should never be engineered to emit switch commands or locally direct device actions

## 4. Data flow

1. app launches, returns to foreground, or user initiates a sync
2. read battery level and charging state
3. attach enrolled installation identity and platform metadata
4. send authenticated telemetry only after iOS enrollment is enabled
5. save last upload status
6. upload opportunistically when the OS permits background transfer

## 5. Acceptance criteria

- the app uses only public and supported APIs
- client uses the platform-aware schema and per-install credential, never the
  Windows shared tenant token
- delayed uploads and stale reports are handled as quality issues rather than deterministic automation events
