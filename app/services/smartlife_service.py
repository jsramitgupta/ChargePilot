import asyncio
import base64
import io
import logging
import secrets
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

logger = logging.getLogger("chargepilot.smartlife")

CLIENT_ID = "HA_3y9q4ak7g4ephrvke"
SCHEMA = "haauthorize"
QR_TTL_SECONDS = 150
EXPIRED_ATTEMPT_RETENTION_SECONDS = 30
CONNECTED_TTL_SECONDS = 600
TOKEN_FIELDS = ("t", "uid", "expire_time", "access_token", "refresh_token")


class SmartLifeError(RuntimeError):
    pass


@dataclass
class LoginAttempt:
    user_id: str
    user_code: str
    token: str
    expires_at: float
    connected: bool = False
    devices: list[dict[str, str]] = field(default_factory=list)
    completed_at: float | None = None
    poll_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class MemoryTokenSaver:
    def __init__(self, session: dict[str, Any]):
        self.session = session

    def update_token(self, token_info: dict[str, Any]) -> None:
        self.session["token_info"] = {key: token_info.get(key) for key in TOKEN_FIELDS}


class SmartLifeService:
    def __init__(self) -> None:
        self._attempts: dict[str, LoginAttempt] = {}
        self._lock = Lock()

    @staticmethod
    def _mint_qr_token(user_code: str) -> str:
        try:
            from tuya_sharing import LoginControl
        except ImportError as exc:
            raise SmartLifeError("SmartLife sign-in dependencies are not installed.") from exc

        response = LoginControl().qr_code(CLIENT_ID, SCHEMA, user_code)
        if not response.get("success"):
            raise SmartLifeError("SmartLife could not create a sign-in QR code. Check the user code and try again.")
        token = (response.get("result") or {}).get("qrcode")
        if not token:
            raise SmartLifeError("SmartLife returned an invalid sign-in QR code.")
        return str(token)

    @staticmethod
    def _qr_data_url(token: str, scheme: str) -> str:
        try:
            import qrcode
        except ImportError as exc:
            raise SmartLifeError("QR-code dependencies are not installed.") from exc

        content = f"{scheme}--qrLogin?token={token}"
        image = qrcode.make(content)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

    async def start_login(self, user_id: str, user_code: str, scheme: str) -> dict[str, str]:
        token = await asyncio.to_thread(self._mint_qr_token, user_code)
        qr_data_url = await asyncio.to_thread(self._qr_data_url, token, scheme)
        login_id = secrets.token_urlsafe(24)
        attempt = LoginAttempt(
            user_id=user_id,
            user_code=user_code,
            token=token,
            expires_at=time.monotonic() + QR_TTL_SECONDS,
        )
        with self._lock:
            self._prune_expired()
            self._attempts[login_id] = attempt
        return {"login_id": login_id, "qr": qr_data_url}

    @staticmethod
    def _poll_login(token: str, user_code: str) -> dict[str, Any] | None:
        try:
            from tuya_sharing import LoginControl
        except ImportError as exc:
            raise SmartLifeError("SmartLife sign-in dependencies are not installed.") from exc

        authorized, result = LoginControl().login_result(token, CLIENT_ID, user_code)
        if not authorized:
            return None
        return {
            "client_id": CLIENT_ID,
            "user_code": user_code,
            "terminal_id": result.get("terminal_id"),
            "endpoint": result.get("endpoint") or result.get("end_point"),
            "token_info": {key: result.get(key) for key in TOKEN_FIELDS},
        }

    @staticmethod
    def _load_linked_devices(session: dict[str, Any]) -> list[dict[str, str]]:
        try:
            from tuya_sharing import Manager
        except ImportError as exc:
            raise SmartLifeError("SmartLife sign-in dependencies are not installed.") from exc

        manager = Manager(
            session["client_id"],
            session["user_code"],
            session["terminal_id"],
            session["endpoint"],
            session["token_info"],
            MemoryTokenSaver(session),
        )
        manager.update_device_cache()

        devices: list[dict[str, str]] = []
        for device in manager.device_map.values():
            device_id = getattr(device, "id", None)
            local_key = getattr(device, "local_key", None)
            if not device_id or not local_key:
                continue
            devices.append(
                {
                    "device_id": str(device_id),
                    "local_key": str(local_key),
                }
            )
        return devices

    def _prune_expired(self) -> None:
        now = time.monotonic()
        expired = [
            login_id
            for login_id, attempt in self._attempts.items()
            if now
            > (
                attempt.completed_at + CONNECTED_TTL_SECONDS
                if attempt.completed_at is not None
                else attempt.expires_at + EXPIRED_ATTEMPT_RETENTION_SECONDS
            )
        ]
        for login_id in expired:
            del self._attempts[login_id]

    async def poll_login(self, user_id: str, login_id: str) -> dict[str, Any]:
        with self._lock:
            self._prune_expired()
            attempt = self._attempts.get(login_id)
        if attempt is None or attempt.user_id != user_id:
            raise KeyError("SmartLife sign-in session was not found.")

        async with attempt.poll_lock:
            if attempt.connected:
                return {"status": "connected", "devices": attempt.devices}
            if time.monotonic() > attempt.expires_at:
                with self._lock:
                    self._attempts.pop(login_id, None)
                attempt.token = ""
                attempt.user_code = ""
                return {"status": "expired"}

            session = await asyncio.to_thread(
                self._poll_login,
                attempt.token,
                attempt.user_code,
            )
            if session is None:
                return {"status": "pending"}
            devices = await asyncio.to_thread(self._load_linked_devices, session)
            attempt.devices = devices
            attempt.connected = True
            attempt.completed_at = time.monotonic()
            attempt.token = ""
            attempt.user_code = ""
            logger.info("SmartLife account linked with %d devices.", len(devices))
            return {"status": "connected", "devices": devices}


smartlife_service = SmartLifeService()
