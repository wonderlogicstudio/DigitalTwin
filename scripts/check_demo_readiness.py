"""Check whether the Financial Path Twin demo can run safely."""

from __future__ import annotations

import importlib
import json
import os
import socket
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings  # noqa: E402
from src.demo_cache import has_demo_cache, load_precomputed_demo_analysis, missing_demo_cache_files  # noqa: E402


READY = "READY"
READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
NOT_READY = "NOT_READY"

REQUIRED_PACKAGES = ("pandas", "numpy", "sklearn", "streamlit", "plotly", "pytest", "pydantic")
REQUIRED_MD_FILES = (
    "README.md",
    "SPEC.md",
    "DATA_DICTIONARY.md",
    "BUSINESS_RULES.md",
    "ARCHITECTURE.md",
    "TEST_PLAN.md",
    "TASKS.md",
    "DECISIONS.md",
)


def check_demo_readiness(base_dir: Path = settings.BASE_DIR, port: int = 8501) -> dict[str, Any]:
    """Return structured demo readiness checks."""

    checks: list[dict[str, str]] = []
    _add_python_check(checks)
    _add_package_checks(checks)
    _add_file_checks(checks, base_dir)
    _add_cache_checks(checks)
    _add_smoke_check(checks)
    _add_port_check(checks, port)
    _add_api_key_check(checks)
    status = _overall_status(checks)
    return {"status": status, "checks": checks}


def main() -> int:
    """Run readiness checks from the command line."""

    result = check_demo_readiness()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {READY, READY_WITH_WARNINGS} else 1


def _add_python_check(checks: list[dict[str, str]]) -> None:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info[:2] == (3, 11):
        checks.append(_check("python_version", READY, version))
    elif sys.version_info.major == 3 and sys.version_info.minor >= 10:
        checks.append(_check("python_version", READY_WITH_WARNINGS, f"{version}; project target is Python 3.11"))
    else:
        checks.append(_check("python_version", NOT_READY, f"{version}; Python 3.11 is required"))


def _add_package_checks(checks: list[dict[str, str]]) -> None:
    missing: list[str] = []
    for package in REQUIRED_PACKAGES:
        try:
            importlib.import_module(package)
        except Exception:  # noqa: BLE001
            missing.append(package)
    if missing:
        checks.append(_check("packages", NOT_READY, f"missing packages: {missing}"))
    else:
        checks.append(_check("packages", READY, "required packages import successfully"))


def _add_file_checks(checks: list[dict[str, str]], base_dir: Path) -> None:
    missing_md = [name for name in REQUIRED_MD_FILES if not (base_dir / name).exists()]
    checks.append(_check("required_md", NOT_READY if missing_md else READY, f"missing: {missing_md}" if missing_md else "all required MD files exist"))

    raw_files = (settings.CUSTOMER_MASTER_PATH, settings.CUSTOMER_MONTHLY_PATH)
    missing_raw = [str(path) for path in raw_files if not path.exists()]
    checks.append(_check("raw_data", NOT_READY if missing_raw else READY, f"missing: {missing_raw}" if missing_raw else "raw data exists"))

    processed_files = (settings.TRAJECTORY_FEATURES_PATH, settings.DEMO_MATCHED_FUTURE_TRAJECTORY_PATH)
    missing_processed = [str(path) for path in processed_files if not path.exists()]
    checks.append(
        _check(
            "processed_data",
            READY_WITH_WARNINGS if missing_processed else READY,
            f"missing processed/demo artifacts: {missing_processed}" if missing_processed else "processed data exists",
        )
    )

    demo_files = (settings.DEMO_CUSTOMERS_PATH, settings.MAIN_DEMO_CUSTOMER_PATH)
    missing_demo = [str(path) for path in demo_files if not path.exists()]
    checks.append(_check("demo_json", NOT_READY if missing_demo else READY, f"missing: {missing_demo}" if missing_demo else "demo files exist"))


def _add_cache_checks(checks: list[dict[str, str]]) -> None:
    missing_cache = missing_demo_cache_files()
    if missing_cache:
        checks.append(_check("precomputed_cache", NOT_READY, f"missing: {[str(path) for path in missing_cache]}"))
    else:
        checks.append(_check("precomputed_cache", READY, "all precomputed demo artifacts exist"))


def _add_smoke_check(checks: list[dict[str, str]]) -> None:
    if not has_demo_cache():
        checks.append(_check("core_smoke", NOT_READY, "precomputed demo cache is incomplete"))
        return
    try:
        payload = load_precomputed_demo_analysis()
        matched_count = len(payload.analysis["matches"])
        checks.append(_check("core_smoke", READY, f"loaded cached analysis for {payload.customer_id}; matches={matched_count}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("core_smoke", NOT_READY, f"cached analysis failed: {exc}"))


def _add_port_check(checks: list[dict[str, str]], port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        in_use = sock.connect_ex(("127.0.0.1", port)) == 0
    if in_use:
        checks.append(_check("port_8501", READY_WITH_WARNINGS, f"port {port} is already in use"))
    else:
        checks.append(_check("port_8501", READY, f"port {port} is available"))


def _add_api_key_check(checks: list[dict[str, str]]) -> None:
    if os.environ.get("OPENAI_API_KEY"):
        checks.append(_check("api_key", READY, "OPENAI_API_KEY is set; template fallback remains available"))
    else:
        checks.append(_check("api_key", READY_WITH_WARNINGS, "OPENAI_API_KEY is not set; template fallback will be used"))


def _overall_status(checks: list[dict[str, str]]) -> str:
    statuses = {check["status"] for check in checks}
    if NOT_READY in statuses:
        return NOT_READY
    if READY_WITH_WARNINGS in statuses:
        return READY_WITH_WARNINGS
    return READY


def _check(name: str, status: str, message: str) -> dict[str, str]:
    return {"check_name": name, "status": status, "message": message}


if __name__ == "__main__":
    raise SystemExit(main())
