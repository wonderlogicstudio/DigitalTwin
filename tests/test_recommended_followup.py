"""Contracts for human-reviewed Recommended Follow-up and case outcomes."""

from __future__ import annotations

import ast
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import src.recommended_followup as recommended_followup
from src.alert_case import AlertCase, TimingEvidenceReference, create_alert_case
from src.recommended_followup import (
    CASE_OUTCOMES,
    RM_ACTIONS,
    CaseOutcomeRecord,
    RMActionRecord,
    WhatIfSupportingEvidence,
    build_recommended_follow_up,
)


RECORDED_AT = datetime(2026, 8, 23, 9, 0, tzinfo=timezone.utc)


def _case(**overrides: object) -> AlertCase:
    values: dict[str, object] = {
        "alert_id": "ALT-000001",
        "customer_id": "C000001",
        "policy_id": "synthetic_early_warning_demo",
        "policy_version": "0.1.0",
        "selection_policy_id": "transparent_triage_selection_demo",
        "selection_policy_version": "0.1.0",
        "signal_run_id": "crossfit_seed42_5fold_asof12",
        "signal_version": "prospective_signal_snapshot.v1",
        "signal_as_of_month": 12,
        "created_at": RECORDED_AT,
        "due_at": RECORDED_AT + timedelta(days=2),
        "operational_priority": "PRIORITY_REVIEW",
        "why_now_reason_codes": ("CURRENT_STATUS_CONCERNING",),
        "selection_reason_codes": ("PRIORITY_BAND_PRIORITY_REVIEW",),
        "timing_evidence_reference": TimingEvidenceReference(
            source="prospective_signal",
            candidate_month=12,
            evaluation_status="not_evaluated",
        ),
        "episode_key": "C000001:synthetic_early_warning_demo:12",
    }
    values.update(overrides)
    return create_alert_case(**values)  # type: ignore[arg-type]


def test_recommended_follow_up_maps_current_reasons_timing_and_urgency_without_execution() -> None:
    recommendation = build_recommended_follow_up(_case())

    assert recommendation.title == "Recommended Follow-up"
    assert recommendation.urgency == "PROMPT"
    assert recommendation.recommended_actions == ("REVIEW_COMPLETED", "CONTACT_PLANNED")
    assert recommendation.reason_codes == ("CURRENT_STATUS_CONCERNING",)
    assert recommendation.timing_evidence_reference.candidate_month == 12
    assert recommendation.automatic_execution is False
    assert recommendation.automatic_financial_decision is False
    assert recommendation.to_dict()["scope"] == {
        "automatic_execution": False,
        "automatic_financial_decision": False,
        "action_effectiveness_estimated": False,
    }


def test_reason_mapping_supports_monitor_no_action_and_referral_without_financial_decisions() -> None:
    monitor = build_recommended_follow_up(
        _case(why_now_reason_codes=("MONITOR_ONLY",), operational_priority="REVIEW")
    )
    no_action = build_recommended_follow_up(
        _case(why_now_reason_codes=("NO_ACTION_REQUIRED",), operational_priority="REVIEW")
    )
    referral = build_recommended_follow_up(
        _case(why_now_reason_codes=("REFERRAL_INDICATED",), operational_priority="REVIEW")
    )

    assert monitor.urgency == "STANDARD"
    assert monitor.recommended_actions == ("MONITOR_ONLY",)
    assert no_action.recommended_actions == ("NO_ACTION_REQUIRED",)
    assert referral.recommended_actions == ("REVIEW_COMPLETED", "REFERRED")


def test_rm_action_enum_and_record_validation_are_explicit() -> None:
    assert set(RM_ACTIONS) == {
        "REVIEW_COMPLETED",
        "CONTACT_PLANNED",
        "CONTACT_COMPLETED",
        "MONITOR_ONLY",
        "NO_ACTION_REQUIRED",
        "REFERRED",
        "FOLLOW_UP_CREATED",
    }
    for action in RM_ACTIONS:
        record = RMActionRecord(
            alert_id="ALT-000001",
            action=action,  # type: ignore[arg-type]
            recorded_at=RECORDED_AT,
            recorded_by="rm-001",
        )
        assert record.to_dict()["scope"]["automatic_execution"] is False  # type: ignore[index]

    with pytest.raises(ValueError, match="one of"):
        RMActionRecord(
            alert_id="ALT-000001",
            action="AUTOMATED_DECISION",  # type: ignore[arg-type]
            recorded_at=RECORDED_AT,
            recorded_by="rm-001",
        )


