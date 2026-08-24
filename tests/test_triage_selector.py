"""Tests for transparent, capacity-aware triage selection."""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

import src.triage_selector as triage_selector
from src.demo_policy import assess_policy_snapshot, default_demo_policy
from src.prospective_signals import SignalSnapshot
from src.triage_selector import TriageSelector, default_triage_selection_policy
from src.triage_universe import TriageDecisionInput, build_triage_universe


def _snapshot(customer_id: str, **overrides: object) -> SignalSnapshot:
    values: dict[str, object] = {
        "customer_id": customer_id,
        "as_of_month": 12,
        "matched_count": 5,
        "neighbor_ids": ("C900001", "C900002"),
        "historical_cohort_risk_share": 0.30,
        "historical_cohort_risk_share_delta": None,
        "match_distance_mean": 0.20,
        "match_distance_mean_delta": None,
        "neighbor_jaccard_similarity": None,
        "current_status": "healthy",
        "current_status_transition": "initial",
        "financial_stress_factors": (),
        "persistent_financial_stress_factors": (),
        "previous_as_of_month": None,
    }
    values.update(overrides)
    return SignalSnapshot(**values)  # type: ignore[arg-type]


def _input(
    customer_id: str,
    *,
    existing_open_case_reference: str | None = None,
    **snapshot_overrides: object,
) -> TriageDecisionInput:
    snapshot = _snapshot(customer_id, **snapshot_overrides)
    return TriageDecisionInput(
        customer_id,
        snapshot,
        assess_policy_snapshot(default_demo_policy(), snapshot),
        existing_open_case_reference=existing_open_case_reference,
    )


def _universe(*, reverse_inputs: bool = False):
    inputs = (
        _input(
            "C000001",
            existing_open_case_reference="CASE-001",
            current_status="stress",
            financial_stress_factors=("low_savings_rate",),
        ),
        _input(
            "C000002",
            current_status="stress",
            financial_stress_factors=("low_savings_rate",),
            persistent_financial_stress_factors=("low_savings_rate",),
            previous_as_of_month=11,
            neighbor_jaccard_similarity=0.9,
        ),
        _input(
            "C000003",
            financial_stress_factors=("low_savings_rate",),
            persistent_financial_stress_factors=("low_savings_rate",),
            previous_as_of_month=11,
            neighbor_jaccard_similarity=0.8,
        ),
        _input(
            "C000004",
            financial_stress_factors=("low_savings_rate",),
            persistent_financial_stress_factors=("low_savings_rate",),
            previous_as_of_month=11,
            neighbor_jaccard_similarity=0.8,
        ),
        _input("C000005", financial_stress_factors=("low_savings_rate",)),
        _input("C000006"),
        _input("C000007", matched_count=0, financial_stress_factors=("low_savings_rate",)),
    )
    ordered_inputs = tuple(reversed(inputs)) if reverse_inputs else inputs
    return build_triage_universe(
        expected_customer_ids=(
            "C000008",
            "C000004",
            "C000002",
            "C000006",
            "C000003",
            "C000005",
            "C000001",
            "C000007",
        ),
        triage_as_of_month=12,
        signal_run_id="crossfit_seed42_5fold_asof12",
        decision_inputs=ordered_inputs,
    )


def _ranked_customer_ids(result) -> list[str]:  # type: ignore[no-untyped-def]
    return [
        decision.customer_id
        for decision in sorted(
            (decision for decision in result.decisions if decision.review_priority_rank is not None),
            key=lambda decision: decision.review_priority_rank,
        )
    ]


def _selected_customer_ids(result) -> set[str]:  # type: ignore[no-untyped-def]
    return {
        decision.customer_id
        for decision in result.decisions
        if decision.queue_status == "SELECTED_FOR_REVIEW"
    }


def test_default_selection_policy_declares_transparent_order_without_fixed_capacity() -> None:
    policy = default_triage_selection_policy()
    serialized = policy.to_dict()

    assert policy.status == "demo"
    assert policy.max_reviews_per_cycle is None
    assert [dimension["dimension_id"] for dimension in serialized["ranking_dimensions"]] == [
        "operational_priority_band",
        "prospective_timing_bucket",
        "signal_persistence",
        "neighbor_stability",
        "evidence_sufficiency_quality",
        "stable_customer_tie_breaker",
    ]
    assert [dimension["direction"] for dimension in serialized["ranking_dimensions"]] == [
        "descending",
        "ascending",
        "descending",
        "descending",
        "descending",
        "ascending",
    ]
    assert "0-100" not in serialized["rationale"]


def test_lexicographic_priority_order_and_reasons_are_deterministic() -> None:
    selector = TriageSelector()
    first = selector.select(_universe(), default_triage_selection_policy())
    second = selector.select(_universe(reverse_inputs=True), default_triage_selection_policy())
    decisions = {decision.customer_id: decision for decision in first.decisions}

    assert _ranked_customer_ids(first) == ["C000002", "C000001", "C000003", "C000004"]
    assert first.to_dict() == second.to_dict()
    assert decisions["C000002"].priority_tuple == (0, 0, 0, 0, 0, "C000002")
    assert decisions["C000001"].priority_tuple == (0, 0, 1, 2, 0, "C000001")
    assert decisions["C000003"].priority_tuple < decisions["C000004"].priority_tuple
    assert decisions["C000003"].priority_tuple[:5] == decisions["C000004"].priority_tuple[:5]
    assert decisions["C000003"].priority_tuple[-1] < decisions["C000004"].priority_tuple[-1]
    assert "CURRENT_STATUS_CONCERNING" in decisions["C000002"].why_now_reason_codes
    assert "PRIORITY_BAND_PRIORITY_REVIEW" in decisions["C000002"].selection_reason_codes
    assert "PERSISTENCE_PRESENT" in decisions["C000002"].selection_reason_codes
    assert "STABILITY_STABLE" in decisions["C000002"].selection_reason_codes
    assert "CAPACITY_UNBOUNDED" in decisions["C000002"].selection_reason_codes


