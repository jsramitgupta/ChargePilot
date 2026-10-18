# Frontend Design Reference

This is the canonical reference for the ChargePilot browser UI. Keep it aligned
with `frontend/src/App.tsx`, `frontend/src/index.css`,
`frontend/src/theme.css`, and `tests/unit/test_ui_theme.py`.

## Product and interface goals

ChargePilot is an operational workspace for local-first laptop battery
automation and LAN-connected switches. Make live ownership, connectivity,
battery state, and automation outcomes easy to scan without obscuring the
underlying device relationships. Keep actions explicit and explain unavailable
or empty states with the next useful step.

The UI is React-only. FastAPI supplies JSON APIs and authenticated downloads;
do not add a second browser UI or use mock data to fill gaps in API workflows.
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
| `/` | Endpoint and switch overview with live telemetry summary |
| `/endpoints` | Review laptops, ownership, readings, and endpoint assignment |
| `/devices` | Review switches, channels, connector assignment, and device state |
| `/mappings` | Create, edit, and remove endpoint-to-switch battery rules |
| `/events` | Review automation activity and outcomes |
| `/connectors` | Enroll and operate site connectors |
| `/profile` | Manage account details, display time zone, and password |
| `/users` | Invite people by email and manage roles and accounts |
| `/tenants` | Manage tenants as a Super Admin |
| `/agent` | Install and configure the laptop telemetry agent |
| `/account` | Redirect to the shared account settings page |
| `/support` | Send a support request |

All routes except sign-in, registration, and email verification require the
authenticated session. Keep tenant authorization and automation decisions in
the backend; presentation must not become an authorization or rule boundary.
Mapping setup advances only on an explicit user action and saves only from its
explicit create/save action.

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
  tablets, one on narrow phones), and follows with the endpoint activity table.
- The Smart switches page orders discovery, manual setup, and inventory by
  task. Keep scan location and action together, give inventory search and
  filters usable tap targets, and let device cards collapse to one column
  without narrowing a single result to an unused grid track.
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
