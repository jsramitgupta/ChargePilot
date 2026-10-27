# API Specification

## 1. Base URL and routing

The app is mounted under the FastAPI prefix configured in `app/core/config.py`:

```text
/api/v1
```

The root app is served by `app.main` and the main routes are registered as:

- `/health`
- `/ready`
- `/api/v1/telemetry`
- `/api/v1/endpoints`
- `/api/v1/devices`
- `/api/v1/connectors`
- `/api/v1/mappings`
- `/api/v1/events`

## 2. Authentication model

Telemetry ingestion requires a bearer token in the `Authorization` header.

Example:

```http
Authorization: Bearer <YOUR_AGENT_TOKEN>
```

The validation logic lives in `app/services/endpoint_service.py`. It accepts a tenant's configured agent token or the system-wide global token, which is generated randomly when the database is first initialized. Tenant tokens register and update endpoints for that tenant. The global token is for unassigned endpoints; use the tenant-specific token after assigning an endpoint to a tenant.

Browser authentication uses session cookies set by JSON requests to
`POST /api/v1/auth/login` and `POST /api/v1/auth/register`. The React frontend
is the only browser UI for the authenticated ChargePilot console; the separate
Next.js/Strapi documentation site does not provide product operations. Legacy
page GETs redirect to the configured frontend.
Both public signup modes require a Cloudflare Turnstile token, verified
server-side against the configured frontend hostname and the `registration`
action. Production signup fails closed if Turnstile is not configured.
Standard-user signup also requires a valid one-time tenant invite. Browser
mutations reject a supplied `Origin` that does not exactly match the configured
frontend origin. New accounts require a unique email address and configured
SMTP delivery. Signup creates a pending account and returns HTTP 202; the user
must verify a single-use, 30-minute email token before login is allowed.
`POST /api/v1/auth/verify-email` activates the account and starts a session.
`POST /api/v1/auth/resend-verification` requires another Turnstile challenge
and returns a generic response to avoid disclosing account existence.
Existing accounts and accounts created by administrators remain verified.
Signed-in users can contact the configured support inbox using
`GET /api/v1/support/config` and `POST /api/v1/support/email`. The recipient is
server-configured; requests cannot select arbitrary recipients. Email delivery
requires SMTP configuration. Tenant administrators, managers, and Super Admins
can invite managed roles by email. The single-use setup code is stored hashed;
the invited person sets a password before the account is created.

### 2.0 POST /api/v1/auth/login

Accepts JSON `{ "username": "...", "password": "..." }`, verifies the account,
sets the session cookie, and returns the signed-in user. Invalid credentials
return HTTP 401. Pending email verification returns HTTP 403.

### 2.0.1 POST /api/v1/auth/register

Tenant creation request:

```json
{"account_type":"tenant","username":"owner","password":"a-long-password","email":"owner@example.com","tenant_name":"Operations","turnstile_token":"one-time-provider-token"}
```

Creates a tenant and its first tenant-admin account, sends a verification
email, and returns HTTP 202 with `{"message":"Check your email for a link to
verify your account."}`. It does not establish a session until the email is
verified. SMTP credentials and `CHARGEPILOT_FRONTEND_URL` must be configured.
Standard-user request:

```json
{"account_type":"standard","username":"operator","password":"a-long-password","email":"operator@example.com","invite_code":"one-time-code","turnstile_token":"one-time-provider-token"}
```

Standard registration requires a tenant admin/manager generated code. The
database stores only its hash; the invite is consumed in the account-creation
transaction, can be used once, and expires after seven days. The raw code is
returned only when created.

### 2.0.2 POST /api/v1/auth/verify-email

Accepts `{"token":"..."}` from the verification email. Valid, unused tokens
expire after 30 minutes. Success marks the user email verified and establishes
the browser session. Expired, invalid, or replayed tokens return HTTP 422.

### 2.0.3 POST /api/v1/auth/resend-verification

Accepts `{"email":"...","turnstile_token":"..."}`. A new token invalidates any
prior pending verification link. The endpoint returns HTTP 202 with the same
generic message whether an unverified account exists or not.

### 2.0.4 Account invitation activation

- `POST /api/v1/auth/invitation-details` accepts `{"code":"..."}` and returns
  the invited username, email, role, workspace, and expiry for a valid,
  unused invitation. Responses are not cacheable.
- `POST /api/v1/auth/accept-invitation` accepts the same setup code and a
  password of at least 12 characters. It atomically consumes the invitation,
  creates the verified account, and establishes its session. A code cannot be
  reused.

### 2.0.4 Support contact

