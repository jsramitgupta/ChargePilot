# Cross-Platform Telemetry Server Contract

**Status: implemented with platform-specific validation gaps.** The additive
platform-aware schema, tenant-scoped reusable 24-hour enrollment tokens,
hash-only per-install credentials, revocation, freshness checks, automation freshness policy, migration, and Windows/macOS/Android/iOS clients
are shipped. Self-service deregistration and re-enrollment are available in
the Windows, macOS, Android, and iOS clients. `agents-v*` releases publish
Windows, Android, iOS, and macOS binaries whether signing credentials are
configured or not. Each platform is signed and verified when its complete
signing-secret group is configured; otherwise the release notes and manifest
identify the asset as unsigned. Partially configured secret groups fail that
platform job. Android has an emulator smoke test; iOS has a simulator smoke
test. Physical-device validation and signed store distribution remain pending.

## Current server contract

Windows and macOS clients have been validated on their target platforms.
Android has an emulator smoke test and iOS a simulator smoke test; neither has
physical-device validation. The macOS SwiftUI menu-bar app provides enrollment,
background reporting, and optional launch-at-login behavior; further
distribution QA remains. The live `POST /api/v1/telemetry` schema is
`app/schemas/telemetry.py`:

All four shipped native clients use the fixed API origin
`https://api-chargepilot.endusercompute.in`; enrollment screens do not accept
a custom server URL or user-entered device label. Windows and macOS identify
the computer by its OS computer name, Android uses its non-unique model name,
and iOS uses a generic device type. Device serial numbers are not collected.
The enrollment token remains the server-generated, high-entropy, reusable
24-hour bearer token described below.

- required: `hostname`, `battery_percentage` (0–100), `charging`, `timestamp`,
  and `agent_version`
- optional: `hardware_uuid`, `installation_id`, `platform` (defaults to
  `windows`), `device_class`, `ip_address`, `ac_connected`, and `system_metrics`
- Existing Windows installations retain the `hardware_uuid` and shared-token
  behavior during migration; new installations on all four platforms exchange
  a reusable enrollment token for a backend endpoint ID and installation UUID
- the default ingress age limit is seven days, future skew is five minutes,
  and the automation freshness base is ten minutes before tenant-cadence
  scaling
- legacy shared-token auth remains accepted only for Windows during migration;
  new installations use tenant-bound, hash-only, revocable per-install
  credentials
- endpoint snapshots and outbox events are committed together; delayed
  samples cannot regress the current snapshot, and automation is checked
  asynchronously for endpoint state, platform eligibility, and freshness

See [API_SPEC.md](../API_SPEC.md) for the authoritative current contract.

## Tenant reporting cadence and resource samples

Tenant admins and managers configure one reporting interval for their tenant
through `GET`/`PUT /api/v1/admin/tenant-settings`; the supported range is 5 to
1440 minutes and the default is 5. Super Admins must explicitly select a
tenant. The telemetry response includes `reporting_interval_seconds`, which
Windows and macOS use to set their next report. Android stores the server
target but WorkManager repeats no more frequently than its 15-minute minimum.
iOS surfaces the configured target but has no guaranteed repeating background
schedule; reports remain foreground- and Shortcuts-triggered best-effort.
Freshness and online thresholds scale with the configured cadence while
remaining bounded by server settings.

The optional `system_metrics` object supports CPU/GPU utilization percentages,
used/total memory bytes, and up to 16 disks with a display name and used/total
bytes. Agents collect what their platform exposes. GPU utilization is
explicitly unavailable on macOS, Android, and iOS; other unsupported values
remain null/omitted rather than being reported as zero. These snapshots are
stored with battery readings for 30 days. Tenant-scoped
`GET /api/v1/endpoints/{endpoint_id}/details` returns endpoint identity,
status, cadence, mappings, and up to 100 recent samples for the React details
panel.

## Goals and guardrails

- Keep the Windows wire contract working during an additive migration.
- Use explicit platform metadata; never infer platform from hostname or version.
- Do not collect device serial numbers, IMEI, Wi-Fi identifiers, or location.
- Make a backend-generated endpoint ID and a random per-installation UUID the
  identity basis for new mobile sources; an app-generated ID is not claimed to
  be a hardware ID.
- Enable endpoint automation by default across Windows, macOS, Android, and
  iOS. Keep the server-side platform allow-list and 600-second freshness gate
  authoritative; mobile reports and background scheduling remain best-effort.
- Preserve tenant isolation, durable outbox processing, and the site connector
  boundary. Endpoint agents never control Tuya devices directly.

## Implemented contract and remaining work

### 1. Enrollment and per-install credentials (implemented)

