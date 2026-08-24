"""Contracts for the read-only RM Portfolio and selected-only Review Queue."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.alert_case import TimingEvidenceReference, create_alert_case
from src.alert_repository import ALERT_CASE_REPOSITORY_FILENAME
from src.rm_workspace import (
    build_rm_portfolio_queue_view_model,
    customer_context_from_queue_row,
    load_rm_alert_cases,
)


NOW = datetime(2026, 8, 23, 9, 0, tzinfo=timezone.utc)


def _record(
    customer_id: str,
    *,
    label: str,
    selected: bool,
    routing: str,
    rank: int | None,
) -> dict[str, object]:
    return {
        "customer_id": customer_id,
        "policy_id": "synthetic_early_warning_demo",
        "policy_version": "0.1.0",
        "signal_run_id": "crossfit_seed42_5fold_asof12",
        "signal_as_of_month": 12,
        "eligibility_label": label,
        "selected_for_review": selected,
        "selection_disposition": "SELECTED_FOR_REVIEW" if selected else "NOT_QUEUE_ELIGIBLE",
        "routing_disposition": routing,
        "review_priority_rank": rank,
        "selection_reason_codes": ["CAPACITY_UNBOUNDED", "EVIDENCE_SUFFICIENT"],
        "why_now_reason_codes": ["CURRENT_STATUS_CONCERNING"],
        "timing_bucket": "prospective_timing_not_evaluated",
        "timing_evidence_reference": {
            "source": "prospective_signal",
            "candidate_month": 12,
            "evaluation_status": "not_evaluated",
        },
        "historical_landmark_context": {"source": "historical_landmark"},
    }


def _manifest() -> dict[str, object]:
    return {
        "funnel": {
            "monitored_total": 5,
            "eligible_priority": 1,
            "eligible_review": 1,
            "eligible_total": 2,
            "selected_queue_ready": 2,
            "deferred_capacity": 0,
            "monitor_only": 1,
            "no_actionable_signal": 1,
            "insufficient_evidence": 1,
        },
        "reconciliation": {"is_exact": True},
        "records": [
            _record("C000001", label="Priority Review", selected=True, routing="CREATE_NEW_CASE", rank=1),
            _record("C000002", label="Review", selected=True, routing="ROUTE_EXISTING_CASE", rank=2),
            _record("C000003", label="Monitor", selected=False, routing="NO_ROUTING", rank=None),
            _record("C000004", label="Review", selected=False, routing="NO_ROUTING", rank=None),
            _record("C000005", label="Review", selected=False, routing="NO_ROUTING", rank=None),
        ],
    }


def _case(customer_id: str = "C000001"):
    return create_alert_case(
        alert_id=f"ALT-{customer_id}",
        customer_id=customer_id,
        policy_id="synthetic_early_warning_demo",
        policy_version="0.1.0",
        selection_policy_id="transparent_triage_selection_demo",
        selection_policy_version="0.1.0",
        signal_run_id="crossfit_seed42_5fold_asof12",
        signal_version="prospective_signal_snapshot.v1",
        signal_as_of_month=12,
        created_at=NOW - timedelta(days=3),
        due_at=NOW - timedelta(hours=1),
        operational_priority="PRIORITY_REVIEW",
        why_now_reason_codes=("CURRENT_STATUS_CONCERNING",),
        selection_reason_codes=("CAPACITY_UNBOUNDED",),
        timing_evidence_reference=TimingEvidenceReference(
            source="prospective_signal",
            candidate_month=12,
            evaluation_status="not_evaluated",
        ),
        episode_key=f"{customer_id}:synthetic_early_warning_demo:12",
        owner_reference=None,
    )


def _cohort() -> dict[str, object]:
    return {
        "records": [
            {"category_id": "priority_review", "customer_id": "C000001", "status": "selected"},
            {"category_id": "early_signal_review", "customer_id": "C000002", "status": "selected"},
            {"category_id": "monitor_no_alert_comparison", "customer_id": "C000003", "status": "selected"},
            {"category_id": "insufficient_or_landmark_not_found", "customer_id": None, "status": "unavailable"},
        ]
    }


def test_portfolio_uses_manifest_funnel_and_selected_queue_exactly() -> None:
    model = build_rm_portfolio_queue_view_model(
        selection_manifest=_manifest(),
        representative_cohort=_cohort(),
        alert_cases=(_case(),),
        language="en",
        now=NOW,
    )

    funnel = {stage["id"]: stage["count"] for stage in model["portfolio"]["funnel"]}
    assert funnel["monitored_total"] == 5
    assert funnel["selected_queue_ready"] == 2
    assert model["portfolio"]["reconciliation"] == {
        "is_exact": True,
        "manifest_exact": True,
        "record_count": 5,
        "expected_record_count": 5,
        "unique_customer_ids": True,
        "selected_count": 2,
        "expected_selected_count": 2,
        "open_alert_count": 1,
        "status": "exact",
    }
    assert model["portfolio"]["new_alert_count"] == 1
    assert model["portfolio"]["open_alert_count"] == 1
    assert model["portfolio"]["due_alert_count"] == 1
    assert model["portfolio"]["overdue_alert_count"] == 1


def test_queue_excludes_monitor_and_nonselected_rows_and_keeps_prospective_timing_separate() -> None:
    model = build_rm_portfolio_queue_view_model(
        selection_manifest=_manifest(),
        representative_cohort=_cohort(),
        language="en",
        now=NOW,
    )

    rows = model["queue"]["rows"]
    assert [row["customer_id"] for row in rows] == ["C000001", "C000002"]
    assert [row["selection_rank"] for row in rows] == [1, 2]
    assert all(row["timing_evidence_reference"]["source"] == "prospective_signal" for row in rows)
    assert all("historical" not in " ".join(row) for row in rows)
    comparisons = model["representative_comparisons"]
    assert comparisons[2]["customer_id"] == "C000003"
    assert all(item["operational_queue_row"] is False for item in comparisons)


def test_queue_filter_sort_and_safe_row_navigation_are_deterministic() -> None:
    model = build_rm_portfolio_queue_view_model(
        selection_manifest=_manifest(),
        representative_cohort=_cohort(),
        priority_scope="priority",
        owner_scope="unassigned",
        search_query="C000001",
        sort_by="rank",
        now=NOW,
    )

    assert [row["customer_id"] for row in model["queue"]["rows"]] == ["C000001"]
    assert customer_context_from_queue_row(model, "C000001") == "C000001"
    assert customer_context_from_queue_row(model, "C000003") is None
    assert customer_context_from_queue_row(model, "bad customer id") is None


def test_unrelated_open_case_does_not_change_a_versioned_triage_queue() -> None:
    matching_case = _case()
    unrelated_case = replace(
        _case(),
        alert_id="ALT-UNRELATED",
        policy_version="0.2.0",
        updated_at=NOW + timedelta(minutes=1),
    )
    model = build_rm_portfolio_queue_view_model(
        selection_manifest=_manifest(),
        representative_cohort=_cohort(),
        alert_cases=(matching_case, unrelated_case),
        language="en",
        now=NOW,
    )

    assert model["portfolio"]["open_alert_count"] == 1
    assert model["queue"]["rows"][0]["case_alert_id"] == matching_case.alert_id


def test_unavailable_manifest_and_corrupt_repository_are_honest_and_nonmutating(tmp_path: Path) -> None:
    model = build_rm_portfolio_queue_view_model(
        selection_manifest=None,
        representative_cohort=None,
        language="en",
    )
    assert model["available"] is False
    assert model["queue"]["rows"] == ()

    (tmp_path / ALERT_CASE_REPOSITORY_FILENAME).write_text("{bad", encoding="utf-8")
    snapshot = load_rm_alert_cases(tmp_path)
    assert snapshot.cases == ()
    assert snapshot.load_error == "repository_unavailable"