`GET /api/v1/support/config` reports whether SMTP is configured and which
support inbox receives messages. `POST /api/v1/support/email` accepts
`{"reply_email":"user@example.com","subject":"Help","body":"..."}` and sends
the message to `CHARGEPILOT_SUPPORT_RECIPIENT` (default
`chargepilot.support@endusercompute.in`). It requires an authenticated
session, uses the reply address only as `Reply-To`, limits the subject to one
line and the body to 5,000 characters, and returns HTTP 202 after SMTP accepts
the message.

### 2.1 PUT /api/v1/auth/password

Changes the authenticated user's password. The current password must match,
and the new password must be at least 12 characters and no more than 72 UTF-8
bytes.

Request:

```json
{
  "current_password": "current-password",
  "new_password": "a-new-password-with-12-characters"
}
```

The endpoint returns `{"message": "Password changed."}`. The signed-in
session remains active.

### 2.2 PUT /api/v1/auth/profile

Saves the authenticated user's display time zone. `timezone` must be a valid
IANA time-zone identifier (for example, `Asia/Kolkata` or `UTC`). The React
account page presents supported IANA zones in a region-grouped dropdown.

Request:

```json
{"timezone":"Asia/Kolkata"}
```

The response is `{"message":"Time zone saved.","timezone":"Asia/Kolkata"}`.

### 2.3 POST /api/v1/auth/logout

Clears the authenticated browser session and returns `{"status":"logged_out"}`.
React navigation then moves to the frontend login route without navigating the
browser to an API-host page.

### 2.4 GET /api/v1/admin/users

Lists user accounts visible to the signed-in Super Admin, tenant admin, or
tenant manager. Passwords and password hashes are never returned. Tenant admins
and managers see only users in their tenant.

### 2.5 GET /api/v1/admin/tenants

Lists tenants for Super Admin workflows. The response includes each tenant's
agent token, matching the existing Super Admin tenant-management screen. The
response is marked `private, no-store`.

### 2.6 Tenant invitations and administration

- `POST /api/v1/admin/account-invitations` accepts an email, username, role,
  and (for Super Admin) tenant. It sends the recipient a seven-day, one-time
  setup code and a link to choose a password. Email and a public frontend
  origin must be configured; raw codes are never returned by the API.
- `GET /api/v1/admin/account-invitations` lists invitation identity, status,
  and expiry within the caller's tenant scope.
- `DELETE /api/v1/admin/account-invitations/{invitation_id}` revokes an
  unused invitation. Sending a replacement for the same username or email
  invalidates its earlier active invitation.
- `POST /api/v1/admin/invites` creates a seven-day, single-use tenant invite.
  Tenant admins/managers can issue codes for their tenant; Super Admins must
  select the tenant. The raw code is returned once for legacy self-registration
  compatibility; the React People & Invites workflow uses account invitations.
- `GET /api/v1/admin/invites` lists status and expiry without code values.
- `DELETE /api/v1/admin/invites/{invite_id}` revokes an unused invite.
- `POST /api/v1/admin/users`, `PATCH /api/v1/admin/users/{user_id}`, and
  `DELETE /api/v1/admin/users/{user_id}` provide scoped account management
  while retaining at least one tenant administrator. Direct account creation
  remains available to existing integrations; the React UI uses emailed
  invitations instead.
- `POST /api/v1/admin/tenants` creates a tenant; `DELETE
  /api/v1/admin/tenants/{tenant_id}` removes its tenant-scoped records.
- Tenant telemetry credentials can be rotated with
  `POST /api/v1/admin/tenants/{tenant_id}/rotate-agent-token` (Super Admin) or
  `PUT /api/v1/admin/tenant-agent-token` (tenant admin/manager).
- `PUT /api/v1/admin/global-agent-token` saves or regenerates the Super Admin
  global endpoint token.

### 2.7 GET /api/v1/agent/setup

Returns the authenticated user's agent install command and token for the React
setup page. Requires an assigned tenant, except for the Super Admin. A Super
Admin may pass `tenant_id` to select a workspace. The response contains only
the generated one-line PowerShell bootstrap command and whether the user is a
Super Admin; it does not expose tenant or global agent credentials. The
bootstrap downloads the self-contained Windows service executable over HTTPS
and opens its elevated setup UI; the enrollment token is entered in that UI,
not on the command line. The API response is marked `private, no-store`.
The generated Windows command passes the public API origin to its installer,
which uses that origin both to download the executable and initialize the
setup UI. This supports self-hosted deployments when `CHARGEPILOT_API_URL` is
configured; when unset, the request's public origin is used. The origin is not
a credential and is not a device label. Native agent device names continue to
be derived from non-serial platform metadata. Enrollment uses the
server-generated high-entropy token.

### 2.8 GET /api/v1/agent/releases/latest

