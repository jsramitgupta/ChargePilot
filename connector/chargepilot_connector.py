import argparse
import asyncio
import getpass
import ipaddress
import json
import logging
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from tinytuya import OutletDevice, deviceScan

VERSION = "0.1.0"
POLL_INTERVAL_SECONDS = 3
HEARTBEAT_INTERVAL_SECONDS = 20
logger = logging.getLogger("chargepilot.connector")


def _config_path() -> Path:
    configured_path = os.environ.get("CHARGEPILOT_CONNECTOR_CONFIG")
    if configured_path:
        return Path(configured_path)
    if os.name == "nt":
        return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "ChargePilot" / "connector-config.json"
    return Path.home() / ".config" / "chargepilot" / "connector-config.json"


def _api_url(server_url: str, endpoint: str) -> str:
    return f"{server_url.rstrip('/')}/api/v1/connectors/{endpoint.lstrip('/')}"


def _validate_server_url(server_url: str) -> str:
    parsed = urlsplit(server_url)
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("ChargePilot server URL must be an absolute URL without credentials, query, or fragment.")
    if parsed.scheme == "https":
        return server_url.rstrip("/")
    if parsed.scheme == "http" and parsed.hostname.lower() == "localhost":
        return server_url.rstrip("/")
    if parsed.scheme == "http":
        try:
            if ipaddress.ip_address(parsed.hostname).is_loopback:
                return server_url.rstrip("/")
        except ValueError:
            pass
    raise ValueError("ChargePilot server URL must use HTTPS; HTTP is allowed only for loopback development.")


