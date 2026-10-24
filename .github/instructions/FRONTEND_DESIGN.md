# Frontend Design Reference

This is the canonical reference for the ChargePilot browser UI. Keep it aligned
with `frontend/src/App.tsx`, `frontend/src/index.css`,
`frontend/src/theme.css`, and `tests/unit/test_ui_theme.py`.

## Product and interface goals

ChargePilot is an operational workspace for battery telemetry from multiple
device platforms and LAN-connected switches. Make live ownership, connectivity,
battery state, and automation outcomes easy to scan without obscuring the
underlying device relationships. Keep actions explicit and explain unavailable
or empty states with the next useful step.

The UI is React-only. FastAPI supplies JSON APIs and downloads; agent and
connector source archives are public, while setup APIs and credential
management require authentication. Do not add a second browser UI or use mock
data to fill gaps in API workflows.
Authenticated navigation remains left-aligned in a responsive rail.

## Routes and page responsibilities

`App.tsx` owns the route map, session-aware layout, page composition, and
browser interactions:

| Route | Responsibility |
| --- | --- |
| `/login` | Sign in to an existing account |
| `/register` | Create a tenant or complete legacy code-based standard-user signup |
| `/verify-email` | Explain and complete email verification |
| `/accept-invitation` | Review an emailed invitation and set the account password |
| `/` | Endpoint, switch, and energy overview with live telemetry summary |
| `/endpoints` | Review enrolled devices, edit display labels, ownership, recent battery/resource readings, and endpoint assignment |
| `/devices` | Review switches, channels, connector assignment, device state, and optional meter readings |
| `/mappings` | Create, edit, and remove endpoint-to-switch battery rules |
| `/events` | Review automation activity and outcomes |
| `/connectors` | Enroll and operate site connectors |
| `/profile` | Manage account details, display time zone, and password |
| `/users` | Invite people by email and manage roles and accounts |
| `/tenants` | Manage tenants as a Super Admin |
| `/agent` | Create device enrollment tokens and install available telemetry agents |
| `/account` | Redirect to the shared account settings page |
| `/support` | Send a support request |

All routes except sign-in, registration, and email verification require the
authenticated session. Keep tenant authorization and automation decisions in
the backend; presentation must not become an authorization or rule boundary.
The Set up a device page creates a tenant-scoped, platform-independent,
high-entropy enrollment token valid for 24 hours across multiple devices.
Each admin can have at most five active tokens across workspaces. The page
lists only that admin's active tokens, allows a token to be revealed or hidden
until expiry, and allows active tokens to be revoked. Expired and revoked
tokens are not shown. Windows, macOS, Android, and iOS agents exchange a token
for a per-install credential and persist it using platform-appropriate
protected storage. Existing Windows agents using shared tenant tokens remain
compatible during migration. Windows setup offers the PowerShell install
bootstrap, which downloads the executable and opens its setup UI, plus a direct
link to the Windows executable. The UI installs/configures a Windows service,
and lets users deregister and re-enroll without reinstalling; it does not use
Task Scheduler. The executable also provides CLI service controls, including
deregistration, and prompts for enrollment secrets instead of accepting
tokens as command-line arguments. The macOS, Android, and iOS agent UIs also
provide self-service deregistration and re-enrollment. The setup page links to
the latest GitHub Release for Windows, Android, iOS, and macOS builds, and
separately offers source projects. A release may contain signed and unsigned
builds across platforms depending on configured credentials; its release
notes and `agent-release-manifest.json` state the signing status for each.
Partially configured signing groups or failed signature verification stop the
release workflow. Signed iOS profiles limit which devices can install the
ad-hoc IPA. Explain how to install each build. Shipped agent enrollment screens
show the fixed `https://api-chargepilot.endusercompute.in` origin without
allowing edits. Device labels use non-serial platform metadata, and enrollment
asks only for the high-entropy token.
Clearly
explain Android's inexact WorkManager
timing and iOS Shortcuts automation best-effort limits. The iOS setup guidance
should suggest both a battery-level and charger-connected trigger and must not
promise exact timing. The page shows token expiry and enrollment count without
exposing token values unless its creator explicitly reveals one. Revoking a
token prevents new exchanges; admins separately revoke already-issued endpoint
credentials. The Endpoints page shows platform, enrollment state, and last-seen time to
the second; it does not include a separate endpoint automation column.
Selecting **View details** opens a tenant-scoped endpoint panel with identity,
current online/report state, configured cadence, automation eligibility,
device mappings, and up to 100 historical battery and system-resource samples.
Show CPU, memory, disk, and GPU values only when supplied; unsupported or
unavailable values remain explicitly unavailable rather than appearing as
zero. The Agent setup page lets tenant admins and managers choose a tenant-wide
reporting cadence from 5 minutes to 24 hours; Super Admins select the tenant.
The Windows and macOS agents apply the server's returned cadence. Android's
WorkManager cannot run more often than every 15 minutes, and iOS background
reporting remains best-effort, so explain these platform limits instead of
promising an exact schedule.
Endpoint automation is enabled by default for all four platforms, subject to
server-side platform and freshness checks. The Overview shows last-seen age as
a live relative time. The Connectors page supports a published
Docker Compose image with environment-based one-time enrollment and
Docker-managed persistent storage, and a one-line Python installer that
prompts locally for the enrollment code. Connector and agent source downloads
are public; code creation and credential management remain authenticated.
Mapping setup advances only on an explicit user action and saves only from its
explicit create/save action.
The mapping stepper places each label below its numbered marker; connector
segments join the markers only and never run behind step text. Keep this layout
at narrow widths so longer step names wrap without crossing the progress line.
The mapping rule editor can disable automatic turn-on independently from the
regular turn-off threshold, and can enable a separate charging-completion
cutoff that uses the selected device's `charging` telemetry flag. Show threshold labels
in a wrapping legend rather than overlaid on the battery scale so coincident
thresholds remain legible.
Endpoint automation defaults on separately from an individual mapping's
enabled state; the server enforces platform eligibility, sample freshness,
tenant ownership, and battery rules.

