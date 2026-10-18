import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


class FrontendSettings:
    api_url = os.getenv("CHARGEPILOT_API_URL", "")
    frontend_url = os.getenv("CHARGEPILOT_FRONTEND_URL", "")
    turnstile_site_key = os.getenv("CHARGEPILOT_TURNSTILE_SITE_KEY", "")
    environment = os.getenv("CHARGEPILOT_ENVIRONMENT", "production")


settings = FrontendSettings()


FRONTEND_DIRECTORY = Path(__file__).resolve().parents[1] / "frontend-dist"


class FrontendRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIRECTORY), **kwargs)

    def do_GET(self):
        self._serve_request(include_body=True)

    def do_HEAD(self):
        self._serve_request(include_body=False)

    def end_headers(self):
        api_origin = settings.api_url.rstrip("/")
        connect_sources = " ".join(
            source
            for source in ("'self'", api_origin, "https://challenges.cloudflare.com")
            if source
        )
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; object-src 'none'; "
            "frame-ancestors 'none'; form-action 'self'; "
            "script-src 'self' https://challenges.cloudflare.com; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
            f"connect-src {connect_sources}; "
            "frame-src https://challenges.cloudflare.com",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Permissions-Policy", "camera=(), geolocation=(), microphone=()")
        if settings.environment.casefold() == "production":
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        super().end_headers()

    def _serve_request(self, include_body: bool):
        path = urlsplit(self.path).path
        if path == "/runtime-config.js":
            self._serve_runtime_config(include_body)
            return

        if path == "/":
            self._serve_index(include_body)
            return

        requested_file = Path(self.translate_path(self.path))
        if not requested_file.is_file() and not Path(path).suffix:
            self._serve_index(include_body)
            return

        if requested_file.is_dir():
            self.send_error(404, "Not found")
            return

        if include_body:
            super().do_GET()
        else:
            super().do_HEAD()

    def _serve_runtime_config(self, include_body: bool):
        config = {
            "apiBaseUrl": settings.api_url.rstrip("/"),
            "frontendUrl": settings.frontend_url.rstrip("/"),
            "turnstileSiteKey": settings.turnstile_site_key,
        }
        payload = (
            "window.CHARGEPILOT_CONFIG = "
            + json.dumps(config).replace("<", "\\u003c")
            + ";\n"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if include_body:
            self.wfile.write(payload)

    def _serve_index(self, include_body: bool):
        index = FRONTEND_DIRECTORY / "index.html"
        if not index.is_file():
            self.send_error(503, "Frontend build is unavailable")
            return
        payload = index.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if include_body:
            self.wfile.write(payload)

    def list_directory(self, path):
        self.send_error(404, "Not found")
        return None


def main():
    server = ThreadingHTTPServer(
        ("0.0.0.0", 5173),
        partial(FrontendRequestHandler),
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
