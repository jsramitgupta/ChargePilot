import argparse
import asyncio
import ctypes
import getpass
import ipaddress
import json
import logging
import math
import os
import random
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from tinytuya import OutletDevice, deviceScan
from websockets.asyncio.client import connect as websocket_connect
from websockets.exceptions import ConnectionClosed, InvalidStatus, WebSocketException

VERSION = "0.1.6"
HEARTBEAT_INTERVAL_SECONDS = 30
SAFETY_CLAIM_INTERVAL_SECONDS = 60
RECONNECT_MAX_SECONDS = 30
logger = logging.getLogger("chargepilot.connector")


def _config_path() -> Path:
    configured_path = os.environ.get("CHARGEPILOT_CONNECTOR_CONFIG")
    if configured_path:
        return Path(configured_path)
    if os.name == "nt":
        return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "ChargePilot" / "connector-config.json"
    return Path.home() / ".config" / "chargepilot" / "connector-config.json"


def _windows_service_config_path() -> Path:
    return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "ChargePilot" / "connector-config.json"


def _api_url(server_url: str, endpoint: str) -> str:
    return f"{server_url.rstrip('/')}/api/v1/connectors/{endpoint.lstrip('/')}"


def _websocket_url(server_url: str) -> str:
    parsed = urlsplit(server_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = f"{parsed.path.rstrip('/')}/api/v1/connectors/ws"
    return urlunsplit((scheme, parsed.netloc, path, "", ""))


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
                "*S-1-5-19:(OI)(CI)M",
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


def _normalize_device_type(device_type: str | None) -> str:
    value = (device_type or "default").strip()
    if not value:
        return "default"
    if value.lower() in {"switch", "plug", "outlet", "default"}:
        return "default"
    return value


def _read_device_dps(device: OutletDevice) -> dict[str, Any]:
    response = device.status()
    dps = response.get("dps") if isinstance(response, dict) else None
    if dps is None and isinstance(response, dict) and isinstance(response.get("data"), dict):
        dps = response["data"].get("dps")
    if dps is None and isinstance(response, dict) and isinstance(response.get("status"), dict):
        dps = response["status"]
    if not isinstance(dps, dict):
        raise RuntimeError("The local device returned no status datapoints.")
    return dps


def _read_device_state(device: OutletDevice, channel: int) -> bool:
    dps = _read_device_dps(device)
    state = _switch_state(dps.get(str(channel), dps.get(channel)))
    if state is None:
        raise RuntimeError("The local device returned an unsupported channel state.")
    return state


def _meter_value(dps: dict[str, Any], dp_id: Any, multiplier: Any) -> float | None:
    if not isinstance(dp_id, str) or not dp_id:
        return None
    raw_value = dps.get(dp_id)
    if raw_value is None and dp_id.isdigit():
        raw_value = dps.get(int(dp_id))
    if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float, str)):
        return None
    try:
        value = float(raw_value) * float(multiplier)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(value) or value < 0 or value > 1_000_000_000_000:
        return None
    return value


def _meter_readings(dps: dict[str, Any], device_info: dict[str, Any]) -> dict[str, float]:
    readings: dict[str, float] = {}
    power = _meter_value(
        dps,
        device_info.get("power_dp_id"),
        device_info.get("power_multiplier", 1.0),
    )
    energy = _meter_value(
        dps,
        device_info.get("energy_dp_id"),
        device_info.get("energy_multiplier", 0.001),
    )
    if power is not None:
        readings["power_watts"] = power
    if energy is not None:
        readings["energy_total_kwh"] = energy
    return readings


