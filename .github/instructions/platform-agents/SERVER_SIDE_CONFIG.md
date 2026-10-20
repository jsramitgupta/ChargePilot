# Cross-Platform Telemetry Server Contract

**Status: partially implemented.** The additive platform-aware schema,
tenant-scoped reusable 24-hour enrollment tokens, hash-only per-install
credentials, revocation, freshness checks, automation opt-in, migration, and
Windows/macOS agents are shipped. Kotlin/Compose Android and SwiftUI iOS
source projects are implemented, but have not yet been built on their native
toolchains or validated on physical devices; signed app releases are not
available.

## Current server contract

The device-validated clients are the Windows PowerShell agent and the macOS
Swift foreground CLI. Android and iOS source projects are available but are
not yet device-validated. The live `POST /api/v1/telemetry` schema is
`app/schemas/telemetry.py`:

- required: `hostname`, `battery_percentage` (0–100), `charging`, `timestamp`,
  and `agent_version`
- optional: `hardware_uuid`, `installation_id`, `platform` (defaults to
  `windows`), `device_class`, `ip_address`, and `ac_connected`
- Existing Windows installations retain the `hardware_uuid` and shared-token
  behavior during migration; new Windows and macOS installs exchange a
  reusable enrollment token for a backend endpoint ID and installation UUID
- the default ingress age limit is seven days, future skew is five minutes,
  and automation freshness is ten minutes
- legacy shared-token auth remains accepted only for Windows during migration;
  new Windows and macOS installs use tenant-bound, hash-only, revocable
  per-install credentials
- endpoint snapshots and outbox events are committed together; delayed
  samples cannot regress the current snapshot, and automation is checked
  asynchronously for opt-in/platform/freshness

See [API_SPEC.md](../API_SPEC.md) for the authoritative current contract.

## Goals and guardrails

- Keep the Windows wire contract working during an additive migration.
- Use explicit platform metadata; never infer platform from hostname or version.
- Do not collect device serial numbers, IMEI, Wi-Fi identifiers, or location.
- Make a backend-generated endpoint ID and a random per-installation UUID the
  identity basis for new mobile sources; an app-generated ID is not claimed to
  be a hardware ID.
- Make mobile endpoints telemetry-only by default. Do not allow them to trigger
  mappings until an explicit automation policy and freshness gate are shipped.
- Preserve tenant isolation, durable outbox processing, and the site connector
  boundary. Endpoint agents never control Tuya devices directly.

## Implemented contract and remaining work

### 1. Enrollment and per-install credentials (implemented)

Do not embed the existing tenant-wide token in a distributed agent. It can be
extracted and can authorize telemetry for the whole tenant. The enrollment
token is a high-entropy bearer secret, displayed only once, and must be
protected as a temporary secret during the 24-hour window.

The API provides a tenant-admin initiated, reusable 24-hour flow:

1. An authenticated tenant admin creates a high-entropy token scoped to their
   tenant. The token has no platform restriction and can enroll multiple
   devices until expiry or revocation. Never trust a client-supplied
   `tenant_id`.
2. The app exchanges that token over HTTPS for a backend-created endpoint ID
   and a high-entropy, per-install credential.
3. Store only a credential hash server-side; return the raw credential once
   and persist it securely on the client (Windows DPAPI, macOS/iOS Keychain,
   or Android Keystore).
4. Resolve the credential to one endpoint and tenant at ingestion. Admins can
   revoke either the shared enrollment token (preventing future exchanges) or
   an individual endpoint credential (stopping that endpoint).

Routes and payloads are specified in [API_SPEC.md](../API_SPEC.md). Do not
fall back silently to a shared tenant token.

### 2. Endpoint identity and telemetry schema (implemented)

The backward-compatible schema extension includes:

| Field | Recommendation |
| --- | --- |
| `platform` | Enum `windows`, `macos`, `android`, `ios`. Missing Windows values default to `windows`. |
| `device_class` | Optional enum such as `laptop`, `desktop`, `phone`, `tablet`; validate supported combinations. |
| `installation_id` | Random UUID generated once per app installation; unique in the credential/tenant scope. It is not hardware identity. |
| `ip_address` | Optional, volatile diagnostic value; mobile clients may omit it. Do not use it for identity or location inference. |
| `hostname` | Keep existing field compatibility. For mobile, prefer an explicit user-chosen label or a generic platform label; do not upload personal device names by default. |
| battery fields | Keep valid numeric percentage and charging data required for rule evaluation. Model unavailable readings explicitly or skip reporting that sample; never substitute zero/false for unknown. |
| agent version | Keep required and version the client separately from the payload schema. |

