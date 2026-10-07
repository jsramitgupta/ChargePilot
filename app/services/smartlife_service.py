import base64
import json
import os
import tempfile
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import qrcode
from tuya_sharing import LoginControl, Manager

CLIENT_ID = "HA_3y9q4ak7g4ephrvke"
SCHEMA = "haauthorize"
SESSION_PATH = Path(__file__).resolve().parents[1] / ".smartlife_session.json"


class SmartLifeService:
    @staticmethod
    def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix=".smartlife_session.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_path, 0o600)
            os.replace(temp_path, path)
        except Exception:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            raise

    @staticmethod
    def load_session() -> dict[str, Any]:
        if not SESSION_PATH.exists():
            return {}
        try:
            with SESSION_PATH.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            return {}
        return {}

    @staticmethod
    def save_session(data: dict[str, Any]) -> dict[str, Any]:
        SmartLifeService._atomic_write_json(SESSION_PATH, data)
        return data

    @staticmethod
    def clear_session() -> None:
        if SESSION_PATH.exists():
            SESSION_PATH.unlink(missing_ok=True)

    @staticmethod
    def _build_qr_image(token: str) -> str:
        payload = f"{SCHEMA}--qrLogin?token={token}"
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(payload)
        qr.make(fit=True)
        image = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    @staticmethod
    def normalize_device(raw_device: Any) -> dict[str, Any]:
        if isinstance(raw_device, dict):
            payload = raw_device
        else:
            payload = getattr(raw_device, "__dict__", {})

        device_id = (
            payload.get("id")
            or payload.get("device_id")
            or payload.get("devId")
            or payload.get("deviceId")
            or ""
        )
        name = payload.get("name") or payload.get("device_name") or f"SmartLife Device {device_id}"
        local_key = (
            payload.get("local_key")
            or payload.get("localKey")
            or payload.get("key")
            or payload.get("deviceKey")
            or ""
        )
        ip_address = (
            payload.get("ip")
            or payload.get("ip_address")
            or payload.get("localIp")
            or payload.get("ipAddress")
            or ""
        )
        device_type = payload.get("device_type") or payload.get("category") or "switch"
        protocol_version = payload.get("protocol_version") or payload.get("version") or "3.5"

        return {
            "device_id": str(device_id),
            "name": str(name),
            "encrypted_local_key": str(local_key),
            "ip_address": str(ip_address),
            "device_type": "switch" if str(device_type).lower() in {"switch", "plug", "outlet", "default", "cj"} else str(device_type),
            "protocol_version": str(protocol_version),
        }

    @staticmethod
    def start_login(user_code: str) -> dict[str, Any]:
        cleaned = (user_code or "").strip()
        if not cleaned:
            raise ValueError("SmartLife User ID is required.")

        response = LoginControl().qr_code(CLIENT_ID, SCHEMA, cleaned)
        result = response.get("result") if isinstance(response, dict) else {}
        token = result.get("token") or result.get("qrcode") or result.get("qr")
        if not token:
            message = response.get("msg") if isinstance(response, dict) else "Unable to generate QR code."
            code = response.get("code") if isinstance(response, dict) else "unknown"
            raise ValueError(f"Could not start SmartLife login [{code}]: {message}")

        qr_data_url = SmartLifeService._build_qr_image(token)
        session = SmartLifeService.load_session()
        session.update({
            "user_code": cleaned,
            "token": token,
            "qr_data_url": qr_data_url,
            "status": "pending",
            "devices": [],
        })
        SmartLifeService.save_session(session)
        return session

    @staticmethod
    def fetch_linked_devices(user_code: str | None = None, token: str | None = None) -> list[dict[str, Any]]:
        session = SmartLifeService.load_session()
        cleaned_user_code = (user_code or session.get("user_code") or "").strip()
        cleaned_token = token or session.get("token") or ""
        if not cleaned_user_code or not cleaned_token:
            raise ValueError("SmartLife login has not started yet.")

        login_control = LoginControl()
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            try:
                ok, result = login_control.login_result(cleaned_token, CLIENT_ID, cleaned_user_code)
            except Exception:
                time.sleep(2)
                continue
            if ok:
                session.update(
                    {
                        "user_code": cleaned_user_code,
                        "token": cleaned_token,
                        "status": "linked",
                        "session_data": result,
                        "terminal_id": result.get("terminal_id") or result.get("terminalId"),
                        "endpoint": result.get("endpoint") or result.get("end_point"),
                    }
                )
                SmartLifeService.save_session(session)
                manager = Manager(
                    CLIENT_ID,
                    cleaned_user_code,
                    session.get("terminal_id") or "chargepilot-terminal",
                    session.get("endpoint") or "https://apigw.iotbing.com",
                    result,
                )
                manager.update_device_cache()
                devices = []
                for device in manager.device_map.values():
                    normalized = SmartLifeService.normalize_device(device)
                    if normalized.get("device_id") and normalized.get("encrypted_local_key"):
                        devices.append(normalized)
                session["devices"] = devices
                SmartLifeService.save_session(session)
                return devices
            time.sleep(2)

        raise TimeoutError("SmartLife QR scan timed out. Please generate a new QR code and confirm the login on your phone.")
