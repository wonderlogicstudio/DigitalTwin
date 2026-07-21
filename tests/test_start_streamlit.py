"""Tests for the bounded Streamlit launcher."""

from __future__ import annotations

import sys
from pathlib import Path

from scripts.start_streamlit import build_streamlit_command, run_streamlit


class FakeProcess:
    def __init__(self) -> None:
        self.pid = 12345
        self.terminated = False
        self.killed = False
        self.return_code: int | None = None

    def poll(self) -> int | None:
        return self.return_code

    def terminate(self) -> None:
        self.terminated = True
        self.return_code = 0

    def kill(self) -> None:
        self.killed = True
        self.return_code = -9

    def wait(self, timeout: float | None = None) -> int:
        return self.return_code or 0


def test_build_streamlit_command_uses_nonblocking_module_runner() -> None:
    command = build_streamlit_command(Path("app.py"), 8502)

    assert command[:4] == [sys.executable, "-m", "streamlit", "run"]
    assert "app.py" in command
    assert "--server.headless=true" in command
    assert "--server.port=8502" in command
    assert "--browser.gatherUsageStats=false" in command


def test_run_streamlit_stops_temporary_server_after_success(tmp_path: Path) -> None:
    process = FakeProcess()
    calls: list[float] = []

    def fake_waiter(url: str, timeout_seconds: float, poll_interval_seconds: float) -> bool:
        calls.append(timeout_seconds)
        return len(calls) == 2

    exit_code = run_streamlit(
        app_path=tmp_path / "app.py",
        port=8503,
        timeout_seconds=1,
        keep_running=False,
        popen_factory=lambda *args, **kwargs: process,
        health_waiter=fake_waiter,
        reports_dir=tmp_path / "reports",
    )

    assert exit_code == 0
    assert process.terminated is True
    assert process.killed is False


def test_run_streamlit_leaves_server_running_when_requested(tmp_path: Path) -> None:
    process = FakeProcess()
    calls = 0

    def fake_waiter(url: str, timeout_seconds: float, poll_interval_seconds: float) -> bool:
        nonlocal calls
        calls += 1
        return calls == 2

    exit_code = run_streamlit(
        app_path=tmp_path / "app.py",
        port=8504,
        timeout_seconds=1,
        keep_running=True,
        popen_factory=lambda *args, **kwargs: process,
        health_waiter=fake_waiter,
        reports_dir=tmp_path / "reports",
    )

    assert exit_code == 0
    assert process.terminated is False


def test_run_streamlit_returns_failure_and_stops_on_timeout(tmp_path: Path) -> None:
    process = FakeProcess()

    exit_code = run_streamlit(
        app_path=tmp_path / "app.py",
        port=8505,
        timeout_seconds=1,
        keep_running=False,
        popen_factory=lambda *args, **kwargs: process,
        health_waiter=lambda *args, **kwargs: False,
        reports_dir=tmp_path / "reports",
    )

    assert exit_code == 1
    assert process.terminated is True
