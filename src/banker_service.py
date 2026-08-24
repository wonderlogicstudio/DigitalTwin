"""Application service for human RM operations on an AlertCase repository.

This is the only workflow boundary intended for a future UI.  It accepts
explicit expected state and idempotency inputs, returns an operation response,
and delegates persistence to the injected repository.  It does not perform
financial decisions, analytical computation, or external delivery.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Callable, Literal
from uuid import NAMESPACE_URL, uuid5

from src.alert_case import AlertCase, AlertCaseState, CaseResolution, create_alert_case
from src.alert_repository import AlertCaseRepository, AlertCaseRepositoryConflictError
from src.audit_trail import AuditEvent, AuditEventStore, build_banker_audit_event
from src.recommended_followup import CaseOutcomeRecord, RMAction, RMActionRecord


BANKER_SERVICE_SCHEMA_VERSION = "banker_application_service.v1"
BANKER_OPERATIONS = (
    "ACKNOWLEDGE",
    "START_REVIEW",
    "SET_FOLLOW_UP",
    "RECORD_ACTION",
    "CLOSE",
    "REOPEN",
)

BankerOperation = Literal[
    "ACKNOWLEDGE",
    "START_REVIEW",
    "SET_FOLLOW_UP",
    "RECORD_ACTION",
    "CLOSE",
    "REOPEN",
]

_CLOSURE_TO_RESOLUTION: dict[str, CaseResolution] = {
    "REVIEW_COMPLETE_NO_FURTHER_ACTION": "RESOLVED_NO_ACTION",
    "CONTACT_COMPLETED": "CONTACT_COMPLETED",
    "REFERRED_TO_SPECIALIST": "REFERRED",
    "DUPLICATE_OR_SUPERSEDED": "DUPLICATE_OR_SUPERSEDED",
    "UNRESOLVED": "UNRESOLVED",
}


class BankerServiceError(RuntimeError):
    """Base error for explicit BankerApplicationService failures."""


class BankerStateConflictError(BankerServiceError):
    """The case does not have the state the submitter expected."""


class BankerIdempotencyConflictError(BankerServiceError):
    """A token was reused for a different operation payload."""


@dataclass(frozen=True)
class BankerOperationResponse:
    """One complete operation result for the future UI boundary."""

    operation: BankerOperation
    idempotency_token: str
    previous_state: AlertCaseState
    alert_case: AlertCase
    action_record: RMActionRecord | None
    case_outcome: CaseOutcomeRecord | None
    audit_event: AuditEvent
    reopened_from_alert_id: str | None = None
    idempotent_replay: bool = False
    schema_version: str = BANKER_SERVICE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.operation not in BANKER_OPERATIONS:
            raise ValueError(f"operation must be one of {BANKER_OPERATIONS}")
        if not str(self.idempotency_token).strip():
            raise ValueError("idempotency_token must be non-empty")
        if self.previous_state not in {
            "NEW",
            "ACKNOWLEDGED",
            "IN_REVIEW",
            "FOLLOW_UP",
            "SNOOZED",
            "ESCALATED",
            "CLOSED",
        }:
            raise ValueError("previous_state is invalid")
        if self.operation == "RECORD_ACTION" and self.action_record is None:
            raise ValueError("RECORD_ACTION requires action_record")
        if self.audit_event.alert_id != self.alert_case.alert_id:
            raise ValueError("audit_event must identify alert_case")
        if self.operation == "CLOSE":
            if self.alert_case.state != "CLOSED" or self.case_outcome is None:
                raise ValueError("CLOSE requires a CLOSED case and case_outcome")
        if self.operation == "REOPEN":
            if self.previous_state != "CLOSED" or self.alert_case.state != "NEW":
                raise ValueError("REOPEN must create a NEW case from a CLOSED case")
            if not str(self.reopened_from_alert_id or "").strip():
                raise ValueError("REOPEN requires reopened_from_alert_id")
        if self.schema_version != BANKER_SERVICE_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {BANKER_SERVICE_SCHEMA_VERSION}")

    @property
    def current_state(self) -> AlertCaseState:
        return self.alert_case.state

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "operation": self.operation,
            "idempotency_token": self.idempotency_token,
            "previous_state": self.previous_state,
            "current_state": self.current_state,
            "alert_case": self.alert_case.to_dict(),
            "action_record": None if self.action_record is None else self.action_record.to_dict(),
            "case_outcome": None if self.case_outcome is None else self.case_outcome.to_dict(),
            "audit_event": self.audit_event.to_dict(),
            "reopened_from_alert_id": self.reopened_from_alert_id,
            "idempotent_replay": self.idempotent_replay,
            "scope": {
                "ui_direct_repository_write": False,
                "financial_decision_automated": False,
                "external_delivery_implemented": False,
            },
        }


class BankerApplicationService:
    """Consistent RM state/action boundary over an injected AlertCase repository."""

    def __init__(
        self,
        repository: AlertCaseRepository,
        *,
        audit_store: AuditEventStore,
        allow_closed_case_reopen: bool = False,
        reopen_due_in_hours: int = 24,
    ) -> None:
        if not isinstance(allow_closed_case_reopen, bool):
            raise ValueError("allow_closed_case_reopen must be a bool")
        if isinstance(reopen_due_in_hours, bool) or not isinstance(reopen_due_in_hours, int):
            raise ValueError("reopen_due_in_hours must be an integer")
        if reopen_due_in_hours < 0:
            raise ValueError("reopen_due_in_hours must be non-negative")
        self.repository = repository
        self.audit_store = audit_store
        self.allow_closed_case_reopen = allow_closed_case_reopen
        self.reopen_due_in_hours = reopen_due_in_hours
        self._idempotency: dict[str, tuple[str, BankerOperationResponse]] = {}

    def acknowledge(
        self,
        alert_id: str,
        *,
        expected_state: AlertCaseState,
        occurred_at: datetime,
        actor_reference: str,
        idempotency_token: str,
    ) -> BankerOperationResponse:
        """Acknowledge a newly created case."""

        return self._transition(
            operation="ACKNOWLEDGE",
            alert_id=alert_id,
            expected_state=expected_state,
            required_state="NEW",
            target_state="ACKNOWLEDGED",
            occurred_at=occurred_at,
            actor_reference=actor_reference,
            idempotency_token=idempotency_token,
        )

    def start_review(
        self,
        alert_id: str,
        *,
        expected_state: AlertCaseState,
        occurred_at: datetime,
        actor_reference: str,
        idempotency_token: str,
    ) -> BankerOperationResponse:
        """Move an acknowledged case into human review."""

        return self._transition(
            operation="START_REVIEW",
            alert_id=alert_id,
            expected_state=expected_state,
            required_state="ACKNOWLEDGED",
            target_state="IN_REVIEW",
            occurred_at=occurred_at,
            actor_reference=actor_reference,
            idempotency_token=idempotency_token,
        )

    def set_follow_up(
        self,
        alert_id: str,
        *,
        expected_state: AlertCaseState,
        occurred_at: datetime,
        actor_reference: str,
        idempotency_token: str,
    ) -> BankerOperationResponse:
        """Record that an in-review case needs a human follow-up."""

        return self._transition(
            operation="SET_FOLLOW_UP",
            alert_id=alert_id,
            expected_state=expected_state,
            required_state="IN_REVIEW",
            target_state="FOLLOW_UP",
            occurred_at=occurred_at,
            actor_reference=actor_reference,
            idempotency_token=idempotency_token,
        )

    def record_action(
        self,
        alert_id: str,
        *,
        expected_state: AlertCaseState,
        action: RMAction,
        occurred_at: datetime,
        actor_reference: str,
        idempotency_token: str,
        note: str | None = None,
    ) -> BankerOperationResponse:
        """Return one staff action record without silently changing case state."""

        fingerprint = _fingerprint(
            "RECORD_ACTION",
            alert_id,
            expected_state,
            action,
            occurred_at,
            actor_reference,
            note,
        )
        _validate_actor_reference(actor_reference)

        def operation() -> BankerOperationResponse:
            current = self._load_expected(alert_id, expected_state)
            if current.state == "CLOSED":
                raise BankerStateConflictError("cannot record an RM action for a CLOSED AlertCase")
            record = RMActionRecord(
                alert_id=current.alert_id,
                action=action,
                recorded_at=occurred_at,
                recorded_by=actor_reference,
                note=note,
            )
            audit_event = self._audit_requested(
                alert_case=current,
                operation="RECORD_ACTION",
                fingerprint=fingerprint,
                timestamp=occurred_at,
                actor_reference=actor_reference,
                previous_state=current.state,
                new_state=current.state,
                metadata={"rm_action": action},
            )
            return BankerOperationResponse(
                operation="RECORD_ACTION",
                idempotency_token=idempotency_token,
                previous_state=current.state,
                alert_case=current,
                action_record=record,
                case_outcome=None,
                audit_event=audit_event,
            )

        return self._run_idempotent(idempotency_token, fingerprint, operation)

    def close(
        self,
        alert_id: str,
        *,
        expected_state: AlertCaseState,
        occurred_at: datetime,
        actor_reference: str,
        idempotency_token: str,
        case_outcome: CaseOutcomeRecord,
    ) -> BankerOperationResponse:
        """Close an active case with an explicit workflow outcome and reason."""

        fingerprint = _fingerprint(
            "CLOSE",
            alert_id,
            expected_state,
            occurred_at,
            actor_reference,
            case_outcome.to_dict(),
        )
        _validate_actor_reference(actor_reference)

        def operation() -> BankerOperationResponse:
            current = self._load_expected(alert_id, expected_state)
            if current.state == "CLOSED":
                raise BankerStateConflictError("AlertCase is already CLOSED")
            if case_outcome.alert_id != current.alert_id or case_outcome.customer_id != current.customer_id:
                raise ValueError("case_outcome must identify the current AlertCase")
            if case_outcome.recorded_at != occurred_at or case_outcome.recorded_by != actor_reference:
                raise ValueError("case_outcome actor and recorded_at must match close operation")
            if case_outcome.closure_reason is None:
                raise ValueError("closing requires a case_outcome with closure_reason")
            resolution = _CLOSURE_TO_RESOLUTION.get(case_outcome.closure_reason)
            if resolution is None:
                raise ValueError("case_outcome closure_reason is unsupported")
            audit_event = self._audit_requested(
                alert_case=current,
                operation="CLOSE",
                fingerprint=fingerprint,
                timestamp=occurred_at,
                actor_reference=actor_reference,
                previous_state=current.state,
                new_state="CLOSED",
                metadata={
                    "case_outcome": case_outcome.outcome,
                    "closure_reason": case_outcome.closure_reason,
                },
            )
            try:
                closed = current.transition_to(
                    "CLOSED",
                    occurred_at=occurred_at,
                    state_change_reason=f"BANKER_CLOSE:{actor_reference}",
                    case_resolution=resolution,
                )
                stored = self.repository.update(closed, expected_updated_at=current.updated_at)
            except AlertCaseRepositoryConflictError as error:
                raise BankerStateConflictError(str(error)) from error
            return BankerOperationResponse(
                operation="CLOSE",
                idempotency_token=idempotency_token,
                previous_state=current.state,
                alert_case=stored,
                action_record=None,
                case_outcome=case_outcome,
                audit_event=audit_event,
            )

        return self._run_idempotent(idempotency_token, fingerprint, operation)

    def reopen(
        self,
        alert_id: str,
        *,
        expected_state: AlertCaseState,
        occurred_at: datetime,
        actor_reference: str,
        idempotency_token: str,
    ) -> BankerOperationResponse:
        """Create a fresh NEW case from a closed case when explicitly enabled."""

        fingerprint = _fingerprint(
            "REOPEN",
            alert_id,
            expected_state,
            occurred_at,
            actor_reference,
        )
        _validate_actor_reference(actor_reference)

        def operation() -> BankerOperationResponse:
            current = self._load_expected(alert_id, expected_state)
            if current.state != "CLOSED":
                raise BankerStateConflictError("only a CLOSED AlertCase can be reopened")
            if not self.allow_closed_case_reopen:
                raise BankerServiceError("closed-case reopening is not enabled")
            new_alert_id = _reopened_alert_id(current.alert_id, idempotency_token)
            candidate = create_alert_case(
                alert_id=new_alert_id,
                customer_id=current.customer_id,
                policy_id=current.policy_id,
                policy_version=current.policy_version,
                selection_policy_id=current.selection_policy_id,
                selection_policy_version=current.selection_policy_version,
                signal_run_id=current.signal_run_id,
                signal_version=current.signal_version,
                signal_as_of_month=current.signal_as_of_month,
                created_at=occurred_at,
                due_at=occurred_at + timedelta(hours=self.reopen_due_in_hours),
                operational_priority=current.operational_priority,
                why_now_reason_codes=current.why_now_reason_codes,
                selection_reason_codes=current.selection_reason_codes,
                timing_evidence_reference=current.timing_evidence_reference,
                episode_key=current.episode_key,
                owner_reference=current.owner_reference,
            )
            audit_event = self._audit_requested(
                alert_case=candidate,
                operation="REOPEN",
                fingerprint=fingerprint,
                timestamp=occurred_at,
                actor_reference=actor_reference,
                previous_state="CLOSED",
                new_state="NEW",
                metadata={"reopened_from_alert_id": current.alert_id},
            )
            existing_reopen = self.repository.get(new_alert_id)
            if existing_reopen is not None:
                if (
                    existing_reopen.customer_id != current.customer_id
                    or existing_reopen.episode_key != current.episode_key
                ):
                    raise BankerServiceError("reopen ID conflicts with an unrelated AlertCase")
                return BankerOperationResponse(
                    operation="REOPEN",
                    idempotency_token=idempotency_token,
                    previous_state="CLOSED",
                    alert_case=existing_reopen,
                    action_record=None,
                    case_outcome=None,
                    audit_event=audit_event,
                    reopened_from_alert_id=current.alert_id,
                    idempotent_replay=True,
                )
            stored = self.repository.create(candidate)
            return BankerOperationResponse(
                operation="REOPEN",
                idempotency_token=idempotency_token,
                previous_state="CLOSED",
                alert_case=stored,
                action_record=None,
                case_outcome=None,
                audit_event=audit_event,
                reopened_from_alert_id=current.alert_id,
            )

        return self._run_idempotent(idempotency_token, fingerprint, operation)

    def _transition(
        self,
        *,
        operation: BankerOperation,
        alert_id: str,
        expected_state: AlertCaseState,
        required_state: AlertCaseState,
        target_state: AlertCaseState,
        occurred_at: datetime,
        actor_reference: str,
        idempotency_token: str,
    ) -> BankerOperationResponse:
        _validate_actor_reference(actor_reference)
        fingerprint = _fingerprint(
            operation,
            alert_id,
            expected_state,
            target_state,
            occurred_at,
            actor_reference,
        )

        def operation_fn() -> BankerOperationResponse:
            current = self._load_expected(alert_id, expected_state)
            if current.state != required_state:
                raise BankerStateConflictError(
                    f"{operation} requires {required_state}, found {current.state}"
                )
            audit_event = self._audit_requested(
                alert_case=current,
                operation=operation,
                fingerprint=fingerprint,
                timestamp=occurred_at,
                actor_reference=actor_reference,
                previous_state=current.state,
                new_state=target_state,
            )
            try:
                updated = current.transition_to(
                    target_state,
                    occurred_at=occurred_at,
                    state_change_reason=f"BANKER_{operation}:{actor_reference}",
                )
                stored = self.repository.update(updated, expected_updated_at=current.updated_at)
            except AlertCaseRepositoryConflictError as error:
                raise BankerStateConflictError(str(error)) from error
            return BankerOperationResponse(
                operation=operation,
                idempotency_token=idempotency_token,
                previous_state=current.state,
                alert_case=stored,
                action_record=None,
                case_outcome=None,
                audit_event=audit_event,
            )

        return self._run_idempotent(idempotency_token, fingerprint, operation_fn)

    def _audit_requested(
        self,
        *,
        alert_case: AlertCase,
        operation: BankerOperation,
        fingerprint: str,
        timestamp: datetime,
        actor_reference: str,
        previous_state: AlertCaseState,
        new_state: AlertCaseState,
        metadata: dict[str, str | int | bool | None] | None = None,
    ) -> AuditEvent:
        """Append audit evidence before any repository state mutation.

        The event is explicitly a requested transition.  If the following
        repository write fails, the existing event remains an honest record of
        the request and the case remains at its prior state.
        """

        event = build_banker_audit_event(
            alert_case,
            operation=operation,
            operation_fingerprint=fingerprint,
            timestamp=timestamp,
            actor_reference=actor_reference,
            previous_state=previous_state,
            new_state=new_state,
            metadata=metadata,
        )
        return self.audit_store.append(event)

    def _load_expected(self, alert_id: str, expected_state: AlertCaseState) -> AlertCase:
        if not str(alert_id).strip():
            raise ValueError("alert_id must be non-empty")
        current = self.repository.get(alert_id)
        if current is None:
            raise KeyError(f"unknown alert_id: {alert_id}")
        if current.state != expected_state:
            raise BankerStateConflictError(
                f"stale state for {alert_id}: expected {expected_state}, found {current.state}"
            )
        return current

    def _run_idempotent(
        self,
        idempotency_token: str,
        fingerprint: str,
        operation: Callable[[], BankerOperationResponse],
    ) -> BankerOperationResponse:
        if not str(idempotency_token).strip():
            raise ValueError("idempotency_token must be non-empty")
        prior = self._idempotency.get(idempotency_token)
        if prior is not None:
            prior_fingerprint, prior_response = prior
            if prior_fingerprint != fingerprint:
                raise BankerIdempotencyConflictError(
                    "idempotency_token was already used for a different operation"
                )
            return replace(prior_response, idempotent_replay=True)
        response = operation()
        self._idempotency[idempotency_token] = (fingerprint, response)
        return response


def _fingerprint(*values: object) -> str:
    return "|".join(_fingerprint_value(value) for value in values)


def _fingerprint_value(value: object) -> str:
    if isinstance(value, datetime):
        _validate_aware_datetime(value, "occurred_at")
        return value.isoformat()
    if isinstance(value, dict):
        return repr(sorted((str(key), _fingerprint_value(item)) for key, item in value.items()))
    return repr(value)


def _reopened_alert_id(alert_id: str, idempotency_token: str) -> str:
    return f"ALT-{uuid5(NAMESPACE_URL, f'reopen|{alert_id}|{idempotency_token}').hex.upper()}"


def _validate_aware_datetime(value: datetime, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be a timezone-aware datetime")


def _validate_actor_reference(value: str) -> None:
    if not str(value).strip():
        raise ValueError("actor_reference must be non-empty")
