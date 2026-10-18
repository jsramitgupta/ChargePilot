import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
from pydantic import SecretStr

import app.frontend_server as frontend_server


@pytest.fixture
def frontend_server_url(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<!doctype html><title>ChargePilot</title>")
    monkeypatch.setattr(frontend_server, "FRONTEND_DIRECTORY", tmp_path)
    monkeypatch.setattr(frontend_server.settings, "api_url", "https://api.example.com/")
    monkeypatch.setattr(frontend_server.settings, "frontend_url", "https://app.example.com/")
    server = ThreadingHTTPServer(("127.0.0.1", 0), frontend_server.FrontendRequestHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_runtime_config_is_injected_without_caching(frontend_server_url):
    with urllib.request.urlopen(f"{frontend_server_url}/runtime-config.js") as response:
        content = response.read().decode()
        assert response.headers["Cache-Control"] == "no-store"

    assert json.loads(content.removeprefix("window.CHARGEPILOT_CONFIG = ").rstrip(";\n")) == {
        "apiBaseUrl": "https://api.example.com",
        "frontendUrl": "https://app.example.com",
        "turnstileSiteKey": "",
    }


def test_turnstile_site_key_is_public_only_when_secret_is_configured(frontend_server_url, monkeypatch):
    monkeypatch.setattr(frontend_server.settings, "turnstile_site_key", "public-site-key")
    monkeypatch.setattr(
        frontend_server.settings,
        "turnstile_secret_key",
        SecretStr("private-secret-key"),
    )

    with urllib.request.urlopen(f"{frontend_server_url}/runtime-config.js") as response:
        content = response.read().decode()

    config = json.loads(content.removeprefix("window.CHARGEPILOT_CONFIG = ").rstrip(";\n"))
    assert config["turnstileSiteKey"] == "public-site-key"
    assert "private-secret-key" not in content


def test_frontend_routes_fall_back_to_the_spa_and_missing_assets_404(frontend_server_url):
    with urllib.request.urlopen(frontend_server_url) as response:
        assert response.read() == b"<!doctype html><title>ChargePilot</title>"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]

    with urllib.request.urlopen(f"{frontend_server_url}/mappings") as response:
        assert response.read() == b"<!doctype html><title>ChargePilot</title>"

    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(f"{frontend_server_url}/assets/missing.js")
    assert error.value.code == 404
