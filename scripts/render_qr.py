"""Render SmartLife/Tuya QR images for an existing session token.

Usage:
  python scripts/render_qr.py

Reads `app/.smartlife_session.json` for a `token` field and writes
`app/static/smartlife-qr.png|.svg` and `app/static/tuyaSmart-qr.png|.svg`.
Also prints data-URIs for each generated file to stdout.
"""
import base64
import json
import os
from io import BytesIO
from pathlib import Path

import qrcode

ROOT = Path(__file__).resolve().parents[1]
SESSION_FILE = ROOT / "app" / ".smartlife_session.json"
OUT_DIR = ROOT / "app" / "static"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_session():
    if not SESSION_FILE.exists():
        raise SystemExit(f"Session file not found: {SESSION_FILE}")
    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        token = data.get("token")
        if not token:
            raise SystemExit("No 'token' field found in session file. Start login first.")
        return data
    except json.JSONDecodeError:
        raise SystemExit(f"Invalid JSON in session file: {SESSION_FILE}")


def make_qr_payload(scheme: str, token: str) -> str:
    return f"{scheme}--qrLogin?token={token}"


def try_make_png(qr: qrcode.QRCode) -> bytes | None:
    try:
        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


def make_svg_bytes(qr: qrcode.QRCode) -> bytes:
    from qrcode.image.svg import SvgImage

    svg = qr.make_image(image_factory=SvgImage)
    buf = BytesIO()
    svg.save(buf)
    return buf.getvalue()


def render_for_scheme(scheme: str, token: str) -> dict:
    payload = make_qr_payload(scheme, token)
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(payload)
    qr.make(fit=True)

    out = {}
    png_bytes = try_make_png(qr)
    png_path = OUT_DIR / f"{scheme}-qr.png"
    svg_path = OUT_DIR / f"{scheme}-qr.svg"

    if png_bytes:
        png_path.write_bytes(png_bytes)
        out["png"] = str(png_path)
        out["png_data_uri"] = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
    else:
        # PNG generation failed (likely missing Pillow); write SVG instead
        svg_bytes = make_svg_bytes(qr)
        svg_path.write_bytes(svg_bytes)
        out["svg"] = str(svg_path)
        out["svg_data_uri"] = "data:image/svg+xml;base64," + base64.b64encode(svg_bytes).decode("ascii")

    return out


def main():
    session = load_session()
    token = session.get("token")
    created_at = session.get("created_at")
    expires_at = session.get("expires_at")
    schemes = ["smartlife", "tuyaSmart"]
    results = {}
    for s in schemes:
        results[s] = render_for_scheme(s, token)

    out = {"schemes": results, "token": token}
    if created_at:
        out["created_at"] = int(created_at)
    if expires_at:
        out["expires_at"] = int(expires_at)
        try:
            import time

            out["ttl_seconds"] = max(0, int(int(expires_at) - time.time()))
        except Exception:
            pass

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