## Visual system

The visual language is a mineral-green control workspace. Green anchors
navigation and connected/healthy states; copper is a restrained focus cue for
energy, selection, and key thresholds. Keep danger, warning, success, and
informational states semantically distinct.

### Shared color tokens

`index.css` defines the light palette and `theme.css` overrides the tokens on
`body.theme-dark`. Use these CSS variables for shared surfaces and controls
instead of introducing page-specific color values.

| Token | Light | Dark |
| --- | --- | --- |
| `--ink` | `#193833` | `#e3eee8` |
| `--forest` | `#173f39` | `#173f39` |
| `--leaf` | `#397a61` | `#9bc8aa` |
| `--copper` | `#c98338` | `#e0a456` |
| `--paper` | `#eef3f0` | `#101c19` |
| `--surface` | `#ffffff` | `#192824` |
| `--surface-muted` | `#f5f8f6` | `#21312b` |
| `--line` | `#d7e2dc` | `#32443d` |
| `--muted` | `#71827b` | `#a1b3aa` |

Semantic status colors have matching light and dark tokens. Retain their
meaning and verify text contrast on each surface. A state should not be
communicated by color alone; pair it with readable text or an icon.
Text selection uses theme-aware ink and surface colors, and battery readings
in the mapping device picker use the shared foreground token in both themes.
Overview metric icons use the shared leaf token in both themes; reserve
operational state colors for explicit status indicators.

### Typography

- Use the system UI stack `Aptos`, `Segoe UI`, then generic sans-serif. Do not
  add a network-hosted font dependency; the app must remain usable offline and
  self-hosted.
- Keep the type voice direct and operational. Use sentence case and
  left-aligned headings and body copy; reserve all-caps styling for compact
  sequence labels or metadata that already use that convention.
- Use the existing scale as a guide: page titles are about 25–34 px, major
  section titles 17–25 px, body and form copy 12–15 px, and compact metadata
  10–12 px. Keep the smallest sizes for secondary metadata, not instructions,
  form labels, errors, or action names.
- Use weight and spacing to establish hierarchy instead of adding a second
  typeface. Keep numeric readings prominent but subordinate to their meaning.
- Prefer line lengths under roughly 80 characters for explanatory copy.

## Layout and interaction decisions

- Desktop authenticated pages use a fixed left rail and a fluid content
  workspace. At mobile widths the rail becomes a dismissible overlay and
  content keeps a single-column reading order.