For mobile, do not derive or transmit serial/IMEI. Reinstallation should
create a new installation identity unless a documented, secure recovery flow
is designed. Resolve identity from the authenticated credential, not solely
from request JSON. Keep the existing `hardware_uuid` handling for Windows.

The backend, API serialization, SQL migration, and rollback are in the
repository. Apply
`deploy/migrations/20261020_cross_platform_telemetry.sql` before deploying to
an existing PostgreSQL installation; do not rely on startup `create_all()` to
upgrade production.

### 3. Freshness and automation safety (implemented)

Separate accepting/storing telemetry from deciding whether an event is safe to
automate on:

- The seven-day ingress age remains configurable; timestamps over five minutes
  in the future are rejected by default.
- Old queued samples may be stored for diagnostics but cannot trigger
  automation after the configured 600-second processing age.
- Delayed telemetry does not regress the current snapshot or `last_seen_at`;
  its original timestamp is retained in the outbox payload.
- New enrolled endpoints have `automation_enabled=false`. Admins can opt in
  only after a fresh sample, and both API and worker enforce the platform
  allow-list and freshness policy.
- Keep backend hysteresis and cooldown authoritative for any opted-in source.
- Tests cover duplicate/out-of-order Windows events, delayed snapshots,
  future-dated ingress, enrollment replay, identity mismatch, revocation, and
  opt-in/freshness gates.

Do not set fixed per-platform "freshness" promises based on an OS scheduler.
Measure real devices and use a conservative, server-side maximum sample age
for automation, distinct from UI online/offline presentation.

### 4. Configuration (implemented)

The settings are implemented, validated, and listed in `.env.example`:

```text
CHARGEPILOT_TELEMETRY_MAX_AGE_SECONDS
CHARGEPILOT_TELEMETRY_MAX_FUTURE_SKEW_SECONDS
CHARGEPILOT_TELEMETRY_AUTOMATION_MAX_AGE_SECONDS
CHARGEPILOT_TELEMETRY_ENABLED_PLATFORMS
CHARGEPILOT_TELEMETRY_AUTOMATION_ENABLED_PLATFORMS
```

Telemetry and enrollment default to all four platforms. Automation defaults
to Windows/macOS only, and each enrolled endpoint still requires explicit
admin opt-in. Android/iOS API acceptance does not mean native clients are
shipped or validated. Use the 600-second sample-age gate rather than assuming
OS schedulers guarantee a reporting interval.

### 5. API, event, and operator surfaces

- Update `/api/v1/telemetry` docs and tests for old and new payload versions.
- Ensure the outbox contains the normalized platform and endpoint identity;
  retain the existing endpoint aggregate key, ordering, and event idempotency.
- Keep the existing Kafka topic and consumers backward-compatible; add
  platform metadata as optional fields rather than introducing a second topic
  without measured need.
- Expose platform and last-seen/report quality in endpoint list/detail APIs
  before adding frontend filters.
- Admins can see endpoint platform, enrollment state, and automation
  eligibility in the React Endpoints page and revoke endpoint credentials.
  Raw credentials are never returned after enrollment.
- Treat invalid schema/authentication as request errors; do not acknowledge
  failed persistence or synthesize a success-shaped fallback.

### 6. Deployment and rollout

1. Back up an existing production database and apply the cross-platform SQL
   migration before deployment.
2. Deploy the backend and verify legacy Windows telemetry/automation.
3. Enable macOS enrollment for a test tenant; endpoints default to
   telemetry-only.
4. Review report age, rejected samples, outbox age, Kafka lag, and endpoint
   ownership before admin automation opt-in.
5. Implement Android and iOS clients, validate real-device behavior and
   privacy disclosures, then explicitly add them to the telemetry allow-list.

Mobile HTTPS telemetry does not require local-network permission. If a future
client directly discovers or controls Tuya devices, that is a separate feature
requiring platform privacy review; it must not bypass the assigned site
connector.

## Delivery status

- [x] Enrollment code and per-install credentials are tenant-bound, revocable,
      hashed at rest, and returned only once.
- [x] Installation identity does not depend on serial/IMEI or a client-selected
      tenant.
- [x] Existing Windows telemetry and agent setup remain compatible.
- [x] PostgreSQL migration and rollback scripts are included.
- [x] Delayed, stale, duplicate, and future-dated paths have focused tests.
- [x] New enrolled endpoints cannot trigger automation by default.
- [x] Android and iOS source projects and setup-page source downloads.
- [ ] Native mobile builds, physical-device QA, and signed distribution.
- [ ] Signed macOS menu-bar/login-item distribution and macOS-target build QA.