Do not embed the existing tenant-wide token in a distributed agent. It can be
extracted and can authorize telemetry for the whole tenant. The enrollment
token is a high-entropy bearer secret and remains revealable by its creator
until it expires after 24 hours. Each admin may have at most five active
tokens across workspaces. The API stores the verifier as a hash and encrypts a
separate reveal value with `CHARGEPILOT_ENCRYPTION_KEY`.

The API provides a tenant-admin initiated, reusable 24-hour flow:

1. An authenticated tenant admin creates a high-entropy token scoped to their
   tenant. The token has no platform restriction and can enroll multiple
   devices until expiry or revocation. Never trust a client-supplied
   `tenant_id`.
   The creator may hide or reveal it while active; expired and revoked tokens
   are not listed.
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
| `hostname` | Keep existing field compatibility. Windows/macOS may use the OS computer name; Android may use its non-unique model name and iOS a generic model name. Do not collect serials or upload personal mobile device names. Admins can set a separate console display label. |
| battery fields | Keep valid numeric percentage and charging data required for rule evaluation. Model unavailable readings explicitly or skip reporting that sample; never substitute zero/false for unknown. |
| agent version | Keep required and version the client separately from the payload schema. |

Do not derive or transmit serial/IMEI on any platform. Reinstallation should
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
  automation after the effective processing age: the larger of the configured
  automation age (600 seconds by default) and twice the tenant reporting
  interval, capped by the ingress maximum age.
- Delayed telemetry does not regress the current snapshot or `last_seen_at`;
  its original timestamp is retained in the outbox payload.
- new enrolled endpoints have `automation_enabled=true` for all platforms.
  Existing endpoints are enabled by the reviewed data migration. The API and
  worker enforce the platform allow-list and sample freshness policy.
- Keep backend hysteresis, cooldown, tenant matching, and enabled mappings
  authoritative for every source.
- Tests cover duplicate/out-of-order Windows events, delayed snapshots,
  future-dated ingress, enrollment replay, identity mismatch, revocation, and
  automation default/freshness gates.

Do not set fixed per-platform "freshness" promises based on an OS scheduler.
The server scales its freshness and online windows with the tenant's
configured reporting interval; platform scheduling limits still apply and
these policy windows do not promise when the next sample will arrive.

### 4. Configuration (implemented)

The settings are implemented, validated, and listed in `.env.example`:

```text
CHARGEPILOT_TELEMETRY_MAX_AGE_SECONDS
CHARGEPILOT_TELEMETRY_MAX_FUTURE_SKEW_SECONDS
CHARGEPILOT_TELEMETRY_AUTOMATION_MAX_AGE_SECONDS
CHARGEPILOT_TELEMETRY_ENABLED_PLATFORMS
CHARGEPILOT_TELEMETRY_AUTOMATION_ENABLED_PLATFORMS
```

Telemetry, enrollment, and automation default to all four platforms. Endpoint
automation defaults on; operators may narrow the server platform allow-list.
Android has only been smoke-tested on an emulator; neither mobile client has
physical-device validation. Tagged release APKs are signed when the complete
Android secret group is configured; otherwise the published APK is unsigned.
The iOS release IPA uses ad-hoc signing when its complete signing group and
`APPLE_TEAM_ID` are configured, and is installable only on devices in its
provisioning profile; it is not an App Store distribution. Without those
secrets, the IPA is unsigned. The 600-second automation-age default is scaled
to the tenant's reporting interval; neither it nor the configured interval
means an OS scheduler guarantees report timing.

### 5. API, event, and operator surfaces

- `/api/v1/telemetry` accepts optional resource metrics and returns the
  tenant's interval in `reporting_interval_seconds`; focused tests cover
  validation, persistence, retention, and cadence behavior.
- Ensure the outbox contains the normalized platform and endpoint identity;
  retain the existing endpoint aggregate key, ordering, and event idempotency.
- Keep the existing Kafka topic and consumers backward-compatible; add
  platform metadata as optional fields rather than introducing a second topic
  without measured need.
- Expose platform and last-seen/report quality in endpoint list/detail APIs.
- Expose tenant cadence configuration to authorized administrators and
  tenant-scoped endpoint history through the React Endpoints details panel.
- Admins can see endpoint platform and enrollment state in the React Endpoints
  page and revoke endpoint credentials; a separate automation column is not
  shown. Automation defaults on and the backend continues to enforce
  eligibility.
  Raw credentials are never returned after enrollment.
- Treat invalid schema/authentication as request errors; do not acknowledge
  failed persistence or synthesize a success-shaped fallback.

### 6. Deployment and rollout

1. Back up an existing production database and apply the cross-platform SQL
   migration before deployment.
2. Apply `deploy/migrations/20261024_tenant_reporting_and_system_metrics.sql`
   before deploying the tenant cadence and resource-history behavior.
