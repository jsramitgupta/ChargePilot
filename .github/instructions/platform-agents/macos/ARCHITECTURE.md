# macOS Agent Architecture

## 1. Core architecture

The shipped client is a foreground Swift CLI that collects power data while
awake and while the process is running. It does not command switches or
manipulate Tuya devices. It uses the live tenant-scoped enrollment and
platform-aware telemetry contract. The installation ID is stored locally and
the per-install credential is stored in Keychain.

## 2. Components

- Power source service: reads battery state and charging metadata using Apple power APIs
- Identity manager: creates and preserves a random installation ID; server
  enrollment binds it to one endpoint and tenant
- Network uploader: sends the agreed versioned payload using the enrolled
  per-install credential
- Scheduler: determines when to read and transmit based on the user session and OS state
- Foreground status: reports last upload success/failure in the terminal;
  graphical status UI remains future work

## 3. Key design decisions

- battery checks should be opportunistic rather than a guaranteed real-time loop
- telemetry is uploaded over HTTPS using an additive backend contract; the
  legacy Windows payload/auth behavior remains unchanged
- app state should never replace backend validation or mapping rules
- no local auto-control logic should exist in the app

## 4. Data flow

1. app starts or wakes
2. retrieve installation identity and credential from secure storage
3. read battery state and available optional power-source metadata
4. build the agreed platform-aware payload; omit unavailable network data
5. send authenticated JSON through the enrolled per-install credential
6. update local success/failure state
7. retry later if upload fails

## 5. Acceptance criteria

- telemetry uses the platform-aware contract and never uses the tenant-wide
  Windows token
- the app is structured so a separate AI or engineer can swap scheduler details without changing server logic
- background and sleep behavior are documented as expected limitations
