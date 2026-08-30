"""Tests for saved display evidence in RM Monthly Review Snapshots."""

from __future__ import annotations

import json

import pandas as pd

from config import settings
from src.matcher import TrajectoryMatcher
from src.monthly_review_snapshot import build_monthly_review_snapshot
from src.rm_portfolio import RELATIONSHIP_LABELS, RmPortfolio, RmPortfolioCustomer


def _portfolio(priority: str = "CORE") -> RmPortfolio:
    return RmPortfolio(
        rm_portfolio_id="RM-TEST-001",
        universe_customer_count=3,
        portfolio_selection_seed=20260828,
        relationship_assignment_seed=42,
        customers=(
            RmPortfolioCustomer(
                customer_id="C000001",
                rm_portfolio_id="RM-TEST-001",
                relationship_priority=priority,
                relationship_label=RELATIONSHIP_LABELS[priority],
            ),
        ),
    )


def _monthly_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "customer_id": customer_id,
                "month": month,
                "monthly_status": "watch" if customer_id == "C000001" else "healthy",
                "delinquency_flag": 0,
                "savings_rate": 0.10,
                "dsr": 0.23,
                "fixed_expense_ratio": 0.32,
                "cash_balance": 1_000_000 - (month * 10_000),
            }
            for customer_id in ("C000001", "C000002", "C000003")
            for month in range(1, 13)
        ]
    )


def _features_frame() -> pd.DataFrame:
    features: dict[str, object] = {"customer_id": ("C000001", "C000002", "C000003")}
    for index, feature_name in enumerate(settings.MATCH_FEATURES, start=1):
        features[feature_name] = (float(index), float(index + 1), float(index + 2))
    return pd.DataFrame(features)


def _completed_analysis(*_args: object, **_kwargs: object) -> dict[str, object]:
    return {
        "customer_id": "C000001",
        "matched_ids": ["C000003", "C000002"],
        "outcome_summary": {
            "matched_count": 2,
            "outcomes": {"healthy": {"count": 1, "ratio": 0.5}},
            "first_stress_month_median": 15,
            "first_delinquency_month_median": None,
        },
        "breakpoint_result": {
            "status": "found",
            "breakpoint_month": 13,
            "months_from_current": 1,
            "primary_factor": "cash_balance_ratio",
        },
        "breakpoint_comparison": pd.DataFrame(
            [
                {
                    "month": 13,
                    "metric": "cash_balance_ratio",
                    "risk_group_mean": 0.42,
                    "avoidance_group_mean": 0.81,
                    "risk_count": 20,
                    "avoidance_count": 21,
                },
                {
                    "month": 14,
                    "metric": "cash_balance_ratio",
                    "risk_group_mean": 0.38,
                    "avoidance_group_mean": 0.83,
                    "risk_count": 20,
                    "avoidance_count": 21,
                },
            ]
        ),
        "whatif_results": {
            "simulation_months": 24,
            "scenarios": [
                {
                    "scenario_id": 1,
                    "scenario_name": "baseline",
                    "ending_cash_balance": 100.0,
                    "minimum_cash_balance": 50.0,
                    "average_savings_rate": 0.1,
                    "cash_depletion_month": None,
                    "improvement_vs_baseline": 0.0,
                    "total_saved_expense": 0.0,
                    "months_with_negative_savings": 0,
                    "monthly_data": [{"month": 1, "cash_balance": 1.0}],
                }
            ],
        },
        "errors": {},
    }


def _snapshot(analysis_runner=_completed_analysis, priority: str = "CORE"):
    features_df = _features_frame()
    return build_monthly_review_snapshot(
        _portfolio(priority),
        _monthly_frame(),
        features_df,
        TrajectoryMatcher().fit(features_df),
        snapshot_id="monthly-12-evidence",
        top_k=2,
        analysis_runner=analysis_runner,
    )


def test_snapshot_saves_json_safe_deterministic_display_evidence_from_analysis() -> None:
    first_record = _snapshot().records[0]
    second_record = _snapshot().records[0]
    evidence = first_record.supporting_evidence

    assert evidence == second_record.supporting_evidence
    assert first_record.matched_customer_ids == ("C000003", "C000002")
    assert evidence is not None
    assert evidence["available"] is True
    assert evidence["evidence_status"] == "available"
    assert evidence["provenance"] == {
        "snapshot_id": "monthly-12-evidence",
        "analysis_as_of_month": 12,
        "generated_from": "existing_customer_analysis",
        "source_service": "src.customer_analysis.run_customer_analysis",
    }
    assert evidence["why_now"]["primary_factor"] == "cash_balance_ratio"
    assert len(evidence["current_change_cards"]) == 4

    chart = evidence["cohort_path_chart"]
    assert chart["available"] is True
    assert chart["comparison_type"] == "historical_matched_cohort_comparison"
    assert chart["metric"] == "cash_balance_ratio"
    assert chart["group_sizes"] == {"risk_path": 20, "avoidance_path": 21}
    assert chart["breakpoint_marker"] == {"month": 13}
    assert [point["month"] for point in chart["risk_path"]] == [13, 14]

    whatif_summary = evidence["whatif_summary"]
    assert whatif_summary["available"] is True
    assert whatif_summary["scenarios"] == [
        {
            "scenario_id": 1,
            "scenario_name": "baseline",
            "ending_cash_balance": 100.0,
            "minimum_cash_balance": 50.0,
            "average_savings_rate": 0.1,
            "cash_depletion_month": None,
            "improvement_vs_baseline": 0.0,
            "total_saved_expense": 0.0,
            "months_with_negative_savings": 0,
        }
    ]
    assert "monthly_data" not in json.dumps(first_record.as_dict())
    json.dumps(first_record.as_dict())