3. Deploy the backend and verify legacy Windows telemetry/automation.
4. Verify all-platform automation defaults and the cadence-scaled freshness
   policy with fresh test telemetry before creating mappings.
5. Review report age, rejected samples, outbox age, Kafka lag, endpoint
   ownership, and command results.
6. Complete Android and iOS acceptance testing and validate real-device
   behavior and privacy disclosures; mobile reports may be delayed or skipped.

Mobile HTTPS telemetry does not require local-network permission. If a future
client directly discovers or controls Tuya devices, that is a separate feature
requiring platform privacy review; it must not bypass the assigned site
connector.

## Delivery status

- [x] Enrollment code verifier and per-install credentials are tenant-bound
      and revocable; reveal material is encrypted at rest, while raw
      per-install credentials are returned only once.
- [x] Installation identity does not depend on serial/IMEI or a client-selected
      tenant.
- [x] Existing Windows telemetry and agent setup remain compatible.
- [x] PostgreSQL migration and rollback scripts are included.
- [x] Delayed, stale, duplicate, and future-dated paths have focused tests.
- [x] New enrolled endpoints default to automation enabled on all four
      platforms, subject to server-side freshness, platform, tenant, and
      enabled-mapping checks.
- [x] Agents support self-service deregistration and re-enrollment without
      reinstalling.
- [x] Android and iOS source projects and setup-page source downloads.
- [x] Android debug APK build and emulator smoke test.
- [x] iOS unsigned device IPA build and simulator smoke test.
- [x] Release workflow supports signed and unsigned tagged assets on Windows,
      Android, iOS, and macOS; configured signatures are verified and
      per-platform signing status is published with the release.
- [x] Client deregistration, local credential cleanup, and fresh-identity
      enrollment controls on Windows, macOS, Android, and iOS.
- [ ] Configure platform signing secrets and publish/verify signed builds for
      those platforms.
- [ ] Android/iOS physical-device QA and iOS App Store distribution review.
- [ ] macOS menu-bar/login-item acceptance QA.

## Agent release signing secrets

The `Build endpoint agent artifacts` workflow publishes unsigned platform
builds when a signing-secret group is entirely absent. If any secret in a
platform group is supplied, that group must be complete and its signature
verification must pass or the release is stopped. Store the following as
repository **Actions secrets** to enable signatures; never commit these values
or put them in source archives:

Agent versions come from `agent/VERSION` for development builds and from the
numeric `agents-vMAJOR.MINOR.PATCH` tag for releases. The same version is
embedded in all platform telemetry and platform package metadata; release IPA
and DMG filenames use that version. Android build numbers are derived from the
same version so updates have increasing package versions.

| Secret | Content |
| --- | --- |
| `ANDROID_KEYSTORE_BASE64` | Base64-encoded release JKS/PKCS12 keystore; keep this key for subsequent upgrades. |
| `ANDROID_KEYSTORE_PASSWORD` | Keystore password. |
| `ANDROID_KEY_ALIAS` | Release key alias. |
| `ANDROID_KEY_PASSWORD` | Release key password. |
| `WINDOWS_SIGNING_PFX_BASE64` | Base64-encoded Authenticode signing PFX. |
| `WINDOWS_SIGNING_PFX_PASSWORD` | PFX password. |
| `MACOS_DEVELOPER_ID_P12_BASE64` | Base64-encoded Developer ID Application certificate and private key. |
| `MACOS_DEVELOPER_ID_P12_PASSWORD` | P12 password. |
| `MACOS_DEVELOPER_ID_APPLICATION` | Exact Developer ID Application identity shown by `security find-identity`. |
| `IOS_DISTRIBUTION_CERTIFICATE_BASE64` | Base64-encoded Apple Distribution P12. |
| `IOS_DISTRIBUTION_CERTIFICATE_PASSWORD` | Distribution P12 password. |
| `IOS_ADHOC_PROVISIONING_PROFILE_BASE64` | Ad-hoc provisioning profile for `in.chargepilot.agent` with intended device UDIDs. |
| `APPLE_TEAM_ID` | Apple Developer Team ID. |
| `APPLE_ID` | Apple account used for notarization. |
| `APPLE_APP_SPECIFIC_PASSWORD` | App-specific password for that Apple account. |

`APPLE_TEAM_ID` is shared by the iOS and macOS signing groups. Supplying it
alone does not enable signing; each platform's complete set of platform
secrets is required. A partial platform group fails that platform's release
job.

Use a durable Android release key and back it up securely: replacing it
prevents existing installations from receiving in-place updates. The iOS
artifact is ad-hoc provisioned only for included device UDIDs, not an App
Store build. Credentials are not available in the current repository
configuration; do not claim an artifact is signed unless
`agent-release-manifest.json` says so. Branch/PR artifacts are development
builds and are not covered by the tagged-release signing checks.
