"""Table-driven contracts for the pure RM guided-workflow state model."""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from src.i18n import t, validate_translation_keys
from src.rm_guided_workflow import (
    RM_GUIDED_STATUS_VALUES,
    RM_GUIDED_STEP_IDS,
    RMGuidedContext,
    build_rm_guided_workflow_state,
)


def _portfolio(*, available: bool = True, exact: bool = True, rows: tuple[dict[str, object], ...] | None = None) -> dict[str, object]:
    return {
        "available": available,
        "portfolio": {"reconciliation": {"is_exact": exact}},
        "queue": {
            "rows": rows
            if rows is not None
            else (
                {
                    "customer_id": "C000001",
                    "routing_disposition": "CREATE_NEW_CASE",
                },
            )
        },
    }


def _review(*, available: bool = True, customer_id: str = "C000001", stale: bool = False) -> dict[str, object]:
    return {
        "available": available,
        "customer_id": customer_id,
        "stale": stale,
        "header": {"context_type": "operational_queue"},
        "workflow_case": {"available": True, "alert_id": "ALT-000001", "state": "IN_REVIEW"},
    }


def _ready_context() -> RMGuidedContext:
    return RMGuidedContext(
        portfolio_queue_view_model=_portfolio(),
        customer_review_view_model=_review(),
        capacity_acknowledged=True,
        capacity_value=12,
        customer_id="C000001",
        customer_origin="operational_queue",
        current_case_metadata={"available": True, "alert_id": "ALT-000001"},
        activity_audit_metadata={"available": True, "events": ()},
        last_banker_operation_metadata={"success": True},
        evidence_acknowledged=True,
    )


def _statuses(context: RMGuidedContext) -> list[str]:
    return [step.status for step in build_rm_guided_workflow_state(context).steps]


@pytest.mark.parametrize(
    ("context", "expected_statuses", "current_step_id", "next_action_key", "block_reason_key"),
    [
        (
            replace(_ready_context(), portfolio_queue_view_model=_portfolio(available=False)),
            ["BLOCKED"] * 5,
            "PORTFOLIO_CAPACITY",
            "rm.guided.next.open_capacity",
            "rm.guided.block.artifact_unavailable",
        ),
        (
            replace(_ready_context(), portfolio_queue_view_model=_portfolio(exact=False)),
            ["BLOCKED"] * 5,
            "PORTFOLIO_CAPACITY",
            "rm.guided.next.open_capacity",
            "rm.guided.block.reconciliation_failed",
        ),
        (
            replace(_ready_context(), capacity_acknowledged=False),
            ["CURRENT", "BLOCKED", "BLOCKED", "BLOCKED", "BLOCKED"],
            "PORTFOLIO_CAPACITY",
            "rm.guided.next.open_capacity",
            None,
        ),
        (
            replace(_ready_context(), portfolio_queue_view_model=_portfolio(rows=())),
            ["COMPLETE", "BLOCKED", "BLOCKED", "BLOCKED", "BLOCKED"],
            "QUEUE_SELECTION",
            "rm.guided.next.select_queue_customer",
            "rm.guided.block.queue_empty",
        ),
        (
            replace(_ready_context(), customer_origin="representative_comparison"),
            ["COMPLETE", "CURRENT", "BLOCKED", "BLOCKED", "BLOCKED"],
            "QUEUE_SELECTION",
            "rm.guided.next.select_queue_customer",
            "rm.guided.block.representative_not_operational",
        ),
        (
            replace(_ready_context(), customer_review_view_model=_review(available=False)),
            ["COMPLETE", "COMPLETE", "BLOCKED", "BLOCKED", "BLOCKED"],
            "CUSTOMER_EVIDENCE_REVIEW",
            "rm.guided.next.review_evidence",
            "rm.guided.block.review_unavailable",
        ),
        (
            replace(_ready_context(), evidence_acknowledged=False),
            ["COMPLETE", "COMPLETE", "CURRENT", "BLOCKED", "BLOCKED"],
            "CUSTOMER_EVIDENCE_REVIEW",
            "rm.guided.next.review_evidence",
            None,
        ),
        (
            replace(_ready_context(), current_case_metadata={"available": False}),
            ["COMPLETE", "COMPLETE", "COMPLETE", "BLOCKED", "BLOCKED"],
            "RM_ACTION",
            "rm.guided.next.record_action",
            "rm.guided.block.no_case",
        ),
        (
            replace(_ready_context(), last_banker_operation_metadata=None),
            ["COMPLETE", "COMPLETE", "COMPLETE", "CURRENT", "BLOCKED"],
            "RM_ACTION",
            "rm.guided.next.record_action",
            None,
        ),
        (
            replace(_ready_context(), activity_audit_metadata={"available": False}),
            ["COMPLETE", "COMPLETE", "COMPLETE", "COMPLETE", "BLOCKED"],
            "AUDIT_PREVIEW",
            "rm.guided.next.review_audit",
            "rm.guided.block.audit_unavailable",
        ),
        (
            _ready_context(),
            ["COMPLETE", "COMPLETE", "COMPLETE", "COMPLETE", "CURRENT"],
            "AUDIT_PREVIEW",
            "rm.guided.next.review_audit",
            None,
        ),
        (
            replace(_ready_context(), audit_acknowledged=True),
            ["COMPLETE"] * 5,
            None,
            None,
            None,
        ),
    ],
)
def test_five_step_status_matrix(
    context: RMGuidedContext,
    expected_statuses: list[str],
    current_step_id: str | None,
    next_action_key: str | None,
    block_reason_key: str | None,
) -> None:
    state = build_rm_guided_workflow_state(context)

    assert [step.step_id for step in state.steps] == list(RM_GUIDED_STEP_IDS)
    assert [step.status for step in state.steps] == expected_statuses
    assert state.current_step_id == current_step_id
    assert state.next_action_key == next_action_key
    assert state.block_reason_key == block_reason_key
    assert state.safe_to_proceed is (expected_statuses == ["COMPLETE"] * 5)


