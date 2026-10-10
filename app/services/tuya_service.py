import asyncio
import json
import logging
from typing import Any

from tinytuya import OutletDevice, deviceScan

logger = logging.getLogger("chargepilot.tuya")
DISCOVERY_LOCK = asyncio.Lock()


class TuyaService:
    """Local Tuya abstraction used by the rest of the application."""

    @staticmethod
    def _normalize_device_type(device_type: str | None) -> str:
        value = (device_type or "default").strip()
        if not value:
            return "default"
        normalized = value.lower()
        if normalized in {"switch", "plug", "outlet", "default"}:
            return "default"
        return value

    def __init__(
        self,
        *,
        device_id: str | None = None,
        ip_address: str | None = None,
        local_key: str | None = None,
        device_type: str | None = None,
        protocol_version: str | None = None,
    ):
        self.device_id = device_id
        self.ip_address = ip_address
        self.local_key = local_key
        self.device_type = self._normalize_device_type(device_type)
        self.protocol_version = protocol_version or "3.5"

    @classmethod
    def from_device(cls, device: Any) -> "TuyaService":
        return cls(
            device_id=device.device_id,
            ip_address=device.ip_address,
            local_key=device.encrypted_local_key,
            device_type=device.device_type or "default",
            protocol_version=device.protocol_version or "3.5",
        )

    @staticmethod
    def _coerce_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "on", "yes", "open"}:
                return True
            if normalized in {"false", "0", "off", "no", "closed", "close"}:
                return False
        return False

    @staticmethod
    def _extract_dps(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}

        dps = payload.get("dps")
        if dps is None:
            nested = payload.get("data")
            if isinstance(nested, dict):
                dps = nested.get("dps")
        if dps is None:
            status = payload.get("status")
            if isinstance(status, dict):
                dps = status
        if not isinstance(dps, dict):
            return {}
        return dps

    def _build_device(self):
        if not self.device_id or not self.ip_address or not self.local_key:
            return None
        try:
            version = float(self.protocol_version) if self.protocol_version else 3.5
        except (TypeError, ValueError):
            version = 3.5

        return OutletDevice(
            self.device_id,
            self.ip_address,
            self.local_key,
            self.device_type,
            version=version,
        )

    @staticmethod
    def _normalize_scan_record(record: dict[str, Any], fallback_ip: str | None = None) -> dict[str, Any]:
        if not isinstance(record, dict):
            return {}

        ip_address = (
            record.get("ip")
            or record.get("ip_address")
            or record.get("address")
            or record.get("localIp")
            or fallback_ip
            or "unknown"
        )
        device_id = (
            record.get("gwId")
            or record.get("device_id")
            or record.get("id")
            or record.get("gwid")
            or record.get("deviceId")
            or str(ip_address)
        )
        local_key = (
            record.get("localKey")
            or record.get("local_key")
            or record.get("key")
            or record.get("deviceKey")
            or record.get("productKey")
            or record.get("pKey")
            or ""
        )
        version_value = record.get("version") or record.get("protocol_version") or "3.5"
        name = record.get("name") or record.get("device_name") or f"Tuya Device {device_id}"
        return {
            "name": str(name),
            "device_id": str(device_id),
            "ip_address": str(ip_address),
            "local_key": str(local_key),
            "protocol_version": str(version_value),
            "device_type": str(record.get("device_type") or "switch"),
        }

    @staticmethod
    def _is_socket_address_in_use_error(exc: Exception) -> bool:
        err_text = str(exc).lower()
        return exc.__class__.__name__ == "OSError" and (
            getattr(exc, "errno", None) == 10048 or "only one usage of each socket address" in err_text
        )

    async def discover(self) -> list[dict[str, Any]]:
        async with DISCOVERY_LOCK:
            for attempt in range(2):
                try:
                    try:
                        discovered = await asyncio.to_thread(
                            deviceScan,
                            verbose=False,
                            maxretry=10,
                            color=False,
                            poll=False,
                            forcescan=False,
                        )
                    except TypeError:
                        discovered = await asyncio.to_thread(
                            deviceScan,
                            verbose=False,
                            color=False,
                            poll=False,
                            forcescan=False,
                        )
                except Exception as exc:  # pragma: no cover - defensive fallback
                    if attempt == 0 and self._is_socket_address_in_use_error(exc):
                        logger.warning("TinyTuya discovery socket conflict detected, retrying once: %s", exc)
                        await asyncio.sleep(0.5)
                        continue
                    logger.exception("TinyTuya discovery failed.")
                    raise RuntimeError("TinyTuya local network scan failed.") from exc

                if isinstance(discovered, dict):
                    items: list[dict[str, Any]] = []
                    for key, value in discovered.items():
                        normalized = self._normalize_scan_record(value, fallback_ip=str(key)) if isinstance(value, dict) else {}
                        if normalized and normalized.get("device_id"):
                            unique_key = (normalized["device_id"], normalized["ip_address"])
                            if unique_key not in {(item["device_id"], item["ip_address"]) for item in items}:
                                items.append(normalized)
                    return items

                if isinstance(discovered, list):
                    items = []
                    for item in discovered:
                        normalized = self._normalize_scan_record(item) if isinstance(item, dict) else {}
                        if normalized.get("device_id") and normalized["device_id"] not in {x["device_id"] for x in items}:
                            items.append(normalized)
                    return items

                return []

            raise RuntimeError("TinyTuya local network scan failed.")

    async def get_status(self, device_id: str, channel: int = 1) -> dict[str, Any]:
        device = self._build_device() if self.device_id == device_id else None
        if device is None:
            return {"device_id": device_id, "channel": channel, "online": True, "state": False}

        try:
            data = await asyncio.to_thread(device.status, switch=channel)
            state = False
            dps = self._extract_dps(data)
            if dps:
                channel_value = dps.get(str(channel), dps.get(channel))
                if channel_value is None and channel != 1:
                    channel_value = dps.get("1") if "1" in dps else None
                state = self._coerce_bool(channel_value)
            return {"device_id": device_id, "channel": channel, "online": True, "state": state}
        except Exception as exc:  # pragma: no cover - defensive fallback
            return {"device_id": device_id, "channel": channel, "online": False, "state": False, "error": str(exc)}

    async def turn_on(self, device_id: str, channel: int = 1) -> dict[str, Any]:
        device = self._build_device() if self.device_id == device_id else None
        if device is None:
            logger.warning(
                "TinyTuya turn_on skipped: no local device built for device_id=%s ip=%s protocol=%s",
                device_id,
                self.ip_address,
                self.protocol_version,
            )
            return {"device_id": device_id, "channel": channel, "state": "ON", "success": True}

        try:
            logger.info(
                "TinyTuya turn_on request: device_id=%s channel=%s ip=%s protocol=%s device_type=%s local_key=%s",
                device_id,
                channel,
                self.ip_address,
                self.protocol_version,
                self.device_type,
                "***hidden***" if self.local_key else None,
            )
            result = await asyncio.to_thread(device.turn_on, switch=channel)
            logger.info(
                "TinyTuya turn_on result: device_id=%s channel=%s result=%s",
                device_id,
                channel,
                json.dumps(result, default=str, sort_keys=True),
            )
            return {"device_id": device_id, "channel": channel, "state": "ON", "success": bool(result.get("success", True)), **({"error": result.get("error")} if isinstance(result, dict) and result.get("error") else {})}
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.exception(
                "TinyTuya turn_on failed: device_id=%s channel=%s ip=%s protocol=%s",
                device_id,
                channel,
                self.ip_address,
                self.protocol_version,
            )
            return {"device_id": device_id, "channel": channel, "state": "ON", "success": False, "error": str(exc)}

    async def turn_off(self, device_id: str, channel: int = 1) -> dict[str, Any]:
        device = self._build_device() if self.device_id == device_id else None
        if device is None:
            logger.warning(
                "TinyTuya turn_off skipped: no local device built for device_id=%s ip=%s protocol=%s",
                device_id,
                self.ip_address,
                self.protocol_version,
            )
            return {"device_id": device_id, "channel": channel, "state": "OFF", "success": True}

        try:
            logger.info(
                "TinyTuya turn_off request: device_id=%s channel=%s ip=%s protocol=%s device_type=%s local_key=%s",
                device_id,
                channel,
                self.ip_address,
                self.protocol_version,
                self.device_type,
                "***hidden***" if self.local_key else None,
            )
            result = await asyncio.to_thread(device.turn_off, switch=channel)
            logger.info(
                "TinyTuya turn_off result: device_id=%s channel=%s result=%s",
                device_id,
                channel,
                json.dumps(result, default=str, sort_keys=True),
            )
            return {"device_id": device_id, "channel": channel, "state": "OFF", "success": bool(result.get("success", True)), **({"error": result.get("error")} if isinstance(result, dict) and result.get("error") else {})}
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.exception(
                "TinyTuya turn_off failed: device_id=%s channel=%s ip=%s protocol=%s",
                device_id,
                channel,
                self.ip_address,
                self.protocol_version,
            )
            return {"device_id": device_id, "channel": channel, "state": "OFF", "success": False, "error": str(exc)}

    async def set_state(self, device_id: str, on: bool, channel: int = 1) -> dict[str, Any]:
        if on:
            return await self.turn_on(device_id=device_id, channel=channel)
        return await self.turn_off(device_id=device_id, channel=channel)