def test_non_found_breakpoint_never_invents_a_chart() -> None:
    def no_breakpoint_analysis(*args: object, **kwargs: object) -> dict[str, object]:
        result = _completed_analysis(*args, **kwargs)
        result["breakpoint_result"] = {
            "status": "not_found",
            "breakpoint_month": None,
            "months_from_current": None,
            "primary_factor": None,
        }
        return result

    evidence = _snapshot(no_breakpoint_analysis).records[0].supporting_evidence

    assert evidence is not None
    assert evidence["cohort_path_chart"] == {
        "available": False,
        "status": "unavailable",
        "reason_code": "breakpoint_not_found",
        "reason": "Historical cohort comparison is unavailable because a breakpoint was not found.",
        "scenarios": [],
        "risk_path": [],
        "avoidance_path": [],
    }


def test_insufficient_breakpoint_group_keeps_real_observations_but_no_cohort_chart() -> None:
    def insufficient_group_analysis(*args: object, **kwargs: object) -> dict[str, object]:
        result = _completed_analysis(*args, **kwargs)
        result["breakpoint_result"] = {
            "status": "insufficient_group_size",
            "breakpoint_month": None,
            "months_from_current": None,
            "primary_factor": None,
        }
        return result

    evidence = _snapshot(insufficient_group_analysis).records[0].supporting_evidence

    assert evidence is not None
    assert evidence["why_now"]["status"] == "insufficient_group_size"
    assert len(evidence["current_change_cards"]) == 4
    assert evidence["cohort_path_chart"]["available"] is False
    assert evidence["cohort_path_chart"]["reason_code"] == "breakpoint_insufficient_group_size"
    assert evidence["cohort_path_chart"]["risk_path"] == []


def test_missing_current_summary_has_an_explicit_unavailable_evidence_status() -> None:
    features_df = _features_frame()
    monthly_without_target = _monthly_frame().loc[
        lambda frame: frame["customer_id"] != "C000001"
    ]
    snapshot = build_monthly_review_snapshot(
        _portfolio(),
        monthly_without_target,
        features_df,
        TrajectoryMatcher().fit(features_df),
        snapshot_id="monthly-12-missing-current-summary",
        top_k=2,
        analysis_runner=_completed_analysis,
    )
    evidence = snapshot.records[0].supporting_evidence

    assert evidence is not None
    assert evidence["available"] is False
    assert evidence["evidence_status"] == "current_summary_unavailable"
    assert evidence["cohort_path_chart"]["reason_code"] == "analysis_evidence_unavailable"


def test_analysis_error_marks_every_display_evidence_component_unavailable() -> None:
    def failing_analysis(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("analysis source failed")

    record = _snapshot(failing_analysis).records[0]
    evidence = record.supporting_evidence

    assert evidence is not None
    assert evidence["available"] is False
    assert evidence["evidence_status"] == "analysis_error"
    assert evidence["cohort_path_chart"]["reason_code"] == "analysis_evidence_unavailable"
    assert evidence["whatif_summary"]["reason_code"] == "analysis_evidence_unavailable"
    assert evidence["current_change_cards"] == []


def test_relationship_metadata_never_changes_saved_evidence_or_analysis_inputs() -> None:
    core_record = _snapshot(priority="CORE").records[0]
    standard_record = _snapshot(priority="STANDARD").records[0]

    assert core_record.relationship_metadata != standard_record.relationship_metadata
    assert core_record.matched_customer_ids == standard_record.matched_customer_ids
    assert core_record.breakpoint == standard_record.breakpoint
    assert core_record.outcome_summary == standard_record.outcome_summary
    assert core_record.supporting_evidence == standard_record.supporting_evidence


def test_evidence_builder_does_not_invoke_matcher_or_analysis_twice() -> None:
    calls = 0

    def runner(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return _completed_analysis(*args, **kwargs)

    snapshot = _snapshot(runner)

    assert calls == 1
    assert snapshot.records[0].supporting_evidence is not None
