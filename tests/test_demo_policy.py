"""Contract tests for the versioned prospective demo policy."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import src.demo_policy as demo_policy
from src.demo_policy import (
    DemoPolicyRule,
    HistoricalLandmarkContext,
    PolicyEvaluationContext,
    VersionedDemoPolicy,
    assess_policy_snapshot,
    default_demo_policy,
)
from src.prospective_signals import SignalSnapshot


def _snapshot(**overrides: object) -> SignalSnapshot:
    values: dict[str, object] = {
        "customer_id": "C000001",
        "as_of_month": 12,
        "matched_count": 5,
        "neighbor_ids": ("C000002", "C000003"),
        "historical_cohort_risk_share": 0.30,
        "historical_cohort_risk_share_delta": None,
        "match_distance_mean": 0.20,
        "match_distance_mean_delta": None,
        "neighbor_jaccard_similarity": None,
        "current_status": "watch",
        "current_status_transition": "initial",
        "financial_stress_factors": ("low_savings_rate",),
        "persistent_financial_stress_factors": (),
        "previous_as_of_month": None,
    }
    values.update(overrides)
    return SignalSnapshot(**values)  # type: ignore[arg-type]


def test_default_policy_is_serializable_versioned_demo_not_approved() -> None:
    policy = default_demo_policy()
    serialized = policy.to_dict()

    assert policy.status == "demo"
    assert policy.status != "approved"
    assert serialized["schema_version"] == "versioned_demo_policy.v1"
    assert serialized["policy_id"] == "synthetic_early_warning_demo"
    assert serialized["version"] == "0.1.0"
    assert serialized["persistence_months"] == 2
    assert serialized["cooldown_months"] == 1
    assert serialized["source_backtest_run"] == "crossfit_seed42_5fold_asof12"
    assert len(serialized["rules"]) == 4
    assert serialized["approval_evidence"] is None
    assert all(label in {"Monitor", "Review", "Priority Review"} for label in [
        rule["operational_label"] for rule in serialized["rules"]
    ])


def test_approved_policy_requires_explicit_evidence_and_invalid_status_is_rejected() -> None:
    base = default_demo_policy()

    with pytest.raises(ValueError, match="approval_evidence"):
        VersionedDemoPolicy(
            **{**base.__dict__, "status": "approved", "approval_evidence": None}
        )
    with pytest.raises(ValueError, match="status must be one of"):
        VersionedDemoPolicy(**{**base.__dict__, "status": "production"})  # type: ignore[arg-type]


def test_assessment_exposes_why_now_timing_and_separate_historical_landmark() -> None:
    snapshot = _snapshot(
        current_status="stress",
        financial_stress_factors=("low_savings_rate", "elevated_dsr"),
        persistent_financial_stress_factors=("low_savings_rate",),
    )
    assessment = assess_policy_snapshot(
        default_demo_policy(),
        snapshot,
        historical_landmark_context=HistoricalLandmarkContext("found", 14),
    )
    serialized = assessment.to_dict()

    assert assessment.eligibility is True
    assert assessment.operational_label == "Priority Review"
    assert set(assessment.matched_rule_ids) == {
        "current_stress_or_delinquent",
        "persistent_financial_stress",
        "multiple_current_financial_stress_factors",
        "current_financial_stress_factor",
    }
    assert assessment.why_now_reasons
    assert serialized["prospective_timing_evidence"] == {
        "candidate_month": 12,
        "source": "prospective_signal",
        "evaluation_status": "not_evaluated",
        "lead_time_months": None,
        "lead_time_unit": "months",
    }
    assert serialized["historical_landmark_context"] == {
        "breakpoint_status": "found",
        "breakpoint_month": 14,
        "source": "historical_landmark",
        "is_live_alert_trigger": False,
    }
    assert serialized["scope"] == {
        "triage_input_only": True,
        "rm_queue_selection": False,
        "alert_creation": False,
    }


def test_cooldown_changes_eligibility_without_hiding_the_matching_reasons() -> None:
    snapshot = _snapshot(financial_stress_factors=("low_savings_rate",))
    assessment = assess_policy_snapshot(
        default_demo_policy(),
        snapshot,
        context=PolicyEvaluationContext(months_since_last_eligible=0),
    )

    assert assessment.matched_rule_ids == ("current_financial_stress_factor",)
    assert assessment.cooldown_applied is True
    assert assessment.eligibility is False
    assert assessment.operational_label == "Monitor"
    assert "cooldown" in " ".join(assessment.why_now_reasons).lower()


def test_historical_landmark_cannot_be_created_as_a_live_trigger() -> None:
    with pytest.raises(ValueError, match="cannot be live alert triggers"):
        HistoricalLandmarkContext("found", 14, is_live_alert_trigger=True)


def test_historical_landmark_is_never_a_policy_trigger() -> None:
    snapshot = _snapshot(financial_stress_factors=())
    policy = default_demo_policy()

    without_landmark = assess_policy_snapshot(policy, snapshot)
    with_landmark = assess_policy_snapshot(
        policy,
        snapshot,
        historical_landmark_context=HistoricalLandmarkContext("found", 13),
    )

    assert without_landmark.eligibility is False
    assert with_landmark.eligibility == without_landmark.eligibility
    assert with_landmark.operational_label == without_landmark.operational_label
    assert with_landmark.matched_rule_ids == without_landmark.matched_rule_ids


def test_policy_evaluation_only_reads_snapshot_and_imports_no_evaluator() -> None:
    source_path = Path(demo_policy.__file__)
    source = source_path.read_text(encoding="utf-8")
    source_tree = ast.parse(source)
    imported_modules = [
        alias.name
        for node in ast.walk(source_tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    ]
    baseline = assess_policy_snapshot(default_demo_policy(), _snapshot())
    changed_metadata = _snapshot(
        historical_cohort_risk_share=0.99,
        historical_cohort_risk_share_delta=0.99,
        neighbor_ids=("C009999",),
        match_distance_mean=99.0,
    )
    after_metadata_change = assess_policy_snapshot(default_demo_policy(), changed_metadata)

    assert not any("evaluator" in module for module in imported_modules)
    assert "final_outcome" not in source
    assert "persona" not in source
    assert baseline.matched_rule_ids == after_metadata_change.matched_rule_ids
    assert baseline.eligibility == after_metadata_change.eligibility


def test_rule_contract_rejects_non_policy_rule_shapes() -> None:
    with pytest.raises(ValueError, match="current_status rules"):
        DemoPolicyRule(
            "invalid",
            "current_status",
            "gte",
            1,
            "Monitor",
            "Invalid.",
        )
