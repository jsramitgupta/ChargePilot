from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = PROJECT_ROOT / "frontend" / "src"
APP_COMPONENT = FRONTEND / "App.tsx"
LIGHT_THEME = FRONTEND / "index.css"
DARK_THEME = FRONTEND / "theme.css"


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
