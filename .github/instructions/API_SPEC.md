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
is the only browser UI; legacy page GETs redirect to the configured frontend.
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
the generated one-line PowerShell install command and whether the user is a
Super Admin; it does not expose tenant or global agent credentials. The
command downloads the installer over HTTPS and uses `iex`; the response is
marked `private, no-store`.

The following agent source downloads do not require a browser session and
contain no credentials. They issue a `302` redirect to the corresponding asset
on the latest stable `agents-v*` GitHub Release. The agent workflow publishes
these source files alongside the platform build artifacts:

- `GET /agent/download` redirects to the Windows PowerShell source ZIP.
- `GET /agent/macos/download` redirects to the Swift/macOS source ZIP.
- `GET /agent/android/download` redirects to the Kotlin/Compose Android source
  project ZIP.
- `GET /agent/ios/download` redirects to the SwiftUI Xcode project ZIP.
- `GET /agent/install.ps1` redirects to the scheduled-task installer used by
  the one-line command.
- `GET /agent/BatteryAgent.ps1` redirects to the telemetry script fetched by
  the installer.

Create an `agents-v*` release before deploying an API version that uses these
redirects; without a published agent release, the GitHub asset URLs are not
available. No application environment variable is required.

The authenticated **Set up a device** page links to the latest GitHub Release
for published platform builds: Android `app-debug.apk`, macOS
`ChargePilotAgent-0.1.0.dmg`, and iOS `ChargePilotAgent-0.1.0-unsigned.ipa`.
The Android APK is debug-signed; the macOS DMG is unsigned and not notarized;
the iOS IPA requires signing and provisioning before installation. The page
also links to each platform's source archive and gives installation steps.

- `GET /connectors/download` returns the Python/Docker source ZIP.
- `GET /connectors/install.sh` returns the Python bootstrap script; it prompts
  locally for the one-time connector enrollment code.

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
  "message": "Telemetry accepted for asynchronous automation processing."
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
- delayed telemetry can be retained in the outbox for diagnostics but cannot
  overwrite a newer endpoint snapshot or `last_seen_at`
- identifies an endpoint by `hardware_uuid`, while capturing the current
  hostname as mutable display metadata; a hostname change updates the existing
  hardware record rather than creating another endpoint
- identifies enrolled installations by their opaque per-install credential;
  platform and installation ID in the request must match the server-side
  endpoint record
- links a legacy endpoint without a hardware UUID to its UUID on the first
  matching telemetry for that tenant and hostname; existing endpoint IDs,
  mappings, and history are preserved
- relays the event to the `chargepilot.telemetry.v1` Kafka topic using a
  tenant/endpoint ordering key
- new enrolled endpoints have automation disabled until an authorized
  administrator opts in after a fresh sample. Workers independently check
  endpoint opt-in, platform allow-list, and sample age (600 seconds by
  default) before evaluating mappings
- Windows endpoints preserve their existing automation eligibility. New
  macOS endpoints are telemetry-only until explicitly enabled.
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
per-install credential. Windows protects the saved credential with Windows
user-scoped DPAPI; macOS and iOS store it in Keychain, and Android encrypts it
using Android Keystore. New Windows enrollments use an installation UUID
rather than a hardware UUID. Existing Windows agents using the legacy shared
token remain compatible during migration. Android has a debug APK build and
emulator smoke test; physical-device validation and signed distribution
remain pending. iOS has an unsigned device IPA build and simulator smoke test;
physical-device validation and signed distribution remain pending. The iOS
source exposes a Shortcuts action for fresh
battery/charging reports, but iOS may defer or skip its invocation.
Automation remains separately gated to the configured Windows/macOS
allow-list.

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
  credential locally (Windows user-scoped DPAPI, macOS/iOS Keychain, or
  Android Keystore). Each exchange creates a distinct endpoint identity bound
  to the request's platform and installation UUID.