- Auth screens share the product story panel and form card; on small screens
  the story becomes a compact lead-in above the form.
- Keep tables horizontally navigable when needed. Prefer readable semantic
  labels and stable columns over shrinking operational data to fit.
- The Overview keeps the live telemetry context and mapping actions brief,
  shows fleet metrics as a four-column desktop summary (two columns on
  tablets, one on narrow phones), and follows with the ten most recently seen
  endpoints. The Endpoints table includes search, 50/100-row page sizing, and
  pagination; both pages refresh every 30 seconds while visible and provide a
  manual refresh with the last successful update time. Sort endpoints newest
  first and place missing timestamps last. Show a recognizable platform mark,
  display label and platform name together in the device identity cell on both
  pages; do not display the telemetry device-class value in these views.
  macOS uses an Apple-mark display and iOS an Apple-mark phone; Windows and
  Android use their platform marks. Keep the visible platform name accessible
  as text and omit protocol values such as `laptop`.
  Tenant admins, managers, and Super Admins can edit a device's display label
  inline from the Endpoints table. Keep the agent-reported hostname separate
  so telemetry refreshes do not overwrite the chosen label.
- The Smart switches page orders discovery, manual setup, and inventory by
  task. Keep scan location and action together, give inventory search and
  filters usable tap targets, and let device cards collapse to one column
  without narrowing a single result to an unused grid track. Load configured
  inventory independently from connector status refreshes; report refresh
  failures without hiding switch management.
  The switch setup presents identity, local access, and command routing as
  three clear stages. Route choices use selectable cards: tenant users see only
  their enrolled tenant connectors, while Super Admins can select a connector
  and the new switch is created in that connector's tenant. A connector scan
  preselects that same route. The Smart Life key-retrieval dialog and discovery
  results use the shared theme surfaces and status tokens in both themes.
  Compatible Tuya meters can be configured per switch through a guided
  "find readings" action. Show power/energy descriptions and live samples
  instead of requiring users to know datapoint IDs or conversion multipliers;
  keep those values in advanced setup. Only recognized reading names get
  suggested roles; let users select unknown numeric readings and their units.
  Never guess from device family or treat unsupported readings as zero. Show
  the sample time, connector requirement, and cumulative-counter
  partial-month behavior.
- Overview energy totals include only power samples from the last five minutes
  and energy recorded for the current UTC month. Show the number of contributing
  switches and an explicit no-data state. Cumulative energy starts at its first
  observation in each month; do not present a partial counter delta as a full
  month total.
- Use surface, muted-surface, and line tokens for hierarchy. Reserve the
  mineral-green hero and navigation surfaces for strong anchors; do not turn
  every content group into an identical raised card.
- Keep selected, hover, focus, disabled, success, warning, and error states
  visible in both themes. Keyboard focus must remain obvious, and controls must
  retain accessible names and state.
- Respect reduced-motion preferences. Motion should communicate an
  interaction or state change rather than decorate a page.

## Theme behavior

The theme preference is stored locally as `chargepilot-theme` (`light` or
`dark`). On first use, follow `prefers-color-scheme`; afterward, the saved
preference is authoritative. `useAppTheme()` toggles `body.theme-dark`, and the
shared token definitions keep surfaces, text, controls, and semantic status
colors paired across themes.

`index.css` contains the light tokens, shared components, and responsive
layout. `theme.css` contains dark token overrides and narrowly scoped
component/utility adjustments. Avoid blanket rules on generic elements such as
`div` or `span`; scope any necessary dark adjustment to a semantic component.
Prefer tokens in shared CSS over `!important` utility overrides.

## Change and verification checklist

When adding or updating a page, component, status, or typography:

1. Use the shared tokens and established component patterns.
2. Check the light and dark versions, including hover, focus, disabled, empty,
   loading, and error states where applicable.
3. Check desktop and narrow/mobile layouts, keyboard operation, and readable
   contrast. Do not rely on color alone to express state.
4. Keep this route/design reference and `CURRENT_STATE.md` accurate when
   responsibilities or behavior change.
5. Update `tests/unit/test_ui_theme.py`; run the targeted pytest test and the
   frontend lint/build commands (`npm run lint` and `npm run build`).
