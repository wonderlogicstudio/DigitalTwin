"""Tests for the RM Monthly Snapshot batch CLI and workload report."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

import scripts.build_rm_monthly_snapshot as snapshot_cli
from config import settings
from src.daily_review import MONITOR, REVIEW_NOW, UPCOMING
from src.monthly_review_snapshot import MonthlyReviewSnapshot, MonthlyReviewSnapshotRecord


def _customer_ids(size: int = settings.CUSTOMER_COUNT) -> list[str]:
    return [f"C{index:06d}" for index in range(1, size + 1)]


def _snapshot_record(
    customer_id: str,
    relationship_priority: str,
    *,
    breakpoint_status: str,
    months_from_current: int | None,
    current_status: str | None,
    evidence_available: bool = True,
) -> MonthlyReviewSnapshotRecord:
    return MonthlyReviewSnapshotRecord(
        customer_id=customer_id,
        snapshot_id="monthly-2026-08",
        analysis_as_of_month=12,
        current_summary={"current_status": current_status},
        matched_count=200,
        breakpoint={
            "status": breakpoint_status,
            "breakpoint_month": 13 if breakpoint_status == "found" else None,
            "months_from_current": months_from_current,
            "primary_factor": "cash_balance_ratio",
        },
        evidence={"available": evidence_available, "status": "available", "errors": {}},
        relationship_metadata={
            "source": "synthetic_crm_overlay",
            "rm_portfolio_id": "RM-POC-001",
            "relationship_priority": relationship_priority,
            "relationship_label": relationship_priority,
        },
        outcome_summary=None,
    )


def _write_cli_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    customer_ids = _customer_ids()
    master_path = tmp_path / "data" / "raw" / "customer_master.csv"
    monthly_path = tmp_path / "data" / "raw" / "customer_monthly_5000.csv"
    features_path = tmp_path / "data" / "processed" / "trajectory_features.csv"
    master_path.parent.mkdir(parents=True)
    features_path.parent.mkdir(parents=True)
    master_path.write_text(
        "customer_id,persona,final_outcome,cash_balance\n"
        + "".join(
            f"{customer_id},stable,healthy,{index * 1000}\n"
            for index, customer_id in enumerate(customer_ids, start=1)
        ),
        encoding="utf-8",
    )
    monthly_path.write_text(
        "customer_id,month,monthly_status,delinquency_flag\nC000001,1,healthy,0\n",
        encoding="utf-8",
    )
    feature_data: dict[str, object] = {"customer_id": customer_ids}
    for feature_index, feature_name in enumerate(settings.MATCH_FEATURES, start=1):
        feature_data[feature_name] = [
            customer_index + (feature_index / 100.0)
            for customer_index in range(len(customer_ids))
        ]
    pd.DataFrame(feature_data).to_csv(features_path, index=False)
    return master_path, monthly_path, features_path


def test_workload_report_uses_saved_snapshot_values_without_reanalysis() -> None:
    snapshot = MonthlyReviewSnapshot(
        snapshot_id="monthly-2026-08",
        analysis_as_of_month=12,
        rm_portfolio_id="RM-POC-001",
        universe_customer_count=5_000,
        records=(
            _snapshot_record(
                "C000001", "CORE", breakpoint_status="found", months_from_current=1, current_status="watch"
            ),
            _snapshot_record(
                "C000002", "CORE", breakpoint_status="found", months_from_current=1, current_status="healthy"
            ),
            _snapshot_record(
                "C000003", "PRIORITY", breakpoint_status="not_found", months_from_current=None, current_status="healthy"
            ),
            _snapshot_record(
                "C000004", "STANDARD", breakpoint_status="insufficient_group_size", months_from_current=None, current_status="healthy"
            ),
            _snapshot_record(
                "C000005", "STANDARD", breakpoint_status="error", months_from_current=None, current_status="healthy", evidence_available=False
            ),
        ),
    )

    report = snapshot_cli.build_workload_report(snapshot)

    assert report["portfolio_customer_count"] == 5
    assert report["breakpoint_status_distribution"] == {
        "found": 2,
        "not_found": 1,
        "insufficient_group_size": 1,
        "other": 1,
    }
    assert report["daily_review_distribution"] == {
        REVIEW_NOW: 1,
        UPCOMING: 1,
        MONITOR: 3,
    }
    assert report["relationship_priority_by_bucket"]["CORE"] == {
        REVIEW_NOW: 1,
        UPCOMING: 1,
        MONITOR: 0,
    }
    assert report["upcoming_core_customer_count"] == 1


def test_cli_writes_snapshot_and_workload_report_without_changing_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    master_path, monthly_path, features_path = _write_cli_inputs(tmp_path)
    input_digests = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (master_path, monthly_path, features_path)
    }
    snapshot_path = tmp_path / "artifacts" / "rm_daily_review" / "monthly" / "monthly-2026-08.json"
    report_path = snapshot_path.with_name("monthly-2026-08_workload_report.json")

    def fake_snapshot_builder(portfolio, *_args, snapshot_id: str, **_kwargs):
        records = tuple(
            _snapshot_record(
                customer.customer_id,
                customer.relationship_priority,
                breakpoint_status=("found" if index % 3 != 2 else "insufficient_group_size"),
                months_from_current=(1 if index % 3 != 2 else None),
                current_status=("watch" if index % 3 == 0 else "healthy"),
            )
            for index, customer in enumerate(portfolio.customers)
        )
        return MonthlyReviewSnapshot(
            snapshot_id=snapshot_id,
            analysis_as_of_month=12,
            rm_portfolio_id=portfolio.rm_portfolio_id,
            universe_customer_count=portfolio.universe_customer_count,
            records=records,
        )

    monkeypatch.setattr(snapshot_cli, "build_monthly_review_snapshot", fake_snapshot_builder)

    assert snapshot_cli.main(
        [
            "--snapshot-id",
            "monthly-2026-08",
            "--customer-master",
            str(master_path),
            "--customer-monthly",
            str(monthly_path),
            "--trajectory-features",
            str(features_path),
            "--output",
            str(snapshot_path),
            "--workload-report-output",
            str(report_path),
        ]
    ) == 0

    assert {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in input_digests
    } == input_digests
    snapshot_payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    output = capsys.readouterr().out
    assert len(snapshot_payload["records"]) == 300
    assert report_payload["portfolio_customer_count"] == 300
    assert sum(report_payload["daily_review_distribution"].values()) == 300
    relationship_by_bucket = report_payload["relationship_priority_by_bucket"]
    assert set(relationship_by_bucket) == {"CORE", "PRIORITY", "STANDARD"}
    assert all(
        set(bucket_counts) == {REVIEW_NOW, UPCOMING, MONITOR}
        for bucket_counts in relationship_by_bucket.values()
    )
    assert sum(
        count
        for bucket_counts in relationship_by_bucket.values()
        for count in bucket_counts.values()
    ) == 300
    assert "오늘 먼저 확인:" in output
    assert "곧 확인 예정 중 핵심관리 고객:" in output


def test_workload_report_writer_rejects_core_data_paths(tmp_path: Path) -> None:
    report = {"snapshot_id": "monthly-2026-08"}
    written_path = snapshot_cli.write_workload_report(report, tmp_path / "workload_report.json")

    assert json.loads(written_path.read_text(encoding="utf-8")) == report
    with pytest.raises(ValueError, match="must not overwrite core data"):
        snapshot_cli.write_workload_report(
            report,
            settings.DATA_DEMO_DIR / "monthly-2026-08_workload_report.json",
        )