- `POST /api/v1/endpoints/{endpoint_id}/credential/revoke` invalidates an
  enrolled endpoint credential and disables its automation. Re-enrollment
  currently requires deleting the old endpoint and creating a new
  installation identity.
- `PATCH /api/v1/endpoints/{endpoint_id}/automation` accepts
  `{"enabled":true|false}`. Enabling requires a recent sample and a platform
  allowed by `CHARGEPILOT_TELEMETRY_AUTOMATION_ENABLED_PLATFORMS`.
- Defaults are configured in `.env.example`: Windows, macOS, Android, and iOS
  are enabled for enrollment and telemetry. Automation remains limited to
  Windows/macOS by default; every enrolled endpoint starts with automation
  disabled and requires explicit admin opt-in after a fresh sample. Automation
  max age defaults to 600 seconds, ingress max age to seven days, and future
  skew to 300 seconds.

### 3.4 GET /api/v1/endpoints

Lists visible endpoint records with tenant ID/name, platform, installation
identity, battery, online/offline status, credential enrollment state, and
automation eligibility. Tenant names are `null` for unassigned endpoints.

Example response:

```json
[
  {
    "id": "...",
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

### 3.5 PATCH /api/v1/endpoints/{endpoint_id}/tenant

Assigns an unassigned endpoint to an existing tenant. Super Admin only.
Endpoints already assigned to another tenant cannot be transferred through
this operation, and an endpoint with mappings cannot be assigned. After
assignment, reconfigure the Windows agent with the tenant-specific token.

`DELETE /api/v1/endpoints/{endpoint_id}` removes an endpoint and its mappings.

```json
{"tenant_id": "<tenant-uuid>"}
```

### 3.6 GET /api/v1/endpoints/agent-config

Returns the endpoint's current agent configuration and mappings. Newly enrolled
agents authenticate with their per-install credential and must supply the
matching `endpoint_id` query parameter. The credential resolves to one endpoint
and tenant; a mismatched endpoint ID is not disclosed. Legacy Windows agents
may continue authenticating with their tenant/global token and identifying the
endpoint by `hardware_uuid` or hostname during migration. This route never
returns an endpoint credential.

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

### 4.4 GET /api/v1/devices/{device_id}/channels

Lists all channels for a device.

### 4.5 POST /api/v1/devices/{device_id}/channels

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

### 4.6 PUT /api/v1/devices/{device_id}

Updates device metadata.

### 4.7 DELETE /api/v1/devices/{device_id}

Deletes a device.

### 4.8 GET /api/v1/devices/channels/{channel_id}

Gets one channel.

### 4.9 PUT /api/v1/devices/channels/{channel_id}

Updates one channel.

### 4.10 DELETE /api/v1/devices/channels/{channel_id}

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

Request: `{"version":"0.1.2"}`

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

### POST /api/v1/connectors/heartbeat

Refreshes last-seen time and connector version. The connector sends its
credential and `{"version":"0.1.2"}`.

### POST /api/v1/connectors/commands/claim

Claims up to one command for that connector. Returns `{"command":null}` when no
work is waiting. State commands include metadata for a registered device
assigned to that connector; local keys are not returned from user-facing
device APIs.

Commands are persisted, leased, expire, and are eligible for bounded reclaim
after connection loss. Operations are allowlisted (`set_state`, `get_status`,
`discover`) and device commands are scoped to the authenticating connector.

### POST /api/v1/connectors/commands/{command_id}/result

Acknowledges a claimed operation:

```json
{"success":true,"result":{"state":true},"error":null}
```

Failures use `success: false`; discovery results contain normalized device
metadata and must not include local keys. Result bodies are size-limited.

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
  "turn_on_enabled": true,
  "on_threshold": 79,
  "off_threshold": 99,
  "turn_off_when_charging_enabled": false,
  "charging_off_threshold": 99,
  "minimum_state_change_interval": 300
}
```

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