Returns the latest `agents-v*` release tag and supported `.exe`, `.dmg`,
`.ipa`, and `.apk` asset names and ChargePilot API URLs. It is public so native
agents can check for updates without a GitHub account. When the GitHub
repository is private, the API fetches release metadata using
`CHARGEPILOT_AGENT_RELEASE_GITHUB_TOKEN`, a fine-grained token scoped to this
repository with Contents: read permission. Store it only in the API runtime
secret. The response is cached publicly for five minutes and contains only
installable binaries, never source archives or direct GitHub URLs.

`GET /agent/releases/latest/download/{asset_name}` streams an allow-listed
binary from the latest `agents-v*` release through the API. The endpoint is
public, so it intentionally makes those binaries public; release source
archives are not returned. `GET /agent/ChargePilotAgent.exe` remains as a
compatibility route for the Windows installer. `GET /agent/install.ps1`
serves the installer script bundled in the API image.

GitHub network, status, invalid release metadata, and asset-download errors
return an explicit `502` response. Unsupported assets return `404`.
`GET /agent/download`, `/agent/macos/download`, `/agent/android/download`,
`/agent/ios/download`, and `/agent/BatteryAgent.ps1` return `410 Gone` because
they previously exposed source archives or legacy source code.

The **Set up a device** page lists the current Windows EXE, Android APK, macOS
DMG, and iOS IPA from this API. Tagged releases publish those binaries whether
or not signing secrets are configured. Each release includes
`agent-release-manifest.json` and notes identifying each platform as signed
or unsigned. The iOS signed option is ad-hoc provisioned for included devices,
not an App Store release. Partially configured signing-secret groups or
signature verification failures stop the release workflow.

`GET /connectors/download` and `GET /connectors/install.sh` return `410 Gone`.
Connector installation is supported through the published Docker Hub image;
the API no longer serves connector source code or a Python bootstrap installer.

## 3. Endpoint reference

### 3.1 GET /health

Returns app health status.

Response:

```json
{"status": "ok"}
```

### 3.2 GET /ready

Returns readiness only after a database connectivity query succeeds. If PostgreSQL is unavailable, the endpoint returns HTTP 503 with a database-unavailable detail.

Response:

```json
{"status": "ready"}
```

### 3.3 POST /api/v1/telemetry

Receives battery telemetry from Windows and enrolled platform agents. The API
commits the latest endpoint snapshot and a durable outbox event in one
PostgreSQL transaction; rule evaluation and switch commands happen
asynchronously in Kafka consumers.

Request schema (`app/schemas/telemetry.py`):

```json
{
  "hardware_uuid": "4b4b2b91-6c32-4d5b-8a9f-2a73b8e94d11",
  "platform": "windows",
  "device_class": "laptop",
  "hostname": "LAPTOP-01",
  "ip_address": "192.168.1.20",
  "battery_percentage": 82,
  "charging": false,
  "ac_connected": true,
  "switch_state": null,
  "system_metrics": {
    "cpu_usage_percent": 12.5,
    "gpu_usage_percent": null,
    "memory_used_bytes": 4294967296,
    "memory_total_bytes": 17179869184,
    "disks": [
      {"name": "System", "used_bytes": 128849018880, "total_bytes": 256060514304}
    ]
  },
  "timestamp": "2026-10-19T11:00:00Z",
  "agent_version": "1.0.0"
}
```

Validation rules:

- `hardware_uuid`: required to create a new endpoint; normalized as a UUID and
  unique across the installation. Existing legacy endpoints may omit it while
  matching their previously registered hostname.
- `platform`: `windows`, `macos`, `android`, or `ios`; omitted values default
  to `windows` for the existing PowerShell agent.
- `installation_id`: required for enrolled platform credentials and must
  match the ID assigned during enrollment. It is not hardware identity.
- `device_class`: optional (`laptop`, `desktop`, `phone`, or `tablet`), with
  platform-compatible combinations only.
- `hostname`: 1-160 chars
- `ip_address`: optional; if supplied, 7-64 chars
- `battery_percentage`: integer in range 0-100
- `charging`: required boolean. A sample without a usable battery reading
  must not be sent.
- `ac_connected`: optional boolean; `null` represents unavailable/unknown
  rather than a synthetic false value.
- `system_metrics`: optional resource snapshot. CPU/GPU utilization is a
  percentage in the range 0–100; memory and disk capacities are byte counts;
  each disk has a platform-provided name and used/total capacity. Individual
  unsupported or unavailable metrics are `null` or omitted; clients must not
  report zero as a substitute for unknown. At most 16 disks are accepted.
- `timestamp`: valid datetime; samples older than seven days or more than five
  minutes in the future are rejected by default.
- `agent_version`: 1-50 chars

Success response:

```json
{
  "status": "accepted",
  "hostname": "LAPTOP-01",
  "hardware_uuid": "4b4b2b91-6c32-4d5b-8a9f-2a73b8e94d11",
  "platform": "windows",
  "battery_percentage": 82,
  "message": "Telemetry accepted for asynchronous automation processing.",
  "reporting_interval_seconds": 1800
}
```

