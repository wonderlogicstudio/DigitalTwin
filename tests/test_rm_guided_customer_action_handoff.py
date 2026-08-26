"""Guided contracts for Customer Review, RM Action, and Activity/Audit handoff."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import app as app_module
from streamlit.testing.v1 import AppTest

from src.rm_guided_workflow import RMGuidedContext, build_rm_guided_workflow_state


def _portfolio() -> dict[str, object]:
    return {
        "available": True,
        "portfolio": {"reconciliation": {"is_exact": True}},
        "queue": {
            "rows": (
                {
                    "customer_id": "C000001",
                    "routing_disposition": "CREATE_NEW_CASE",
                },
            )
        },
    }


def _review(*, case_available: bool = True, case_state: str = "ACKNOWLEDGED") -> dict[str, object]:
    return {
        "available": True,
        "customer_id": "C000001",
        "header": {
            "context_type": "operational_queue",
            "operational_label": "Priority Review",
            "context_label": "Operational review queue",
            "case_state": case_state if case_available else "NO_OPEN_ALERT",
            "due_at": None,
            "selection_reason": "Saved selection reason",
            "why_now": "Current observed signal",
        },
        "workflow_case": {
            "available": case_available,
            "alert_id": "ALT-000001" if case_available else None,
            "state": case_state if case_available else None,
        },
    }


def _valid_history() -> dict[str, object]:
    return {
        "available": True,
        "events": (
            {
                "event_id": "AUD-000001",
                "event_type": "BANKER_ACKNOWLEDGE_REQUESTED",
                "alert_id": "ALT-000001",
                "customer_id": "C000001",
                "operation": "ACKNOWLEDGE",
                "new_state": "ACKNOWLEDGED",
            },
        ),
    }


def test_customer_review_keeps_evidence_order_and_places_customer_acknowledgement_with_it() -> None:
    source = '''\
import streamlit as st
import app

st.session_state["rm_customer_context"] = "C000001"
st.session_state["rm_guided_customer_origin"] = "operational_queue"
review = {
    "customer_id": "C000001",
    "header": {
        "context_type": "operational_queue", "operational_label": "Priority Review",
        "context_label": "Operational review queue", "case_state": "NO_OPEN_ALERT",
        "due_at": None, "selection_reason": "Saved selection reason",
        "why_now": "Current observed signal",
    },
    "provenance": {"policy_id": "policy", "policy_version": "v1", "selection_as_of_month": 12},
    "current_signals": {"available": False, "message": "current unavailable"},
    "chart_trajectory": None,
    "prospective_timing": {"available": False, "message": "timing unavailable"},
    "twin_evidence": {"available": False, "message": "twin unavailable"},
    "historical_landmark": {"status": "not_found", "message": "landmark unavailable", "caption": "retrospective only"},
    "recommended_follow_up": {"available": False, "message": "no automatic action", "whatif_supporting_evidence": {"message": "no What-if"}},
    "workflow_case": {"available": False, "alert_id": None, "state": None},
}
app._render_rm_customer_review(review, language="en", workflow_service=None)
'''
    at = AppTest.from_string(source)
    at.run(timeout=30)

    assert not at.exception
    markdown = [str(item.value) for item in at.markdown]
    selection_index = next(index for index, value in enumerate(markdown) if "Saved selection reason" in value)
    why_now_index = next(index for index, value in enumerate(markdown) if "Current observed signal" in value)
    current_signal_index = next(index for index, value in enumerate(markdown) if "Current Signals" in value)
    assert selection_index < why_now_index < current_signal_index
    assert at.checkbox(key="rm_guided_evidence_acknowledged_C000001_control").label == (
        "Selection Reason and Why Now checked."
    )
    assert not any("Create Case" in str(item.label) for item in at.button)


def test_current_feedback_requires_current_case_customer_state_and_typed_audit_event() -> None:
    history = _valid_history()
    marker = app_module._rm_guided_relevant_action_audit_marker(
        history,
        alert_id="ALT-000001",
        customer_id="C000001",
    )
    feedback = {
        "alert_id": "ALT-000001",
        "customer_id": "C000001",
        "operation": "ACKNOWLEDGE",
        "current_state": "ACKNOWLEDGED",
        "audit_event_id": "AUD-000001",
    }

    accepted = app_module._rm_guided_current_action_feedback(
        feedback,
        alert_id="ALT-000001",
        customer_id="C000001",
        case_state="ACKNOWLEDGED",
        relevant_audit_marker=marker,
    )
    stale_customer = app_module._rm_guided_current_action_feedback(
        {**feedback, "customer_id": "C000002"},
        alert_id="ALT-000001",
        customer_id="C000001",
        case_state="ACKNOWLEDGED",
        relevant_audit_marker=marker,
    )
    stale_event = app_module._rm_guided_relevant_action_audit_marker(
        {
            "available": True,
            "events": ({**history["events"][0], "event_type": "UNVERIFIED"},),
        },
        alert_id="ALT-000001",
        customer_id="C000001",
    )

    assert accepted == {
        "success": True,
        "operation": "ACKNOWLEDGE",
        "audit_event_id": "AUD-000001",
        "current_state": "ACKNOWLEDGED",
    }
    assert stale_customer is None
    assert stale_event["relevant_action"] is False


def test_action_success_or_reloaded_current_audit_advances_only_to_activity_audit() -> None:
    history = _valid_history()
    marker = app_module._rm_guided_relevant_action_audit_marker(
        history,
        alert_id="ALT-000001",
        customer_id="C000001",
    )
    context = RMGuidedContext(
        portfolio_queue_view_model=_portfolio(),
        customer_review_view_model=_review(),
        capacity_acknowledged=True,
        capacity_value=2,
        customer_id="C000001",
        customer_origin="operational_queue",
        current_case_metadata=_review()["workflow_case"],
        activity_audit_metadata=history,
        relevant_audit_marker=marker,
        evidence_acknowledged=True,
    )

    state = build_rm_guided_workflow_state(context)

    assert state.steps[2].status == "COMPLETE"
    assert state.steps[3].status == "COMPLETE"
    assert state.steps[4].status == "CURRENT"
    assert state.current_step_id == "AUDIT_PREVIEW"

    completed = build_rm_guided_workflow_state(replace(context, audit_acknowledged=True))
    assert completed.steps[4].status == "COMPLETE"
    assert completed.current_step_id is None


def test_no_case_service_and_audit_unavailable_have_distinct_safe_blocks() -> None:
    no_case = build_rm_guided_workflow_state(
        RMGuidedContext(
            portfolio_queue_view_model=_portfolio(),
            customer_review_view_model=_review(case_available=False),
            capacity_acknowledged=True,
            capacity_value=2,
            customer_id="C000001",
            customer_origin="operational_queue",
            evidence_acknowledged=True,
        )
    )
    unavailable_service = build_rm_guided_workflow_state(
        RMGuidedContext(
            portfolio_queue_view_model=_portfolio(),
            customer_review_view_model=_review(),
            capacity_acknowledged=True,
            capacity_value=2,
            customer_id="C000001",
            customer_origin="operational_queue",
            evidence_acknowledged=True,
            workflow_service_available=False,
        )
    )
    audit_unavailable = build_rm_guided_workflow_state(
        RMGuidedContext(
            portfolio_queue_view_model=_portfolio(),
            customer_review_view_model=_review(),
            capacity_acknowledged=True,
            capacity_value=2,
            customer_id="C000001",
            customer_origin="operational_queue",
            evidence_acknowledged=True,
            last_banker_operation_metadata={"success": True},
            activity_audit_metadata={"available": False},
        )
    )

    assert no_case.steps[2].status == "COMPLETE"
    assert no_case.steps[3].block_reason_key == "rm.guided.block.no_case"
    assert unavailable_service.steps[3].block_reason_key == "rm.guided.block.service_unavailable"
    assert audit_unavailable.steps[3].status == "COMPLETE"
    assert audit_unavailable.steps[4].block_reason_key == "rm.guided.block.audit_unavailable"


def test_preview_is_visible_only_for_the_current_offline_case_and_customer() -> None:
    preview = {
        "available": True,
        "alert_id": "ALT-000001",
        "customer_id": "C000001",
        "status": "PREVIEW",
        "sent": False,
        "external_delivery_attempted": False,
        "scope": {"case_mutated": False, "audit_mutated": False, "network_called": False},
    }

    assert app_module._rm_guided_preview_matches_current_case(
        preview,
        alert_id="ALT-000001",
        customer_id="C000001",
    )
    assert not app_module._rm_guided_preview_matches_current_case(
        preview,
        alert_id="ALT-000001",
        customer_id="C000002",
    )
    assert not app_module._rm_guided_preview_matches_current_case(
        {**preview, "sent": True},
        alert_id="ALT-000001",
        customer_id="C000001",
    )


def test_customer_switch_clears_evidence_action_audit_and_preview_state() -> None:
    session: dict[str, object] = {
        "rm_customer_context": "C000001",
        "rm_guided_customer_id": "C000001",
        "rm_guided_customer_origin": "operational_queue",
        "rm_guided_evidence_acknowledged_C000001": True,
        "rm_guided_last_action_ref": {"alert_id": "ALT-000001"},
        "rm_guided_audit_acknowledged_ALT-000001": True,
        "rm_notification_preview_result:ALT-000001": {"status": "PREVIEW"},
        "rm_workflow_feedback": {"alert_id": "ALT-000001"},
    }

    assert app_module._apply_rm_guided_customer_handoff(
        session,
        target="C000002",
        origin="operational_queue",
    )

    assert session["rm_customer_context"] == "C000002"
    assert session["rm_guided_customer_origin"] == "operational_queue"
    assert not any(
        key == "rm_guided_last_action_ref"
        or key == "rm_workflow_feedback"
        or key.startswith(
            (
                "rm_guided_evidence_acknowledged_",
                "rm_guided_audit_acknowledged_",
                "rm_notification_preview_result:",
            )
        )
        for key in session
    )
