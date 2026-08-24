"""Provider-neutral Alert/Case domain contract and explicit state machine.

An :class:`AlertCase` is a prospective-policy review work item.  It does not
evaluate policy eligibility, alter triage selection, persist data, or deliver
an external message.  Its workflow resolution is intentionally distinct from
synthetic analytical labels.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal, Mapping

from config import settings


ALERT_CASE_SCHEMA_VERSION = "alert_case.v1"
ALERT_CASE_STATES = (
    "NEW",
    "ACKNOWLEDGED",
    "IN_REVIEW",
    "FOLLOW_UP",
    "SNOOZED",
    "ESCALATED",
    "CLOSED",
)
OPERATIONAL_PRIORITIES = ("REVIEW", "PRIORITY_REVIEW")
CASE_RESOLUTIONS = (
    "RESOLVED_NO_ACTION",
    "CONTACT_COMPLETED",
    "REFERRED",
    "DUPLICATE_OR_SUPERSEDED",
    "UNRESOLVED",
)

AlertCaseState = Literal[
    "NEW",
    "ACKNOWLEDGED",
    "IN_REVIEW",
    "FOLLOW_UP",
    "SNOOZED",
    "ESCALATED",
    "CLOSED",
]
OperationalPriority = Literal["REVIEW", "PRIORITY_REVIEW"]
CaseResolution = Literal[
    "RESOLVED_NO_ACTION",
    "CONTACT_COMPLETED",
    "REFERRED",
    "DUPLICATE_OR_SUPERSEDED",
    "UNRESOLVED",
]


ALLOWED_STATE_TRANSITIONS: dict[AlertCaseState, frozenset[AlertCaseState]] = {
    "NEW": frozenset({"ACKNOWLEDGED", "IN_REVIEW", "SNOOZED", "ESCALATED"}),
    "ACKNOWLEDGED": frozenset({"IN_REVIEW", "FOLLOW_UP", "SNOOZED", "ESCALATED", "CLOSED"}),
    "IN_REVIEW": frozenset({"FOLLOW_UP", "SNOOZED", "ESCALATED", "CLOSED"}),
    "FOLLOW_UP": frozenset({"IN_REVIEW", "SNOOZED", "ESCALATED", "CLOSED"}),
    "SNOOZED": frozenset({"ACKNOWLEDGED", "IN_REVIEW", "ESCALATED", "CLOSED"}),
    "ESCALATED": frozenset({"IN_REVIEW", "FOLLOW_UP", "SNOOZED", "CLOSED"}),
    "CLOSED": frozenset(),
}


@dataclass(frozen=True)
class TimingEvidenceReference:
    """Current prospective timing evidence carried into a review work item."""

    source: str
    candidate_month: int
    evaluation_status: str
    lead_time_months: None = None

    def __post_init__(self) -> None:
        if self.source != "prospective_signal":
            raise ValueError("timing evidence source must be prospective_signal")
        _validate_month(self.candidate_month, "candidate_month")
        if not str(self.evaluation_status).strip():
            raise ValueError("evaluation_status must be non-empty")
        if self.lead_time_months is not None:
            raise ValueError("prospective case timing cannot include retrospective lead-time")

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "candidate_month": self.candidate_month,
            "evaluation_status": self.evaluation_status,
            "lead_time_months": None,
            "lead_time_unit": "months",
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "TimingEvidenceReference":
        _require_exact_keys(
            payload,
            {"source", "candidate_month", "evaluation_status", "lead_time_months", "lead_time_unit"},
            "timing evidence",
        )
        if payload["lead_time_unit"] != "months":
            raise ValueError("timing evidence lead_time_unit must be months")
        return cls(
            source=str(payload["source"]),
            candidate_month=_as_int(payload["candidate_month"], "candidate_month"),
            evaluation_status=str(payload["evaluation_status"]),
            lead_time_months=payload["lead_time_months"],  # validated as None by the constructor
        )


@dataclass(frozen=True)
class AlertCase:
    """A canonical RM review work item with explicit, side-effect-free state."""

    alert_id: str
    customer_id: str
    policy_id: str
    policy_version: str
    selection_policy_id: str
    selection_policy_version: str
    signal_run_id: str
    signal_version: str
    signal_as_of_month: int
    created_at: datetime
    updated_at: datetime
    due_at: datetime
    operational_priority: OperationalPriority
    why_now_reason_codes: tuple[str, ...]
    selection_reason_codes: tuple[str, ...]
    timing_evidence_reference: TimingEvidenceReference
    state: AlertCaseState
    episode_key: str
    owner_reference: str | None = None
    snoozed_until: datetime | None = None
    case_resolution: CaseResolution | None = None
    last_state_change_reason: str = "CASE_CREATED"
    schema_version: str = ALERT_CASE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty(
            {
                "alert_id": self.alert_id,
                "customer_id": self.customer_id,
                "policy_id": self.policy_id,
                "policy_version": self.policy_version,
                "selection_policy_id": self.selection_policy_id,
                "selection_policy_version": self.selection_policy_version,
                "signal_run_id": self.signal_run_id,
                "signal_version": self.signal_version,
                "episode_key": self.episode_key,
                "last_state_change_reason": self.last_state_change_reason,
            }
        )
        _validate_month(self.signal_as_of_month, "signal_as_of_month")
        _validate_datetime(self.created_at, "created_at")
        _validate_datetime(self.updated_at, "updated_at")
        _validate_datetime(self.due_at, "due_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not be before created_at")
        if self.due_at < self.created_at:
            raise ValueError("due_at must not be before created_at")
        if self.operational_priority not in OPERATIONAL_PRIORITIES:
            raise ValueError(f"operational_priority must be one of {OPERATIONAL_PRIORITIES}")
        if not self.why_now_reason_codes or any(
            not str(code).strip() for code in self.why_now_reason_codes
        ):
            raise ValueError("why_now_reason_codes must contain non-empty values")
        if len(self.why_now_reason_codes) != len(set(self.why_now_reason_codes)):
            raise ValueError("why_now_reason_codes must be unique")
        if not self.selection_reason_codes or any(
            not str(code).strip() for code in self.selection_reason_codes
        ):
            raise ValueError("selection_reason_codes must contain non-empty values")
        if len(self.selection_reason_codes) != len(set(self.selection_reason_codes)):
            raise ValueError("selection_reason_codes must be unique")
        if self.timing_evidence_reference.candidate_month != self.signal_as_of_month:
            raise ValueError("timing evidence candidate_month must match signal_as_of_month")
        if self.state not in ALERT_CASE_STATES:
            raise ValueError(f"state must be one of {ALERT_CASE_STATES}")
        if self.owner_reference is not None and not str(self.owner_reference).strip():
            raise ValueError("owner_reference must be non-empty or None")
        if self.state == "SNOOZED":
            if self.snoozed_until is None:
                raise ValueError("SNOOZED cases require snoozed_until")
            _validate_datetime(self.snoozed_until, "snoozed_until")
            if self.snoozed_until <= self.updated_at:
                raise ValueError("snoozed_until must be after updated_at")
        elif self.snoozed_until is not None:
            raise ValueError("only SNOOZED cases can include snoozed_until")
        if self.state == "CLOSED":
            if self.case_resolution not in CASE_RESOLUTIONS:
                raise ValueError("CLOSED cases require a valid case_resolution")
        elif self.case_resolution is not None:
            raise ValueError("case_resolution is set only when a case is CLOSED")
        if self.schema_version != ALERT_CASE_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {ALERT_CASE_SCHEMA_VERSION}")

    def can_transition_to(self, target_state: AlertCaseState) -> bool:
        """Return whether the requested target is an allowed next state."""

        _validate_state(target_state, "target_state")
        return target_state in ALLOWED_STATE_TRANSITIONS[self.state]

    def transition_to(
        self,
        target_state: AlertCaseState,
        *,
        occurred_at: datetime,
        state_change_reason: str,
        snoozed_until: datetime | None = None,
        case_resolution: CaseResolution | None = None,
    ) -> "AlertCase":
        """Return a new case in an allowed state, otherwise raise an explicit error."""

        _validate_state(target_state, "target_state")
        _validate_datetime(occurred_at, "occurred_at")
        if occurred_at < self.updated_at:
            raise ValueError("occurred_at must not be before updated_at")
        if not str(state_change_reason).strip():
            raise ValueError("state_change_reason must be non-empty")
        if not self.can_transition_to(target_state):
            raise ValueError(f"illegal AlertCase transition: {self.state} -> {target_state}")
        if target_state == "SNOOZED":
            if snoozed_until is None:
                raise ValueError("SNOOZED transitions require snoozed_until")
            _validate_datetime(snoozed_until, "snoozed_until")
            if snoozed_until <= occurred_at:
                raise ValueError("snoozed_until must be after occurred_at")
        elif snoozed_until is not None:
            raise ValueError("only SNOOZED transitions can include snoozed_until")
        if target_state == "CLOSED":
            if case_resolution not in CASE_RESOLUTIONS:
                raise ValueError("CLOSED transitions require a valid case_resolution")
        elif case_resolution is not None:
            raise ValueError("case_resolution is allowed only for CLOSED transitions")
        return replace(
            self,
            state=target_state,
            updated_at=occurred_at,
            snoozed_until=snoozed_until,
            case_resolution=case_resolution,
            last_state_change_reason=str(state_change_reason),
        )

    def to_dict(self) -> dict[str, object]:
        """Serialize the stable work-item contract without delivery metadata."""

        return {
            "schema_version": self.schema_version,
            "alert_id": self.alert_id,
            "customer_id": self.customer_id,
            "policy_reference": {
                "policy_id": self.policy_id,
                "policy_version": self.policy_version,
            },
            "selection_reference": {
                "selection_policy_id": self.selection_policy_id,
                "selection_policy_version": self.selection_policy_version,
                "selection_reason_codes": list(self.selection_reason_codes),
            },
            "signal_reference": {
                "signal_run_id": self.signal_run_id,
                "signal_version": self.signal_version,
                "signal_as_of_month": self.signal_as_of_month,
            },
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "due_at": self.due_at.isoformat(),
            "operational_priority": self.operational_priority,
            "why_now_reason_codes": list(self.why_now_reason_codes),
            "timing_evidence_reference": self.timing_evidence_reference.to_dict(),
            "state": self.state,
            "episode_key": self.episode_key,
            "owner_reference": self.owner_reference,
            "snoozed_until": None if self.snoozed_until is None else self.snoozed_until.isoformat(),
            "case_resolution": self.case_resolution,
            "last_state_change_reason": self.last_state_change_reason,
            "scope": {
                "persistence_implemented": False,
                "external_delivery_implemented": False,
                "synthetic_analytics_attached": False,
            },
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "AlertCase":
        """Deserialize only the declared core schema; reject undeclared fields."""

        _require_exact_keys(
            payload,
            {
                "schema_version",
                "alert_id",
                "customer_id",
                "policy_reference",
                "selection_reference",
                "signal_reference",
                "created_at",
                "updated_at",
                "due_at",
                "operational_priority",
                "why_now_reason_codes",
                "timing_evidence_reference",
                "state",
                "episode_key",
                "owner_reference",
                "snoozed_until",
                "case_resolution",
                "last_state_change_reason",
                "scope",
            },
            "alert case",
        )
        if payload["schema_version"] != ALERT_CASE_SCHEMA_VERSION:
            raise ValueError("Unexpected alert case schema version")
        policy_reference = _as_mapping(payload["policy_reference"], "policy_reference")
        _require_exact_keys(policy_reference, {"policy_id", "policy_version"}, "policy_reference")
        selection_reference = _as_mapping(payload["selection_reference"], "selection_reference")
        _require_exact_keys(
            selection_reference,
            {"selection_policy_id", "selection_policy_version", "selection_reason_codes"},
            "selection_reference",
        )
        signal_reference = _as_mapping(payload["signal_reference"], "signal_reference")
        _require_exact_keys(
            signal_reference,
            {"signal_run_id", "signal_version", "signal_as_of_month"},
            "signal_reference",
        )
        scope = _as_mapping(payload["scope"], "scope")
        _require_exact_keys(
            scope,
            {"persistence_implemented", "external_delivery_implemented", "synthetic_analytics_attached"},
            "scope",
        )
        if any(scope[key] is not False for key in scope):
            raise ValueError("alert case scope flags must remain false in the domain model")
        reason_codes_value = payload["why_now_reason_codes"]
        if not isinstance(reason_codes_value, list):
            raise ValueError("why_now_reason_codes must be a list")
        selection_reason_codes_value = selection_reference["selection_reason_codes"]
        if not isinstance(selection_reason_codes_value, list):
            raise ValueError("selection_reason_codes must be a list")
        return cls(
            alert_id=str(payload["alert_id"]),
            customer_id=str(payload["customer_id"]),
            policy_id=str(policy_reference["policy_id"]),
            policy_version=str(policy_reference["policy_version"]),
            selection_policy_id=str(selection_reference["selection_policy_id"]),
            selection_policy_version=str(selection_reference["selection_policy_version"]),
            signal_run_id=str(signal_reference["signal_run_id"]),
            signal_version=str(signal_reference["signal_version"]),
            signal_as_of_month=_as_int(signal_reference["signal_as_of_month"], "signal_as_of_month"),
            created_at=_parse_datetime(payload["created_at"], "created_at"),
            updated_at=_parse_datetime(payload["updated_at"], "updated_at"),
            due_at=_parse_datetime(payload["due_at"], "due_at"),
            operational_priority=str(payload["operational_priority"]),  # type: ignore[arg-type]
            why_now_reason_codes=tuple(str(code) for code in reason_codes_value),
            selection_reason_codes=tuple(str(code) for code in selection_reason_codes_value),
            timing_evidence_reference=TimingEvidenceReference.from_dict(
                _as_mapping(payload["timing_evidence_reference"], "timing_evidence_reference")
            ),
            state=str(payload["state"]),  # type: ignore[arg-type]
            episode_key=str(payload["episode_key"]),
            owner_reference=None if payload["owner_reference"] is None else str(payload["owner_reference"]),
            snoozed_until=(
                None
                if payload["snoozed_until"] is None
                else _parse_datetime(payload["snoozed_until"], "snoozed_until")
            ),
            case_resolution=(
                None if payload["case_resolution"] is None else str(payload["case_resolution"])
            ),  # type: ignore[arg-type]
            last_state_change_reason=str(payload["last_state_change_reason"]),
        )


def create_alert_case(
    *,
    alert_id: str,
    customer_id: str,
    policy_id: str,
    policy_version: str,
    selection_policy_id: str,
    selection_policy_version: str,
    signal_run_id: str,
    signal_version: str,
    signal_as_of_month: int,
    created_at: datetime,
    due_at: datetime,
    operational_priority: OperationalPriority,
    why_now_reason_codes: tuple[str, ...],
    selection_reason_codes: tuple[str, ...],
    timing_evidence_reference: TimingEvidenceReference,
    episode_key: str,
    owner_reference: str | None = None,
) -> AlertCase:
    """Create a new work item without selecting, persisting, or delivering it."""

    return AlertCase(
        alert_id=alert_id,
        customer_id=customer_id,
        policy_id=policy_id,
        policy_version=policy_version,
        selection_policy_id=selection_policy_id,
        selection_policy_version=selection_policy_version,
        signal_run_id=signal_run_id,
        signal_version=signal_version,
        signal_as_of_month=signal_as_of_month,
        created_at=created_at,
        updated_at=created_at,
        due_at=due_at,
        operational_priority=operational_priority,
        why_now_reason_codes=why_now_reason_codes,
        selection_reason_codes=selection_reason_codes,
        timing_evidence_reference=timing_evidence_reference,
        state="NEW",
        episode_key=episode_key,
        owner_reference=owner_reference,
    )


def _validate_state(value: str, label: str) -> None:
    if value not in ALERT_CASE_STATES:
        raise ValueError(f"{label} must be one of {ALERT_CASE_STATES}")


def _validate_month(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if not 1 <= value <= settings.TOTAL_MONTHS:
        raise ValueError(f"{label} must be between 1 and {settings.TOTAL_MONTHS}")


def _validate_datetime(value: datetime, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be a timezone-aware datetime")


def _require_non_empty(values: Mapping[str, str]) -> None:
    empty = [name for name, value in values.items() if not str(value).strip()]
    if empty:
        raise ValueError(f"required fields must be non-empty: {empty}")


def _require_exact_keys(payload: Mapping[str, object], expected: set[str], label: str) -> None:
    actual = set(payload)
    if actual != expected:
        raise ValueError(f"{label} keys differ; missing={sorted(expected - actual)}, extra={sorted(actual - expected)}")


def _as_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _as_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _parse_datetime(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO datetime string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{label} must be an ISO datetime string") from error
    _validate_datetime(parsed, label)
    return parsed
