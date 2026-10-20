# macOS Agent PRD

## 1. Product goal

The first deliverable is a native Swift foreground CLI that reports battery
state while the Mac is awake and the process is running. The platform-aware
backend enrollment and schema are implemented. Signed menu-bar/login-item
distribution is future work.

## 2. User value

- provides opt-in Mac telemetry to ChargePilot; new endpoint automation is
  disabled until an admin explicitly opts in
- supports ChargePilot's existing local-first design and site connector control path
- preserves a clear separation between telemetry and actual device control

## 3. Functional requirements

- read battery percentage and charging state from Apple power-source APIs
- include observation timestamp, platform, app version, installation identity,
  and explicit user-provided label; omit IP address and hardware serial
- authenticate using a per-install credential from the shipped enrollment flow
- store the credential in Keychain and installation metadata locally
- provide foreground success/failure status in the CLI
- expose graceful failure states when the network is unavailable or the backend rejects the report

## 4. Non-functional requirements

- must not perform any switch actions or local-device control logic
- must gracefully handle sleep, logout, and app termination
- must limit logging to safe operational diagnostics
- must keep backend identity and tenant validation rules authoritative

## 5. Success criteria

- the agent enrolls and uploads through the platform-aware API
- Windows telemetry and automation remain unchanged
- the backend can distinguish this agent without collecting a hardware serial
- stale, delayed, or invalid samples cannot trigger switch control
- the user can revoke/re-enroll without editing code or embedding a tenant token
