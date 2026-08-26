"""Pure, display-only state contract for the RM guided workflow.

This module reads already prepared display models and explicit UI metadata.  It
does not import the UI framework, recompute selection, or call a workflow
service.  It only explains the current guided step and its safe boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence


RM_GUIDED_STEP_IDS = (
    "PORTFOLIO_CAPACITY",
    "QUEUE_SELECTION",
    "CUSTOMER_EVIDENCE_REVIEW",
    "RM_ACTION",
    "AUDIT_PREVIEW",
)
RM_GUIDED_STATUS_VALUES = (
    "COMPLETE",
    "CURRENT",
    "AVAILABLE",
    "BLOCKED",
    "NOT_APPLICABLE",
)
RM_GUIDED_CUSTOMER_ORIGINS = (
    "operational_queue",
    "representative_comparison",
    "none",
    "restored_operational_context",
)

_STEP_SPECS = (
    (
        "PORTFOLIO_CAPACITY",
        1,
        "rm.guided.title.portfolio_capacity",
        "rm.guided.complete.portfolio_capacity",
        "rm.guided.next.open_capacity",
        "portfolio_capacity",
        False,
        ("portfolio.reconciliation", "capacity.comparison"),
    ),
    (
        "QUEUE_SELECTION",
        2,
        "rm.guided.title.queue_selection",
        "rm.guided.complete.queue_selection",
        "rm.guided.next.select_queue_customer",
        "queue_selection",
        True,
        ("queue.visible_operational_row",),
    ),
    (
        "CUSTOMER_EVIDENCE_REVIEW",
        3,
        "rm.guided.title.customer_evidence_review",
        "rm.guided.complete.customer_evidence_review",
        "rm.guided.next.review_evidence",
        "customer_evidence_review",
        True,
        ("customer_review.selection_reason", "customer_review.why_now"),
    ),
    (
        "RM_ACTION",
        4,
        "rm.guided.title.rm_action",
        "rm.guided.complete.rm_action",
        "rm.guided.next.record_action",
        "rm_action",
        True,
        ("workflow_case", "banker_operation", "activity_audit"),
    ),
    (
        "AUDIT_PREVIEW",
        5,
        "rm.guided.title.audit_preview",
        "rm.guided.complete.audit_preview",
        "rm.guided.next.review_audit",
        "audit_preview",
        True,
        ("activity_audit", "offline_preview"),
    ),
)
_SCOPE_PROOF = {
    "analytics_recomputed": False,
    "triage_recomputed": False,
    "capacity_approved": False,
    "queue_mutated": False,
    "case_created": False,
    "repository_mutated": False,
    "future_data_loaded": False,
}


@dataclass(frozen=True)
class RMGuidedContext:
    """Inputs already prepared by existing display models and UI state."""

    portfolio_queue_view_model: Mapping[str, object] | None = None
    customer_review_view_model: Mapping[str, object] | None = None
    capacity_acknowledged: bool = False
    capacity_value: int | None = None
    capacity_comparison_only: bool = True
    operational_queue_mutated: bool = False
    source_ranking_recomputed: bool = False
    approved_capacity: bool = False
    customer_id: str | None = None
    customer_origin: str = "none"
    workflow_service_available: bool = True
    current_case_metadata: Mapping[str, object] | None = None
    activity_audit_metadata: Mapping[str, object] | None = None
    last_banker_operation_metadata: Mapping[str, object] | None = None
    relevant_audit_marker: Mapping[str, object] | None = None
    evidence_acknowledged: bool = False
    audit_acknowledged: bool = False
    preview_seen: bool = False


@dataclass(frozen=True)
class RMGuidedStep:
    """One localized-key step card for the guided shell."""

    step_id: str
    ordinal: int
    title_key: str
    status: str
    status_key: str
    completion_message_key: str
    next_action_key: str | None
    block_reason_key: str | None
    source_refs: tuple[str, ...]
    safe_to_proceed: bool
    target_tab_id: str
    operational: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "step_id": self.step_id,
            "ordinal": self.ordinal,
            "title_key": self.title_key,
            "status": self.status,
            "status_key": self.status_key,
            "completion_message_key": self.completion_message_key,
            "next_action_key": self.next_action_key,
            "block_reason_key": self.block_reason_key,
            "source_refs": self.source_refs,
            "safe_to_proceed": self.safe_to_proceed,
            "target_tab_id": self.target_tab_id,
            "operational": self.operational,
        }


@dataclass(frozen=True)
class RMGuidedWorkflowState:
    """A deterministic, non-persisted description of the five workflow steps."""

    steps: tuple[RMGuidedStep, ...]
    current_step_id: str | None
    next_action_key: str | None
    block_reason_key: str | None
    safe_to_proceed: bool
    scope: Mapping[str, bool]
    capacity_contract: Mapping[str, bool]
    preview_seen: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "steps": tuple(step.to_dict() for step in self.steps),
            "current_step_id": self.current_step_id,
            "next_action_key": self.next_action_key,
            "block_reason_key": self.block_reason_key,
            "safe_to_proceed": self.safe_to_proceed,
            "scope": dict(self.scope),
            "capacity_contract": dict(self.capacity_contract),
            "preview": {
                "seen": self.preview_seen,
                "status": "PREVIEW",
                "sent": False,
                "external_delivery_attempted": False,
            },
        }


def build_rm_guided_workflow_state(context: RMGuidedContext) -> RMGuidedWorkflowState:
    """Build the five-step display state without changing any input or artifact."""

    capacity_contract = _capacity_contract(context)
    if not _artifact_available(context.portfolio_queue_view_model):
        return _blocked_from(
            context,
            capacity_contract,
            step_index=0,
            block_reason_key="rm.guided.block.artifact_unavailable",
        )
    if not _artifact_reconciles(context.portfolio_queue_view_model):
        return _blocked_from(
            context,
            capacity_contract,
            step_index=0,
            block_reason_key="rm.guided.block.reconciliation_failed",
        )
    if not _capacity_contract_is_safe(capacity_contract):
        return _blocked_from(
            context,
            capacity_contract,
            step_index=0,
            block_reason_key="rm.guided.block.capacity_contract_invalid",
        )
    if not _capacity_is_acknowledged(context):
        return _current_with_downstream_blocked(
            context,
            capacity_contract,
            step_index=0,
            block_reason_key=None,
        )

    completed = [_step(0, "COMPLETE", safe_to_proceed=True)]
    if _queue_rows(context.portfolio_queue_view_model) == ():
        return _blocked_after(
            context,
            capacity_contract,
            completed,
            step_index=1,
            block_reason_key="rm.guided.block.queue_empty",
        )
    origin = _normalized_origin(context.customer_origin)
    if origin == "representative_comparison":
        return _current_after(
            context,
            capacity_contract,
            completed,
            step_index=1,
            block_reason_key="rm.guided.block.representative_not_operational",
        )
    if origin == "none":
        return _current_after(context, capacity_contract, completed, step_index=1, block_reason_key=None)
    if origin is None:
        return _blocked_after(
            context,
            capacity_contract,
            completed,
            step_index=1,
            block_reason_key="rm.guided.block.customer_origin_invalid",
        )
    if not _is_visible_operational_customer(context, origin):
        return _blocked_after(
            context,
            capacity_contract,
            completed,
            step_index=1,
            block_reason_key="rm.guided.block.queue_customer_not_visible",
        )

    completed.append(_step(1, "COMPLETE", safe_to_proceed=True))
    if not _review_available(context):
        return _blocked_after(
            context,
            capacity_contract,
            completed,
            step_index=2,
            block_reason_key="rm.guided.block.review_unavailable",
        )
    if context.evidence_acknowledged is not True:
        return _current_after(context, capacity_contract, completed, step_index=2, block_reason_key=None)

    completed.append(_step(2, "COMPLETE", safe_to_proceed=True))
    if not _case_available(context):
        return _blocked_after(
            context,
            capacity_contract,
            completed,
            step_index=3,
            block_reason_key="rm.guided.block.no_case",
        )
    if context.workflow_service_available is not True:
        return _blocked_after(
            context,
            capacity_contract,
            completed,
            step_index=3,
            block_reason_key="rm.guided.block.service_unavailable",
        )
    if not _action_or_audit_confirms_action(context):
        return _current_after(context, capacity_contract, completed, step_index=3, block_reason_key=None)

    completed.append(_step(3, "COMPLETE", safe_to_proceed=True))
    if not _audit_available(context.activity_audit_metadata):
        return _blocked_after(
            context,
            capacity_contract,
            completed,
            step_index=4,
            block_reason_key="rm.guided.block.audit_unavailable",
        )
    if context.audit_acknowledged is not True:
        return _current_after(context, capacity_contract, completed, step_index=4, block_reason_key=None)

    completed.append(_step(4, "COMPLETE", safe_to_proceed=True))
    return RMGuidedWorkflowState(
        steps=tuple(completed),
        current_step_id=None,
        next_action_key=None,
        block_reason_key=None,
        safe_to_proceed=True,
        scope=dict(_SCOPE_PROOF),
        capacity_contract=capacity_contract,
        preview_seen=context.preview_seen is True,
    )


def _artifact_available(model: Mapping[str, object] | None) -> bool:
    return isinstance(model, Mapping) and model.get("available") is True


def _artifact_reconciles(model: Mapping[str, object] | None) -> bool:
    portfolio = model.get("portfolio") if isinstance(model, Mapping) else None
    reconciliation = portfolio.get("reconciliation") if isinstance(portfolio, Mapping) else None
    return isinstance(reconciliation, Mapping) and reconciliation.get("is_exact") is True


def _capacity_contract(context: RMGuidedContext) -> dict[str, bool]:
    return {
        "comparison_only": context.capacity_comparison_only is True,
        "operational_queue_mutated": context.operational_queue_mutated is True,
        "source_ranking_recomputed": context.source_ranking_recomputed is True,
        "approved_capacity": context.approved_capacity is True,
    }


def _capacity_contract_is_safe(contract: Mapping[str, bool]) -> bool:
    return (
        contract["comparison_only"] is True
        and contract["operational_queue_mutated"] is False
        and contract["source_ranking_recomputed"] is False
        and contract["approved_capacity"] is False
    )


def _capacity_is_acknowledged(context: RMGuidedContext) -> bool:
    return (
        context.capacity_acknowledged is True
        and isinstance(context.capacity_value, int)
        and not isinstance(context.capacity_value, bool)
        and context.capacity_value >= 0
    )


def _queue_rows(model: Mapping[str, object] | None) -> tuple[Mapping[str, object], ...]:
    queue = model.get("queue") if isinstance(model, Mapping) else None
    rows = queue.get("rows") if isinstance(queue, Mapping) else None
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return ()
    return tuple(row for row in rows if isinstance(row, Mapping))


def _normalized_origin(origin: str) -> str | None:
    return origin if origin in RM_GUIDED_CUSTOMER_ORIGINS else None


def _is_visible_operational_customer(context: RMGuidedContext, origin: str) -> bool:
    if origin not in {"operational_queue", "restored_operational_context"}:
        return False
    customer_id = context.customer_id
    if not isinstance(customer_id, str) or not customer_id:
        return False
    return any(
        row.get("customer_id") == customer_id
        and row.get("routing_disposition") in {"CREATE_NEW_CASE", "ROUTE_EXISTING_CASE"}
        for row in _queue_rows(context.portfolio_queue_view_model)
    )


def _review_available(context: RMGuidedContext) -> bool:
    review = context.customer_review_view_model
    if not isinstance(review, Mapping) or review.get("available") is not True:
        return False
    if review.get("customer_id") != context.customer_id:
        return False
    if any(review.get(key) is True for key in ("stale", "source_stale", "is_stale")):
        return False
    header = review.get("header")
    return isinstance(header, Mapping) and header.get("context_type") == "operational_queue"


def _case_available(context: RMGuidedContext) -> bool:
    metadata = context.current_case_metadata
    if metadata is None and isinstance(context.customer_review_view_model, Mapping):
        candidate = context.customer_review_view_model.get("workflow_case")
        metadata = candidate if isinstance(candidate, Mapping) else None
    return isinstance(metadata, Mapping) and metadata.get("available") is True


def _action_or_audit_confirms_action(context: RMGuidedContext) -> bool:
    operation = context.last_banker_operation_metadata
    if isinstance(operation, Mapping) and (
        operation.get("success") is True or operation.get("applied") is True
    ):
        return True
    marker = context.relevant_audit_marker
    return (
        isinstance(marker, Mapping)
        and marker.get("available") is True
        and marker.get("relevant_action") is True
    )


def _audit_available(metadata: Mapping[str, object] | None) -> bool:
    return isinstance(metadata, Mapping) and metadata.get("available") is True


def _step(
    step_index: int,
    status: str,
    *,
    safe_to_proceed: bool,
    block_reason_key: str | None = None,
) -> RMGuidedStep:
    step_id, ordinal, title_key, completion_key, next_key, target_tab_id, operational, source_refs = _STEP_SPECS[
        step_index
    ]
    return RMGuidedStep(
        step_id=step_id,
        ordinal=ordinal,
        title_key=title_key,
        status=status,
        status_key=f"rm.guided.status.{status.lower()}",
        completion_message_key=completion_key,
        next_action_key=next_key,
        block_reason_key=block_reason_key,
        source_refs=source_refs,
        safe_to_proceed=safe_to_proceed,
        target_tab_id=target_tab_id,
        operational=operational,
    )


def _blocked_from(
    context: RMGuidedContext,
    capacity_contract: Mapping[str, bool],
    *,
    step_index: int,
    block_reason_key: str,
) -> RMGuidedWorkflowState:
    steps = [_step(index, "BLOCKED", safe_to_proceed=False, block_reason_key=block_reason_key if index == step_index else "rm.guided.block.upstream_blocked") for index in range(len(_STEP_SPECS))]
    return _state_from_steps(context, capacity_contract, steps, step_index)


def _blocked_after(
    context: RMGuidedContext,
    capacity_contract: Mapping[str, bool],
    completed: list[RMGuidedStep],
    *,
    step_index: int,
    block_reason_key: str,
) -> RMGuidedWorkflowState:
    steps = [
        *completed,
        _step(step_index, "BLOCKED", safe_to_proceed=False, block_reason_key=block_reason_key),
        *(
            _step(index, "BLOCKED", safe_to_proceed=False, block_reason_key="rm.guided.block.upstream_blocked")
            for index in range(step_index + 1, len(_STEP_SPECS))
        ),
    ]
    return _state_from_steps(context, capacity_contract, steps, step_index)


def _current_with_downstream_blocked(
    context: RMGuidedContext,
    capacity_contract: Mapping[str, bool],
    *,
    step_index: int,
    block_reason_key: str | None,
) -> RMGuidedWorkflowState:
    return _current_after(
        context,
        capacity_contract,
        [],
        step_index=step_index,
        block_reason_key=block_reason_key,
    )


def _current_after(
    context: RMGuidedContext,
    capacity_contract: Mapping[str, bool],
    completed: list[RMGuidedStep],
    *,
    step_index: int,
    block_reason_key: str | None,
) -> RMGuidedWorkflowState:
    steps = [
        *completed,
        _step(step_index, "CURRENT", safe_to_proceed=False, block_reason_key=block_reason_key),
        *(
            _step(index, "BLOCKED", safe_to_proceed=False, block_reason_key="rm.guided.block.prerequisite_incomplete")
            for index in range(step_index + 1, len(_STEP_SPECS))
        ),
    ]
    return _state_from_steps(context, capacity_contract, steps, step_index)


def _state_from_steps(
    context: RMGuidedContext,
    capacity_contract: Mapping[str, bool],
    steps: Sequence[RMGuidedStep],
    current_index: int,
) -> RMGuidedWorkflowState:
    current = steps[current_index]
    return RMGuidedWorkflowState(
        steps=tuple(steps),
        current_step_id=current.step_id,
        next_action_key=current.next_action_key,
        block_reason_key=current.block_reason_key,
        safe_to_proceed=False,
        scope=dict(_SCOPE_PROOF),
        capacity_contract=dict(capacity_contract),
        preview_seen=context.preview_seen is True,
    )
