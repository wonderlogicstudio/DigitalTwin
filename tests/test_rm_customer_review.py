"""Contracts for RM Customer Review rationale, timing, and evidence display."""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from src.alert_case import TimingEvidenceReference, create_alert_case
from src.rm_customer_review import (
    build_rm_customer_review_view_model,
    load_customer_observation,
    load_population_result_index,
)


NOW = datetime(2026, 8, 23, 9, tzinfo=timezone.utc)


def _record(
    customer_id: str,
    *,
    selected: bool,
    disposition: str,
    label: str,
    rank: int | None,
) -> dict[str, object]:
    return {
        "customer_id": customer_id,
        "as_of_month": 12,
        "signal_as_of_month": 12,
        "policy_id": "synthetic_early_warning_demo",
        "policy_version": "0.1.0",
        "signal_run_id": "crossfit_seed42_5fold_asof12",
        "eligibility_label": label,
        "selected_for_review": selected,
        "selection_disposition": disposition,
        "routing_disposition": "CREATE_NEW_CASE" if selected else "NO_ROUTING",
        "review_priority_rank": rank,
        "selection_reason_codes": [
            "PRIORITY_BAND_PRIORITY_REVIEW",
            "TIMING_PROSPECTIVE_SIGNAL_AVAILABLE",
            "EVIDENCE_SUFFICIENT",
        ],
        "why_now_reason_codes": ["CURRENT_STATUS_CONCERNING"],
        "timing_bucket": "prospective_timing_not_evaluated",
        "timing_evidence_reference": {
            "source": "prospective_signal",
            "candidate_month": 12,
            "evaluation_status": "not_evaluated",
            "lead_time_months": None,
        },
        "signal_stability": "initial",
        "signal_persistence": "not_persistent",
    }


def _manifest(*records: dict[str, object]) -> dict[str, object]:
    return {
        "funnel": {"monitored_total": 5000},
        "records": list(records),
    }


def _population_result(*, status: str = "found") -> dict[str, object]:
    return {
        "customer_id": "C000001",
        "analysis_status": "success",
        "matched_count": 200,
        "distance_summary": {"mean": 0.73, "median": 0.70},
        "historical_outcome_shares": {
            "healthy": 0.10,
            "recovered": 0.05,
            "stress": 0.45,
            "delinquent": 0.40,
        },
        "breakpoint_status": status,
        "breakpoint_month": 18 if status == "found" else None,
        "breakpoint_factor": "dsr" if status == "found" else None,
    }


def _observation(tmp_path: Path) -> object:
    rows = []
    for month in range(1, 14):
        rows.append(
            {
                "customer_id": "C000001",
                "month": month,
                "savings_rate": -0.10 if month == 12 else 0.20,
                "dsr": 0.42 if month == 12 else 0.20,
                "fixed_expense_ratio": 0.55 if month == 12 else 0.30,
                "cash_balance": 1_200_000 if month == 12 else 2_000_000,
                "monthly_status": "stress" if month == 12 else "watch",
                "future_only_marker": "not read",
            }
        )
    path = tmp_path / "monthly.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return load_customer_observation("C000001", as_of_month=12, monthly_path=path)


def _cohort(customer_id: str) -> dict[str, object]:
    return {
        "records": [
            {
                "category_id": "monitor_no_alert_comparison",
                "customer_id": customer_id,
                "status": "selected",
            }
        ]
    }


def _case() -> object:
    return create_alert_case(
        alert_id="ALT-1",
        customer_id="C000001",
        policy_id="synthetic_early_warning_demo",
        policy_version="0.1.0",
        selection_policy_id="transparent_triage_selection_demo",
        selection_policy_version="0.1.0",
        signal_run_id="crossfit_seed42_5fold_asof12",
        signal_version="prospective_signal_snapshot.v1",
        signal_as_of_month=12,
        created_at=NOW,
        due_at=NOW + timedelta(days=3),
        operational_priority="PRIORITY_REVIEW",
        why_now_reason_codes=("CURRENT_STATUS_CONCERNING",),
        selection_reason_codes=("PRIORITY_BAND_PRIORITY_REVIEW",),
        timing_evidence_reference=TimingEvidenceReference(
            source="prospective_signal",
            candidate_month=12,
            evaluation_status="not_evaluated",
        ),
        episode_key="C000001:synthetic_early_warning_demo:12",
    )