Behavior:

- validates either the existing tenant/global Windows token or a revocable
  per-install credential issued by endpoint enrollment
- legacy shared tokens are accepted only for Windows reports; other platform
  sources must resolve to their enrolled endpoint and tenant
- rejects telemetry older than seven days and timestamps more than five
  minutes ahead; both limits are configurable
- atomically updates or creates the endpoint snapshot and `TelemetryOutbox`
  record; a successful response means this transaction committed
- stores each accepted sample in battery-reading history, including optional
  system metrics; historical metrics are retained for 30 days
- returns the tenant's configured reporting interval in seconds so agents
  that support dynamic scheduling can update their next-report cadence
- delayed telemetry can be retained in the outbox for diagnostics but cannot
  overwrite a newer endpoint snapshot or `last_seen_at`
- identifies an endpoint by `hardware_uuid`, while capturing the current
  hostname as telemetry metadata; a hostname change updates the existing
  hardware record rather than creating another endpoint. The administrator-set
  display label is stored separately and is not overwritten by telemetry.
- identifies enrolled installations by their opaque per-install credential;
  platform and installation ID in the request must match the server-side
  endpoint record
- links a legacy endpoint without a hardware UUID to its UUID on the first
  matching telemetry for that tenant and hostname; existing endpoint IDs,
  mappings, and history are preserved
- relays the event to the `chargepilot.telemetry.v1` Kafka topic using a
  tenant/endpoint ordering key
- new enrolled endpoints default to automation enabled on all four platforms.
  Workers independently check endpoint enablement, platform allow-list, and
  sample age before evaluating mappings. The effective freshness limit is at
  least the configured automation age (600 seconds by default) or twice the
  tenant reporting interval, whichever is larger, capped by the ingress-age
  limit.
- `switch_state` remains in the wire schema for agent compatibility and does
  not override backend rules
- creates a durable desired-state connector command for connector-assigned
  devices; local direct control remains available for unassigned local devices
- records processing outcomes and sends invalid/exhausted events to the
  `chargepilot.telemetry.dlq.v1` dead-letter topic

Processing is at-least-once. Consumers deduplicate by event ID; clients should
not infer that rule evaluation or device control completed from the HTTP
acceptance response. Monitor outbox age, Kafka consumer lag, dead-letter volume,
and command completion.

Legacy PowerShell telemetry includes `hardware_uuid` and continues to use the
existing tenant/global bearer-token flow. New Windows installs use
platform-independent enrollment and a per-install credential instead.
Kafka-specific service settings use the `CHARGEPILOT_` prefix.

Agents on all four platforms exchange a tenant-scoped enrollment token for a
per-install credential. The Windows service protects its saved credential
with machine-scoped DPAPI in a SYSTEM/Administrators-only ProgramData
directory; macOS and iOS store it in Keychain, and Android encrypts it using
Android Keystore. New Windows enrollments use an installation UUID
rather than a hardware UUID. Existing Windows agents using the legacy shared
token remain compatible during migration. Android has a debug APK build and
emulator smoke test; physical-device validation and a signed release remain
pending. iOS has an unsigned device IPA build and simulator smoke test;
physical-device validation and signed release publication remain pending.
Tagged releases can include unsigned or signed builds per platform; the release
manifest reports the status.
The iOS source exposes a Shortcuts action for fresh battery/charging reports,
but iOS may defer or skip its invocation. Automation defaults to all four
platforms and remains subject to the server-configured allow-list and freshness
policy.
Agents use a non-serial OS computer/model name as the initial label; mobile
agents avoid uploading a personal device name. A tenant admin, manager, or
Super Admin can customize the separate display label from the Endpoints page.

#### Endpoint enrollment and automation operations

- `POST /api/v1/admin/endpoint-enrollments` creates a tenant-scoped,
  high-entropy, platform-independent token valid for 24 hours. One token can
  enroll multiple devices until expiry or revocation. Tenant admins/managers
  are scoped to their tenant; Super Admins must select a tenant. Each creator
  may have at most five active tokens across workspaces; expired and revoked
  tokens do not count. Creation returns the raw token with
  `Cache-Control: private, no-store`.
- `GET /api/v1/admin/endpoint-enrollments` lists only the requesting admin's
  active, unexpired tokens in their authorized tenant scope, including
  workspace name, expiry, and usage metadata. Raw tokens and hashes are never
  returned by this list operation.
- `GET /api/v1/admin/endpoint-enrollments/{enrollment_id}/token` reveals an
  active token to its creator until expiry, with `Cache-Control: private,
  no-store`. It returns 404 for a token the admin cannot access or one that is
  expired/revoked. A pre-existing token without an encrypted reveal value
  returns 409; revoke it and create a replacement.
