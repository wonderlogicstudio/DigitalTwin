"""Tests for the RM Portfolio monthly analysis Snapshot layer."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from config import settings
from src.customer_analysis import run_customer_analysis
from src.data_generator import generate_dataset
from src.feature_engineering import build_trajectory_features
from src.matcher import TrajectoryMatcher
from src.models import GeneratorConfig
from src.monthly_review_snapshot import (
    EVIDENCE_ANALYSIS_ERROR,
    EVIDENCE_AVAILABLE,
    MonthlyReviewSnapshot,
    build_monthly_review_snapshot,
    write_monthly_review_snapshot,
)
from src.rm_portfolio import (
    RELATIONSHIP_LABELS,
    RmPortfolio,
    RmPortfolioCustomer,
    build_rm_portfolio,
)


def _customer_ids(size: int) -> list[str]:
    return [f"C{index:06d}" for index in range(1, size + 1)]


def _observation_monthly_frame(customer_ids: list[str]) -> pd.DataFrame:
    """Create only the observation inputs required for current summaries."""

    rows: list[dict[str, object]] = []
    for customer_index, customer_id in enumerate(customer_ids, start=1):
        for month in range(1, settings.OBSERVATION_END_MONTH + 1):
            rows.append(
                {
                    "customer_id": customer_id,
                    "month": month,
                    "monthly_status": "healthy",
                    "delinquency_flag": 0,
                    "savings_rate": 0.10 + (month * 0.001),
                    "dsr": 0.20 + (customer_index * 0.000001),
                    "fixed_expense_ratio": 0.30,
                    "cash_balance": 1_000_000 + (customer_index * 10) + month,
                }
            )
    return pd.DataFrame(rows)


def _feature_frame(customer_ids: list[str]) -> pd.DataFrame:
    feature_data: dict[str, object] = {"customer_id": customer_ids}
    customer_positions = np.arange(len(customer_ids), dtype=float)
    for feature_index, feature_name in enumerate(settings.MATCH_FEATURES, start=1):
        feature_data[feature_name] = customer_positions + (feature_index / 100.0)
    return pd.DataFrame(feature_data)


def _portfolio(
    customers: list[tuple[str, str]],
    *,
    universe_customer_count: int,
) -> RmPortfolio:
    return RmPortfolio(
        rm_portfolio_id="RM-TEST-001",
        universe_customer_count=universe_customer_count,
        portfolio_selection_seed=20260828,
        relationship_assignment_seed=42,
        customers=tuple(
            RmPortfolioCustomer(
                customer_id=customer_id,
                rm_portfolio_id="RM-TEST-001",
                relationship_priority=priority,
                relationship_label=RELATIONSHIP_LABELS[priority],
            )
            for customer_id, priority in customers
        ),
    )


def _fake_analysis(
    customer_id: str,
    _monthly_df: pd.DataFrame,
    features_df: pd.DataFrame,
    matcher: TrajectoryMatcher,
    *,
    top_k: int,
) -> dict[str, object]:
    """A deterministic analysis-result fixture that still exercises matching."""

    assert len(features_df) == len(matcher._customer_ids)  # noqa: SLF001
    matched_ids = matcher.match(customer_id, top_k=top_k)["matched_customer_id"].astype(str).tolist()
    return {
        "customer_id": customer_id,
        "matched_ids": matched_ids,
        "outcome_summary": {
            "target_customer_id": customer_id,
            "matched_count": len(matched_ids),
            "outcomes": {"healthy": {"count": len(matched_ids), "ratio": 1.0}},
            "first_stress_month_median": 13,
            "first_delinquency_month_median": None,
        },
        "breakpoint_result": {
            "status": "found",
            "breakpoint_month": 13,
            "months_from_current": 1,
            "primary_factor": "cash_balance_ratio",
        },
        "errors": {},
    }


def test_builds_300_portfolio_records_against_full_5000_customer_matcher() -> None:
    customer_ids = _customer_ids(settings.CUSTOMER_COUNT)
    portfolio = build_rm_portfolio(customer_ids)
    monthly_df = _observation_monthly_frame(customer_ids)
    features_df = _feature_frame(customer_ids)
    matcher = TrajectoryMatcher().fit(features_df)

    snapshot = build_monthly_review_snapshot(
        portfolio,
        monthly_df,
        features_df,
        matcher,
        snapshot_id="monthly-12-2026-08",
        top_k=5,
        analysis_runner=_fake_analysis,
    )

    assert snapshot.universe_customer_count == settings.CUSTOMER_COUNT
    assert len(snapshot.records) == 300
    assert [record.customer_id for record in snapshot.records] == sorted(
        customer.customer_id for customer in portfolio.customers
    )
    assert all(record.matched_count == 5 for record in snapshot.records)
    assert all(record.breakpoint["months_from_current"] == 1 for record in snapshot.records)
    assert all(record.evidence["status"] == EVIDENCE_AVAILABLE for record in snapshot.records)
    assert all(
        record.relationship_metadata["relationship_priority"]
        in {"CORE", "PRIORITY", "STANDARD"}
        for record in snapshot.records
    )


def test_snapshot_rejects_a_portfolio_sized_matching_universe() -> None:
    full_customer_ids = _customer_ids(settings.CUSTOMER_COUNT)
    portfolio = build_rm_portfolio(full_customer_ids)
    portfolio_customer_ids = [customer.customer_id for customer in portfolio.customers]
    monthly_df = _observation_monthly_frame(portfolio_customer_ids)
    features_df = _feature_frame(portfolio_customer_ids)
    matcher = TrajectoryMatcher().fit(features_df)

    with pytest.raises(ValueError, match="full matching reference universe"):
        build_monthly_review_snapshot(
            portfolio,
            monthly_df,
            features_df,
            matcher,
            snapshot_id="monthly-12-invalid-universe",
            top_k=5,
            analysis_runner=_fake_analysis,
        )


def test_snapshot_reuses_customer_analysis_service_with_minimal_parity_fields() -> None:
    config = GeneratorConfig(customer_count=250, top_k_matches=20)
    _, monthly_df = generate_dataset(config)
    features_df = build_trajectory_features(monthly_df)
    matcher = TrajectoryMatcher().fit(features_df)
    portfolio = _portfolio([("C000001", "CORE")], universe_customer_count=250)

    direct_analysis = run_customer_analysis(
        "C000001",
        monthly_df,
        features_df,
        matcher,
        top_k=20,
    )
    snapshot = build_monthly_review_snapshot(
        portfolio,
        monthly_df,
        features_df,
        matcher,
        snapshot_id="monthly-12-parity",
        top_k=20,
    )
    record = snapshot.records[0]

    assert record.matched_count == direct_analysis["outcome_summary"]["matched_count"]
    assert record.outcome_summary == {
        field: direct_analysis["outcome_summary"].get(field)
        for field in (
            "matched_count",
            "outcomes",
            "first_stress_month_median",
            "first_delinquency_month_median",
        )
    }
    assert record.breakpoint == {
        field: direct_analysis["breakpoint_result"].get(field)
        for field in (
            "status",
            "breakpoint_month",
            "months_from_current",
            "primary_factor",
        )
    }
    assert record.relationship_metadata["relationship_priority"] == "CORE"
    assert "whatif_results" not in record.as_dict()


def test_relationship_metadata_does_not_change_analysis_values() -> None:
    customer_ids = _customer_ids(10)
    monthly_df = _observation_monthly_frame(customer_ids)
    features_df = _feature_frame(customer_ids)
    matcher = TrajectoryMatcher().fit(features_df)
    core_snapshot = build_monthly_review_snapshot(
        _portfolio([("C000001", "CORE")], universe_customer_count=10),
        monthly_df,
        features_df,
        matcher,
        snapshot_id="monthly-12-core",
        top_k=3,
        analysis_runner=_fake_analysis,
    )
    standard_snapshot = build_monthly_review_snapshot(
        _portfolio([("C000001", "STANDARD")], universe_customer_count=10),
        monthly_df,
        features_df,
        matcher,
        snapshot_id="monthly-12-standard",
        top_k=3,
        analysis_runner=_fake_analysis,
    )

    core_record = core_snapshot.records[0]
    standard_record = standard_snapshot.records[0]
    assert core_record.breakpoint == standard_record.breakpoint
    assert core_record.outcome_summary == standard_record.outcome_summary
    assert core_record.current_summary == standard_record.current_summary
    assert core_record.evidence == standard_record.evidence
    assert core_record.relationship_metadata != standard_record.relationship_metadata


def test_snapshot_order_is_deterministic_and_analysis_errors_are_explicit() -> None:
    customer_ids = _customer_ids(3)
    monthly_df = _observation_monthly_frame(customer_ids)
    features_df = _feature_frame(customer_ids)
    matcher = TrajectoryMatcher().fit(features_df)
    portfolio = _portfolio(
        [("C000003", "STANDARD"), ("C000001", "CORE")],
        universe_customer_count=3,
    )

    def failing_analysis(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("forced analysis failure")

    snapshot = build_monthly_review_snapshot(
        portfolio,
        monthly_df,
        features_df,
        matcher,
        snapshot_id="monthly-12-errors",
        top_k=2,
        analysis_runner=failing_analysis,
    )

    assert [record.customer_id for record in snapshot.records] == ["C000001", "C000003"]
    assert all(record.breakpoint["status"] == "error" for record in snapshot.records)
    assert all(record.evidence["available"] is False for record in snapshot.records)
    assert all(record.evidence["status"] == EVIDENCE_ANALYSIS_ERROR for record in snapshot.records)
    assert all("forced analysis failure" in record.evidence["errors"]["analysis"] for record in snapshot.records)


def test_snapshot_artifact_is_json_serializable_and_rejects_core_data_paths(tmp_path: Path) -> None:
    customer_ids = _customer_ids(3)
    monthly_df = _observation_monthly_frame(customer_ids)
    features_df = _feature_frame(customer_ids)
    matcher = TrajectoryMatcher().fit(features_df)
    snapshot = build_monthly_review_snapshot(
        _portfolio([("C000001", "CORE")], universe_customer_count=3),
        monthly_df,
        features_df,
        matcher,
        snapshot_id="monthly-12-json",
        top_k=2,
        analysis_runner=_fake_analysis,
    )

    output_path = tmp_path / "rm_daily_review" / "monthly-12-json.json"
    written_path = write_monthly_review_snapshot(snapshot, output_path)
    artifact = json.loads(written_path.read_text(encoding="utf-8"))

    assert artifact["schema_version"] == 1
    assert artifact["portfolio_size"] == 1
    assert artifact["records"][0]["snapshot_id"] == "monthly-12-json"
    assert "whatif_results" not in artifact["records"][0]
    with pytest.raises(ValueError, match="must not overwrite core data"):
        write_monthly_review_snapshot(
            snapshot,
            settings.DATA_DEMO_DIR / "monthly-12-json.json",
        )
