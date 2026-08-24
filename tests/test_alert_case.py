"""Contract tests for the provider-neutral Alert/Case state machine."""

from __future__ import annotations

import ast
from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import src.alert_case as alert_case
from src.alert_case import (
    ALERT_CASE_STATES,
    ALLOWED_STATE_TRANSITIONS,
    AlertCase,
    TimingEvidenceReference,
    create_alert_case,
)


CREATED_AT = datetime(2026, 8, 23, 9, 0, tzinfo=timezone.utc)


def _timing() -> TimingEvidenceReference:
    return TimingEvidenceReference(
        source="prospective_signal",
        candidate_month=12,
        evaluation_status="not_evaluated",
    )


def _new_case(**overrides: object) -> AlertCase:
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
        "created_at": CREATED_AT,
        "due_at": CREATED_AT + timedelta(days=3),
        "operational_priority": "PRIORITY_REVIEW",
        "why_now_reason_codes": ("CURRENT_STATUS_CONCERNING",),
        "selection_reason_codes": ("PRIORITY_BAND_PRIORITY_REVIEW",),
        "timing_evidence_reference": _timing(),
        "episode_key": "C000001:synthetic_early_warning_demo:12",
        "owner_reference": "rm-team-a",
    }
    values.update(overrides)
    return create_alert_case(**values)  # type: ignore[arg-type]


def _case_in_state(state: str) -> AlertCase:
    base = _new_case()
    updated_at = CREATED_AT + timedelta(hours=1)
    return replace(
        base,
        state=state,
        updated_at=updated_at,
        snoozed_until=(updated_at + timedelta(days=1) if state == "SNOOZED" else None),
        case_resolution=("RESOLVED_NO_ACTION" if state == "CLOSED" else None),
        last_state_change_reason="STATE_FIXTURE",
    )


def _transition_kwargs(target_state: str) -> dict[str, object]:
    values: dict[str, object] = {
        "occurred_at": CREATED_AT + timedelta(hours=2),
        "state_change_reason": "TESTED_TRANSITION",
    }
    if target_state == "SNOOZED":
        values["snoozed_until"] = CREATED_AT + timedelta(days=1)
    if target_state == "CLOSED":
        values["case_resolution"] = "CONTACT_COMPLETED"
    return values


def test_creation_and_serialization_round_trip_keep_workflow_resolution_separate() -> None:
    case = _new_case()
    closed = case.transition_to(
        "ACKNOWLEDGED",
        **_transition_kwargs("ACKNOWLEDGED"),
    ).transition_to(
        "CLOSED",
        occurred_at=CREATED_AT + timedelta(hours=3),
        state_change_reason="REVIEW_COMPLETE",
        case_resolution="CONTACT_COMPLETED",
    )
    payload = closed.to_dict()

    assert closed.state == "CLOSED"
    assert closed.case_resolution == "CONTACT_COMPLETED"
    assert AlertCase.from_dict(payload) == closed
    assert payload["policy_reference"] == {
        "policy_id": "synthetic_early_warning_demo",
        "policy_version": "0.1.0",
    }
    assert payload["selection_reference"] == {
        "selection_policy_id": "transparent_triage_selection_demo",
        "selection_policy_version": "0.1.0",
        "selection_reason_codes": ["PRIORITY_BAND_PRIORITY_REVIEW"],
    }
    assert payload["signal_reference"] == {
        "signal_run_id": "crossfit_seed42_5fold_asof12",
        "signal_version": "prospective_signal_snapshot.v1",
        "signal_as_of_month": 12,
    }
    assert payload["scope"] == {
        "persistence_implemented": False,
        "external_delivery_implemented": False,
        "synthetic_analytics_attached": False,
    }
    assert {"channel", "provider", "webhook", "recipient"}.isdisjoint(payload)


