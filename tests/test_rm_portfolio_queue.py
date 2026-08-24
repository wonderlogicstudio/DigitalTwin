"""Contracts for the read-only RM Portfolio and selected-only Review Queue."""

from __future__ import annotations

import json
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
            "data_unavailable": 0,
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
    assert model["portfolio"]["case_in_rm_queue_count"] == 1
    assert model["portfolio"]["selected_case_pending_count"] == 1
    assert model["portfolio"]["due_alert_count"] == 1
    assert model["portfolio"]["overdue_alert_count"] == 1
    assert model["portfolio"]["delivery_definition"] == "in_app_rm_work_queue_case"
    assert model["portfolio"]["external_delivery_implemented"] is False
    assert model["portfolio"]["provenance"] == {
        "run_id": None,
        "schema_version": None,
        "policy_id": None,
        "policy_version": None,
        "policy_status": None,
        "selection_as_of_month": None,
        "signal_run_id": None,
        "capacity_scenario_id": None,
    }


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
    assert all(row["selection_reason_details"] for row in rows)
    assert all(row["why_now_reason_details"] for row in rows)
    assert all(
        code not in row["selection_reason_details"]
        for row in rows
        for code in row["selection_reason_codes"]
    )
    assert all("historical" not in " ".join(row) for row in rows)
    assert [row["work_queue_delivery_status"] for row in rows] == [
        "SELECTED_CASE_PENDING",
        "SELECTED_CASE_PENDING",
    ]
    assert all(row["created_at"] is None for row in rows)
    assert all(row["due_status"] == "not_scheduled" for row in rows)
    comparisons = model["representative_comparisons"]
    assert comparisons[2]["customer_id"] == "C000003"
    assert all(item["operational_queue_row"] is False for item in comparisons)


def test_queue_marks_only_matching_open_cases_as_in_app_delivery_with_due_status() -> None:
    model = build_rm_portfolio_queue_view_model(
        selection_manifest=_manifest(),
        representative_cohort=_cohort(),
        alert_cases=(_case(),),
        language="en",
        now=NOW,
    )

    delivered, pending = model["queue"]["rows"]
    assert delivered["work_queue_delivery_status"] == "CASE_IN_RM_QUEUE"
    assert delivered["case_state"] == "NEW"
    assert delivered["created_at"] == (NOW - timedelta(days=3)).isoformat()
    assert delivered["due_status"] == "overdue"
    assert pending["work_queue_delivery_status"] == "SELECTED_CASE_PENDING"
    assert pending["case_state"] == "NO_OPEN_ALERT"
    assert pending["created_at"] is None
    assert pending["due_at"] is None


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


def test_representative_quick_select_requires_a_customer_in_the_saved_manifest() -> None:
    cohort = _cohort()
    cohort["records"][0]["customer_id"] = "C009999"
    model = build_rm_portfolio_queue_view_model(
        selection_manifest=_manifest(),
        representative_cohort=cohort,
        language="en",
        now=NOW,
    )

    priority = model["representative_comparisons"][0]
    assert priority["status"] == "unavailable"
    assert priority["available"] is False
    assert priority["customer_id"] is None


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


def test_persisted_population_funnel_is_exactly_the_rm_product_source() -> None:
    """The shipped RM Portfolio must display saved population/triage counts only."""

    project_root = Path(__file__).resolve().parents[1]
    population_detail = json.loads(
        (project_root / "artifacts" / "population" / "seed42_full_run" / "population_detail.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = json.loads(
        (
            project_root
            / "artifacts"
            / "triage"
            / "seed42_crossfit_5fold_asof12_unbounded"
            / "rm_selection_manifest.json"
        ).read_text(encoding="utf-8")
    )
    cohort = json.loads(
        (
            project_root
            / "artifacts"
            / "triage"
            / "seed42_crossfit_5fold_asof12_unbounded"
            / "rm_representative_cohort.json"
        ).read_text(encoding="utf-8")
    )

    population_ids = {record["customer_id"] for record in population_detail["results"]}
    manifest_ids = {record["customer_id"] for record in manifest["records"]}
    model = build_rm_portfolio_queue_view_model(
        selection_manifest=manifest,
        representative_cohort=None,
        language="en",
        now=NOW,
    )

    assert population_ids == manifest_ids
    assert len(population_ids) == manifest["funnel"]["monitored_total"]
    assert model["portfolio"]["reconciliation"]["is_exact"] is True
    assert {
        stage["id"]: stage["count"] for stage in model["portfolio"]["funnel"]
    } == {key: manifest["funnel"][key] for key in (
        "monitored_total",
        "eligible_priority",
        "eligible_review",
        "eligible_total",
        "selected_queue_ready",
        "deferred_capacity",
        "monitor_only",
        "no_actionable_signal",
        "insufficient_evidence",
        "data_unavailable",
    )}
    assert model["queue"]["unfiltered_count"] == manifest["funnel"]["selected_queue_ready"]
    assert model["portfolio"]["provenance"] == {
        "run_id": manifest["run_id"],
        "schema_version": manifest["schema_version"],
        "policy_id": manifest["selection_policy"]["policy_id"],
        "policy_version": manifest["selection_policy"]["version"],
        "policy_status": manifest["selection_policy"]["status"],
        "selection_as_of_month": manifest["triage_as_of_month"],
        "signal_run_id": manifest["signal_run_id"],
        "capacity_scenario_id": manifest["capacity_scenario"]["scenario_id"],
    }
    assert cohort["selection_rules"] == {
        "uses_triage_universe_only": True,
        "uses_operational_selection_result": False,
        "capacity_independent": True,
        "stable_tie_breaker": "customer_id ascending after category evidence order",
        "unavailable_category_policy": "record unavailable; do not alter customer conditions",
    }
    assert [record["category_id"] for record in cohort["records"]] == [
        "priority_review",
        "early_signal_review",
        "monitor_no_alert_comparison",
        "insufficient_or_landmark_not_found",
    ]
    manifest_by_id = {record["customer_id"]: record for record in manifest["records"]}
    for representative in cohort["records"]:
        customer_id = representative["customer_id"]
        if representative["status"] == "selected":
            source = manifest_by_id[customer_id]
            assert representative["source_primary_disposition"] == source["primary_disposition"]
            assert representative["source_operational_label"] == source["eligibility_label"]
            assert representative["source_signal_run_id"] == source["signal_run_id"]
            assert representative["source_as_of_month"] == source["as_of_month"]
        else:
            assert customer_id is None
            assert representative["selection_reason_codes"] == ["CATEGORY_UNAVAILABLE"]
