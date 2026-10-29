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

The authenticated ChargePilot management console is React-only. FastAPI
supplies JSON APIs, public installable agent binaries, and connector
enrollment APIs; source archives are not distributed. Setup APIs and
credential management require authentication. The separate Next.js/Strapi
site at `docs-site/` is public user documentation, not a second management
console. Do not use mock data to fill gaps in product API workflows.
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
| `/` | Endpoint and switch fleet overview with live telemetry summary |
| `/endpoints` | Review enrolled devices, edit display labels, ownership, recent battery/resource readings, and endpoint assignment |
| `/devices` | Review switches, channels, connector assignment, device state, and optional meter readings |
| `/mappings` | Create, edit, and remove endpoint-to-switch battery rules |
| `/smart-groups` | Create tenant-scoped Windows/macOS endpoint groups, select fixed read-only sensors, and review recent results |
| `/events` | Review automation activity and outcomes |
| `/connectors` | Follow deployment steps, enroll site connectors, review status, and rename connectors |
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
compatible during migration. The setup page lists only the latest Windows
`.exe`, macOS `.dmg`, Android `.apk`, and iOS `.ipa` assets, resolving their
current URLs through the authenticated ChargePilot API. Source archives are
not listed as installable agents. A top-right **Install instructions** action
explains platform-specific installation and signing limits. The Windows
executable opens a setup UI that installs/configures a Windows service and
lets users deregister and re-enroll without reinstalling; it does not use Task
Scheduler. The executable also provides CLI service controls, including
deregistration, and prompts for enrollment secrets instead of accepting
tokens as command-line arguments. The macOS, Android, and iOS agent UIs also
provide self-service deregistration and re-enrollment. A release may contain
signed and unsigned builds across platforms depending on configured
credentials; its release notes and `agent-release-manifest.json` state the
signing status for each.
Partially configured signing groups or failed signature verification stop the
release workflow. Signed iOS profiles limit which devices can install the
ad-hoc IPA. Explain how to install each build. The Windows setup screen shows
the API origin selected by the setup command without allowing edits; Android,
iOS, and macOS use the fixed
`https://api-chargepilot.endusercompute.in` origin. Device labels use
non-serial platform metadata, and enrollment asks only for the high-entropy
token.
Clearly
explain Android's inexact WorkManager
timing and iOS Shortcuts automation best-effort limits. The iOS setup guidance
should suggest both a battery-level and charger-connected trigger and must not
promise exact timing. The page shows token expiry and enrollment count without
exposing token values unless its creator explicitly reveals one. Revoking a
token prevents new exchanges; admins separately revoke already-issued endpoint
credentials. The Endpoints page has fleet counts, online/offline filters,
platform filtering, search, and 50- or 100-device pages, sorted by last report
with missing timestamps last. Each inventory row shows platform, enrollment
state, battery, and last-seen time to the second; it does not include a
separate endpoint automation column. Selecting a device label opens a
tenant-scoped right-side detail drawer with identity, current online/report
state, configured cadence, automation eligibility, device mappings, and up to
100 historical battery and system-resource samples.
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
a live relative time. The Connectors page offers Docker Compose and Windows executable deployment.
Docker uses environment-based one-time enrollment and Docker-managed
persistent storage. When the connector image is private, explain that users
need Docker Hub read access and must authenticate with `docker login` before
pulling it; never put registry credentials in Compose or confuse them with the
one-time enrollment code. Link to the published private connector image access
guide. Windows uses a self-contained executable installed as an automatically
starting Windows service; the enrollment code is entered at a secure prompt,
and the connector credential is stored under ProgramData with access for
SYSTEM, Administrators, and the LocalService service identity. State that the
executable is unsigned and Windows SmartScreen may show a warning. Explain
service controls, manual updates, and that uninstalling does not revoke the
server-side connector.
Both methods show setup readiness and connector status, let authorized
administrators rename a connector without changing its credential or device
assignments, and require revoked connectors to be deleted explicitly. Only
installable binaries are available through the public API proxy; agent and
connector source archives are not distributed. Code creation and credential
management remain authenticated.
Mapping setup has four explicit steps: choose an endpoint, choose a switch,
choose a supported use case, and set battery rules. The use-case choice offers
battery-managed switch cycling, switch-off-only, and switch-and-shutdown for
enrolled Windows/macOS endpoints. Both switch-off use cases disable automatic
turn-on. The server requests endpoint shutdown only after a successful switch
off. Explain the visible, locally cancellable Windows countdown and the local
macOS confirmation; do not imply that an acknowledgement proves shutdown
completed.
Continue advances without saving; create/save remains the only mutation action.
The mapping stepper places each label below its numbered marker; connector
segments join the markers only and never run behind step text. Keep this layout
at narrow widths so longer step names wrap without crossing the progress line.
The rule editor asks only for the selected use case's core thresholds:
battery-cycle mappings show turn-on and turn-off thresholds, while switch-off
mappings show only the turn-off threshold. Keep automatic turn-on, the separate
charging-completion cutoff, change cooldown, and mapping enable state under a
collapsed **More options** disclosure. The charging cutoff uses the selected
device's `charging` telemetry flag. Show threshold labels in a wrapping legend
rather than overlaid on the battery scale so coincident thresholds remain
legible. Do not repeat the selected use case in a separate confirmation panel.
Endpoint automation defaults on separately from an individual mapping's
enabled state; the server enforces platform eligibility, sample freshness,
tenant ownership, and battery rules.
Endpoint details keep the recent-report table and add a graph view for battery,
CPU, memory utilization, and GPU percentages. Missing platform readings are
omitted from the graph rather than displayed as zero; the table remains
available for exact timestamps and reported values. The mapped-switch section
shows each associated switch's recent power reading and current UTC-month
energy alongside its automation state. Power older than five minutes is shown
as waiting for a fresh reading; unconfigured meters remain explicit.

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
  Smart Groups distinguish dynamic rules from explicit one-or-more endpoint
  selection. Offer only the fixed read-only sensor catalog and make the execution
  boundary visible; never imply that uploaded scripts are supported. Show fresh
  matching devices, queue feedback, recent typed results, and clear agent
  availability. Windows sensors run through the service without a signed-in
  user; macOS collection requires its menu-bar app or CLI agent running in a
  signed-in session. Keep the editor and results readable in both themes and
  stack the targeting/results columns on narrow screens.
  Compatible Tuya meters can be configured per switch through a guided
  "find readings" action. Show power/energy descriptions and live samples
  instead of requiring users to know datapoint IDs or conversion multipliers.
  Let users select the source units and decimal places for each raw reading;
  show how a discovered sample changes with that choice. Keep datapoint IDs
  and custom base scales in advanced setup. Only recognized reading names get
  suggested roles; let users select unknown numeric readings and their units.
  Never guess from device family or treat unsupported readings as zero. Show
  the sample time, connector requirement, and cumulative-counter
  partial-month behavior.
- Keep switch consumption out of the Overview. Show live power and month-to-date
  energy per switch in the switch inventory and alongside each mapped switch
  in endpoint details. Label sample times and do not display stale power as
  live. Cumulative energy starts at its first observation in each month; do
  not present a partial counter delta as a full month total.
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
6. Check content at narrow widths (320px, 768px, and desktop), including long
    URLs, paths, identifiers, and commands. Grid/flex children that contain
    user- or server-provided text must be allowed to shrink (`min-width: 0`),
    flexible grid tracks should use `minmax(0, 1fr)`, and long tokens must wrap
    or use an intentionally bounded, accessible scroll area. Verify the page
    itself has no horizontal overflow and that code remains selectable.
7. Keep action labels consistent with their result, require confirmation for
    destructive actions, and make the effect explicit when related data (such
    as an accepted account) is not affected.
