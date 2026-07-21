"""Tests for demo readiness checks."""

from __future__ import annotations

from pathlib import Path

from config import settings
from scripts.check_demo_readiness import NOT_READY, READY, READY_WITH_WARNINGS, check_demo_readiness


def test_readiness_status_not_ready_when_required_files_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "CUSTOMER_MASTER_PATH", tmp_path / "data" / "raw" / "customer_master.csv")
    monkeypatch.setattr(settings, "CUSTOMER_MONTHLY_PATH", tmp_path / "data" / "raw" / "customer_monthly_5000.csv")
    monkeypatch.setattr(settings, "TRAJECTORY_FEATURES_PATH", tmp_path / "data" / "processed" / "trajectory_features.csv")
    monkeypatch.setattr(settings, "DEMO_CUSTOMERS_PATH", tmp_path / "data" / "demo" / "demo_customers.csv")
    monkeypatch.setattr(settings, "MAIN_DEMO_CUSTOMER_PATH", tmp_path / "data" / "demo" / "main_demo_customer.json")
    monkeypatch.setattr(settings, "DEMO_MATCHED_CUSTOMERS_PATH", tmp_path / "data" / "demo" / "matched_customers.csv")
    monkeypatch.setattr(settings, "DEMO_MATCHED_FUTURE_TRAJECTORY_PATH", tmp_path / "data" / "demo" / "matched_future_trajectory.csv")
    monkeypatch.setattr(settings, "DEMO_OUTCOME_SUMMARY_PATH", tmp_path / "data" / "demo" / "outcome_summary.json")
    monkeypatch.setattr(settings, "DEMO_BREAKPOINT_RESULT_PATH", tmp_path / "data" / "demo" / "breakpoint_result.json")
    monkeypatch.setattr(settings, "DEMO_WHATIF_RESULTS_PATH", tmp_path / "data" / "demo" / "whatif_results.json")

    result = check_demo_readiness(base_dir=tmp_path, port=65530)

    assert result["status"] == NOT_READY
    assert any(check["check_name"] == "processed_data" for check in result["checks"])


def test_overall_status_priority() -> None:
    from scripts.check_demo_readiness import _overall_status

    assert _overall_status([{"status": READY}]) == READY
    assert _overall_status([{"status": READY}, {"status": READY_WITH_WARNINGS}]) == READY_WITH_WARNINGS
    assert _overall_status([{"status": READY_WITH_WARNINGS}, {"status": NOT_READY}]) == NOT_READY
