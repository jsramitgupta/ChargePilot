import asyncio
import ctypes
import logging
import threading
from collections.abc import Awaitable, Callable
from ctypes import wintypes

logger = logging.getLogger("chargepilot.connector.service")

SERVICE_WIN32_OWN_PROCESS = 0x00000010
SERVICE_STOPPED = 0x00000001
SERVICE_START_PENDING = 0x00000002
SERVICE_STOP_PENDING = 0x00000003
SERVICE_RUNNING = 0x00000004
SERVICE_ACCEPT_STOP = 0x00000001
SERVICE_ACCEPT_SHUTDOWN = 0x00000004
SERVICE_CONTROL_STOP = 0x00000001
SERVICE_CONTROL_SHUTDOWN = 0x00000005
_CALLBACK = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)


class ServiceStatus(ctypes.Structure):
    _fields_ = [
        ("service_type", wintypes.DWORD),
        ("current_state", wintypes.DWORD),
        ("controls_accepted", wintypes.DWORD),
        ("win32_exit_code", wintypes.DWORD),
        ("service_specific_exit_code", wintypes.DWORD),
        ("check_point", wintypes.DWORD),
        ("wait_hint", wintypes.DWORD),
    ]


class ServiceTableEntry(ctypes.Structure):
    pass


ServiceMain = _CALLBACK(None, wintypes.DWORD, ctypes.POINTER(wintypes.LPWSTR))
ServiceControlHandler = _CALLBACK(
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPVOID,
    wintypes.LPVOID,
)
ServiceTableEntry._fields_ = [
    ("service_name", wintypes.LPWSTR),
    ("service_proc", ServiceMain),
]
ServiceTable = ServiceTableEntry * 2


def run_windows_service(
    service_name: str,
    serve: Callable[[asyncio.Event, Callable[[], None]], Awaitable[None]],
) -> None:
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi32.RegisterServiceCtrlHandlerExW.argtypes = [
        wintypes.LPCWSTR,
        ServiceControlHandler,
        wintypes.LPVOID,
    ]
    advapi32.RegisterServiceCtrlHandlerExW.restype = wintypes.HANDLE
    advapi32.SetServiceStatus.argtypes = [wintypes.HANDLE, ctypes.POINTER(ServiceStatus)]
    advapi32.SetServiceStatus.restype = wintypes.BOOL
    advapi32.StartServiceCtrlDispatcherW.argtypes = [ctypes.POINTER(ServiceTableEntry)]
    advapi32.StartServiceCtrlDispatcherW.restype = wintypes.BOOL

    status_handle = None
    status = ServiceStatus(SERVICE_WIN32_OWN_PROCESS, SERVICE_START_PENDING, 0, 0, 0, 1, 30000)
    status_lock = threading.Lock()
    runtime: dict[str, object] = {"loop": None, "stop_event": None}

    def report(state: int, exit_code: int = 0) -> None:
        with status_lock:
            status.current_state = state
            status.controls_accepted = (
                SERVICE_ACCEPT_STOP | SERVICE_ACCEPT_SHUTDOWN
                if state == SERVICE_RUNNING
                else 0
            )
            status.win32_exit_code = exit_code
            status.wait_hint = 30000 if state in {SERVICE_START_PENDING, SERVICE_STOP_PENDING} else 0
            status.check_point = status.check_point + 1 if state in {
                SERVICE_START_PENDING,
                SERVICE_STOP_PENDING,
            } else 0
            if status_handle and not advapi32.SetServiceStatus(status_handle, ctypes.byref(status)):
                raise ctypes.WinError(ctypes.get_last_error())

    def handle_control(
        control: int,
        _event_type: int,
        _event_data: int,
        _context: int,
    ) -> int:
        if control in {SERVICE_CONTROL_STOP, SERVICE_CONTROL_SHUTDOWN}:
            report(SERVICE_STOP_PENDING)
            loop = runtime["loop"]
            stop_event = runtime["stop_event"]
            if loop is not None and stop_event is not None:
                loop.call_soon_threadsafe(stop_event.set)
            return 0
        return 0

    control_handler = ServiceControlHandler(handle_control)

    def service_main(_argc: int, _argv: ctypes.POINTER(wintypes.LPWSTR)) -> None:
        nonlocal status_handle
        status_handle = advapi32.RegisterServiceCtrlHandlerExW(
            service_name,
            control_handler,
            None,
        )
        if not status_handle:
            logger.error("Could not register the Windows service control handler.")
            return
        report(SERVICE_START_PENDING)

        async def run() -> None:
            loop = asyncio.get_running_loop()
            stop_event = asyncio.Event()
            runtime["loop"] = loop
            runtime["stop_event"] = stop_event

            def set_running() -> None:
                report(SERVICE_RUNNING)

            await serve(stop_event, set_running)

        try:
            asyncio.run(run())
            report(SERVICE_STOPPED)
        except Exception:
            logger.exception("The Windows service stopped unexpectedly.")
            try:
                report(SERVICE_STOPPED, 1)
            except OSError:
                logger.exception("Could not report the service's stopped state.")

    service_main_callback = ServiceMain(service_main)
    service_table = ServiceTable(
        ServiceTableEntry(service_name, service_main_callback),
        ServiceTableEntry(None, None),
    )
    if not advapi32.StartServiceCtrlDispatcherW(service_table):
        error = ctypes.get_last_error()
        raise ctypes.WinError(error)