def test_selected_review_uses_manifest_rationale_and_observed_only_current_signals(tmp_path: Path) -> None:
    record = _record(
        "C000001",
        selected=True,
        disposition="SELECTED_FOR_REVIEW",
        label="Priority Review",
        rank=1,
    )
    model = build_rm_customer_review_view_model(
        customer_id="C000001",
        selection_manifest=_manifest(record),
        representative_cohort=None,
        population_results={"C000001": _population_result()},
        observation=_observation(tmp_path),
        alert_cases=(),
        language="en",
    )

    assert model["available"] is True
    assert model["header"]["context_type"] == "operational_queue"
    assert "5,000" in model["header"]["selection_reason"]
    assert "Priority Review is ordered before Review." in model["header"]["selection_reason"]
    assert "current observed status" in model["header"]["why_now"].lower()
    assert model["current_signals"]["as_of_month"] == 12
    assert model["chart_trajectory"]["month"].max() == 12
    assert model["prospective_timing"]["source"] == "prospective_signal"
    assert model["prospective_timing"]["candidate_month"] == 12
    assert model["scope"]["future_data_loaded"] is False
    assert "historical" not in model["prospective_timing"]
    assert "probability" not in str(model).lower()
    assert "predict" not in str(model).lower()


def test_observation_display_is_invariant_to_changes_after_the_as_of_month(tmp_path: Path) -> None:
    first = _observation(tmp_path)
    path = tmp_path / "monthly.csv"
    frame = pd.read_csv(path)
    frame.loc[frame["month"] == 13, ["savings_rate", "dsr", "cash_balance"]] = [0.99, 0.99, 999_999_999]
    frame.to_csv(path, index=False)
    second = load_customer_observation("C000001", as_of_month=12, monthly_path=path)

    assert first.current_values == second.current_values
    assert first.trajectory.equals(second.trajectory)
    assert second.trajectory["month"].max() == 12


def test_population_result_loader_is_read_only_and_honest_for_corrupt_detail(tmp_path: Path) -> None:
    detail_path = tmp_path / "population_detail.json"
    detail_path.write_text("{bad", encoding="utf-8")
    assert load_population_result_index(detail_path) == {}


def test_deferred_and_representative_contexts_are_not_presented_as_operational_queue(tmp_path: Path) -> None:
    deferred = _record(
        "C000001",
        selected=False,
        disposition="DEFERRED_CAPACITY",
        label="Review",
        rank=3,
    )
    deferred["selection_reason_codes"] = ["CAPACITY_DEFERRED"]
    deferred_model = build_rm_customer_review_view_model(
        customer_id="C000001",
        selection_manifest=_manifest(deferred),
        representative_cohort=None,
        population_results={"C000001": _population_result(status="not_found")},
        observation=_observation(tmp_path),
        language="en",
    )
    assert deferred_model["header"]["context_type"] == "deferred_capacity"
    assert "not in the operational review queue" in deferred_model["header"]["selection_reason"]

    comparison = _record(
        "C000001",
        selected=False,
        disposition="NOT_QUEUE_ELIGIBLE",
        label="Monitor",
        rank=None,
    )
    comparison_model = build_rm_customer_review_view_model(
        customer_id="C000001",
        selection_manifest=_manifest(comparison),
        representative_cohort=_cohort("C000001"),
        population_results={"C000001": _population_result(status="insufficient_group_size")},
        observation=_observation(tmp_path),
        language="en",
    )
    assert comparison_model["header"]["context_type"] == "representative_comparison"
    assert comparison_model["historical_landmark"]["status"] == "insufficient_group_size"


def test_historical_landmark_statuses_remain_retrospective_and_follow_up_requires_case(tmp_path: Path) -> None:
    record = _record(
        "C000001",
        selected=True,
        disposition="SELECTED_FOR_REVIEW",
        label="Priority Review",
        rank=1,
    )
    model = build_rm_customer_review_view_model(
        customer_id="C000001",
        selection_manifest=_manifest(record),
        representative_cohort=None,
        population_results={"C000001": _population_result(status="found")},
        observation=_observation(tmp_path),
        alert_cases=(_case(),),
        language="en",
    )

    assert model["historical_landmark"] == {
        "status": "found",
        "month": 18,
        "factor": "Debt Service Ratio",
        "message": "A historical landmark is available in the similar-path cohort.",
        "caption": "This is retrospective evidence from similar paths. It does not specify a future date for the current customer.",
    }
    assert model["recommended_follow_up"]["available"] is True
    assert model["recommended_follow_up"]["actions"] == ("REVIEW_COMPLETED", "CONTACT_PLANNED")


def test_customer_review_module_has_no_streamlit_or_analytics_execution_dependency() -> None:
    import src.rm_customer_review as customer_review

    source = Path(customer_review.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    ]

    assert "streamlit" not in source.lower()
    assert "run_customer_analysis" not in source
    assert "final_outcome" not in source
    assert "persona" not in source
    assert "standardized_difference" not in source
    assert not any("matcher" in module or "evaluator" in module for module in imported_modules)
