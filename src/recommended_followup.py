"""Human-reviewed follow-up and case-outcome contracts for Alert/Case work.

The module only proposes a follow-up for an existing review work item.  It
does not execute an action, change case state, alter analytical results, or
make a financial decision.  Hypothetical cash-flow scenarios can be attached
as context, but never as proof that an RM action will work.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from src.alert_case import AlertCase, TimingEvidenceReference


RECOMMENDED_FOLLOW_UP_SCHEMA_VERSION = "recommended_follow_up.v1"
RM_ACTIONS = (
    "REVIEW_COMPLETED",
    "CONTACT_PLANNED",
    "CONTACT_COMPLETED",
    "MONITOR_ONLY",
    "NO_ACTION_REQUIRED",
    "REFERRED",
    "FOLLOW_UP_CREATED",
)
CASE_OUTCOMES = (
    "REVIEW_DOCUMENTED",
    "CONTACT_DOCUMENTED",
    "MONITORING_CONTINUES",
    "NO_ACTION_REQUIRED",
    "REFERRED",
    "FOLLOW_UP_SCHEDULED",
    "CLOSED_UNRESOLVED",
)
CLOSURE_REASONS = (
    "REVIEW_COMPLETE_NO_FURTHER_ACTION",
    "CONTACT_COMPLETED",
    "REFERRED_TO_SPECIALIST",
    "DUPLICATE_OR_SUPERSEDED",
    "UNRESOLVED",
)

RMAction = Literal[
    "REVIEW_COMPLETED",
    "CONTACT_PLANNED",
    "CONTACT_COMPLETED",
    "MONITOR_ONLY",
    "NO_ACTION_REQUIRED",
    "REFERRED",
    "FOLLOW_UP_CREATED",
]
CaseOutcome = Literal[
    "REVIEW_DOCUMENTED",
    "CONTACT_DOCUMENTED",
    "MONITORING_CONTINUES",
    "NO_ACTION_REQUIRED",
    "REFERRED",
    "FOLLOW_UP_SCHEDULED",
    "CLOSED_UNRESOLVED",
]
ClosureReason = Literal[
    "REVIEW_COMPLETE_NO_FURTHER_ACTION",
    "CONTACT_COMPLETED",
    "REFERRED_TO_SPECIALIST",
    "DUPLICATE_OR_SUPERSEDED",
    "UNRESOLVED",
]
FollowUpUrgency = Literal["PROMPT", "STANDARD"]

_REFERRAL_REASON_CODES = frozenset({"REFERRAL_INDICATED", "SPECIALIST_REVIEW_REQUIRED"})
_MONITOR_REASON_CODES = frozenset({"MONITOR_ONLY", "MONITORING_CONTINUES"})
_NO_ACTION_REASON_CODES = frozenset({"NO_ACTION_REQUIRED", "DUPLICATE_OR_SUPERSEDED"})
_TERMINAL_CASE_OUTCOMES = frozenset(
    {
        "REVIEW_DOCUMENTED",
        "CONTACT_DOCUMENTED",
        "NO_ACTION_REQUIRED",
        "REFERRED",
        "CLOSED_UNRESOLVED",
    }
)


@dataclass(frozen=True)
class WhatIfSupportingEvidence:
    """A labelled hypothetical scenario, isolated from action effectiveness."""

    scenario_name: str
    simulation_months: int
    evidence_note: str
    supporting_evidence_only: bool = True
    changes_recommendation: bool = False
    estimates_action_effectiveness: bool = False
    schema_version: str = RECOMMENDED_FOLLOW_UP_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty(
            {
                "scenario_name": self.scenario_name,
                "evidence_note": self.evidence_note,
            }
        )
        if isinstance(self.simulation_months, bool) or not isinstance(self.simulation_months, int):
            raise ValueError("simulation_months must be an integer")
        if self.simulation_months <= 0:
            raise ValueError("simulation_months must be positive")
        if (
            self.supporting_evidence_only is not True
            or self.changes_recommendation is not False
            or self.estimates_action_effectiveness is not False
        ):
            raise ValueError("What-if evidence must remain supporting context only")
        if self.schema_version != RECOMMENDED_FOLLOW_UP_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {RECOMMENDED_FOLLOW_UP_SCHEMA_VERSION}")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "scenario_name": self.scenario_name,
            "simulation_months": self.simulation_months,
            "evidence_note": self.evidence_note,
            "supporting_evidence_only": True,
            "changes_recommendation": False,
            "estimates_action_effectiveness": False,
        }


@dataclass(frozen=True)
class RecommendedFollowUp:
    """A human-review recommendation derived from current AlertCase evidence."""

    alert_id: str
    customer_id: str
    title: str
    urgency: FollowUpUrgency
    recommended_actions: tuple[RMAction, ...]
    reason_codes: tuple[str, ...]
    timing_evidence_reference: TimingEvidenceReference
    whatif_supporting_evidence: WhatIfSupportingEvidence | None
    automatic_execution: bool = False
    automatic_financial_decision: bool = False
    schema_version: str = RECOMMENDED_FOLLOW_UP_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty(
            {
                "alert_id": self.alert_id,
                "customer_id": self.customer_id,
                "title": self.title,
            }
        )
        if self.title != "Recommended Follow-up":
            raise ValueError("title must be Recommended Follow-up")
        if self.urgency not in {"PROMPT", "STANDARD"}:
            raise ValueError("urgency must be PROMPT or STANDARD")
        _validate_codes(self.recommended_actions, "recommended_actions", RM_ACTIONS)
        _validate_codes(self.reason_codes, "reason_codes")
        if self.automatic_execution is not False or self.automatic_financial_decision is not False:
            raise ValueError("follow-up must remain human-reviewed and non-decisional")
        if self.schema_version != RECOMMENDED_FOLLOW_UP_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {RECOMMENDED_FOLLOW_UP_SCHEMA_VERSION}")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "alert_id": self.alert_id,
            "customer_id": self.customer_id,
            "title": self.title,
            "urgency": self.urgency,
            "recommended_actions": list(self.recommended_actions),
            "reason_codes": list(self.reason_codes),
            "timing_evidence_reference": self.timing_evidence_reference.to_dict(),
            "whatif_supporting_evidence": (
                None
                if self.whatif_supporting_evidence is None
                else self.whatif_supporting_evidence.to_dict()
            ),
            "scope": {
                "automatic_execution": False,
                "automatic_financial_decision": False,
                "action_effectiveness_estimated": False,
            },
        }


@dataclass(frozen=True)
class RMActionRecord:
    """A staff-recorded action; this object does not itself alter a case."""

    alert_id: str
    action: RMAction
    recorded_at: datetime
    recorded_by: str
    note: str | None = None
    schema_version: str = RECOMMENDED_FOLLOW_UP_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty({"alert_id": self.alert_id, "recorded_by": self.recorded_by})
        if self.action not in RM_ACTIONS:
            raise ValueError(f"action must be one of {RM_ACTIONS}")
        _validate_aware_datetime(self.recorded_at, "recorded_at")
        if self.note is not None and not str(self.note).strip():
            raise ValueError("note must be non-empty or None")
        if self.schema_version != RECOMMENDED_FOLLOW_UP_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {RECOMMENDED_FOLLOW_UP_SCHEMA_VERSION}")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "alert_id": self.alert_id,
            "action": self.action,
            "recorded_at": self.recorded_at.isoformat(),
            "recorded_by": self.recorded_by,
            "note": self.note,
            "scope": {
                "case_state_changed": False,
                "automatic_execution": False,
            },
        }


@dataclass(frozen=True)
class CaseOutcomeRecord:
    """A workflow outcome and optional closure reason, separate from analytics."""

    alert_id: str
    customer_id: str
    outcome: CaseOutcome
    recorded_at: datetime
    recorded_by: str
    closure_reason: ClosureReason | None = None
    action_references: tuple[str, ...] = ()
    schema_version: str = RECOMMENDED_FOLLOW_UP_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty(
            {
                "alert_id": self.alert_id,
                "customer_id": self.customer_id,
                "recorded_by": self.recorded_by,
            }
        )
        if self.outcome not in CASE_OUTCOMES:
            raise ValueError(f"outcome must be one of {CASE_OUTCOMES}")
        _validate_aware_datetime(self.recorded_at, "recorded_at")
        _validate_codes(self.action_references, "action_references", allow_empty=True)
        if self.outcome in _TERMINAL_CASE_OUTCOMES:
            if self.closure_reason not in CLOSURE_REASONS:
                raise ValueError("terminal case outcomes require a valid closure_reason")
        elif self.closure_reason is not None:
            raise ValueError("non-terminal case outcomes cannot include closure_reason")
        if self.schema_version != RECOMMENDED_FOLLOW_UP_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {RECOMMENDED_FOLLOW_UP_SCHEMA_VERSION}")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "alert_id": self.alert_id,
            "customer_id": self.customer_id,
            "outcome": self.outcome,
            "recorded_at": self.recorded_at.isoformat(),
            "recorded_by": self.recorded_by,
            "closure_reason": self.closure_reason,
            "action_references": list(self.action_references),
            "scope": {
                "analytical_label_attached": False,
                "case_state_changed": False,
                "automatic_financial_decision": False,
            },
        }


def build_recommended_follow_up(
    alert_case: AlertCase,
    *,
    whatif_supporting_evidence: WhatIfSupportingEvidence | None = None,
) -> RecommendedFollowUp:
    """Return declared RM follow-up options without executing or selecting anything."""

    if alert_case.state == "CLOSED":
        raise ValueError("cannot recommend follow-up for a CLOSED AlertCase")
    action_codes = _recommendation_actions(alert_case)
    return RecommendedFollowUp(
        alert_id=alert_case.alert_id,
        customer_id=alert_case.customer_id,
        title="Recommended Follow-up",
        urgency=("PROMPT" if alert_case.operational_priority == "PRIORITY_REVIEW" else "STANDARD"),
        recommended_actions=action_codes,
        reason_codes=alert_case.why_now_reason_codes,
        timing_evidence_reference=alert_case.timing_evidence_reference,
        whatif_supporting_evidence=whatif_supporting_evidence,
    )


def _recommendation_actions(alert_case: AlertCase) -> tuple[RMAction, ...]:
    reasons = set(alert_case.why_now_reason_codes)
    if reasons & _MONITOR_REASON_CODES:
        return ("MONITOR_ONLY",)
    if reasons & _NO_ACTION_REASON_CODES:
        return ("NO_ACTION_REQUIRED",)

    actions: list[RMAction] = ["REVIEW_COMPLETED"]
    if alert_case.operational_priority == "PRIORITY_REVIEW":
        actions.append("CONTACT_PLANNED")
    if alert_case.state == "FOLLOW_UP":
        actions.append("FOLLOW_UP_CREATED")
    if reasons & _REFERRAL_REASON_CODES:
        actions.append("REFERRED")
    return tuple(actions)


def _validate_codes(
    values: tuple[str, ...],
    label: str,
    permitted: tuple[str, ...] | None = None,
    *,
    allow_empty: bool = False,
) -> None:
    if not values and not allow_empty:
        raise ValueError(f"{label} must not be empty")
    if any(not str(value).strip() for value in values):
        raise ValueError(f"{label} must contain non-empty values")
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")
    if permitted is not None and any(value not in permitted for value in values):
        raise ValueError(f"{label} contains an unsupported value")


def _require_non_empty(values: dict[str, str]) -> None:
    missing = sorted(name for name, value in values.items() if not str(value).strip())
    if missing:
        raise ValueError(f"required fields must be non-empty: {', '.join(missing)}")


def _validate_aware_datetime(value: datetime, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be a timezone-aware datetime")