- `DELETE /api/v1/admin/endpoint-enrollments/{enrollment_id}` revokes an
  enrollment token, including after it has enrolled devices. Revocation stops
  future exchanges and releases one active-token slot; revoke individual
  endpoint credentials to stop already-enrolled devices.
- `POST /api/v1/endpoint-enrollment/exchange` exchanges the code for a
  backend-created endpoint ID and per-install credential. The raw credential
  is returned once; only its SHA-256 hash is stored. Agents persist the
  credential locally (Windows machine-scoped DPAPI in ProgramData,
  macOS/iOS Keychain, or Android Keystore). Each exchange creates a distinct
  endpoint identity bound to the request's platform and installation UUID.
- `POST /api/v1/endpoints/{endpoint_id}/credential/revoke` invalidates an
  enrolled endpoint credential and disables its automation. Re-enrollment
  can be initiated by the agent itself through
  `POST /api/v1/endpoint-enrollment/deregister`, authenticated with its
  per-install credential. This revokes that credential, disables automation,
  and retains endpoint history; the client can then exchange a new enrollment
  token using a fresh installation identity without being reinstalled.
- `POST /api/v1/endpoint-enrollment/deregister` accepts an empty request (no
  body is required) and returns `204 No Content`. A valid per-install
  credential revokes itself and disables automation. If the credential is
  already revoked, invalid, or its endpoint record was deleted, the request
  succeeds as a no-op so the client can clear its stale local enrollment and
  re-enroll. It never changes a different endpoint.
- `PATCH /api/v1/endpoints/{endpoint_id}/automation` accepts
  `{"enabled":true|false}`. Enabling requires a recent sample and a platform
  allowed by `CHARGEPILOT_TELEMETRY_AUTOMATION_ENABLED_PLATFORMS`.
- New enrolled endpoints have automation enabled by default. The platform
  allow-list also defaults to Windows, macOS, Android, and iOS; an operator can
  narrow it with `CHARGEPILOT_TELEMETRY_AUTOMATION_ENABLED_PLATFORMS`.
  Workers still require a fresh sample, a tenant-matching enabled mapping,
  and the server-side battery rules before creating a command. The effective
  freshness limit is `min(ingress_max_age, max(automation_max_age,
  reporting_interval_minutes * 120))`; defaults are 600 seconds for
  `automation_max_age`, seven days for ingress max age, and 300 seconds for
  future skew. The endpoint automation API remains available for authorized
  administrators to pause or restore endpoint eligibility.

### 3.4 GET /api/v1/endpoints

Lists visible endpoint records with tenant ID/name, editable display label,
telemetry hostname, platform, installation identity, battery, online/offline
status, credential enrollment state, and automation eligibility. Tenant names
are `null` for unassigned endpoints. `display_name` falls back to `hostname`
until an administrator changes the label.

Example response:

```json
[
  {
    "id": "...",
    "display_name": "Office laptop",
    "hostname": "LAPTOP-01",
    "hardware_uuid": "4b4b2b91-6c32-4d5b-8a9f-2a73b8e94d11",
    "platform": "windows",
    "device_class": "laptop",
    "tenant_id": "...",
    "tenant_name": "Operations",
    "ip_address": "192.168.1.20",
    "battery": 82,
    "status": "online",
    "credential_enrolled": false,
    "automation_enabled": true,
    "automation_available": true,
    "mapped_device": "No mapped switch"
  }
]
```

`hardware_uuid` is nullable for endpoints created before the hardware-identity
upgrade. A current agent fills the value on its first matching telemetry
request, keeping the existing endpoint ID and mappings.

### 3.5 PATCH /api/v1/endpoints/{endpoint_id}/label

Tenant admins, managers, and Super Admins can set the endpoint's display label.
The label is trimmed, must contain 1-160 characters, and is stored separately
from the agent-reported hostname so future telemetry cannot overwrite it.

```json
{"label":"Office laptop"}
```

The response includes the updated `display_name`. This operation changes only
the console label; it does not change device identity or telemetry matching.

### 3.6 PATCH /api/v1/endpoints/{endpoint_id}/tenant

Assigns an unassigned endpoint to an existing tenant. Super Admin only.
Endpoints already assigned to another tenant cannot be transferred through
this operation, and an endpoint with mappings cannot be assigned. After
assignment, reconfigure the Windows agent with the tenant-specific token.

`DELETE /api/v1/endpoints/{endpoint_id}` removes an endpoint and its mappings.

```json
{"tenant_id": "<tenant-uuid>"}
```

### 3.7 GET /api/v1/endpoints/agent-config

