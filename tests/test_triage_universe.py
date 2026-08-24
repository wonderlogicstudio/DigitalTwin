"""Contract tests for exact, prospective-only triage universe coverage."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import src.triage_universe as triage_universe
from src.demo_policy import (
    HistoricalLandmarkContext,
    PolicyEvaluationContext,
    assess_policy_snapshot,
    default_demo_policy,
)
from src.prospective_signals import SignalSnapshot
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


def _decision_input(customer_id: str, **snapshot_overrides: object) -> TriageDecisionInput:
    snapshot = _snapshot(customer_id, **snapshot_overrides)
    assessment = assess_policy_snapshot(default_demo_policy(), snapshot)
    return TriageDecisionInput(customer_id, snapshot, assessment)


def test_exact_5000_customer_coverage_has_one_primary_disposition_each() -> None:
    expected_ids = tuple(f"C{index:06d}" for index in range(1, 5_001))
    inputs = tuple(_decision_input(customer_id) for customer_id in reversed(expected_ids))

    universe = build_triage_universe(
        expected_customer_ids=expected_ids,
        triage_as_of_month=12,
        signal_run_id="crossfit_seed42_5fold_asof12",
        decision_inputs=inputs,
    )

    assert len(universe.candidates) == 5_000
    assert [candidate.customer_id for candidate in universe.candidates] == list(expected_ids)
    assert len({candidate.customer_id for candidate in universe.candidates}) == 5_000
    assert all(candidate.primary_disposition == "NO_ACTIONABLE_SIGNAL" for candidate in universe.candidates)
    assert universe.reconciliation.expected_customer_count == 5_000
    assert universe.reconciliation.received_decision_input_count == 5_000
    assert universe.reconciliation.result_customer_count == 5_000
    assert universe.reconciliation.result_coverage_is_exact is True
    assert universe.reconciliation.decision_input_is_complete is True
    assert universe.to_dict()["selection"] == {
        "rm_ranking": False,
        "rm_queue_selection": False,
        "alert_creation": False,
    }


def test_policy_eligibility_is_separate_from_primary_triage_disposition() -> None:
    inputs = (
        _decision_input("C000001", current_status="stress"),
        _decision_input(
            "C000002",
            financial_stress_factors=("low_savings_rate",),
            persistent_financial_stress_factors=("low_savings_rate",),
            previous_as_of_month=11,
            neighbor_jaccard_similarity=0.80,
        ),
        _decision_input("C000003", financial_stress_factors=("low_savings_rate",)),
        _decision_input("C000004"),
    )

    universe = build_triage_universe(
        expected_customer_ids=("C000004", "C000001", "C000003", "C000002"),
        triage_as_of_month=12,
        signal_run_id="run-12",
        decision_inputs=inputs,
    )
    candidates = {candidate.customer_id: candidate for candidate in universe.candidates}

    assert candidates["C000001"].primary_disposition == "ELIGIBLE_PRIORITY"
    assert candidates["C000001"].eligible_for_review is True
    assert candidates["C000002"].primary_disposition == "ELIGIBLE_REVIEW"
    assert candidates["C000002"].signal_persistence == "persistent"
    assert candidates["C000002"].signal_stability == "stable"
    assert candidates["C000003"].primary_disposition == "MONITOR_ONLY"
    assert candidates["C000003"].operational_label == "Monitor"
    assert candidates["C000004"].primary_disposition == "NO_ACTIONABLE_SIGNAL"
    assert candidates["C000004"].operational_label == "Monitor"
    assert candidates["C000004"].why_now_reason_codes == ("NO_POLICY_RULE_MET",)
    assert candidates["C000001"].to_dict()["eligible_for_review"] is True
    assert candidates["C000001"].to_dict()["policy_eligibility"] is True


def test_missing_or_insufficient_evidence_uses_explicit_non_silent_fallbacks() -> None:
    zero_match_input = _decision_input(
        "C000001",
        matched_count=0,
        financial_stress_factors=("low_savings_rate",),
    )
    universe = build_triage_universe(
        expected_customer_ids=("C000001", "C000002"),
        triage_as_of_month=12,
        signal_run_id="run-12",
        decision_inputs=(zero_match_input,),
    )
    candidates = {candidate.customer_id: candidate for candidate in universe.candidates}

    assert candidates["C000001"].primary_disposition == "INSUFFICIENT_EVIDENCE"
    assert candidates["C000001"].why_now_reason_codes[-1] == "NO_REFERENCE_NEIGHBORS"
    assert candidates["C000001"].evidence_sufficiency == "insufficient"
    assert candidates["C000002"].primary_disposition == "DATA_UNAVAILABLE"
    assert candidates["C000002"].eligible_for_review is None
    assert candidates["C000002"].operational_label == "No Signal"
    assert candidates["C000002"].why_now_reason_codes == ("SIGNAL_INPUT_MISSING",)
    assert universe.reconciliation.missing_decision_input_customer_ids == ("C000002",)
    assert universe.reconciliation.result_coverage_is_exact is True
    assert universe.reconciliation.decision_input_is_complete is False


def test_duplicate_unknown_or_misaligned_inputs_are_rejected_not_silently_changed() -> None:
    duplicate = _decision_input("C000001")
    with pytest.raises(ValueError, match="duplicate triage decision input"):
        build_triage_universe(
            expected_customer_ids=("C000001",),
            triage_as_of_month=12,
            signal_run_id="run-12",
            decision_inputs=(duplicate, duplicate),
        )
    with pytest.raises(ValueError, match="unexpected customer IDs"):
        build_triage_universe(
            expected_customer_ids=("C000001",),
            triage_as_of_month=12,
            signal_run_id="run-12",
            decision_inputs=(_decision_input("C999999"),),
        )
    with pytest.raises(ValueError, match="must share triage_as_of_month"):
        build_triage_universe(
            expected_customer_ids=("C000001",),
            triage_as_of_month=12,
            signal_run_id="run-12",
            decision_inputs=(_decision_input("C000001", as_of_month=13),),
        )


def test_historical_landmark_context_is_carried_separately_never_used_as_trigger() -> None:
    snapshot = _snapshot("C000001")
    policy = default_demo_policy()
    baseline = TriageDecisionInput("C000001", snapshot, assess_policy_snapshot(policy, snapshot))
    landmark_context = TriageDecisionInput(
        "C000001",
        snapshot,
        assess_policy_snapshot(
            policy,
            snapshot,
            historical_landmark_context=HistoricalLandmarkContext("found", 13),
        ),
    )

    without_landmark = build_triage_universe(
        expected_customer_ids=("C000001",),
        triage_as_of_month=12,
        signal_run_id="run-12",
        decision_inputs=(baseline,),
    ).candidates[0]
    with_landmark = build_triage_universe(
        expected_customer_ids=("C000001",),
        triage_as_of_month=12,
        signal_run_id="run-12",
        decision_inputs=(landmark_context,),
    ).candidates[0]

    assert with_landmark.primary_disposition == without_landmark.primary_disposition
    assert with_landmark.eligible_for_review == without_landmark.eligible_for_review
    assert with_landmark.historical_landmark_context is not None
    assert with_landmark.historical_landmark_context.is_live_alert_trigger is False


def test_triage_has_no_future_label_or_ui_evaluator_dependency_and_is_deterministic() -> None:
    source = Path(triage_universe.__file__).read_text(encoding="utf-8")
    source_tree = ast.parse(source)
    imported_modules = [
        alias.name
        for node in ast.walk(source_tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    ]
    inputs = (
        _decision_input("C000002", financial_stress_factors=("low_savings_rate",)),
        _decision_input("C000001"),
    )
    first = build_triage_universe(
        expected_customer_ids=("C000001", "C000002"),
        triage_as_of_month=12,
        signal_run_id="run-12",
        decision_inputs=inputs,
    )
    second = build_triage_universe(
        expected_customer_ids=("C000002", "C000001"),
        triage_as_of_month=12,
        signal_run_id="run-12",
        decision_inputs=tuple(reversed(inputs)),
    )

    assert "final_outcome" not in source
    assert "persona" not in source
    assert "event_type" not in source
    assert "streamlit" not in source.lower()
    assert not any("evaluator" in module for module in imported_modules)
    assert not any("alert" in module for module in imported_modules)
    assert first.to_dict() == second.to_dict()


def test_cooldown_policy_signal_remains_monitor_only_not_queue_selection() -> None:
    snapshot = _snapshot("C000001", financial_stress_factors=("low_savings_rate",))
    assessment = assess_policy_snapshot(
        default_demo_policy(),
        snapshot,
        context=PolicyEvaluationContext(months_since_last_eligible=0),
    )
    universe = build_triage_universe(
        expected_customer_ids=("C000001",),
        triage_as_of_month=12,
        signal_run_id="run-12",
        decision_inputs=(TriageDecisionInput("C000001", snapshot, assessment),),
    )
    candidate = universe.candidates[0]

    assert candidate.primary_disposition == "MONITOR_ONLY"
    assert candidate.eligible_for_review is False
    assert "POLICY_COOLDOWN_ACTIVE" in candidate.why_now_reason_codes
    assert candidate.to_dict()["scope"]["rm_queue_selection"] is False