def _meter_candidates(dps: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    power_names = {"activepower", "curpower", "power", "powerw", "watt", "watts"}
    energy_names = {
        "addele",
        "electricenergy",
        "electricity",
        "energy",
        "energykwh",
        "energytotal",
        "totalenergy",
    }
    for raw_id, raw_value in dps.items():
        dp_id = str(raw_id).strip()
        if not dp_id or len(dp_id) > 50 or isinstance(raw_value, bool):
            continue
        if not isinstance(raw_value, (int, float, str)):
            continue
        try:
            sample = float(raw_value)
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(sample) or sample < 0 or sample > 1_000_000_000_000:
            continue
        normalized_id = "".join(character for character in dp_id.lower() if character.isalnum())
        role = (
            "power"
            if normalized_id in power_names
            else "energy"
            if normalized_id in energy_names
            else None
        )
        candidates.append(
            {
                "id": dp_id,
                "label": "Power reading" if role == "power" else "Energy reading" if role == "energy" else "Other reading",
                "sample": sample,
                "suggested_role": role,
            }
        )
        if len(candidates) == 32:
            break
    return candidates


def _execute_device_command(command: dict[str, Any]) -> dict[str, Any]:
    device_info = command.get("device")
    if not isinstance(device_info, dict):
        raise ValueError("The command did not include registered device details.")
    version = float(device_info.get("protocol_version") or 3.5)
    device = OutletDevice(
        device_info["device_id"],
        device_info["ip_address"],
        device_info["local_key"],
        _normalize_device_type(device_info.get("device_type")),
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
        dps = _read_device_dps(device)
        actual_state = _switch_state(dps.get(str(channel), dps.get(channel)))
        if actual_state is None:
            raise RuntimeError("The local device returned an unsupported channel state.")
        if actual_state != desired_state:
            raise RuntimeError("The switch did not report the requested state.")
        return {"state": actual_state, **_meter_readings(dps, device_info)}
    if command["operation"] == "get_status":
        dps = _read_device_dps(device)
        state = _switch_state(dps.get(str(channel), dps.get(channel)))
        if state is None:
            raise RuntimeError("The local device returned an unsupported channel state.")
        return {"state": state, **_meter_readings(dps, device_info)}
    if command["operation"] == "inspect_meter":
        return {"candidates": _meter_candidates(_read_device_dps(device))}
    raise ValueError("Unsupported device operation.")


async def _execute_command(command: dict[str, Any]) -> dict[str, Any]:
    if command.get("operation") == "discover":
        return {"devices": await asyncio.to_thread(_discover)}
    return await asyncio.to_thread(_execute_device_command, command)


async def _drain_commands(
    client: httpx.AsyncClient,
    base_url: str,
    headers: dict[str, str],
    stop_event: asyncio.Event | None = None,
) -> None:
    while True:
        if stop_event is not None and stop_event.is_set():
            return
        response = await client.post(
            _api_url(base_url, "commands/claim"),
            headers=headers,
            json={},
        )
        response.raise_for_status()
        command = response.json().get("command")
        if not command:
            return

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


async def _run_websocket_session(
    client: httpx.AsyncClient,
    base_url: str,
    headers: dict[str, str],
    stop_event: asyncio.Event | None = None,
) -> None:
    async with websocket_connect(
        _websocket_url(base_url),
        additional_headers=headers,
        open_timeout=10,
        ping_interval=20,
        ping_timeout=20,
        close_timeout=10,
        max_size=1024,
        compression=None,
    ) as websocket:
        connected = json.loads(await websocket.recv())
        if not isinstance(connected, dict) or connected.get("type") != "connected":
            raise RuntimeError("ChargePilot returned an invalid WebSocket handshake response.")
        await websocket.send(json.dumps({"type": "hello", "version": VERSION}))
        await _drain_commands(client, base_url, headers, stop_event)
        loop = asyncio.get_running_loop()
        last_heartbeat = loop.time()
        last_safety_claim = loop.time()

        while True:
            if stop_event is not None and stop_event.is_set():
                return
            now = loop.time()
            next_deadline = min(
                last_heartbeat + HEARTBEAT_INTERVAL_SECONDS,
                last_safety_claim + SAFETY_CLAIM_INTERVAL_SECONDS,
            )
            try:
                message = await asyncio.wait_for(
                    websocket.recv(),
                    timeout=min(1, max(0, next_deadline - now))
                    if stop_event is not None
                    else max(0, next_deadline - now),
                )
            except TimeoutError:
                if stop_event is not None and stop_event.is_set():
                    return
                now = loop.time()
                if now - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
                    await websocket.send(
                        json.dumps({"type": "heartbeat", "version": VERSION})
                    )
                    last_heartbeat = now
                if now - last_safety_claim >= SAFETY_CLAIM_INTERVAL_SECONDS:
                    await _drain_commands(client, base_url, headers, stop_event)
                    last_safety_claim = now
                continue

            notification = json.loads(message)
            if (
                isinstance(notification, dict)
                and notification.get("type") == "commands_available"
            ):
                await _drain_commands(client, base_url, headers, stop_event)
                last_safety_claim = loop.time()


async def run_connector(
    server_url: str | None,
    enrollment_code: str | None,
    config_path: Path,
    stop_event: asyncio.Event | None = None,
) -> None:
    async with httpx.AsyncClient(timeout=httpx.Timeout(40.0, connect=10.0)) as client:
        config: dict[str, str]
        if config_path.exists():
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["serverUrl"] = _validate_server_url(config["serverUrl"])
        else:
            if not server_url:
                raise ValueError("--server-url is required for first-time enrollment.")
            server_url = _validate_server_url(server_url)
            if enrollment_code:
                code = enrollment_code
            elif sys.stdin.isatty():
                code = getpass.getpass("One-time ChargePilot enrollment code: ")
            else:
                raise ValueError(
                    "First-time enrollment requires CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE "
                    "when running without an interactive terminal."
                )
            config = await _enroll(client, server_url, code, config_path)
        base_url = config["serverUrl"]
        headers = {"Authorization": f"Bearer {config['token']}"}
        reconnect_delay = 1.0
        while stop_event is None or not stop_event.is_set():
            session_started = asyncio.get_running_loop().time()
            try:
                await _run_websocket_session(client, base_url, headers, stop_event)
            except InvalidStatus as exc:
                if exc.response.status_code in {401, 403}:
                    raise RuntimeError(
                        "ChargePilot rejected the connector credential."
                    ) from exc
                logger.warning(
                    "ChargePilot WebSocket handshake failed with HTTP %s.",
                    exc.response.status_code,
                )
                if asyncio.get_running_loop().time() - session_started >= 60:
                    reconnect_delay = 1.0
                delay = random.uniform(reconnect_delay / 2, reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, RECONNECT_MAX_SECONDS)
                await _wait_for_stop(stop_event, delay)
            except ConnectionClosed as exc:
                if exc.rcvd is not None and exc.rcvd.code in {1003, 1008}:
                    raise RuntimeError(
                        "ChargePilot closed the connector WebSocket due to a policy error."
                    ) from exc
                logger.warning(
                    "ChargePilot WebSocket closed (%s).",
                    exc.rcvd.code if exc.rcvd is not None else "without a close code",
                )
                if asyncio.get_running_loop().time() - session_started >= 60:
                    reconnect_delay = 1.0
                delay = random.uniform(reconnect_delay / 2, reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, RECONNECT_MAX_SECONDS)
                await _wait_for_stop(stop_event, delay)
            except (
                WebSocketException,
                httpx.HTTPError,
                OSError,
                TimeoutError,
                ValueError,
                KeyError,
            ) as exc:
                logger.warning(
                    "ChargePilot connection is unavailable (%s).",
                    type(exc).__name__,
                )
                if asyncio.get_running_loop().time() - session_started >= 60:
                    reconnect_delay = 1.0
                delay = random.uniform(reconnect_delay / 2, reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, RECONNECT_MAX_SECONDS)
                await _wait_for_stop(stop_event, delay)


async def _wait_for_stop(stop_event: asyncio.Event | None, timeout: float) -> None:
    if stop_event is None:
        await asyncio.sleep(timeout)
        return
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=timeout)
    except TimeoutError:
        pass


SERVICE_NAME = "ChargePilotConnector"
INSTALL_DIRECTORY = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "ChargePilot" / "Connector"


def _require_windows_admin() -> None:
    if os.name != "nt":
        raise RuntimeError("The Windows service installer is available only on Windows.")
    if not ctypes.windll.shell32.IsUserAnAdmin():
        arguments = subprocess.list2cmdline(sys.argv[1:])
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, arguments, None, 1
        )
        if result <= 32:
            raise RuntimeError("Administrator permission is required to manage the connector service.")
        raise SystemExit(0)