def test_every_transition_pair_is_explicitly_allowed_or_rejected() -> None:
    checked_pairs = 0
    for source_state in ALERT_CASE_STATES:
        case = _case_in_state(source_state)
        for target_state in ALERT_CASE_STATES:
            checked_pairs += 1
            if target_state in ALLOWED_STATE_TRANSITIONS[source_state]:
                moved = case.transition_to(target_state, **_transition_kwargs(target_state))
                assert moved.state == target_state
                assert moved.updated_at == CREATED_AT + timedelta(hours=2)
                assert moved.last_state_change_reason == "TESTED_TRANSITION"
                assert moved.snoozed_until is not None if target_state == "SNOOZED" else moved.snoozed_until is None
                assert moved.case_resolution == "CONTACT_COMPLETED" if target_state == "CLOSED" else moved.case_resolution is None
            else:
                with pytest.raises(ValueError, match="illegal AlertCase transition"):
                    case.transition_to(target_state, **_transition_kwargs(target_state))
    assert checked_pairs == len(ALERT_CASE_STATES) ** 2


def test_required_fields_and_state_specific_requirements_are_rejected() -> None:
    with pytest.raises(ValueError, match="required fields"):
        _new_case(alert_id="")
    with pytest.raises(ValueError, match="must not be before created_at"):
        _new_case(due_at=CREATED_AT - timedelta(seconds=1))
    with pytest.raises(ValueError, match="unique"):
        _new_case(why_now_reason_codes=("CURRENT_STATUS_CONCERNING", "CURRENT_STATUS_CONCERNING"))
    with pytest.raises(ValueError, match="prospective_signal"):
        TimingEvidenceReference("historical_landmark", 12, "not_evaluated")
    with pytest.raises(ValueError, match="retrospective lead-time"):
        TimingEvidenceReference("prospective_signal", 12, "not_evaluated", 3)  # type: ignore[arg-type]

    case = _new_case()
    with pytest.raises(ValueError, match="SNOOZED transitions require"):
        case.transition_to(
            "SNOOZED",
            occurred_at=CREATED_AT + timedelta(hours=1),
            state_change_reason="WAIT",
        )
    with pytest.raises(ValueError, match="CLOSED transitions require"):
        case.transition_to(
            "ACKNOWLEDGED",
            **_transition_kwargs("ACKNOWLEDGED"),
        ).transition_to(
            "CLOSED",
            occurred_at=CREATED_AT + timedelta(hours=3),
            state_change_reason="COMPLETE",
        )
    with pytest.raises(ValueError, match="case_resolution is allowed only"):
        case.transition_to(
            "ACKNOWLEDGED",
            occurred_at=CREATED_AT + timedelta(hours=1),
            state_change_reason="ACK",
            case_resolution="CONTACT_COMPLETED",  # type: ignore[arg-type]
        )


def test_deserialization_rejects_undeclared_delivery_fields_and_invalid_scope() -> None:
    payload = _new_case().to_dict()
    payload["channel"] = "not-allowed"
    with pytest.raises(ValueError, match="keys differ"):
        AlertCase.from_dict(payload)

    scoped_payload = _new_case().to_dict()
    scoped_payload["scope"]["persistence_implemented"] = True  # type: ignore[index]
    with pytest.raises(ValueError, match="scope flags"):
        AlertCase.from_dict(scoped_payload)


def test_module_is_provider_neutral_and_has_no_analytics_label_dependency() -> None:
    source = Path(alert_case.__file__).read_text(encoding="utf-8")
    source_tree = ast.parse(source)
    imported_modules = [
        alias.name
        for node in ast.walk(source_tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    ]
    field_names = {field.name for field in fields(AlertCase)}

    assert "final_outcome" not in source
    assert "persona" not in source
    assert "event_type" not in source
    assert "streamlit" not in source.lower()
    assert not any("notification" in module or "provider" in module for module in imported_modules)
    assert not any("evaluator" in module or "triage_selector" in module for module in imported_modules)
    assert {"channel", "provider", "webhook", "recipient"}.isdisjoint(field_names)
