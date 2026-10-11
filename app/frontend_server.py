import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from app.core.config import settings


FRONTEND_DIRECTORY = Path(__file__).resolve().parents[1] / "frontend-dist"


class FrontendRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIRECTORY), **kwargs)

    def do_GET(self):
        self._serve_request(include_body=True)

    def do_HEAD(self):
        self._serve_request(include_body=False)

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