def _run_sc(*arguments: str, allow_failure: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["sc.exe", *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode and not allow_failure:
        details = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"Windows service command failed: {details or result.returncode}")
    return result


async def _install_windows_connector(server_url: str) -> None:
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Install the packaged ChargePilotConnector.exe to register the Windows service.")
    server_url = _validate_server_url(server_url)
    _require_windows_admin()
    existing_service = _run_sc("query", SERVICE_NAME, allow_failure=True)
    if existing_service.returncode == 0:
        raise RuntimeError("The ChargePilot connector service is already installed.")

    config_path = _windows_service_config_path()
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["serverUrl"] = _validate_server_url(config["serverUrl"])
    else:
        code = getpass.getpass("One-time ChargePilot enrollment code: ")
        if not code:
            raise ValueError("The one-time enrollment code cannot be empty.")
        async with httpx.AsyncClient(timeout=httpx.Timeout(40.0, connect=10.0)) as client:
            config = await _enroll(client, server_url, code, config_path)

    executable = INSTALL_DIRECTORY / "ChargePilotConnector.exe"
    INSTALL_DIRECTORY.mkdir(parents=True, exist_ok=True)
    shutil.copy2(sys.executable, executable)
    command = subprocess.list2cmdline([str(executable), "service"])
    _run_sc(
        "create",
        SERVICE_NAME,
        "binPath=",
        command,
        "start=",
        "auto",
        "obj=",
        "NT AUTHORITY\\LocalService",
        "DisplayName=",
        "ChargePilot Site Connector",
    )
    _run_sc(
        "description",
        SERVICE_NAME,
        "Runs ChargePilot's local Tuya connector and durable command client.",
    )
    _run_sc(
        "failure",
        SERVICE_NAME,
        "reset=",
        "86400",
        "actions=",
        "restart/5000/restart/5000/restart/30000",
    )
    _run_sc("start", SERVICE_NAME)
    logger.info("ChargePilot connector service installed and started.")


async def _run_windows_service() -> None:
    if __package__:
        from .windows_service import run_windows_service
    else:
        from windows_service import run_windows_service

    async def serve(stop_event: asyncio.Event, set_running: Any) -> None:
        set_running()
        await run_connector(None, None, _windows_service_config_path(), stop_event)

    run_windows_service(SERVICE_NAME, serve)


def _manage_windows_service(command: str) -> None:
    _require_windows_admin()
    if command == "start":
        _run_sc("start", SERVICE_NAME)
    elif command == "stop":
        _run_sc("stop", SERVICE_NAME)
    elif command == "status":
        result = _run_sc("query", SERVICE_NAME, allow_failure=True)
        print((result.stdout or result.stderr).strip())
        if result.returncode:
            raise RuntimeError("The ChargePilot connector service is not installed.")
    elif command == "uninstall":
        _run_sc("stop", SERVICE_NAME, allow_failure=True)
        _run_sc("delete", SERVICE_NAME)
        config_path = _windows_service_config_path()
        if config_path.exists():
            config_path.unlink()
        logger.info("Connector service removed. Revoke its credential in ChargePilot if it is no longer needed.")


def _run_service_command() -> None:
    log_directory = _windows_service_config_path().parent / "logs"
    log_directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_directory / "connector.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[handler],
        force=True,
    )
    asyncio.run(_run_windows_service())


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "run"
    if command in {"install", "uninstall", "start", "stop", "status", "service"}:
        arguments = sys.argv[2:]
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        try:
            if command == "install":
                parser = argparse.ArgumentParser(description="Install the ChargePilot Windows connector service.")
                parser.add_argument("--server-url", required=True, help="Public ChargePilot API origin.")
                asyncio.run(_install_windows_connector(parser.parse_args(arguments).server_url))
            elif command == "service":
                if arguments:
                    raise ValueError("The service command accepts no arguments.")
                _run_service_command()
            else:
                if arguments:
                    raise ValueError(f"The {command} command accepts no arguments.")
                _manage_windows_service(command)
            return
        except KeyboardInterrupt:
            return
        except Exception as exc:
            logger.error("Connector %s failed: %s", command, exc)
            sys.exit(1)

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
        help="Read the one-time enrollment code from a file (legacy option).",
    )
    parser.add_argument("--config", type=Path, default=_config_path(), help="Connector configuration path.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        enrollment_code = args.enrollment_code or os.environ.pop("CHARGEPILOT_CONNECTOR_ENROLLMENT_CODE", None)
        if args.enrollment_code_file and not args.config.exists() and not enrollment_code:
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
