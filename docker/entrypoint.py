import signal
import subprocess
import sys
import time


def stop_processes(processes: list[subprocess.Popen]):
    for process in processes:
        if process.poll() is None:
            process.terminate()

    for process in processes:
        if process.poll() is None:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main() -> int:
    processes = [
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
            ]
        ),
        subprocess.Popen([sys.executable, "-m", "app.frontend_server"]),
    ]
    stopping = False

    def request_stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    exit_code = 0
    try:
        while not stopping:
            completed = next(
                (process for process in processes if process.poll() is not None),
                None,
            )
            if completed is not None:
                exit_code = completed.returncode or 1
                break
            time.sleep(0.25)
    finally:
        stop_processes(processes)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