def test_case_outcomes_and_closure_reasons_are_workflow_records() -> None:
    terminal = CaseOutcomeRecord(
        alert_id="ALT-000001",
        customer_id="C000001",
        outcome="CONTACT_DOCUMENTED",
        recorded_at=RECORDED_AT,
        recorded_by="rm-001",
        closure_reason="CONTACT_COMPLETED",
        action_references=("ACT-001",),
    )
    monitoring = CaseOutcomeRecord(
        alert_id="ALT-000001",
        customer_id="C000001",
        outcome="MONITORING_CONTINUES",
        recorded_at=RECORDED_AT,
        recorded_by="rm-001",
    )

    assert "CONTACT_DOCUMENTED" in CASE_OUTCOMES
    assert terminal.to_dict()["scope"]["analytical_label_attached"] is False  # type: ignore[index]
    assert monitoring.closure_reason is None
    with pytest.raises(ValueError, match="require a valid closure_reason"):
        CaseOutcomeRecord(
            alert_id="ALT-000001",
            customer_id="C000001",
            outcome="REFERRED",
            recorded_at=RECORDED_AT,
            recorded_by="rm-001",
        )
    with pytest.raises(ValueError, match="cannot include closure_reason"):
        CaseOutcomeRecord(
            alert_id="ALT-000001",
            customer_id="C000001",
            outcome="FOLLOW_UP_SCHEDULED",
            recorded_at=RECORDED_AT,
            recorded_by="rm-001",
            closure_reason="UNRESOLVED",
        )


def test_whatif_context_does_not_change_recommendations_or_estimate_action_effectiveness() -> None:
    case = _case()
    baseline = build_recommended_follow_up(case)
    evidence = WhatIfSupportingEvidence(
        scenario_name="fixed_expense_cut_300k",
        simulation_months=24,
        evidence_note="Rule-based cash-flow scenario for discussion only.",
    )
    supported = build_recommended_follow_up(case, whatif_supporting_evidence=evidence)

    assert supported.recommended_actions == baseline.recommended_actions
    assert supported.urgency == baseline.urgency
    assert supported.whatif_supporting_evidence is not None
    assert supported.whatif_supporting_evidence.to_dict()["estimates_action_effectiveness"] is False
    with pytest.raises(ValueError, match="supporting context only"):
        WhatIfSupportingEvidence(
            scenario_name="fixed_expense_cut_300k",
            simulation_months=24,
            evidence_note="Not permitted.",
            changes_recommendation=True,
        )
    with pytest.raises(ValueError, match="supporting context only"):
        WhatIfSupportingEvidence(
            scenario_name="fixed_expense_cut_300k",
            simulation_months=24,
            evidence_note="Not permitted.",
            estimates_action_effectiveness=True,
        )


def test_recommendation_copy_excludes_automatic_financial_decision_phrases() -> None:
    rendered = str(build_recommended_follow_up(_case()).to_dict()).lower()
    forbidden = (
        "next best action",
        "approve",
        "decline",
        "restructure",
        "product sell",
    )
    assert all(phrase not in rendered for phrase in forbidden)


def test_contract_module_has_no_analytics_or_external_delivery_dependency() -> None:
    source = Path(recommended_followup.__file__).read_text(encoding="utf-8")
    source_tree = ast.parse(source)
    imported_modules = [
        alias.name
        for node in ast.walk(source_tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    ]
    field_names = {
        field.name
        for model in (recommended_followup.RecommendedFollowUp, CaseOutcomeRecord)
        for field in fields(model)
    }

    assert "final_outcome" not in source
    assert "persona" not in source
    assert "streamlit" not in source.lower()
    assert "whatif_simulator" not in source
    assert not any("notification" in module or "provider" in module for module in imported_modules)
    assert {"channel", "provider", "webhook", "recipient"}.isdisjoint(field_names)