def test_capacity_none_zero_n_and_above_eligible_are_explicit_and_monotonic() -> None:
    selector = TriageSelector()
    universe = _universe()
    all_eligible = selector.select(universe, default_triage_selection_policy())
    zero = selector.select(universe, default_triage_selection_policy(max_reviews_per_cycle=0))
    two = selector.select(universe, default_triage_selection_policy(max_reviews_per_cycle=2))
    ten = selector.select(universe, default_triage_selection_policy(max_reviews_per_cycle=10))
    hundred = selector.select(universe, default_triage_selection_policy(max_reviews_per_cycle=100))
    thousand = selector.select(universe, default_triage_selection_policy(max_reviews_per_cycle=1000))

    assert all_eligible.eligible_review_count == 4
    assert all_eligible.selected_for_review_count == 4
    assert zero.selected_for_review_count == 0
    assert zero.deferred_capacity_count == 4
    assert two.selected_for_review_count == 2
    assert two.deferred_capacity_count == 2
    assert ten.selected_for_review_count == 4
    assert (
        _selected_customer_ids(zero)
        <= _selected_customer_ids(two)
        <= _selected_customer_ids(ten)
        <= _selected_customer_ids(hundred)
        <= _selected_customer_ids(thousand)
    )
    assert _selected_customer_ids(ten) == _selected_customer_ids(all_eligible)
    assert _selected_customer_ids(hundred) == _selected_customer_ids(all_eligible)
    assert _selected_customer_ids(thousand) == _selected_customer_ids(all_eligible)
    zero_decisions = {decision.customer_id: decision for decision in zero.decisions}
    assert zero_decisions["C000002"].queue_status == "DEFERRED_CAPACITY"
    assert "CAPACITY_DEFERRED" in zero_decisions["C000002"].selection_reason_codes
    two_decisions = {decision.customer_id: decision for decision in two.decisions}
    assert two_decisions["C000002"].queue_status == "SELECTED_FOR_REVIEW"
    assert two_decisions["C000001"].queue_status == "SELECTED_FOR_REVIEW"
    assert "CAPACITY_WITHIN_LIMIT" in two_decisions["C000001"].selection_reason_codes


def test_monitor_no_signal_and_insufficient_evidence_never_enter_operational_queue() -> None:
    result = TriageSelector().select(_universe(), default_triage_selection_policy(max_reviews_per_cycle=10))
    decisions = {decision.customer_id: decision for decision in result.decisions}

    for customer_id in ("C000005", "C000006", "C000007", "C000008"):
        assert decisions[customer_id].queue_status == "NOT_QUEUE_ELIGIBLE"
        assert decisions[customer_id].review_priority_rank is None
        assert decisions[customer_id].routing_action == "NO_ROUTING"
        assert decisions[customer_id].selection_reason_codes == (
            "NOT_QUEUE_ELIGIBLE",
            "NO_ROUTING",
        )


def test_selected_routing_contract_distinguishes_existing_case_without_side_effects() -> None:
    result = TriageSelector().select(_universe(), default_triage_selection_policy(max_reviews_per_cycle=2))
    decisions = {decision.customer_id: decision for decision in result.decisions}

    assert decisions["C000001"].routing_action == "ROUTE_EXISTING_CASE"
    assert decisions["C000001"].existing_open_case_reference == "CASE-001"
    assert decisions["C000002"].routing_action == "CREATE_NEW_CASE"
    assert decisions["C000003"].routing_action == "NO_ROUTING"
    assert decisions["C000003"].queue_status == "DEFERRED_CAPACITY"
    assert result.to_dict()["selection"] == {
        "automatic_capacity_choice": False,
        "case_repository_implemented": False,
        "notification_provider_implemented": False,
    }
    assert all(
        decision.to_dict()["scope"]["case_creation_executed"] is False
        for decision in result.decisions
    )


def test_invalid_capacity_and_future_label_or_ui_dependencies_are_rejected_or_absent() -> None:
    with pytest.raises(ValueError, match="max_reviews_per_cycle"):
        default_triage_selection_policy(max_reviews_per_cycle=-1)
    with pytest.raises(ValueError, match="max_reviews_per_cycle"):
        default_triage_selection_policy(max_reviews_per_cycle=True)  # type: ignore[arg-type]

    source = Path(triage_selector.__file__).read_text(encoding="utf-8")
    source_tree = ast.parse(source)
    imported_modules = [
        alias.name
        for node in ast.walk(source_tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    ]

    assert "final_outcome" not in source
    assert "persona" not in source
    assert "event_type" not in source
    assert "risk_score" not in source
    assert "streamlit" not in source.lower()
    assert not any("evaluator" in module for module in imported_modules)
    assert not any("notification" in module for module in imported_modules)
    assert not any("provider" in module for module in imported_modules)


def test_selector_rejects_non_reconciled_triage_universe() -> None:
    universe = _universe()
    incomplete_reconciliation = replace(
        universe.reconciliation,
        result_missing_customer_ids=("C000008",),
    )
    incomplete_universe = replace(universe, reconciliation=incomplete_reconciliation)

    with pytest.raises(ValueError, match="coverage must reconcile exactly"):
        TriageSelector().select(incomplete_universe, default_triage_selection_policy())
