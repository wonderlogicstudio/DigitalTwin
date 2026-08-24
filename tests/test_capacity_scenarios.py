"""Contracts for caller-supplied, comparison-only RM capacity scenarios."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from src.capacity_scenarios import (
    CapacityScenario,
    build_capacity_comparison_report,
    build_capacity_comparison_view_model,
    export_capacity_comparison_report,
)


def _record(customer_id: str, rank: int | None, label: str, *, eligible: bool = True) -> dict[str, object]:
    return {
        "customer_id": customer_id,
        "review_priority_rank": rank,
        "eligible_for_review": eligible,
        "eligibility_label": label,
    }


def _manifest() -> dict[str, object]:
    return {
        "run_id": "fixture_run",
        "schema_version": "rm_selection_manifest.v1",
        "signal_run_id": "fixture_signal_run",
        "triage_as_of_month": 12,
        "selection_policy": {"policy_id": "fixture_policy", "version": "0.1.0", "status": "demo"},
        "funnel": {"monitored_total": 4, "eligible_total": 3},
        "records": [
            _record("C000002", 2, "Review"),
            _record("C000004", None, "Monitor", eligible=False),
            _record("C000001", 1, "Priority Review"),
            _record("C000003", 3, "Review"),
        ],
    }


def _result(capacity: int | None):
    report = build_capacity_comparison_report(
        _manifest(),
        (CapacityScenario(f"scenario_{'unbounded' if capacity is None else capacity}", capacity),),
    )
    return report.scenarios[0]


def test_capacity_cutoff_preserves_saved_rank_order_and_reconciles_counts() -> None:
    unbounded = _result(None)
    one = _result(1)
    two = _result(2)

    assert unbounded.selected_customer_ids == ("C000001", "C000002", "C000003")
    assert unbounded.selected_count == 3
    assert unbounded.deferred_count == 0
    assert unbounded.coverage_percent == 100.0
    assert one.selected_customer_ids == ("C000001",)
    assert one.deferred_customer_ids == ("C000002", "C000003")
    assert one.selected_count + one.deferred_count == one.eligible_count == 3
    assert one.selected_priority_count == 1
    assert one.selected_review_count == 0
    assert one.deferred_priority_count == 0
    assert one.deferred_review_count == 2
    assert two.selected_customer_ids == unbounded.selected_customer_ids[:2]
    assert one.selected_customer_ids == two.selected_customer_ids[:1]
    assert one.ranking_digest == two.ranking_digest == unbounded.ranking_digest


@pytest.mark.parametrize(
    ("capacity", "selected", "deferred"),
    ((0, 0, 3), (1, 1, 2), (3, 3, 0), (4, 3, 0), (None, 3, 0)),
)
def test_capacity_edge_cases_are_explicit(capacity: int | None, selected: int, deferred: int) -> None:
    result = _result(capacity)

    assert result.selected_count == selected
    assert result.deferred_count == deferred
    assert result.estimated_carry_over_count == deferred
    assert result.scenario.is_unbounded_reference is (capacity is None)


def test_no_approved_default_or_invalid_capacity_is_allowed() -> None:
    assert CapacityScenario("draft", 10).status == "draft"
    assert CapacityScenario("demo", None, status="demo").scope == "comparison_only"
    with pytest.raises(ValueError, match="approval_evidence_reference"):
        CapacityScenario("approved_without_evidence", 10, status="approved")
    assert CapacityScenario(
        "approved_with_evidence",
        10,
        status="approved",
        approval_evidence_reference="governance-record-reference",
    ).status == "approved"
    for invalid in (-1, True, 1.5):
        with pytest.raises(ValueError, match="max_reviews_per_cycle"):
            CapacityScenario("invalid", invalid)  # type: ignore[arg-type]


def test_report_is_deterministic_detail_reconciled_and_atomic(tmp_path: Path) -> None:
    source = _manifest()
    scenarios = (CapacityScenario("zero", 0), CapacityScenario("one", 1), CapacityScenario("all", None))
    first = build_capacity_comparison_report(source, scenarios)
    second = build_capacity_comparison_report(source, scenarios)

    assert first.to_dict() == second.to_dict()
    assert first.reconciliation["is_exact"] is True
    assert first.reconciliation["record_count"] == 4
    assert first.reconciliation["ranked_eligible_count"] == 3
    destination = export_capacity_comparison_report(first, tmp_path / "capacity" / "report.json")
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["selection"]["automatic_capacity_choice"] is False
    assert payload["selection"]["source_ranking_recomputed"] is False
    assert payload["scenarios"][1]["selected_customer_ids"] == ["C000001"]
    assert not list(destination.parent.glob(".*.tmp"))
    assert source == _manifest()


def test_mismatched_detail_and_funnel_or_duplicate_scenario_is_rejected() -> None:
    inconsistent = _manifest()
    inconsistent["funnel"] = {"monitored_total": 4, "eligible_total": 2}
    with pytest.raises(ValueError, match="reconciliation"):
        build_capacity_comparison_report(inconsistent, (CapacityScenario("one", 1),))
    with pytest.raises(ValueError, match="unique"):
        build_capacity_comparison_report(
            _manifest(),
            (CapacityScenario("same", 1), CapacityScenario("same", 2)),
        )


def test_view_model_is_comparison_only_and_module_has_no_leakage_or_ui_dependency() -> None:
    view_model = build_capacity_comparison_view_model(_manifest(), CapacityScenario("one", 1))
    assert view_model["comparison_only"] is True
    assert view_model["scenario"]["selected_count"] == 1
    assert view_model["scenario"]["scenario"]["status"] == "draft"

    import src.capacity_scenarios as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = [
        alias.name.lower()
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    ]
    assert "streamlit" not in source.lower()
    assert "final_outcome" not in source
    assert "persona" not in source
    assert not any("evaluator" in name or "matcher" in name for name in imported_modules)