Returns the endpoint's current agent configuration and mappings. Newly enrolled
agents authenticate with their per-install credential and must supply the
matching `endpoint_id` query parameter. The credential resolves to one endpoint
and tenant; a mismatched endpoint ID is not disclosed. Legacy Windows agents
may continue authenticating with their tenant/global token and identifying the
endpoint by `hardware_uuid` or hostname during migration. This route never
returns an endpoint credential.

### 3.8 GET /api/v1/endpoints/{endpoint_id}/details

Returns tenant-scoped endpoint identity and status, current reporting cadence,
automation eligibility, mappings, and recent battery/resource history. The
optional `limit` query parameter defaults to 100 and is limited to 1–100.
Each history entry includes battery/charging state and `system_metrics` when
the agent supplied it. Results are ordered oldest-to-newest for charting;
the API returns the newest samples within the requested limit. Each mapped
switch includes configured meter datapoints, its latest power value and sample
time, and current UTC-month energy and sample time. These readings remain
tenant-scoped through the endpoint's mappings. A missing or out-of-tenant
endpoint returns 404.

### 3.9 Tenant reporting schedule

`GET /api/v1/admin/tenant-settings` returns
`tenant_id`, `tenant_name`, and `telemetry_interval_minutes`. `PUT` accepts
`telemetry_interval_minutes` from 5 through 1440 inclusive. Tenant admins and
managers can read or update their own tenant's value. Super Admins must specify
the target tenant using `tenant_id` on both operations. Attempts to access a
different tenant are forbidden.

The default is five minutes. Accepted telemetry returns the configured value
as `reporting_interval_seconds`; clients apply it after the next successful
report. Windows and macOS use that server response for their next interval.
Android persists the value but WorkManager clamps repeating work to its
15-minute minimum. iOS displays the target cadence but only reports on
foreground/Shortcuts triggers; it cannot guarantee a repeating background
schedule. The API scales endpoint online and automation freshness windows to
at least twice the configured interval, bounded by configured server limits.

## 4. Device API

Authenticated JSON device operations:

- `POST /api/v1/devices/{device_id}/state` accepts `desired_state` and an
  optional `channel_id`. Connector-routed commands are queued durably; local
  devices retain direct LAN control.
- `PUT /api/v1/devices/{device_id}/connector` accepts a connector ID or `null`;
  only tenant administrators/managers can change assignments.
- `DELETE /api/v1/devices/{device_id}` removes the switch and its mappings and
  channels.

### 4.1 GET /api/v1/devices

Returns visible devices ordered by creation time, including `tenant_id` and
`tenant_name`.

### 4.2 POST /api/v1/devices

Creates a device record.

Required fields:

```json
{
  "name": "Living Room Plug",
  "device_id": "abc123",
  "ip_address": "192.168.1.42",
  "device_type": "default",
  "protocol_version": "3.5",
  "encrypted_local_key": "...",
  "enabled": true
}
```

Super Admins may include `tenant_id` to create a switch in a selected tenant;
the tenant must exist. Other users always create devices in their own tenant,
regardless of any supplied `tenant_id`.

### 4.3 GET /api/v1/devices/{device_id}

Retrieves one device by UUID.

### 4.4 PUT /api/v1/devices/{device_id}/meter-settings

Saves optional per-device Tuya meter datapoint configuration. The operation is
tenant-scoped and requires an authenticated session.

Request:

```json
{
  "power_dp_id": "cur_power",
  "power_multiplier": 0.1,
  "energy_dp_id": "add_ele",
  "energy_multiplier": 0.001,
  "energy_counter_type": "cumulative"
}
```

