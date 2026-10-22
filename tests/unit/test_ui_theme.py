import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = PROJECT_ROOT / "frontend" / "src"
APP_COMPONENT = FRONTEND / "App.tsx"
LIGHT_THEME = FRONTEND / "index.css"
DARK_THEME = FRONTEND / "theme.css"
HTML_ENTRY = PROJECT_ROOT / "frontend" / "index.html"


def css_rule(stylesheet: str, selector: str) -> str:
    match = re.search(rf"(?m)^\s*{re.escape(selector)}\s*\{{([^}}]*)\}}", stylesheet)
    assert match, f"Missing CSS rule: {selector}"
    return match.group(1)


def contrast_ratio(foreground: str, background: str) -> float:
    def luminance(color: str) -> float:
        channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [
            channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
            for channel in channels
        ]
        return sum(weight * channel for weight, channel in zip((0.2126, 0.7152, 0.0722), linear))

    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def test_react_is_the_only_browser_ui():
    assert not (PROJECT_ROOT / "app" / "templates").exists()
    assert not (PROJECT_ROOT / "app" / "static").exists()
    assert "TemplateResponse" not in (PROJECT_ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "AuthBrandPanel" in APP_COMPONENT.read_text(encoding="utf-8")
    assert "rail-nav" in APP_COMPONENT.read_text(encoding="utf-8")


def test_light_and_dark_themes_share_chargepilot_design_tokens():
    light = LIGHT_THEME.read_text(encoding="utf-8")
    dark = DARK_THEME.read_text(encoding="utf-8")

    for token in ("--ink", "--forest", "--leaf", "--copper", "--paper", "--surface", "--line"):
        assert token in light
        assert token in dark

    assert "#173f39" in light
    assert "#c98338" in light
    assert "body.theme-dark" in dark
    assert "prefers-reduced-motion" in light


def test_text_selection_and_mapping_battery_badge_follow_theme_contrast():
    light = LIGHT_THEME.read_text(encoding="utf-8")
    dark = DARK_THEME.read_text(encoding="utf-8")

    for token in ("--selection-ink", "--selection-surface"):
        assert token in light
        assert token in dark

    assert "color: var(--selection-ink);" in css_rule(light, "::selection")
    assert "background: var(--selection-surface);" in css_rule(light, "::selection")
    assert ".mapping-choice-battery,\n.mapping-switch-state {" in light
    assert "color: var(--ink);" in light.split(".mapping-choice-battery,", 1)[1].split("}", 1)[0]
    assert "#101c19" in dark
    assert "#9bc8aa" in dark


def test_mapping_wizard_and_switch_inventory_have_tenant_safe_theme_support():
    app = APP_COMPONENT.read_text(encoding="utf-8")
    light = LIGHT_THEME.read_text(encoding="utf-8")
    dark = DARK_THEME.read_text(encoding="utf-8")

    assert "Choose device" in app
    assert "Choose switch" in app
    assert "Set battery rules" in app
    assert 'className="mapping-step-title"' in app
    assert "switch-filter-group" in app
    assert "switch-view-toggle" in app
    assert "connector.tenant_id === device.tenant_id" in app
    assert "channel_id: channelId || null" in app
    assert ".mapping-stepper" in light
    assert "flex-direction: column;" in css_rule(light, ".mapping-stepper button")
    assert "top: 21px;" in css_rule(light, ".mapping-stepper li:not(:last-child)::after")
    assert ".mapping-step-title" in light
    assert ".switch-inventory-grid" in light
    assert "body.theme-dark .mapping-builder" in dark
    assert "body.theme-dark .switch-route-warning" in dark


def test_device_setup_links_to_published_builds_and_explains_installation():
    app = APP_COMPONENT.read_text(encoding="utf-8")

    assert "https://github.com/jsramitgupta/ChargePilot/releases/latest" in app
    assert "View latest macOS release assets" in app
    assert "View latest Android release assets" in app
    assert "View latest iOS release assets" in app
    assert "chargepilot-android-agent-source.zip" in app
    assert "chargepilot-ios-agent-source.zip" in app
    assert "agent-release-manifest.json" in app
    assert "otherwise they are unsigned" in app
    assert "deregister" in app
    assert "allow your browser or file manager to install this app" in app
    assert "select your signing team" in app
    assert "Shortcuts" in app
    assert "Set up a laptop" not in app


def test_overview_and_endpoints_pair_platform_marks_with_device_identity():
    app = APP_COMPONENT.read_text(encoding="utf-8")
    light = LIGHT_THEME.read_text(encoding="utf-8")
    dark = DARK_THEME.read_text(encoding="utf-8")

    assert app.count("<EndpointIdentity endpoint={endpoint} />") == 2
    assert "platform === 'windows'" in app
    assert "platform === 'android'" in app
    assert "platform === 'macos'" in app
    assert "platform === 'ios'" in app
    assert "endpoint.device_class" not in app
    assert 'endpoint-identity-platform">{PLATFORM_NAMES[endpoint.platform]}' in app
    assert ".endpoint-identity {" in light
    assert ".platform-mark-windows {" in light
    assert ".platform-mark-android {" in light
    assert "body.theme-dark .platform-mark-windows" in dark
    assert "body.theme-dark .platform-mark-android" in dark


def test_switch_energy_readings_and_datapoint_settings_use_theme_aware_ui():
    app = APP_COMPONENT.read_text(encoding="utf-8")
    light = LIGHT_THEME.read_text(encoding="utf-8")
    dark = DARK_THEME.read_text(encoding="utf-8")

    assert "Switch energy" in app
    assert "Configure switch meters" in app
    assert "meter-settings" in app
    assert "Cumulative total" in app
    assert "Monthly counter" in app
    assert "does not guess them" in app
    assert ".energy-summary" in light
    assert ".switch-meter-panel" in light
    assert "body.theme-dark .energy-summary" in dark
    assert "body.theme-dark .switch-meter-readings strong" in dark


def test_mapping_threshold_preview_keeps_labels_clear_when_thresholds_coincide():
    app = APP_COMPONENT.read_text(encoding="utf-8")
    light = LIGHT_THEME.read_text(encoding="utf-8")
    dark = DARK_THEME.read_text(encoding="utf-8")

    assert 'className="mapping-threshold-legend" role="group" aria-label="Automation thresholds"' in app
    assert "Turn on at or below {onThreshold}%" in app
    assert "Charging cutoff at or above {chargingOffThreshold}%" in app
    assert ".mapping-threshold-legend {" in light
    assert "flex-wrap: wrap;" in css_rule(light, ".mapping-threshold-legend")
    assert "body.theme-dark .mapping-threshold-legend .is-charging" in dark


def test_timezone_setting_uses_iana_dropdown_for_admin_accounts():
    app = APP_COMPONENT.read_text(encoding="utf-8")
    api = (PROJECT_ROOT / "app" / "api" / "auth.py").read_text(encoding="utf-8")

    assert "Intl.supportedValuesOf('timeZone')" in app
    assert "TIME_ZONE_REGIONS.map" in app
    assert 'id="profile-timezone"' in app
    assert "currentTimezone !== 'UTC' && !TIME_ZONE_OPTIONS.includes(currentTimezone)" in app
    assert "body: JSON.stringify({ timezone: timezone || user?.timezone || 'UTC' })" in app
    assert "ZoneInfo(value)" in api


def test_dashboard_actions_and_mapping_wizard_share_responsive_theme_components():
    app = APP_COMPONENT.read_text(encoding="utf-8")
    light = LIGHT_THEME.read_text(encoding="utf-8")
    dark = DARK_THEME.read_text(encoding="utf-8")

    assert 'className="dashboard-header-actions"' in app
    assert 'className="primary-btn" to="/mappings"' in app
    assert ".dashboard-header-actions" in light
    assert ".primary-btn," in light
    assert ".secondary-btn {" in light
    assert "@media (max-width: 720px)" in light
    assert ".profile-preference-form" in light
    assert "body.theme-dark .hero-panel" in dark
    assert "body.theme-dark .hero-panel .secondary-btn" in dark
    assert "body.theme-dark .profile-preference h2" in dark
    assert "--surface-muted" in light
    assert "--surface-muted" in dark


def test_overview_and_switch_pages_have_responsive_operational_layouts():
    app = APP_COMPONENT.read_text(encoding="utf-8")
    light = LIGHT_THEME.read_text(encoding="utf-8")
    dark = DARK_THEME.read_text(encoding="utf-8")

    assert 'className="dashboard-page"' in app
    dashboard = app.split("function DashboardPage()", 1)[1].split("\nfunction ", 1)[0]
    assert "<th>Device</th>" in dashboard
    assert "<EndpointIdentity endpoint={endpoint} />" in dashboard
    assert "endpoint.device_class" not in dashboard
    assert "colSpan={8}" in dashboard
    assert "Latest reports" in dashboard
    assert "sortEndpointsByLastSeen(endpoints)" in dashboard
    assert "refetchInterval: ENDPOINTS_REFRESH_INTERVAL" in dashboard
    assert "className=\"live-refresh-control\"" in app
    assert 'className="stats-grid" aria-label="Fleet summary"' in app
    assert 'className="panel metric-card"' in app
    assert 'className="switch-page"' in app
    assert "className=\"switch-discovery-panel\"" in app
    assert "className=\"switch-add-panel\"" in app
    assert "grid-template-columns: repeat(4, minmax(0, 1fr));" in css_rule(light, ".stats-grid")
    assert "grid-template-columns: repeat(auto-fit, minmax(min(100%, 430px), 1fr));" in css_rule(light, ".switch-inventory-grid")
    assert "@media (max-width: 860px)" in light
    assert "@media (max-width: 400px)" in light
    assert "body.theme-dark .switch-page-hero" in dark
    assert "body.theme-dark .switch-discovery-panel" in dark


def test_endpoints_page_has_recent_first_pagination_search_and_refresh():
    app = APP_COMPONENT.read_text(encoding="utf-8")
    endpoints = app.split("function EndpointsPage()", 1)[1].split("\nfunction ", 1)[0]
    dashboard = app.split("function DashboardPage()", 1)[1].split("\nfunction ", 1)[0]

    assert "<h1>Endpoints</h1>" in endpoints
    assert "sortEndpointsByLastSeen(data)" in endpoints
    assert "refetchInterval: ENDPOINTS_REFRESH_INTERVAL" in endpoints
    assert 'id="endpoint-search"' in endpoints
    assert "<option value={50}>50 devices</option>" in endpoints
    assert "<option value={100}>100 devices</option>" in endpoints
    assert "aria-label=\"Endpoint pages\"" in endpoints
    assert "aria-sort=\"descending\"" in endpoints
    assert "<th>Automation</th>" not in endpoints
    assert "automationMutation" not in endpoints
    assert "formatTimestampWithSeconds(endpoint.last_seen_at)" in endpoints
    assert "colSpan={9}" in endpoints
    assert "<RelativeTimestamp value={endpoint.last_seen_at} now={now} />" in dashboard
    assert "Intl.RelativeTimeFormat" in app
    assert "timeStyle: 'medium'" in app
    assert "absoluteSeconds < 60" in app
    assert "absoluteSeconds < 3_600" in app
    assert "absoluteSeconds < 86_400" in app


def test_switch_setup_routes_and_smartlife_dialog_follow_the_shared_theme():
    app = APP_COMPONENT.read_text(encoding="utf-8")
    light = LIGHT_THEME.read_text(encoding="utf-8")
    dark = DARK_THEME.read_text(encoding="utf-8")

    assert "role=\"radiogroup\"" in app
    assert "switch-route-choice" in app
    assert "isSuperAdmin || connector.tenant_id === user?.tenant_id" in app
    assert "tenant_id: deviceTenantId" in app
    assert "connector.tenant_name" in app
    assert "smartlife-modal" in app
    assert ".switch-setup-form" in light
    assert ".switch-route-choice.is-selected" in light
    assert ".switch-scan-results" in light
    assert ".smartlife-modal" in light
    assert "background: var(--surface);" in css_rule(light, ".smartlife-modal")
    assert "body.theme-dark" in dark
    assert "--surface-muted: #21312b;" in css_rule(dark, "body.theme-dark")


def test_shared_controls_and_surfaces_use_theme_tokens():
    light = LIGHT_THEME.read_text(encoding="utf-8")
    dark = DARK_THEME.read_text(encoding="utf-8")

    panel = css_rule(light, ".panel")
    primary = css_rule(light, ".btn-primary")
    secondary = css_rule(light, ".btn-secondary")
    assert "border-color: var(--line);" in panel
    assert "background: var(--surface);" in panel
    assert "color: var(--ink);" in panel
    assert "min-height: 42px;" in primary
    assert "background: var(--forest);" in primary
    assert "border-color: var(--line);" in secondary
    assert "color: var(--ink);" in secondary
    assert "body.theme-dark .page-shell input" in dark
    assert "body.theme-dark .page-shell select" in dark
    assert "body.theme-dark .page-shell .text-slate-900" in dark

    hero = css_rule(light, ".hero-panel")
    actions = css_rule(light, ".hero-actions")
    assert "grid-template-columns: minmax(0, 1fr) auto;" in hero
    assert "display: flex;" in actions
    assert "gap: 10px;" in actions
    assert "flex-wrap: wrap;" in actions


def test_auth_controls_and_semantic_statuses_follow_both_themes():
    app = APP_COMPONENT.read_text(encoding="utf-8")
    light = LIGHT_THEME.read_text(encoding="utf-8")
    dark = DARK_THEME.read_text(encoding="utf-8")
    html = HTML_ENTRY.read_text(encoding="utf-8")

    assert "className={`theme-toggle ${className}`}" in app
    assert 'aria-pressed={isDark}' in app
    assert "meta[name=\"theme-color\"]" in app
    assert 'isDark ? \'#101c19\' : \'#eef3f0\'' in app
    assert '<meta name="theme-color" content="#eef3f0"' in html
    assert 'className="metric-icon"' in app
    assert "bg-violet-50" not in app
    assert "role=\"alert\"" in app
    assert "document.body.classList.add('bg-slate-50')" not in app

    theme_toggle = css_rule(light, ".theme-toggle")
    field_group = css_rule(light, ".field-group")
    error_alert = css_rule(light, ".alert.error")
    success_alert = css_rule(light, ".alert.success")
    metric_icon = css_rule(light, ".metric-icon")
    auth_helper = css_rule(light, ".auth-helper")
    dark_tokens = css_rule(dark, "body.theme-dark")

    assert "color: var(--ink);" in theme_toggle
    assert "background: var(--surface);" in theme_toggle
    assert "color: var(--ink);" in field_group
    assert "color: var(--danger-ink);" in error_alert
    assert "background: var(--danger-surface);" in error_alert
    assert "color: var(--success-ink);" in success_alert
    assert "color: var(--leaf);" in metric_icon
    assert "background: color-mix(in srgb, var(--surface) 82%, var(--leaf));" in metric_icon
    assert "color: var(--muted);" in auth_helper
    assert "--danger-ink: #f0b5a6;" in dark_tokens
    assert "--danger-surface: #38221e;" in dark_tokens
    assert "--success-ink: #b8e0c0;" in dark_tokens
    assert contrast_ratio("#f0b5a6", "#38221e") >= 4.5
    assert contrast_ratio("#b8e0c0", "#21382b") >= 4.5


def test_people_invitations_and_account_settings_follow_the_shared_theme():
    app = APP_COMPONENT.read_text(encoding="utf-8")
    light = LIGHT_THEME.read_text(encoding="utf-8")
    dark = DARK_THEME.read_text(encoding="utf-8")
    users_page = app.split("function UsersPage()", 1)[1].split("\nfunction ", 1)[0]

    assert 'path="/accept-invitation"' in app
    assert "function AcceptInvitationPage()" in app
    assert "function ChangePasswordSection()" in app
    assert "'/api/v1/auth/accept-invitation'" in app
    assert "'/api/v1/admin/account-invitations'" in users_page
    assert "Send invitation" in users_page
    assert "Copy invite code" not in users_page
    assert "Create a user" not in users_page
    assert 'path="/account" element={<Navigate to="/profile" replace />}' in app
    assert "Only the super admin can change this password." not in app

    for selector in (
        ".people-invite-section",
        ".people-invitation-row",
        ".people-table",
        ".account-summary",
        ".account-password-section",
    ):
        assert selector in light

    assert "var(--surface)" in css_rule(light, ".account-summary")
    assert "var(--line)" in css_rule(light, ".people-table td")
    assert "--warning-surface: #fffaf1;" in css_rule(light, ":root")
    assert "--warning-surface: #382d1f;" in css_rule(dark, "body.theme-dark")
    assert contrast_ratio("#efc98f", "#382d1f") >= 4.5


def test_mapping_rule_inputs_do_not_submit_until_explicit_save():
    app = APP_COMPONENT.read_text(encoding="utf-8")
    mappings_page = app.split("function MappingsPage()", 1)[1].split("\nfunction ", 1)[0]

    assert "<form" not in mappings_page
    assert "onSubmit=" not in mappings_page
    assert "type=\"submit\"" not in mappings_page
    assert "form.handleSubmit((values) => mutation.mutate({ mappingId: editingMappingId, values }))()" in mappings_page
    assert "'Create mapping'" in mappings_page
    assert "'Save changes'" in mappings_page
    assert "function editMapping(mapping: Mapping)" in mappings_page
    assert "method: mappingId ? 'PUT' : 'POST'" in mappings_page
    assert "className=\"mapping-edit-button\"" in mappings_page
    assert "className=\"mapping-delete-button\"" in mappings_page
    advance_step = mappings_page.split("async function advanceStep()", 1)[1].split("\n  function ", 1)[0]
    assert "mutation.mutate" not in advance_step


def test_dark_tables_and_mapping_number_inputs_have_readable_theme_colors():
    dark = DARK_THEME.read_text(encoding="utf-8")

    table_cells = css_rule(dark, "body.theme-dark .page-shell .table-wrap td")
    strong_cells = css_rule(dark, "body.theme-dark .page-shell .table-wrap .strong-cell")
    success_badges = css_rule(dark, "body.theme-dark .page-shell .table-wrap .badge.success")
    number_input = css_rule(dark, "body.theme-dark .page-shell .mapping-number-input input")

    assert "color: #bdcdc4;" in table_cells
    assert "color: #e3eee8 !important;" in strong_cells
    assert "color: #b8e0c0;" in success_badges
    assert "background-color: transparent !important;" in number_input
    assert contrast_ratio("#bdcdc4", "#192824") >= 4.5
    assert contrast_ratio("#e3eee8", "#192824") >= 4.5
    assert contrast_ratio("#b8e0c0", "#22392f") >= 4.5


def test_connector_page_explains_supported_deployments_and_local_network_needs():
    app = APP_COMPONENT.read_text(encoding="utf-8")
    connectors_page = app.split("function ConnectorsPage()", 1)[1].split("\nfunction ", 1)[0]
    light = LIGHT_THEME.read_text(encoding="utf-8")
    dark = DARK_THEME.read_text(encoding="utf-8")
    connector_readme = (PROJECT_ROOT / "connector" / "README.md").read_text(encoding="utf-8")

    assert "Docker Compose" in connectors_page
    assert "Python process" in connectors_page
    assert "Linux or macOS terminal" in connectors_page
    assert "Linux server, NAS, or Raspberry Pi" in connectors_page
    assert "no inbound Internet port is required" in connectors_page
    assert "Create enrollment code" in connectors_page
    assert "endusercompute/chargepilot-connector:sha-" in connectors_page
    assert "curl -fsSL" in connectors_page
    assert "/connectors/install.sh | sh" in connectors_page
    assert "same local network" in connectors_page
    assert ".connector-deploy-guide" in light
    assert "body.theme-dark .connector-deploy-guide" in dark
    assert "endusercompute/chargepilot-connector:sha-" in connector_readme
