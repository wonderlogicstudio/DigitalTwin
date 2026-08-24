"""Protocol-only contracts for a future, human-reviewed RM pilot.

The public repository may define synthetic pilot measurement fields and review
criteria, but it must not recruit people, process customer data, send a
notification, or make a financial or policy decision. This module deliberately
contains no workflow, repository, scorer, policy, transport, or UI dependency.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Literal

from config import settings


RM_PILOT_PROTOCOL_SCHEMA_VERSION = "rm_pilot_protocol.v1"
RM_PILOT_MEASUREMENT_SCHEMA_VERSION = "rm_pilot_measurement.v1"
RM_PILOT_ARTIFACT_DIR = settings.BASE_DIR / "artifacts" / "post_p0" / "rm_pilot"

ApprovalStatus = Literal["not_requested", "pending", "approved"]
ReviewOutcome = Literal["REVIEWED", "DEFERRED", "MONITOR", "NO_ACTION"]
RecommendationDecision = Literal["ACCEPTED", "MODIFIED", "REJECTED", "NOT_APPLICABLE"]
FollowUpStatus = Literal["NOT_CREATED", "CREATED", "COMPLETED", "NOT_APPLICABLE"]
StopCriterion = Literal[
    "WORKLOAD_OVERLOAD",
    "TIMING_SEMANTICS_CONFUSING",
    "HIGH_UNUSABLE_EVIDENCE",
    "PRIVACY_OR_SECURITY_ISSUE",
    "WORKFLOW_CORRUPTION",
]

_APPROVAL_STATUSES = frozenset({"not_requested", "pending", "approved"})
_REVIEW_OUTCOMES = ("REVIEWED", "DEFERRED", "MONITOR", "NO_ACTION")
_RECOMMENDATION_DECISIONS = ("ACCEPTED", "MODIFIED", "REJECTED", "NOT_APPLICABLE")
_FOLLOW_UP_STATUSES = ("NOT_CREATED", "CREATED", "COMPLETED", "NOT_APPLICABLE")
_STOP_CRITERIA = (
    "WORKLOAD_OVERLOAD",
    "TIMING_SEMANTICS_CONFUSING",
    "HIGH_UNUSABLE_EVIDENCE",
    "PRIVACY_OR_SECURITY_ISSUE",
    "WORKFLOW_CORRUPTION",
)
_SANITIZED_FEEDBACK_CODES = frozenset(
    {
        "EVIDENCE_CLEAR",
        "EVIDENCE_INSUFFICIENT",
        "TIMING_CLEAR",
        "TIMING_UNCLEAR",
        "WORKLOAD_CONSTRAINED",
        "FOLLOW_UP_CONTEXT_NEEDED",
    }
)
_RECOMMENDATION_REASON_CODES = frozenset(
    {
        "EVIDENCE_RELEVANT",
        "EVIDENCE_INSUFFICIENT",
        "TIMING_UNCLEAR",
        "CAPACITY_CONSTRAINT",
        "FOLLOW_UP_CONTEXT_NEEDED",
        "NOT_ACTIONABLE",
    }
)
_OVERRIDE_REASON_CODES = frozenset(
    {
        "HUMAN_CONTEXT_OVERRIDE",
        "TIMING_INTERPRETATION_OVERRIDE",
        "EVIDENCE_QUALITY_OVERRIDE",
        "WORKLOAD_OVERRIDE",
    }
)
_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


class RMPilotProtocolError(ValueError):
    """A pilot protocol request crosses a declared safety or schema boundary."""


@dataclass(frozen=True)
class PilotScope:
    """Human-supplied pilot scope placeholders, never a workload recommendation."""

    participating_rm_count: int | None = None
    synthetic_cohort_reference: str | None = None
    duration_period_count: int | None = None
    review_capacity_per_period: int | None = None
    approval_status: ApprovalStatus = "not_requested"
    approval_reference: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("participating_rm_count", self.participating_rm_count),
            ("duration_period_count", self.duration_period_count),
            ("review_capacity_per_period", self.review_capacity_per_period),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value <= 0
            ):
                raise RMPilotProtocolError(f"{field_name} must be a positive integer or None")
        _validate_optional_reference(self.synthetic_cohort_reference, "synthetic_cohort_reference")
        if self.approval_status not in _APPROVAL_STATUSES:
            raise RMPilotProtocolError("approval_status must be not_requested, pending, or approved")
        _validate_optional_reference(self.approval_reference, "approval_reference")
        if self.approval_status == "approved":
            if self.approval_reference is None:
                raise RMPilotProtocolError("approved pilot scope requires an approval_reference")
            if any(
                value is None
                for value in (
                    self.participating_rm_count,
                    self.synthetic_cohort_reference,
                    self.duration_period_count,
                    self.review_capacity_per_period,
                )
            ):
                raise RMPilotProtocolError(
                    "approved pilot scope requires participating RMs, cohort, duration, and capacity"
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "participating_rm_count": self.participating_rm_count,
            "synthetic_cohort_reference": self.synthetic_cohort_reference,
            "duration_period_count": self.duration_period_count,
            "review_capacity_per_period": self.review_capacity_per_period,
            "approval_status": self.approval_status,
            "approval_reference": self.approval_reference,
            "automatically_selected": False,
            "bank_standard_claimed": False,
        }


@dataclass(frozen=True)
class RMPilotProtocol:
    """Repository-safe pilot protocol: synthetic only and not initiated."""

    protocol_id: str = "RM_PILOT_PROTOCOL_V1"
    scope: PilotScope = field(default_factory=PilotScope)
    schema_version: str = RM_PILOT_PROTOCOL_SCHEMA_VERSION
    protocol_status: str = "protocol_only_not_initiated"
    data_scope: str = "synthetic_pseudonymous_cases_only"
    actual_rm_recruitment_performed: bool = False
    actual_customer_data_processed: bool = False
    external_notification_delivery_enabled: bool = False
    automatic_alert_or_financial_decision_enabled: bool = False
    automatic_policy_approval: bool = False
    automatic_capacity_approval: bool = False
    customer_financial_outcome_improvement_claimed: bool = False
    raw_feedback_public_export_allowed: bool = False

    def __post_init__(self) -> None:
        _validate_reference(self.protocol_id, "protocol_id")
        if self.schema_version != RM_PILOT_PROTOCOL_SCHEMA_VERSION:
            raise RMPilotProtocolError("unexpected pilot protocol schema version")
        if self.protocol_status != "protocol_only_not_initiated":
            raise RMPilotProtocolError("this repository contract must remain protocol_only_not_initiated")
        if self.data_scope != "synthetic_pseudonymous_cases_only":
            raise RMPilotProtocolError("pilot protocol is limited to synthetic pseudonymous cases")
        if any(
            (
                self.actual_rm_recruitment_performed,
                self.actual_customer_data_processed,
                self.external_notification_delivery_enabled,
                self.automatic_alert_or_financial_decision_enabled,
                self.automatic_policy_approval,
                self.automatic_capacity_approval,
                self.customer_financial_outcome_improvement_claimed,
                self.raw_feedback_public_export_allowed,
            )
        ):
            raise RMPilotProtocolError("the public protocol cannot enable pilot execution or approvals")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "protocol_id": self.protocol_id,
            "protocol_status": self.protocol_status,
            "data_scope": self.data_scope,
            "scope": self.scope.to_dict(),
            "execution_boundary": {
                "actual_rm_recruitment_performed": self.actual_rm_recruitment_performed,
                "actual_customer_data_processed": self.actual_customer_data_processed,
                "external_notification_delivery_enabled": self.external_notification_delivery_enabled,
                "automatic_alert_or_financial_decision_enabled": self.automatic_alert_or_financial_decision_enabled,
            },
            "governance_boundary": {
                "automatic_policy_approval": self.automatic_policy_approval,
                "automatic_capacity_approval": self.automatic_capacity_approval,
                "human_governance_review_required": True,
            },
            "claim_boundary": {
                "customer_financial_outcome_improvement_claimed": self.customer_financial_outcome_improvement_claimed,
                "raw_feedback_public_export_allowed": self.raw_feedback_public_export_allowed,
            },
            "limitations": [
                "This is a synthetic protocol, not evidence of RM productivity or customer outcomes.",
                "Pilot scope values require human governance approval outside this public repository.",
            ],
        }


@dataclass(frozen=True)
class PilotMeasurement:
    """One synthetic, pseudonymous RM-review measurement without customer PII."""

    case_reference: str
    alert_reference: str
    reviewer_pseudonymous_reference: str
    review_period: str
    evidence_usefulness_rating: int | None
    actionability_rating: int | None
    perceived_timeliness_rating: int | None
    review_completed: bool
    review_completion_seconds: int | None
    review_outcome: ReviewOutcome
    recommendation_decision: RecommendationDecision
    recommendation_reason_code: str | None
    follow_up_status: FollowUpStatus
    insufficient_evidence: bool
    human_override: bool = False
    override_reason_code: str | None = None
    sanitized_feedback_code: str | None = None
    private_feedback_exists: bool = False
    schema_version: str = RM_PILOT_MEASUREMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field_name, value in (
            ("case_reference", self.case_reference),
            ("alert_reference", self.alert_reference),
            ("reviewer_pseudonymous_reference", self.reviewer_pseudonymous_reference),
            ("review_period", self.review_period),
        ):
            _validate_reference(value, field_name)
        for field_name, value in (
            ("evidence_usefulness_rating", self.evidence_usefulness_rating),
            ("actionability_rating", self.actionability_rating),
            ("perceived_timeliness_rating", self.perceived_timeliness_rating),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value not in {1, 2, 3, 4, 5}
            ):
                raise RMPilotProtocolError(f"{field_name} must be an integer from 1 to 5 or None")
        if not isinstance(self.review_completed, bool):
            raise RMPilotProtocolError("review_completed must be a boolean")
        if self.review_completion_seconds is not None and (
            isinstance(self.review_completion_seconds, bool)
            or not isinstance(self.review_completion_seconds, int)
            or self.review_completion_seconds < 0
        ):
            raise RMPilotProtocolError("review_completion_seconds must be a non-negative integer or None")
        if self.review_completion_seconds is not None and not self.review_completed:
            raise RMPilotProtocolError("review completion time requires review_completed")
        if self.review_outcome not in _REVIEW_OUTCOMES:
            raise RMPilotProtocolError("review_outcome is invalid")
        if self.recommendation_decision not in _RECOMMENDATION_DECISIONS:
            raise RMPilotProtocolError("recommendation_decision is invalid")
        if self.follow_up_status not in _FOLLOW_UP_STATUSES:
            raise RMPilotProtocolError("follow_up_status is invalid")
        if not isinstance(self.insufficient_evidence, bool):
            raise RMPilotProtocolError("insufficient_evidence must be a boolean")
        _validate_optional_code(
            self.recommendation_reason_code,
            "recommendation_reason_code",
            _RECOMMENDATION_REASON_CODES,
        )
        if self.recommendation_decision in {"MODIFIED", "REJECTED"} and self.recommendation_reason_code is None:
            raise RMPilotProtocolError(
                "modified or rejected recommendation requires a sanitized reason code"
            )
        if not isinstance(self.human_override, bool):
            raise RMPilotProtocolError("human_override must be a boolean")
        _validate_optional_code(self.override_reason_code, "override_reason_code", _OVERRIDE_REASON_CODES)
        if self.human_override != (self.override_reason_code is not None):
            raise RMPilotProtocolError("human_override and override_reason_code must agree")
        _validate_optional_code(
            self.sanitized_feedback_code,
            "sanitized_feedback_code",
            _SANITIZED_FEEDBACK_CODES,
        )
        if not isinstance(self.private_feedback_exists, bool):
            raise RMPilotProtocolError("private_feedback_exists must be a boolean")
        if self.schema_version != RM_PILOT_MEASUREMENT_SCHEMA_VERSION:
            raise RMPilotProtocolError("unexpected pilot measurement schema version")

    @property
    def measurement_key(self) -> tuple[str, str, str]:
        """One measurement per pseudonymous case/alert/review-period tuple."""

        return (self.case_reference, self.alert_reference, self.review_period)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "case_reference": self.case_reference,
            "alert_reference": self.alert_reference,
            "reviewer_pseudonymous_reference": self.reviewer_pseudonymous_reference,
            "review_period": self.review_period,
            "evidence_usefulness_rating": self.evidence_usefulness_rating,
            "actionability_rating": self.actionability_rating,
            "perceived_timeliness_rating": self.perceived_timeliness_rating,
            "review_completed": self.review_completed,
            "review_completion_seconds": self.review_completion_seconds,
            "review_outcome": self.review_outcome,
            "recommendation_decision": self.recommendation_decision,
            "recommendation_reason_code": self.recommendation_reason_code,
            "follow_up_status": self.follow_up_status,
            "insufficient_evidence": self.insufficient_evidence,
            "human_override": self.human_override,
            "override_reason_code": self.override_reason_code,
            "sanitized_feedback_code": self.sanitized_feedback_code,
            "private_feedback_exists": self.private_feedback_exists,
            "public_raw_feedback_export_allowed": False,
        }


@dataclass(frozen=True)
class PilotMeasurementSummary:
    """Aggregate process evidence only; it cannot establish a customer outcome."""

    declared_review_period_count: int
    measurement_count: int
    review_completed_count: int
    review_outcome_counts: dict[str, int]
    recommendation_decision_counts: dict[str, int]
    follow_up_status_counts: dict[str, int]
    insufficient_evidence_count: int
    rating_summary: dict[str, dict[str, float | int | None]]
    review_completion_seconds_median: float | None
    schema_version: str = RM_PILOT_MEASUREMENT_SCHEMA_VERSION

    @property
    def alerts_reviewed_per_period(self) -> float:
        return round(self.review_completed_count / self.declared_review_period_count, 4)

    @property
    def insufficient_evidence_frequency(self) -> float:
        if self.measurement_count == 0:
            return 0.0
        return round(self.insufficient_evidence_count / self.measurement_count, 4)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "declared_review_period_count": self.declared_review_period_count,
            "measurement_count": self.measurement_count,
            "review_completed_count": self.review_completed_count,
            "alerts_reviewed_per_period": self.alerts_reviewed_per_period,
            "review_outcome_counts": dict(self.review_outcome_counts),
            "recommendation_decision_counts": dict(self.recommendation_decision_counts),
            "follow_up_status_counts": dict(self.follow_up_status_counts),
            "insufficient_evidence_count": self.insufficient_evidence_count,
            "insufficient_evidence_frequency": self.insufficient_evidence_frequency,
            "rating_summary": self.rating_summary,
            "review_completion_seconds_median": self.review_completion_seconds_median,
            "customer_financial_outcome_improvement_proven": False,
            "limitations": [
                "Process measurements are human-review evidence only.",
                "No customer financial outcome or intervention effect is measured here.",
            ],
        }


@dataclass(frozen=True)
class PilotStopSignal:
    """A human-reported stop concern; detection never stops a pilot automatically."""

    criterion: StopCriterion
    observed: bool
    evidence_reference: str | None = None

    def __post_init__(self) -> None:
        if self.criterion not in _STOP_CRITERIA:
            raise RMPilotProtocolError("unsupported pilot stop criterion")
        if not isinstance(self.observed, bool):
            raise RMPilotProtocolError("observed must be a boolean")
        _validate_optional_reference(self.evidence_reference, "evidence_reference")
        if self.observed and self.evidence_reference is None:
            raise RMPilotProtocolError("an observed stop signal requires an evidence_reference")

    def to_dict(self) -> dict[str, object]:
        return {
            "criterion": self.criterion,
            "observed": self.observed,
            "evidence_reference": self.evidence_reference,
            "automatic_stop": False,
        }


@dataclass(frozen=True)
class PilotGovernanceReview:
    """A human decision checkpoint, not an execution or approval service."""

    scope_approval_status: ApprovalStatus
    active_stop_criteria: tuple[str, ...]
    human_governance_review_required: bool = True
    automatic_pilot_start_allowed: bool = False
    automatic_pilot_stop: bool = False
    automatic_policy_approval: bool = False
    automatic_capacity_approval: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "scope_approval_status": self.scope_approval_status,
            "active_stop_criteria": list(self.active_stop_criteria),
            "human_governance_review_required": self.human_governance_review_required,
            "automatic_pilot_start_allowed": self.automatic_pilot_start_allowed,
            "automatic_pilot_stop": self.automatic_pilot_stop,
            "automatic_policy_approval": self.automatic_policy_approval,
            "automatic_capacity_approval": self.automatic_capacity_approval,
            "actual_pilot_execution_authorized": False,
        }


def build_pilot_measurement_summary(
    measurements: Iterable[PilotMeasurement],
    *,
    declared_review_period_count: int,
) -> PilotMeasurementSummary:
    """Summarize synthetic measurements with exact one-record-per-period checks."""

    if (
        isinstance(declared_review_period_count, bool)
        or not isinstance(declared_review_period_count, int)
        or declared_review_period_count <= 0
    ):
        raise RMPilotProtocolError("declared_review_period_count must be a positive integer")
    records = tuple(measurements)
    if any(not isinstance(record, PilotMeasurement) for record in records):
        raise RMPilotProtocolError("measurements must be PilotMeasurement instances")
    keys = tuple(record.measurement_key for record in records)
    if len(keys) != len(set(keys)):
        raise RMPilotProtocolError("pilot measurements must be unique per case, alert, and review period")
    return PilotMeasurementSummary(
        declared_review_period_count=declared_review_period_count,
        measurement_count=len(records),
        review_completed_count=sum(record.review_completed for record in records),
        review_outcome_counts=_counts(records, "review_outcome", _REVIEW_OUTCOMES),
        recommendation_decision_counts=_counts(
            records,
            "recommendation_decision",
            _RECOMMENDATION_DECISIONS,
        ),
        follow_up_status_counts=_counts(records, "follow_up_status", _FOLLOW_UP_STATUSES),
        insufficient_evidence_count=sum(record.insufficient_evidence for record in records),
        rating_summary={
            "evidence_usefulness": _rating_summary(
                tuple(record.evidence_usefulness_rating for record in records)
            ),
            "review_actionability": _rating_summary(
                tuple(record.actionability_rating for record in records)
            ),
            "perceived_timeliness": _rating_summary(
                tuple(record.perceived_timeliness_rating for record in records)
            ),
        },
        review_completion_seconds_median=_median_or_none(
            tuple(
                record.review_completion_seconds
                for record in records
                if record.review_completion_seconds is not None
            )
        ),
    )


def build_pilot_governance_review(
    scope: PilotScope,
    stop_signals: Iterable[PilotStopSignal],
) -> PilotGovernanceReview:
    """Return a human-review checkpoint without approving or starting anything."""

    signals = tuple(stop_signals)
    if any(not isinstance(signal, PilotStopSignal) for signal in signals):
        raise RMPilotProtocolError("stop_signals must be PilotStopSignal instances")
    criteria = tuple(signal.criterion for signal in signals if signal.observed)
    if len(criteria) != len(set(criteria)):
        raise RMPilotProtocolError("observed stop criteria must be unique")
    return PilotGovernanceReview(
        scope_approval_status=scope.approval_status,
        active_stop_criteria=criteria,
    )


def pilot_measurement_schema_template() -> dict[str, object]:
    """Return a source-free schema template, not a row-level pilot export."""

    return {
        "schema_version": RM_PILOT_MEASUREMENT_SCHEMA_VERSION,
        "scope": "synthetic_pilot_measurement_contract_only",
        "record_identity": ["case_reference", "alert_reference", "review_period"],
        "pseudonymous_reference_fields": [
            "case_reference",
            "alert_reference",
            "reviewer_pseudonymous_reference",
        ],
        "measurement_fields": {
            "ratings": [
                "evidence_usefulness_rating",
                "actionability_rating",
                "perceived_timeliness_rating",
            ],
            "review_process": [
                "review_completed",
                "review_completion_seconds",
                "review_outcome",
                "recommendation_decision",
                "recommendation_reason_code",
                "follow_up_status",
                "insufficient_evidence",
            ],
            "human_feedback": [
                "human_override",
                "override_reason_code",
                "sanitized_feedback_code",
                "private_feedback_exists",
            ],
        },
        "process_metrics": [
            "evidence_usefulness_rating",
            "review_actionability_rating",
            "perceived_timeliness_rating",
            "review_completion_time",
            "alerts_reviewed_per_period",
            "defer_monitor_no_action_counts",
            "recommendation_decision_reason",
            "follow_up_created_completed",
            "insufficient_evidence_frequency",
        ],
        "privacy": {
            "customer_pii_fields_allowed": False,
            "raw_free_text_stored_in_public_repository": False,
            "raw_feedback_public_export_allowed": False,
            "sanitized_code_only_in_public_contract": True,
        },
        "outcome_boundary": {
            "customer_financial_outcome_improvement_primary_success": False,
            "longer_term_outcome_requires_separate_governance_and_duration": True,
        },
    }


def pilot_governance_checklist_template() -> dict[str, object]:
    """List the required human checkpoint items without claiming completion."""

    return {
        "schema_version": RM_PILOT_PROTOCOL_SCHEMA_VERSION,
        "status": "not_ready_for_actual_pilot_execution",
        "scope_parameters": {
            "participating_rms": "human_approval_required",
            "synthetic_customer_cohort": "human_approval_required",
            "duration": "human_approval_required",
            "review_capacity": "human_approval_required",
        },
        "stop_criteria": list(_STOP_CRITERIA),
        "required_human_reviews": [
            "scope_and_capacity",
            "timing_semantics",
            "evidence_usability",
            "privacy_and_security",
            "workflow_integrity",
            "post_pilot_policy_and_capacity_decision",
        ],
        "automatic_approvals": {
            "policy": False,
            "capacity": False,
            "pilot_start": False,
            "pilot_stop": False,
        },
        "execution_boundary": {
            "actual_rm_recruitment": False,
            "actual_customer_data": False,
            "external_notification_delivery": False,
        },
    }


def export_pilot_metadata(
    payload: dict[str, object],
    output_path: Path,
    *,
    allowed_root: Path | None = None,
) -> Path:
    """Atomically write protocol metadata below an injected Post-P0 root only."""

    destination = Path(output_path)
    root = Path(allowed_root) if allowed_root is not None else RM_PILOT_ARTIFACT_DIR
    _assert_pilot_metadata_path(destination, root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, destination)
    except OSError:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
        raise
    return destination


def _counts(
    records: tuple[PilotMeasurement, ...],
    attribute: str,
    values: tuple[str, ...],
) -> dict[str, int]:
    counts = Counter(str(getattr(record, attribute)) for record in records)
    return {value: counts[value] for value in values}


def _rating_summary(values: tuple[int | None, ...]) -> dict[str, float | int | None]:
    observed = tuple(value for value in values if value is not None)
    return {
        "observed_count": len(observed),
        "mean": None if not observed else round(sum(observed) / len(observed), 4),
    }


def _median_or_none(values: tuple[int, ...]) -> float | None:
    return None if not values else float(median(values))


def _validate_optional_reference(value: str | None, field_name: str) -> None:
    if value is not None:
        _validate_reference(value, field_name)


def _validate_reference(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not _REFERENCE_PATTERN.fullmatch(value):
        raise RMPilotProtocolError(
            f"{field_name} must be an opaque letters-digits-underscore-hyphen reference"
        )


def _validate_optional_code(value: str | None, field_name: str, allowed: frozenset[str]) -> None:
    if value is not None and value not in allowed:
        raise RMPilotProtocolError(f"{field_name} must be a supported sanitized code or None")


def _assert_pilot_metadata_path(destination: Path, allowed_root: Path) -> None:
    resolved_destination = destination.resolve()
    resolved_root = allowed_root.resolve()
    forbidden_roots = (
        settings.DATA_RAW_DIR.resolve(),
        settings.DATA_PROCESSED_DIR.resolve(),
        settings.DATA_DEMO_DIR.resolve(),
    )
    if any(_is_within(resolved_destination, forbidden) for forbidden in forbidden_roots):
        raise RMPilotProtocolError("pilot metadata must not write to canonical data paths")
    if not _is_within(resolved_destination, resolved_root):
        raise RMPilotProtocolError("pilot metadata must be written under its injected Post-P0 root")


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True
