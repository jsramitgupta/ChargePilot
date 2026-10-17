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