def _save_config(path: Path, config: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        username = getpass.getuser()
        result = subprocess.run(
            [
                "icacls",
                str(path.parent),
                "/inheritance:r",
                "/grant:r",
                f"{username}:(OI)(CI)F",
                "*S-1-5-18:(OI)(CI)F",
                "*S-1-5-32-544:(OI)(CI)F",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError("Could not restrict permissions on the connector configuration directory.")
    else:
        path.parent.chmod(stat.S_IRWXU)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    if os.name != "nt":
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)


async def _enroll(client: httpx.AsyncClient, server_url: str, code: str, config_path: Path) -> dict[str, str]:
    server_url = _validate_server_url(server_url)
    response = await client.post(
        _api_url(server_url, "enroll"),
        headers={"Authorization": f"Bearer {code}"},
        json={"version": VERSION},
    )
    response.raise_for_status()
    enrollment = response.json()
    config = {
        "serverUrl": server_url.rstrip("/"),
        "connectorId": enrollment["connector_id"],
        "token": enrollment["token"],
        "version": VERSION,
    }
    _save_config(config_path, config)
    return config


def _normalize_discovery_record(record: dict[str, Any], fallback_ip: str | None = None) -> dict[str, str]:
    ip_address = str(record.get("ip") or record.get("ip_address") or fallback_ip or "unknown")
    device_id = str(
        record.get("gwId") or record.get("device_id") or record.get("id") or record.get("deviceId") or ip_address
    )
    return {
        "device_id": device_id,
        "name": str(record.get("name") or record.get("device_name") or f"Tuya Device {device_id}"),
        "ip_address": ip_address,
        "protocol_version": str(record.get("version") or record.get("protocol_version") or "3.5"),
        "device_type": str(record.get("device_type") or "switch"),
    }


def _discover() -> list[dict[str, str]]:
    try:
        found = deviceScan(verbose=False, maxretry=10, color=False, poll=False, forcescan=False)
    except TypeError:
        found = deviceScan(verbose=False, color=False, poll=False, forcescan=False)
    records = found.items() if isinstance(found, dict) else enumerate(found) if isinstance(found, list) else []
    devices: dict[str, dict[str, str]] = {}
    for key, value in records:
        if isinstance(value, dict):
            normalized = _normalize_discovery_record(value, str(key) if isinstance(found, dict) else None)
            devices[normalized["device_id"]] = normalized
    return list(devices.values())


def _switch_state(value: Any) -> bool | None:
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
    return None


def _read_device_state(device: OutletDevice, channel: int) -> bool:
    response = device.status(switch=channel)
    dps = response.get("dps") if isinstance(response, dict) else None
    if dps is None and isinstance(response, dict) and isinstance(response.get("data"), dict):
        dps = response["data"].get("dps")
    if dps is None and isinstance(response, dict) and isinstance(response.get("status"), dict):
        dps = response["status"]
    if not isinstance(dps, dict):
        raise RuntimeError("The local device returned no channel state.")
    state = _switch_state(dps.get(str(channel), dps.get(channel)))
    if state is None:
        raise RuntimeError("The local device returned an unsupported channel state.")
    return state


def _execute_device_command(command: dict[str, Any]) -> dict[str, Any]:
    device_info = command.get("device")
    if not isinstance(device_info, dict):
        raise ValueError("The command did not include registered device details.")
    version = float(device_info.get("protocol_version") or 3.5)
    device = OutletDevice(
        device_info["device_id"],
        device_info["ip_address"],
        device_info["local_key"],
        device_info.get("device_type") or "default",
        version=version,
    )
    channel = int(command.get("channel_index") or 1)
    if command["operation"] == "set_state":
        desired_state = bool(command["desired_state"])
        response = (
            device.turn_on(switch=channel)
            if desired_state
            else device.turn_off(switch=channel)
        )
        success = not isinstance(response, dict) or bool(response.get("success", True))
        if isinstance(response, dict) and response.get("error"):
            raise RuntimeError("The local device rejected the requested state.")
        if not success:
            raise RuntimeError("The local device rejected the requested state.")
        actual_state = _read_device_state(device, channel)
        if actual_state != desired_state:
            raise RuntimeError("The switch did not report the requested state.")
        return {"state": actual_state}
    if command["operation"] == "get_status":
        return {"state": _read_device_state(device, channel)}
    raise ValueError("Unsupported device operation.")


async def _execute_command(command: dict[str, Any]) -> dict[str, Any]:
    if command.get("operation") == "discover":
        return {"devices": await asyncio.to_thread(_discover)}
    return await asyncio.to_thread(_execute_device_command, command)


async def run_connector(server_url: str | None, enrollment_code: str | None, config_path: Path) -> None:
    async with httpx.AsyncClient(timeout=httpx.Timeout(40.0, connect=10.0)) as client:
        config: dict[str, str]
        if config_path.exists():
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["serverUrl"] = _validate_server_url(config["serverUrl"])
        else:
            if not server_url:
                raise ValueError("--server-url is required for first-time enrollment.")
            server_url = _validate_server_url(server_url)
            code = enrollment_code or getpass.getpass("One-time ChargePilot enrollment code: ")
            config = await _enroll(client, server_url, code, config_path)
        base_url = config["serverUrl"]
        headers = {"Authorization": f"Bearer {config['token']}"}
        last_heartbeat = 0.0

        while True:
            loop_time = asyncio.get_running_loop().time()
            try:
                if loop_time - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
                    response = await client.post(
                        _api_url(base_url, "heartbeat"),
                        headers=headers,
                        json={"version": VERSION},
                    )
                    response.raise_for_status()
                    last_heartbeat = loop_time

                response = await client.post(
                    _api_url(base_url, "commands/claim"),
                    headers=headers,
                    json={},
                )
                response.raise_for_status()
                command = response.json().get("command")
                if not command:
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                    continue

                try:
                    result = await _execute_command(command)
                    acknowledgment = {"success": True, "result": result}
                except Exception as exc:
                    logger.warning("Command %s failed: %s", command.get("id"), exc)
                    acknowledgment = {
                        "success": False,
                        "error": "Local device operation failed; check connector and device logs.",
                        "result": {},
                    }
                response = await client.post(
                    _api_url(base_url, f"commands/{command['id']}/result"),
                    headers=headers,
                    json=acknowledgment,
                )
                response.raise_for_status()
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                logger.warning("ChargePilot connection is unavailable: %s", exc)
                await asyncio.sleep(min(POLL_INTERVAL_SECONDS * 2, 30))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ChargePilot site connector.")
    parser.add_argument(
        "--server-url",
        default=os.environ.get("CHARGEPILOT_CONNECTOR_SERVER_URL"),
        help="ChargePilot base URL, required only for enrollment.",
    )
    parser.add_argument("--enrollment-code", help=argparse.SUPPRESS)
    parser.add_argument(
        "--enrollment-code-file",
        default=os.environ.get("CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE_FILE"),
        help="Read the one-time enrollment code from a file, e.g. a Docker secret.",
    )
    parser.add_argument("--config", type=Path, default=_config_path(), help="Connector configuration path.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        enrollment_code = args.enrollment_code
        if args.enrollment_code_file and not args.config.exists():
            enrollment_code = Path(args.enrollment_code_file).read_text(encoding="utf-8").strip()
            if not enrollment_code:
                raise ValueError("The enrollment code file is empty.")
        asyncio.run(run_connector(args.server_url, enrollment_code, args.config))
    except KeyboardInterrupt:
        return
    except Exception as exc:
        logger.error("Connector stopped: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