Reading IDs are stored internally. Use the discovery operation below to find
numeric readings from the configured switch; recognizable names are suggested
as power or energy, and other readings can be selected by their live sample.
Multipliers convert raw values to watts and kWh. The guided setup can shift a
raw reading by up to six decimal places and saves that choice in the existing
multiplier field. For example, raw power `591` with a one-place decimal shift
uses `power_multiplier: 0.1` and is recorded as `59.1 W`. No additional API
field or database migration is required for this scale adjustment.
`energy_counter_type` is `cumulative` (the API derives monthly deltas) or
`monthly` (the API uses the device's reported month counter). Each setting may
be disabled by sending a `null` datapoint ID. The response includes
configuration, latest power,
current UTC-month energy, independent `meter_power_sample_at` /
`meter_energy_sample_at` timestamps, and cumulative tracking start.
Unconfigured values are `null`, not zero.

### 4.4.1 POST /api/v1/devices/{device_id}/meter-discovery

Finds meter reading candidates from the current status of an enabled switch.
For a switch assigned to a site connector, the API returns `202 Accepted` with
a `command_id` and
the authenticated user polls `GET /api/v1/connectors/commands/{command_id}`.
The connector sends at most 32 finite, numeric readings (ID, sample, and
optional recognized power/energy role); it does not send the full device
status map. For an unassigned switch, the API reads it directly from the local
ChargePilot host, returns `200 OK` with the same candidate shape, and completes
the read in the request:

```json
{
  "candidates": [
    {
      "id": "cur_power",
      "label": "Power reading",
      "sample": 845,
      "suggested_role": "power"
    }
  ]
}
```

The route is tenant-scoped. It does not change switch state or persist
candidates. Unknown numeric readings are presented for user selection; the
API does not infer their units or meter meaning. Direct reads require the
ChargePilot host to reach the switch. In cloud hosting, assign an online site
connector on the switch LAN.

### 4.5 GET /api/v1/devices/{device_id}/channels

Lists all channels for a device.

### 4.6 POST /api/v1/devices/{device_id}/channels

Creates a new device channel.

Example body:

```json
{
  "channel_index": 1,
  "name": "Channel 1",
  "dp_id": "1",
  "enabled": true
}
```

### 4.7 PUT /api/v1/devices/{device_id}

Updates device metadata.

### 4.8 DELETE /api/v1/devices/{device_id}

Deletes a device.

### 4.9 GET /api/v1/devices/channels/{channel_id}

Gets one channel.

### 4.10 PUT /api/v1/devices/channels/{channel_id}

Updates one channel.

### 4.11 DELETE /api/v1/devices/channels/{channel_id}

Deletes one channel.

## 5. Site connector API

Connector endpoints are mounted at `/api/v1/connectors`. Enrollment uses a
one-time enrollment code. Connector heartbeat and command routes use the
connector-specific bearer credential. User-facing management routes use the
signed-in ChargePilot session and normal tenant authorization.

### GET /api/v1/connectors

Lists connectors visible to the authenticated user, including connector
`tenant_id`, `tenant_name`, active/enrolled status, and online status.

### POST /api/v1/connectors/enroll

Exchange a one-time enrollment code in the `Authorization: Bearer` header for a
connector ID and permanent credential. Codes expire after 15 minutes, are
single-use, and are returned only once.

Request: `{"version":"0.1.4"}`

Response:

```json
{"connector_id":"<uuid>","name":"Office LAN","token":"<secret-returned-once>"}
```

### POST /api/v1/connectors/enrollment-codes

Creates a connector and returns its single-use enrollment code once. Requires
Super Admin or tenant admin/manager access. Tenant admins are scoped to their
own tenant; a Super Admin must provide `tenant_id`.

Request:

```json
{"name":"Office LAN","tenant_id":"<tenant-uuid>"}
```

The response includes `id`, `name`, `enrollment_code`, and `expires_at`. Codes
expire after 15 minutes and are stored only as hashes. The response is marked
`private, no-store`.

### PATCH /api/v1/connectors/{connector_id}

Renames a connector without changing its tenant, credentials, or device
assignments. Accepts `{"name":"Warehouse LAN"}`. The name is trimmed and must
contain 1–160 characters. Super Admins and tenant administrators/managers may
rename connectors in their authorized tenant scope.

### POST /api/v1/connectors/heartbeat

Refreshes last-seen time and connector version. The connector sends its
credential and `{"version":"0.1.4"}`.

### POST /api/v1/connectors/commands/claim

Claims up to one command for that connector. Returns `{"command":null}` when no
work is waiting. Device commands include metadata for a registered device
assigned to that connector; local keys are not returned from user-facing
device APIs.

Commands are persisted, leased, expire, and are eligible for bounded reclaim
after connection loss. Operations are allowlisted (`set_state`, `get_status`,
`inspect_meter`, `discover`) and device commands are scoped to the authenticating connector.
For a connector-assigned switch with an enabled mapping and fresh,
automation-eligible endpoint telemetry, telemetry processing requests a live
`get_status` before evaluating battery rules. Idle command polling also
schedules mapped-switch status checks about once per minute. A successful
status result is reconciled using the endpoint's latest fresh battery and
charging sample, and any corrective `set_state` command still observes the
mapping's hysteresis, turn-on setting, charging cutoff, and cooldown. Stale,
disabled, or platform-disallowed telemetry cannot trigger reconciliation.

For devices with meter datapoints configured, idle command polling schedules
`get_status` work about once per minute when no other command is waiting. The
command includes only the configured datapoint IDs and conversion multipliers;
the connector returns normalized `power_watts` and `energy_total_kwh` values,
never the arbitrary DPS map. Meter data is ignored unless its corresponding
datapoint is configured.

### POST /api/v1/connectors/commands/{command_id}/result

Acknowledges a claimed operation:

```json
{"success":true,"result":{"state":true},"error":null}
```

Failures use `success: false`; discovery results contain normalized device
metadata and must not include local keys. Result bodies are size-limited.
Successful `get_status` or `set_state` results may also include configured
`power_watts` and `energy_total_kwh` values. Successful `inspect_meter`
results contain up to 32 finite numeric candidates and recognized role hints,
not the full status map. Cumulative counters are converted to UTC-month deltas
by the API; full-month totals require collection from the start of the month.

### GET /api/v1/connectors/commands/{command_id}

Returns a tenant-scoped command status (`queued`, `leased`, `succeeded`,
`failed`, or `expired`) and sanitized result.

### POST /api/v1/connectors/{connector_id}/revoke

Revokes the connector credential and unassigns its devices. Available to
tenant administrators/managers and the Super Admin.

### DELETE /api/v1/connectors/{connector_id}

Permanently deletes a revoked connector and its command history. Active
connectors must be revoked first. This action is tenant-scoped.

The authenticated **Connectors** page creates enrollment codes, shows
heartbeat status, and serves the connector package. The **Switches** page
assigns devices. Its `POST /devices/scan` discovery endpoint accepts an
optional JSON body:

```json
{"source":"server"}
```

`source` is `server` (the default, scans from the ChargePilot app runtime's
network) or `connector` (delegates to an online site connector). For remote
scans, pass `connector_id` to select a specific connector:

```json
{"source":"connector","connector_id":"<connector-uuid>"}
```

Both paths return normalized switch metadata without local keys. The server
scan requires the app host/container to have LAN access and permit TinyTuya
discovery traffic.

## 6. Mapping API

### 5.1 GET /api/v1/mappings

Returns all endpoint-to-device mappings.

### 5.2 POST /api/v1/mappings

Creates a mapping only when the endpoint and switch belong to the same
tenant. `GET /api/v1/mappings` includes the mapping's tenant name.

Example body:

```json
{
  "endpoint_id": "<endpoint-uuid>",
  "device_id": "<device-uuid>",
  "channel_id": "<channel-uuid>",
  "enabled": true,
  "use_case": "battery_cycle",
  "turn_on_enabled": true,
  "on_threshold": 79,
  "off_threshold": 99,
  "turn_off_when_charging_enabled": false,
  "charging_off_threshold": 99,
  "minimum_state_change_interval": 300
}
```

`use_case` is either `battery_cycle` (the existing battery-threshold
turn-on/turn-off behavior) or `switch_off_only`. The latter always disables
automatic turn-on, including when a client submits `turn_on_enabled: true`.
Existing mappings receive `battery_cycle` when the compatibility schema adds
the field. Turning off the switch and shutting down a Windows/macOS endpoint
is not supported: telemetry agents do not currently receive or execute
shutdown commands, so the management UI presents that choice as unavailable.

`turn_on_enabled` controls only automatic switch turn-on; when false, the
mapping may still turn an on switch off at `off_threshold`. The optional
charging-completion cutoff is enabled by
`turn_off_when_charging_enabled`. It uses the separate
`charging_off_threshold` and applies only when telemetry reports
`charging: true`; `ac_connected` alone does not activate it. Percentage
thresholds must be between 0 and 100, and the minimum interval cannot be
negative. Existing mappings default to turn-on enabled and charging cutoff
disabled.

### 5.3 GET /api/v1/mappings/{mapping_id}

Gets one mapping.

### 5.4 PUT /api/v1/mappings/{mapping_id}

Updates one mapping. `channel_id` may be set to a channel belonging to the
selected switch, or to `null` to target the whole switch.

### 5.5 DELETE /api/v1/mappings/{mapping_id}

Deletes one mapping.

## 6. Events API

### 6.1 GET /api/v1/events

Lists automation events ordered by newest first.

Example response:

```json
[
  {
    "id": "...",
    "event_type": "TURN_ON",
    "success": true,
    "reason": "battery 15% reached 79% rule",
    "endpoint_id": "...",
    "device_id": "...",
    "channel_id": "...",
    "previous_state": "false",
    "new_state": "true",
    "created_at": "2025-01-01T12:00:00Z"
  }
]
```

## 7. Data model notes

The main persisted models are:

- `Endpoint`
- `Device`
- `DeviceChannel`
- `Mapping`
- `AutomationEvent`

The app stores the last-seen timestamp, current switch state, last state change timestamp, and event reasons for later debugging.

## 8. Important implementation nuances

- `switch_state` may be explicit in the telemetry payload, but the service still applies rule evaluation when it is `null`.
- Device state is often nested under `dps` rather than a flat boolean field.
- Channel selection is required for multi-gang devices and directly affects the command sent to TinyTuya.
- Generic device labels (`switch`, `plug`, and `outlet`) are normalized to TinyTuya's `default` OutletDevice profile by both direct control and the site connector.
- The API layer is intentionally simple and should be treated as a local admin interface, not a public production API by default.
