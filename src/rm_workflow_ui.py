"""Application-facing adapters for RM action, audit, and offline preview UI.

The presentation layer uses this module instead of opening workflow or audit
files. State changes remain exclusively behind ``BankerApplicationService``;
this adapter only selects an explicit existing case operation, reads the
append-only audit history, and renders a provider-neutral offline preview.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal, Mapping
from uuid import NAMESPACE_URL, uuid5

from config import settings
from src.alert_case import AlertCase, AlertCaseState
from src.alert_repository import FileAlertCaseRepository
from src.audit_trail import AuditEvent, AuditEventStore, AuditTrailError, FileAuditEventStore
from src.banker_service import BankerApplicationService, BankerOperationResponse
from src.notifications import (
    NotificationRequest,
    NotificationService,
    PreviewNotificationService,
    build_alert_customer_deep_link,
    NotificationIntent,
)
from src.recommended_followup import CaseOutcome, CaseOutcomeRecord, ClosureReason, RMAction


RM_WORKFLOW_UI_SCHEMA_VERSION = "rm_workflow_ui.v1"
RM_UI_OPERATIONS = (
    "ACKNOWLEDGE",
    "START_REVIEW",
    "SET_FOLLOW_UP",
    "RECORD_ACTION",
    "CLOSE",
    "REOPEN",
)
RMUIOperation = Literal[
    "ACKNOWLEDGE",
    "START_REVIEW",
    "SET_FOLLOW_UP",
    "RECORD_ACTION",
    "CLOSE",
    "REOPEN",
]


@dataclass
class RMWorkflowUIService:
    """A small dependency bundle for one RM Workspace browser session.

    The object intentionally retains the Banker service's in-memory
    idempotency records for one browser session. It has no direct create or
    update method for AlertCase or audit artifacts.
    """

    banker_service: BankerApplicationService
    audit_store: AuditEventStore
    preview_service: NotificationService
    schema_version: str = RM_WORKFLOW_UI_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RM_WORKFLOW_UI_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {RM_WORKFLOW_UI_SCHEMA_VERSION}")


def create_file_backed_rm_workflow_ui_service(
    *,
    workflow_root: Path | None = None,
    audit_root: Path | None = None,
) -> RMWorkflowUIService:
    """Build the P0 session service without writing either backing store.

    Alert creation remains the responsibility of the triage-to-alert cycle.
    Reopening is explicitly supported through the existing Banker service.
    """

    repository = FileAlertCaseRepository(
        Path(workflow_root or (settings.BASE_DIR / "artifacts" / "workflow"))
    )
    audit_store = FileAuditEventStore(
        Path(audit_root or (settings.BASE_DIR / "artifacts" / "audit"))
    )
    return RMWorkflowUIService(
        banker_service=BankerApplicationService(
            repository,
            audit_store=audit_store,
            allow_closed_case_reopen=True,
        ),
        audit_store=audit_store,
        preview_service=PreviewNotificationService(),
    )


def perform_rm_workflow_operation(
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
) -> BankerOperationResponse:
    """Delegate one explicit UI submission to BankerApplicationService only."""

    if operation not in RM_UI_OPERATIONS:
        raise ValueError(f"operation must be one of {RM_UI_OPERATIONS}")
    if not isinstance(occurred_at, datetime) or occurred_at.tzinfo is None:
        raise ValueError("occurred_at must be timezone-aware")
    common: dict[str, Any] = {
        "expected_state": expected_state,
        "occurred_at": occurred_at,
        "actor_reference": actor_reference,
        "idempotency_token": idempotency_token,
    }
    if operation == "ACKNOWLEDGE":
        return service.banker_service.acknowledge(alert_id, **common)
    if operation == "START_REVIEW":
        return service.banker_service.start_review(alert_id, **common)
    if operation == "SET_FOLLOW_UP":
        return service.banker_service.set_follow_up(alert_id, **common)
    if operation == "RECORD_ACTION":
        if action is None:
            raise ValueError("RECORD_ACTION requires an RM action")
        return service.banker_service.record_action(alert_id, action=action, **common)
    if operation == "CLOSE":
        if close_outcome is None or closure_reason is None:
            raise ValueError("CLOSE requires a case outcome and closure reason")
        alert_case = _load_case_for_close(service, alert_id)
        outcome = CaseOutcomeRecord(
            alert_id=alert_case.alert_id,
            customer_id=alert_case.customer_id,
            outcome=close_outcome,
            recorded_at=occurred_at,
            recorded_by=actor_reference,
            closure_reason=closure_reason,
        )
        return service.banker_service.close(alert_id, case_outcome=outcome, **common)
    return service.banker_service.reopen(alert_id, **common)


def build_rm_activity_history(
    service: RMWorkflowUIService,
    *,
    alert_id: str | None = None,
    customer_id: str | None = None,
) -> dict[str, object]:
    """Return one chronological, human-readable append-only event history."""

    try:
        events = service.audit_store.list_events()
    except (AuditTrailError, OSError, ValueError):
        return {
            "available": False,
            "message": "audit_unavailable",
            "events": (),
            "scope": {"audit_file_mutated": False},
        }
    filtered = [
        event
        for event in events
        if (alert_id is None or event.alert_id == alert_id)
        and (customer_id is None or event.customer_id == customer_id)
    ]
    ordered = sorted(filtered, key=lambda event: (event.timestamp, event.sequence, event.event_id))
    return {
        "available": True,
        "message": "ok" if ordered else "no_activity",
        "events": tuple(_activity_event_view(event) for event in ordered),
        "scope": {"audit_file_mutated": False},
    }


def load_rm_workflow_case(
    service: RMWorkflowUIService,
    *,
    alert_id: str,
) -> AlertCase | None:
    """Read one case through the workflow boundary for a UI view model."""

    return service.banker_service.repository.get(alert_id)


def build_offline_notification_preview(
    service: RMWorkflowUIService,
    *,
    alert_case: AlertCase,
) -> dict[str, object]:
    """Capture one deterministic offline preview without changing any case state."""

    material = f"{alert_case.alert_id}|{alert_case.customer_id}|{alert_case.updated_at.isoformat()}"
    identifier = uuid5(NAMESPACE_URL, material).hex.upper()
    request = NotificationRequest(
        request_id=f"NTF-REQUEST-{identifier}",
        requested_at=alert_case.updated_at,
        intent=NotificationIntent(
            intent_id=f"NTF-INTENT-{identifier}",
            alert_id=alert_case.alert_id,
            customer_id=alert_case.customer_id,
            title="RM review preview",
            body=(
                "Offline preview only for an existing RM review case. "
                "It is not sent and does not change the case."
            ),
            deep_link=build_alert_customer_deep_link(
                alert_id=alert_case.alert_id,
                customer_id=alert_case.customer_id,
            ),
        ),
    )
    result = service.preview_service.notify(request)
    if result.status != "PREVIEW" or result.sent or result.external_delivery_attempted:
        raise RuntimeError("P0 notification preview must remain offline and not sent")
    return {
        "available": True,
        "alert_id": alert_case.alert_id,
        "customer_id": alert_case.customer_id,
        "status": result.status,
        "sent": False,
        "external_delivery_attempted": False,
        "title": request.intent.title,
        "body": request.intent.body,
        "deep_link": request.intent.deep_link,
        "captured_preview": result.captured_preview,
        "scope": {
            "case_mutated": False,
            "audit_mutated": False,
            "network_called": False,
            "external_delivery_implemented": False,
        },
    }


def make_submission_token(
    *,
    alert_id: str,
    expected_state: AlertCaseState,
    operation: RMUIOperation,
    action: str | None = None,
    namespace: str = "rm",
) -> str:
    """Return a stable UI retry token for the same intended submission."""

    if not str(namespace).strip():
        raise ValueError("namespace must be non-empty")
    material = "|".join((namespace, alert_id, expected_state, operation, action or ""))
    return "ui-" + sha256(material.encode("utf-8")).hexdigest()[:24]


def utc_now() -> datetime:
    """Keep the time source explicit and easy to inject in focused tests."""

    return datetime.now(timezone.utc)


def _load_case_for_close(service: RMWorkflowUIService, alert_id: str) -> AlertCase:
    repository = service.banker_service.repository
    alert_case = repository.get(alert_id)
    if alert_case is None:
        raise KeyError(f"unknown alert_id: {alert_id}")
    return alert_case


def _activity_event_view(event: AuditEvent) -> Mapping[str, object]:
    metadata = dict(event.metadata)
    operation = str(metadata.get("operation", event.event_type.removeprefix("BANKER_").removesuffix("_REQUESTED")))
    detail = metadata.get("rm_action") or metadata.get("case_outcome") or metadata.get("closure_reason")
    return {
        "sequence": event.sequence,
        "event_id": event.event_id,
        "event_type": event.event_type,
        "alert_id": event.alert_id,
        "customer_id": event.customer_id,
        "timestamp": event.timestamp.isoformat(),
        "operation": operation,
        "actor_reference": event.actor_reference,
        "previous_state": event.previous_state,
        "new_state": event.new_state,
        "detail": detail,
        "policy_version": event.policy_version,
        "signal_version": event.signal_version,
    }
