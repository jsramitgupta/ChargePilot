import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = PROJECT_ROOT / "frontend" / "src"
APP_COMPONENT = FRONTEND / "App.tsx"
LIGHT_THEME = FRONTEND / "index.css"
DARK_THEME = FRONTEND / "theme.css"


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


def test_mapping_wizard_and_switch_inventory_have_tenant_safe_theme_support():
    app = APP_COMPONENT.read_text(encoding="utf-8")
    light = LIGHT_THEME.read_text(encoding="utf-8")
    dark = DARK_THEME.read_text(encoding="utf-8")

    assert "Choose laptop" in app
    assert "Choose switch" in app
    assert "Set battery rules" in app
    assert "switch-filter-group" in app
    assert "switch-view-toggle" in app
    assert "connector.tenant_id === device.tenant_id" in app
    assert "channel_id: channelId || null" in app
    assert ".mapping-stepper" in light
    assert ".switch-inventory-grid" in light
    assert "body.theme-dark .mapping-builder" in dark
    assert "body.theme-dark .switch-route-warning" in dark


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

    assert 'className="hero-actions"' in app
    assert 'className="primary-btn" to="/mappings"' in app
    assert ".hero-actions" in light
    assert ".primary-btn," in light
    assert ".secondary-btn {" in light
    assert "@media (max-width: 720px)" in light
    assert ".profile-preference-form" in light
    assert "body.theme-dark .hero-panel" in dark
    assert "body.theme-dark .hero-panel .secondary-btn" in dark
    assert "body.theme-dark .profile-preference h2" in dark
    assert "--surface-muted" in light
    assert "--surface-muted" in dark


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
