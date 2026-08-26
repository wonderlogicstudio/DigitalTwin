"""Application-facing state and view model for the isolated workflow demo.

The module intentionally does not import Streamlit.  It owns only the
``rm_workflow_demo_*`` session namespace and delegates any explicit runtime
initialization to the isolated fixture contract from :mod:`src.workflow_demo`.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Mapping

from src.alert_case import AlertCase, AlertCaseState
from src.rm_workflow_ui import (
    RMUIOperation,
    RMWorkflowUIService,
    create_file_backed_rm_workflow_ui_service,
    perform_rm_workflow_operation,
)
from src.recommended_followup import CaseOutcome, ClosureReason, RMAction
from src.workflow_demo import (
    WorkflowDemoError,
    WorkflowDemoFixture,
    WorkflowDemoPaths,
    WorkflowDemoRuntimeSnapshot,
    load_demo_fixture,
    load_demo_runtime,
    reset_demo,
)


WORKFLOW_DEMO_SESSION_PREFIX = "rm_workflow_demo_"
WORKFLOW_DEMO_OPEN_KEY = f"{WORKFLOW_DEMO_SESSION_PREFIX}open"
WORKFLOW_DEMO_SELECTED_ALERT_KEY = f"{WORKFLOW_DEMO_SESSION_PREFIX}selected_alert_id"
WORKFLOW_DEMO_RESET_ERROR_KEY = f"{WORKFLOW_DEMO_SESSION_PREFIX}reset_error"
WORKFLOW_DEMO_SERVICE_KEY = f"{WORKFLOW_DEMO_SESSION_PREFIX}service"
WORKFLOW_DEMO_PATHS_KEY = f"{WORKFLOW_DEMO_SESSION_PREFIX}paths"
WORKFLOW_DEMO_FEEDBACK_KEY = f"{WORKFLOW_DEMO_SESSION_PREFIX}feedback"
WORKFLOW_DEMO_PREVIEW_KEY = f"{WORKFLOW_DEMO_SESSION_PREFIX}preview"
WORKFLOW_DEMO_SESSION_KEYS = frozenset(
    {
        WORKFLOW_DEMO_OPEN_KEY,
        WORKFLOW_DEMO_SELECTED_ALERT_KEY,
        WORKFLOW_DEMO_RESET_ERROR_KEY,
        WORKFLOW_DEMO_SERVICE_KEY,
        WORKFLOW_DEMO_PATHS_KEY,
        WORKFLOW_DEMO_FEEDBACK_KEY,
        WORKFLOW_DEMO_PREVIEW_KEY,
    }
)

WorkflowDemoShellStatus = Literal[
    "DEMO_NOT_INITIALIZED",
    "DEMO_READY",
    "DEMO_FIXTURE_UNAVAILABLE",
    "DEMO_CORRUPT",
    "DEMO_STALE_SELECTION",
]


class WorkflowDemoStaleServiceError(RuntimeError):
    """An action attempted to use a service invalidated by demo reset/exit."""


@dataclass(frozen=True)
class WorkflowDemoShell:
    """Display-only state for the secondary RM workflow-demo context."""

    status: WorkflowDemoShellStatus
    fixture: WorkflowDemoFixture | None
    snapshot: WorkflowDemoRuntimeSnapshot | None
    cases: tuple[AlertCase, ...]
    selected_alert_id: str | None
    selected_case: AlertCase | None
    detail: str | None = None

    @property
    def is_ready(self) -> bool:
        return self.status == "DEMO_READY"


def is_workflow_demo_open(session_state: Mapping[str, object]) -> bool:
    """Return whether this session explicitly entered the demo context."""

    return session_state.get(WORKFLOW_DEMO_OPEN_KEY) is True


def enter_workflow_demo(session_state: MutableMapping[str, Any]) -> None:
    """Enter without loading, initializing, or resetting any runtime files."""

    _clear_workflow_demo_session(session_state, retain_open=False)
    session_state[WORKFLOW_DEMO_OPEN_KEY] = True


def exit_workflow_demo(session_state: MutableMapping[str, Any]) -> None:
    """Leave only the secondary demo context; default RM state is untouched."""

    _clear_workflow_demo_session(session_state, retain_open=False)


def prepare_workflow_demo_reset(session_state: MutableMapping[str, Any]) -> None:
    """Clear demo-local selection/feedback while retaining explicit entry."""

    _clear_workflow_demo_session(session_state, retain_open=True)
    session_state[WORKFLOW_DEMO_OPEN_KEY] = True


def load_workflow_demo_shell(
    *,
    paths: WorkflowDemoPaths | None = None,
    selected_alert_id: str | None = None,
) -> WorkflowDemoShell:
    """Read only the isolated fixture/runtime; no default-repository fallback."""

    resolved_paths = paths or WorkflowDemoPaths.default()
    try:
        fixture = load_demo_fixture(resolved_paths)
    except WorkflowDemoError as error:
        return WorkflowDemoShell(
            status="DEMO_FIXTURE_UNAVAILABLE",
            fixture=None,
            snapshot=None,
            cases=(),
            selected_alert_id=None,
            selected_case=None,
            detail=str(error),
        )
    snapshot = load_demo_runtime(resolved_paths)
    if snapshot.status != "DEMO_READY":
        return WorkflowDemoShell(
            status=snapshot.status,
            fixture=fixture,
            snapshot=snapshot,
            cases=(),
            selected_alert_id=None,
            selected_case=None,
            detail=snapshot.detail,
        )
    cases = snapshot.cases
    if len(cases) > 3:
        return WorkflowDemoShell(
            status="DEMO_CORRUPT",
            fixture=fixture,
            snapshot=snapshot,
            cases=(),
            selected_alert_id=None,
            selected_case=None,
            detail="workflow-demo runtime exceeds the maximum case count",
        )
    case_by_id = {case.alert_id: case for case in cases}
    requested = str(selected_alert_id).strip() if selected_alert_id else ""
    if requested and requested not in case_by_id:
        return WorkflowDemoShell(
            status="DEMO_STALE_SELECTION",
            fixture=fixture,
            snapshot=snapshot,
            cases=cases,
            selected_alert_id=requested,
            selected_case=None,
            detail="the selected demo case is no longer present in the isolated runtime",
        )
    active_alert_id = requested or (cases[0].alert_id if cases else None)
    return WorkflowDemoShell(
        status="DEMO_READY",
        fixture=fixture,
        snapshot=snapshot,
        cases=cases,
        selected_alert_id=active_alert_id,
        selected_case=None if active_alert_id is None else case_by_id[active_alert_id],
    )


def initialize_or_reset_workflow_demo(
    *,
    paths: WorkflowDemoPaths | None = None,
) -> WorkflowDemoShell:
    """Explicitly create/reset only the isolated demo runtime."""

    resolved_paths = paths or WorkflowDemoPaths.default()
    try:
        snapshot = reset_demo(resolved_paths)
    except WorkflowDemoError as error:
        return WorkflowDemoShell(
            status="DEMO_CORRUPT",
            fixture=None,
            snapshot=None,
            cases=(),
            selected_alert_id=None,
            selected_case=None,
            detail=str(error),
        )
    return load_workflow_demo_shell(paths=resolved_paths, selected_alert_id=(snapshot.cases[0].alert_id if snapshot.cases else None))


def get_workflow_demo_ui_service(
    session_state: MutableMapping[str, Any],
    *,
    paths: WorkflowDemoPaths | None = None,
) -> RMWorkflowUIService | None:
    """Return a session-local service backed only by an initialized demo runtime.

    The caller must explicitly initialize the tiny synthetic runtime first.
    This function never substitutes the default RM workflow or audit roots and
    keeps the Banker service's retry ledger within the demo session namespace.
    """

    resolved_paths = paths or WorkflowDemoPaths.default()
    snapshot = load_demo_runtime(resolved_paths)
    if not snapshot.is_ready:
        return None
    existing = session_state.get(WORKFLOW_DEMO_SERVICE_KEY)
    if isinstance(existing, RMWorkflowUIService):
        return existing
    service = create_file_backed_rm_workflow_ui_service(
        workflow_root=resolved_paths.workflow_root,
        audit_root=resolved_paths.audit_root,
    )
    session_state[WORKFLOW_DEMO_SERVICE_KEY] = service
    session_state[WORKFLOW_DEMO_PATHS_KEY] = resolved_paths
    return service


def perform_workflow_demo_operation(
    session_state: Mapping[str, object],
    service: RMWorkflowUIService,
    *,
    operation: RMUIOperation,
    alert_id: str,
    expected_state: AlertCaseState,
    occurred_at: datetime,
    actor_reference: str,
    idempotency_token: str,
    action: RMAction | None = None,
    close_outcome: CaseOutcome | None = None,
    closure_reason: ClosureReason | None = None,
    paths: WorkflowDemoPaths | None = None,
) -> object:
    """Run a Banker operation only for the current isolated demo service.

    Reset and exit remove the service object from the demo session namespace.
    A stale Streamlit callback therefore fails before it can reach the
    repository. The underlying operation remains the existing application
    adapter; this wrapper adds only demo-context freshness validation.
    """

    session_paths = session_state.get(WORKFLOW_DEMO_PATHS_KEY)
    resolved_paths = (
        paths
        or (session_paths if isinstance(session_paths, WorkflowDemoPaths) else None)
        or WorkflowDemoPaths.default()
    )
    if session_state.get(WORKFLOW_DEMO_SERVICE_KEY) is not service:
        raise WorkflowDemoStaleServiceError(
            "workflow-demo service is stale after reset, exit, or replacement"
        )
    if not load_demo_runtime(resolved_paths).is_ready:
        raise WorkflowDemoStaleServiceError("workflow-demo runtime is not ready")
    return perform_rm_workflow_operation(
        service,
        operation=operation,
        alert_id=alert_id,
        expected_state=expected_state,
        occurred_at=occurred_at,
        actor_reference=actor_reference,
        idempotency_token=idempotency_token,
        action=action,
        close_outcome=close_outcome,
        closure_reason=closure_reason,
    )


def _clear_workflow_demo_session(
    session_state: MutableMapping[str, Any],
    *,
    retain_open: bool,
) -> None:
    """Clear only reserved demo keys; never touch RM/default customer state."""

    for key in tuple(session_state):
        if not isinstance(key, str) or not key.startswith(WORKFLOW_DEMO_SESSION_PREFIX):
            continue
        if retain_open and key == WORKFLOW_DEMO_OPEN_KEY:
            continue
        session_state.pop(key, None)
