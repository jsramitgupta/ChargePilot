from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STYLE_SHEET = PROJECT_ROOT / "app" / "static" / "style.css"
TEMPLATES = PROJECT_ROOT / "app" / "templates"


def test_light_and_dark_themes_define_the_shared_semantic_palette():
    stylesheet = STYLE_SHEET.read_text(encoding="utf-8-sig")
    light_tokens = stylesheet.split(":root {", maxsplit=1)[1].split("}", maxsplit=1)[0]
    dark_tokens = stylesheet.split("body.theme-dark {", maxsplit=1)[1].split("}", maxsplit=1)[0]

    for token in ("--bg", "--panel", "--soft", "--muted", "--line", "--primary"):
        assert f"{token}:" in light_tokens
        assert f"{token}:" in dark_tokens


def test_shared_brand_surfaces_are_used_across_pages_and_wizards():
    stylesheet = STYLE_SHEET.read_text(encoding="utf-8-sig")
    devices = (TEMPLATES / "devices.html").read_text(encoding="utf-8")
    mappings = (TEMPLATES / "mappings.html").read_text(encoding="utf-8")
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    agent_setup = (TEMPLATES / "agent_setup.html").read_text(encoding="utf-8")

    assert 'href="/static/style.css?v=18"' in base
    assert ".ui-page-hero" in stylesheet
    assert ".ui-accent-surface" in stylesheet
    assert ".ui-modal-heading" in stylesheet
    assert "ui-page-hero" in devices
    assert "ui-accent-surface" in devices
    assert "mapping-dialog-header ui-modal-heading" in mappings
    assert "agent-guide-dialog-header ui-modal-heading" in base
    assert "ui-modal-heading" in agent_setup


def test_configured_switches_share_a_surface_in_both_themes():
    stylesheet = STYLE_SHEET.read_text(encoding="utf-8-sig")
    devices = (TEMPLATES / "devices.html").read_text(encoding="utf-8")

    assert ".switch-device-card {\n  position: relative;" in stylesheet
    assert "background: linear-gradient(145deg, var(--panel), var(--panel-2));" in stylesheet
    assert "body.theme-dark .switch-device-card[data-state=\"off\"]" in stylesheet
    assert "body.theme-dark .switch-device-card[data-state=\"on\"]" in stylesheet
    assert ".switch-channel-row {\n  background: var(--panel-2);" in stylesheet
    assert "switch-device-card rounded-[24px] border border-slate-200 bg-gradient-to-br" not in devices
