"""Start the Streamlit app with a bounded health check.

Running ``python -m streamlit run app.py`` directly is correct for a manual
server session, but it never returns while the server is alive. This launcher
keeps automated checks from hanging by starting Streamlit in the background,
waiting for one HTTP response, and then either stopping it or leaving it running.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORT = int(os.environ.get("DEMO_PORT", "8501"))
DEFAULT_TIMEOUT_SECONDS = 30.0


class ProcessLike(Protocol):
    pid: int

    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...


PopenFactory = Callable[..., ProcessLike]
HealthWaiter = Callable[[str, float, float], bool]


def build_streamlit_command(app_path: Path, port: int) -> list[str]:
    """Build the Streamlit command without invoking a blocking shell."""

    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.headless=true",
        f"--server.port={port}",
        "--browser.gatherUsageStats=false",
    ]


def wait_for_http_ok(url: str, timeout_seconds: float, poll_interval_seconds: float = 0.5) -> bool:
    """Return True if the URL responds with HTTP 2xx/3xx before the timeout."""

    deadline = time.monotonic() + max(timeout_seconds, 0)
    while time.monotonic() <= deadline:
        if _http_status_ok(url):
            return True
        time.sleep(poll_interval_seconds)
    return False


def run_streamlit(
    *,
    app_path: Path = PROJECT_ROOT / "app.py",
    port: int = DEFAULT_PORT,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    keep_running: bool = False,
    popen_factory: PopenFactory | None = None,
    health_waiter: HealthWaiter | None = None,
    reports_dir: Path = PROJECT_ROOT / "reports",
) -> int:
    """Start Streamlit and exit with a bounded health-check result."""

    popen_factory = popen_factory or subprocess.Popen
    health_waiter = health_waiter or wait_for_http_ok
    app_path = app_path.resolve()
    url = f"http://localhost:{port}"

    if health_waiter(url, 0.2, 0.1):
        print(f"Streamlit is already responding at {url}")
        return 0

    reports_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = reports_dir / "streamlit_start.out.log"
    stderr_path = reports_dir / "streamlit_start.err.log"
    command = build_streamlit_command(app_path, port)

    with stdout_path.open("ab") as stdout_file, stderr_path.open("ab") as stderr_file:
        process = popen_factory(
            command,
            cwd=str(PROJECT_ROOT),
            stdout=stdout_file,
            stderr=stderr_file,
        )

    if health_waiter(url, timeout_seconds, 0.5):
        print(f"Streamlit is healthy at {url} (pid={process.pid})")
        if keep_running:
            print("Server left running. Stop it from Task Manager or with Stop-Process if needed.")
        else:
            _terminate_process(process)
            print("Smoke check complete; temporary Streamlit server stopped.")
        return 0

    _terminate_process(process)
    print(f"Streamlit did not respond within {timeout_seconds:.0f}s.")
    print(f"stdout log: {stdout_path}")
    print(f"stderr log: {stderr_path}")
    return 1


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start Streamlit with a bounded health check.")
    parser.add_argument("--app", type=Path, default=PROJECT_ROOT / "app.py", help="Streamlit app path.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind. Defaults to DEMO_PORT or 8501.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS, help="Health-check timeout in seconds.")
    parser.add_argument(
        "--keep-running",
        action="store_true",
        help="Leave the Streamlit server running after the health check succeeds.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return run_streamlit(
        app_path=args.app,
        port=args.port,
        timeout_seconds=args.timeout,
        keep_running=args.keep_running,
    )


def _http_status_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            return 200 <= response.status < 400
    except (OSError, urllib.error.URLError):
        return False


def _terminate_process(process: ProcessLike) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