def test_representative_id_never_becomes_operational_solely_because_the_id_matches() -> None:
    state = build_rm_guided_workflow_state(
        replace(_ready_context(), customer_origin="representative_comparison")
    )

    assert state.steps[1].status != "COMPLETE"
    assert state.steps[1].block_reason_key == "rm.guided.block.representative_not_operational"


def test_restored_context_requires_the_same_visible_operational_queue_row() -> None:
    restored = build_rm_guided_workflow_state(
        replace(_ready_context(), customer_origin="restored_operational_context")
    )
    missing = build_rm_guided_workflow_state(
        replace(
            _ready_context(),
            customer_origin="restored_operational_context",
            customer_id="C000099",
        )
    )

    assert restored.steps[1].status == "COMPLETE"
    assert missing.steps[1].status == "BLOCKED"
    assert missing.block_reason_key == "rm.guided.block.queue_customer_not_visible"


def test_capacity_acknowledgement_proves_comparison_only_and_keeps_scope_non_mutating() -> None:
    state = build_rm_guided_workflow_state(_ready_context())

    assert state.steps[0].status == "COMPLETE"
    assert state.capacity_contract == {
        "comparison_only": True,
        "operational_queue_mutated": False,
        "source_ranking_recomputed": False,
        "approved_capacity": False,
    }
    assert state.scope == {
        "analytics_recomputed": False,
        "triage_recomputed": False,
        "capacity_approved": False,
        "queue_mutated": False,
        "case_created": False,
        "repository_mutated": False,
        "future_data_loaded": False,
    }
    unsafe = build_rm_guided_workflow_state(
        replace(_ready_context(), operational_queue_mutated=True)
    )
    assert unsafe.steps[0].status == "BLOCKED"
    assert unsafe.block_reason_key == "rm.guided.block.capacity_contract_invalid"
    assert unsafe.scope["queue_mutated"] is False


def test_relevant_audit_marker_can_confirm_action_without_reinterpreting_preview() -> None:
    state = build_rm_guided_workflow_state(
        replace(
            _ready_context(),
            last_banker_operation_metadata=None,
            relevant_audit_marker={"available": True, "relevant_action": True},
        )
    )

    assert state.steps[3].status == "COMPLETE"
    assert state.steps[4].status == "CURRENT"


def test_preview_seen_is_supporting_state_not_a_send_or_a_completion_condition() -> None:
    before = build_rm_guided_workflow_state(_ready_context())
    seen = build_rm_guided_workflow_state(replace(_ready_context(), preview_seen=True))

    assert [step.status for step in seen.steps] == [step.status for step in before.steps]
    assert seen.preview_seen is True
    assert seen.to_dict()["preview"] == {
        "seen": True,
        "status": "PREVIEW",
        "sent": False,
        "external_delivery_attempted": False,
    }


def test_historical_and_injected_metadata_do_not_change_guided_state() -> None:
    baseline = _ready_context()
    altered_review = {
        **_review(),
        "historical_landmark": {"status": "found", "month": 18},
        "future_event_metadata": {"month": 30, "event_type": "injected"},
    }
    altered = replace(baseline, customer_review_view_model=altered_review)

    assert build_rm_guided_workflow_state(altered).to_dict() == build_rm_guided_workflow_state(
        baseline
    ).to_dict()


def test_state_builder_is_deterministic_and_exposes_all_contract_fields() -> None:
    context = _ready_context()
    first = build_rm_guided_workflow_state(context)
    second = build_rm_guided_workflow_state(context)

    assert first.to_dict() == second.to_dict()
    assert set(RM_GUIDED_STATUS_VALUES) == {
        "COMPLETE",
        "CURRENT",
        "AVAILABLE",
        "BLOCKED",
        "NOT_APPLICABLE",
    }
    for step in first.steps:
        assert step.ordinal in range(1, 6)
        assert step.title_key.startswith("rm.guided.title.")
        assert step.status_key.startswith("rm.guided.status.")
        assert step.completion_message_key.startswith("rm.guided.complete.")
        assert step.next_action_key is not None
        assert step.source_refs
        assert step.target_tab_id


def test_guided_i18n_keys_are_complete_in_korean_and_english() -> None:
    state = build_rm_guided_workflow_state(_ready_context())
    keys = {
        key
        for step in state.steps
        for key in (
            step.title_key,
            step.status_key,
            step.completion_message_key,
            step.next_action_key,
        )
        if key is not None
    }
    keys.update(
        {
            "rm.guided.block.no_case",
            "rm.guided.block.queue_empty",
            "rm.guided.block.artifact_unavailable",
            "rm.guided.block.representative_not_operational",
            "rm.guided.block.review_unavailable",
        }
    )

    assert validate_translation_keys() == []
    for language in ("ko", "en"):
        assert all(t(key, language) != key for key in keys)


def test_guided_module_has_no_ui_analytics_or_write_dependency() -> None:
    import src.rm_guided_workflow as module

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
    assert "run_customer_analysis" not in source
    assert "write_text" not in source
    assert "repository" not in imported_modules
    assert not any(
        marker in imported
        for imported in imported_modules
        for marker in ("matcher", "evaluator", "scorer", "feature", "analytics")
    )
