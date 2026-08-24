"""Provider- and UI-independent triage universe contract.

This module turns one fixed-as-of policy assessment per customer into one
explicit triage disposition.  Eligibility remains a policy signal: it is not
an RM queue decision, a ranking, a case creation, or a notification.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from config import settings
from src.demo_policy import HistoricalLandmarkContext, PolicyAssessment, PolicyTimingEvidence
from src.prospective_signals import SignalSnapshot


TRIAGE_UNIVERSE_SCHEMA_VERSION = "triage_universe.v1"
TRIAGE_DISPOSITIONS = (
    "ELIGIBLE_PRIORITY",
    "ELIGIBLE_REVIEW",
    "MONITOR_ONLY",
    "NO_ACTIONABLE_SIGNAL",
    "INSUFFICIENT_EVIDENCE",
    "DATA_UNAVAILABLE",
)
TRIAGE_OPERATIONAL_LABELS = ("Priority Review", "Review", "Monitor", "No Signal")
TRIAGE_REASON_COPY = {
    "CURRENT_STATUS_CONCERNING": "Current observed status meets the demo policy condition.",
    "PERSISTENT_FINANCIAL_STRESS": "A current financial stress factor was also observed previously.",
    "MULTIPLE_CURRENT_FINANCIAL_STRESS_FACTORS": "Multiple current financial stress factors are present.",
    "CURRENT_FINANCIAL_STRESS_FACTOR": "A current financial stress factor is present.",
    "POLICY_RULE_MET": "A declared demo policy rule is currently met.",
    "POLICY_COOLDOWN_ACTIVE": "The policy signal is in its configured cooldown period.",
    "NO_POLICY_RULE_MET": "No declared demo policy rule is currently met.",
    "NO_REFERENCE_NEIGHBORS": "No reference neighbors are available for sufficient evidence.",
    "SIGNAL_INPUT_MISSING": "No policy and signal input was supplied for this fixed triage run.",
}

TriageDisposition = Literal[
    "ELIGIBLE_PRIORITY",
    "ELIGIBLE_REVIEW",
    "MONITOR_ONLY",
    "NO_ACTIONABLE_SIGNAL",
    "INSUFFICIENT_EVIDENCE",
    "DATA_UNAVAILABLE",
]
TriageOperationalLabel = Literal["Priority Review", "Review", "Monitor", "No Signal"]

_RULE_REASON_CODES = {
    "current_stress_or_delinquent": "CURRENT_STATUS_CONCERNING",
    "persistent_financial_stress": "PERSISTENT_FINANCIAL_STRESS",
    "multiple_current_financial_stress_factors": "MULTIPLE_CURRENT_FINANCIAL_STRESS_FACTORS",
    "current_financial_stress_factor": "CURRENT_FINANCIAL_STRESS_FACTOR",
}


@dataclass(frozen=True)
class TriageDecisionInput:
    """One prospective snapshot and policy assessment for a single customer."""

    customer_id: str
    signal_snapshot: SignalSnapshot
    policy_assessment: PolicyAssessment
    existing_open_case_reference: str | None = None

    def __post_init__(self) -> None:
        customer_id = str(self.customer_id)
        if not customer_id.strip():
            raise ValueError("customer_id must be non-empty")
        if self.signal_snapshot.customer_id != customer_id:
            raise ValueError("signal_snapshot customer_id must match customer_id")
        if self.policy_assessment.customer_id != customer_id:
            raise ValueError("policy_assessment customer_id must match customer_id")
        if self.policy_assessment.as_of_month != self.signal_snapshot.as_of_month:
            raise ValueError("policy assessment and signal snapshot as_of_month must match")
        if not self.policy_assessment.triage_input_only:
            raise ValueError("policy assessment must be marked as triage input only")
        if self.policy_assessment.rm_queue_selection or self.policy_assessment.alert_creation:
            raise ValueError("policy assessment must not contain queue selection or alert creation")
        if self.existing_open_case_reference is not None and not str(
            self.existing_open_case_reference
        ).strip():
            raise ValueError("existing_open_case_reference must be non-empty or None")


@dataclass(frozen=True)
class TriageTimingEvidenceReference:
    """Prospective signal timing reference, separate from historical context."""

    source: str
    candidate_month: int
    evaluation_status: str
    lead_time_months: None = None

    @classmethod
    def from_policy_timing(cls, timing: PolicyTimingEvidence) -> "TriageTimingEvidenceReference":
        return cls(
            source=timing.source,
            candidate_month=timing.candidate_month,
            evaluation_status=timing.evaluation_status,
            lead_time_months=timing.lead_time_months,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "candidate_month": self.candidate_month,
            "evaluation_status": self.evaluation_status,
            "lead_time_months": self.lead_time_months,
            "lead_time_unit": "months",
        }


@dataclass(frozen=True)
class TriageCandidate:
    """Exactly one primary, non-queue disposition for one universe customer."""

    customer_id: str
    triage_as_of_month: int
    signal_as_of_month: int
    signal_run_id: str
    policy_id: str | None
    policy_version: str | None
    eligible_for_review: bool | None
    operational_label: TriageOperationalLabel
    primary_disposition: TriageDisposition
    why_now_reason_codes: tuple[str, ...]
    timing_bucket: str
    timing_evidence_reference: TriageTimingEvidenceReference | None
    signal_persistence: str
    signal_stability: str
    evidence_quality: str
    evidence_sufficiency: str
    data_availability_status: str
    existing_open_case_reference: str | None
    historical_landmark_context: HistoricalLandmarkContext | None

    def __post_init__(self) -> None:
        if not str(self.customer_id).strip() or not str(self.signal_run_id).strip():
            raise ValueError("customer_id and signal_run_id must be non-empty")
        _validate_month(self.triage_as_of_month, "triage_as_of_month")
        _validate_month(self.signal_as_of_month, "signal_as_of_month")
        if self.operational_label not in TRIAGE_OPERATIONAL_LABELS:
            raise ValueError(f"operational_label must be one of {TRIAGE_OPERATIONAL_LABELS}")
        if self.primary_disposition not in TRIAGE_DISPOSITIONS:
            raise ValueError(f"primary_disposition must be one of {TRIAGE_DISPOSITIONS}")
        if not self.why_now_reason_codes or len(self.why_now_reason_codes) != len(
            set(self.why_now_reason_codes)
        ):
            raise ValueError("why_now_reason_codes must be non-empty and unique")
        unknown_reason_codes = sorted(set(self.why_now_reason_codes) - set(TRIAGE_REASON_COPY))
        if unknown_reason_codes:
            raise ValueError(f"unknown triage reason codes: {unknown_reason_codes}")
        if self.primary_disposition == "DATA_UNAVAILABLE":
            if self.eligible_for_review is not None or self.operational_label != "No Signal":
                raise ValueError("data-unavailable candidates cannot claim a policy signal")
        if self.primary_disposition == "INSUFFICIENT_EVIDENCE" and self.data_availability_status != "available":
            raise ValueError("insufficient evidence requires available source data")
        if self.timing_evidence_reference is not None and (
            self.timing_evidence_reference.candidate_month != self.signal_as_of_month
        ):
            raise ValueError("timing evidence candidate_month must match signal_as_of_month")

    def to_dict(self) -> dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "triage_as_of_month": self.triage_as_of_month,
            "signal_as_of_month": self.signal_as_of_month,
            "signal_run_id": self.signal_run_id,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "eligible_for_review": self.eligible_for_review,
            "policy_eligibility": self.eligible_for_review,
            "operational_label": self.operational_label,
            "primary_disposition": self.primary_disposition,
            "why_now_reason_codes": list(self.why_now_reason_codes),
            "why_now_reason_copy": [TRIAGE_REASON_COPY[code] for code in self.why_now_reason_codes],
            "timing_bucket": self.timing_bucket,
            "timing_evidence_reference": (
                None
                if self.timing_evidence_reference is None
                else self.timing_evidence_reference.to_dict()
            ),
            "signal_persistence": self.signal_persistence,
            "signal_stability": self.signal_stability,
            "evidence_quality": self.evidence_quality,
            "evidence_sufficiency": self.evidence_sufficiency,
            "data_availability_status": self.data_availability_status,
            "existing_open_case_reference": self.existing_open_case_reference,
            "historical_landmark_context": (
                None
                if self.historical_landmark_context is None
                else self.historical_landmark_context.to_dict()
            ),
            "scope": {
                "policy_eligibility_only": True,
                "rm_queue_selection": False,
                "alert_creation": False,
            },
        }


@dataclass(frozen=True)
class TriageUniverseReconciliation:
    """Exact result coverage and explicit missing-input information."""

    expected_customer_count: int
    received_decision_input_count: int
    result_customer_count: int
    missing_decision_input_customer_ids: tuple[str, ...]
    result_missing_customer_ids: tuple[str, ...]
    result_unexpected_customer_ids: tuple[str, ...]
    duplicate_result_customer_ids: tuple[str, ...]

    @property
    def result_coverage_is_exact(self) -> bool:
        return not (
            self.result_missing_customer_ids
            or self.result_unexpected_customer_ids
            or self.duplicate_result_customer_ids
        )

    @property
    def decision_input_is_complete(self) -> bool:
        return not self.missing_decision_input_customer_ids

    def to_dict(self) -> dict[str, object]:
        return {
            "expected_customer_count": self.expected_customer_count,
            "received_decision_input_count": self.received_decision_input_count,
            "result_customer_count": self.result_customer_count,
            "missing_decision_input_customer_ids": list(self.missing_decision_input_customer_ids),
            "result_missing_customer_ids": list(self.result_missing_customer_ids),
            "result_unexpected_customer_ids": list(self.result_unexpected_customer_ids),
            "duplicate_result_customer_ids": list(self.duplicate_result_customer_ids),
            "result_coverage_is_exact": self.result_coverage_is_exact,
            "decision_input_is_complete": self.decision_input_is_complete,
        }


@dataclass(frozen=True)
class TriageUniverse:
    """One fixed-as-of triage record for every expected customer ID."""

    triage_as_of_month: int
    signal_run_id: str
    candidates: tuple[TriageCandidate, ...]
    reconciliation: TriageUniverseReconciliation
    schema_version: str = TRIAGE_UNIVERSE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validate_month(self.triage_as_of_month, "triage_as_of_month")
        if not str(self.signal_run_id).strip():
            raise ValueError("signal_run_id must be non-empty")
        ordered = tuple(sorted(self.candidates, key=lambda candidate: candidate.customer_id))
        candidate_ids = [candidate.customer_id for candidate in ordered]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("triage universe cannot contain duplicate customer IDs")
        if any(candidate.triage_as_of_month != self.triage_as_of_month for candidate in ordered):
            raise ValueError("all candidates must share triage_as_of_month")
        if any(candidate.signal_run_id != self.signal_run_id for candidate in ordered):
            raise ValueError("all candidates must share signal_run_id")
        if self.schema_version != TRIAGE_UNIVERSE_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {TRIAGE_UNIVERSE_SCHEMA_VERSION}")
        object.__setattr__(self, "candidates", ordered)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "triage_as_of_month": self.triage_as_of_month,
            "signal_run_id": self.signal_run_id,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "reconciliation": self.reconciliation.to_dict(),
            "selection": {
                "rm_ranking": False,
                "rm_queue_selection": False,
                "alert_creation": False,
            },
        }


def build_triage_universe(
    *,
    expected_customer_ids: Sequence[str],
    triage_as_of_month: int,
    signal_run_id: str,
    decision_inputs: Iterable[TriageDecisionInput],
) -> TriageUniverse:
    """Build exact universe coverage, using explicit fallback for missing input.

    An input is never silently omitted: unexpected and duplicate IDs are
    rejected, while an expected ID with no supplied input receives the
    ``DATA_UNAVAILABLE`` primary disposition.
    """

    expected_ids = _normalize_expected_ids(expected_customer_ids)
    _validate_month(triage_as_of_month, "triage_as_of_month")
    if not str(signal_run_id).strip():
        raise ValueError("signal_run_id must be non-empty")

    normalized_inputs = tuple(decision_inputs)
    _validate_decision_inputs(normalized_inputs, expected_ids, triage_as_of_month)
    inputs_by_customer = {decision_input.customer_id: decision_input for decision_input in normalized_inputs}
    missing_input_ids = tuple(customer_id for customer_id in expected_ids if customer_id not in inputs_by_customer)
    candidates = tuple(
        _candidate_from_input(
            decision_input=inputs_by_customer[customer_id],
            triage_as_of_month=triage_as_of_month,
            signal_run_id=signal_run_id,
        )
        if customer_id in inputs_by_customer
        else _data_unavailable_candidate(
            customer_id=customer_id,
            triage_as_of_month=triage_as_of_month,
            signal_run_id=signal_run_id,
        )
        for customer_id in expected_ids
    )
    reconciliation = _reconcile_triage_universe(
        expected_ids=expected_ids,
        candidates=candidates,
        received_decision_input_count=len(normalized_inputs),
        missing_input_ids=missing_input_ids,
    )
    return TriageUniverse(
        triage_as_of_month=triage_as_of_month,
        signal_run_id=signal_run_id,
        candidates=candidates,
        reconciliation=reconciliation,
    )


def _candidate_from_input(
    *,
    decision_input: TriageDecisionInput,
    triage_as_of_month: int,
    signal_run_id: str,
) -> TriageCandidate:
    snapshot = decision_input.signal_snapshot
    assessment = decision_input.policy_assessment
    reason_codes = _reason_codes_for_assessment(assessment)
    timing_reference = TriageTimingEvidenceReference.from_policy_timing(
        assessment.prospective_timing_evidence
    )
    if snapshot.matched_count == 0:
        primary_disposition: TriageDisposition = "INSUFFICIENT_EVIDENCE"
        reason_codes = _unique_reason_codes((*reason_codes, "NO_REFERENCE_NEIGHBORS"))
        evidence_quality = "insufficient"
        evidence_sufficiency = "insufficient"
    else:
        primary_disposition = _primary_disposition(assessment)
        evidence_quality = "sufficient"
        evidence_sufficiency = "sufficient"
    return TriageCandidate(
        customer_id=decision_input.customer_id,
        triage_as_of_month=triage_as_of_month,
        signal_as_of_month=snapshot.as_of_month,
        signal_run_id=signal_run_id,
        policy_id=assessment.policy_id,
        policy_version=assessment.policy_version,
        eligible_for_review=assessment.eligibility,
        operational_label=assessment.operational_label,
        primary_disposition=primary_disposition,
        why_now_reason_codes=reason_codes,
        timing_bucket=_timing_bucket(timing_reference),
        timing_evidence_reference=timing_reference,
        signal_persistence=_signal_persistence(snapshot),
        signal_stability=_signal_stability(snapshot),
        evidence_quality=evidence_quality,
        evidence_sufficiency=evidence_sufficiency,
        data_availability_status="available",
        existing_open_case_reference=decision_input.existing_open_case_reference,
        historical_landmark_context=assessment.historical_landmark_context,
    )


def _data_unavailable_candidate(
    *,
    customer_id: str,
    triage_as_of_month: int,
    signal_run_id: str,
) -> TriageCandidate:
    return TriageCandidate(
        customer_id=customer_id,
        triage_as_of_month=triage_as_of_month,
        signal_as_of_month=triage_as_of_month,
        signal_run_id=signal_run_id,
        policy_id=None,
        policy_version=None,
        eligible_for_review=None,
        operational_label="No Signal",
        primary_disposition="DATA_UNAVAILABLE",
        why_now_reason_codes=("SIGNAL_INPUT_MISSING",),
        timing_bucket="no_timing_evidence",
        timing_evidence_reference=None,
        signal_persistence="not_available",
        signal_stability="not_available",
        evidence_quality="unavailable",
        evidence_sufficiency="unknown",
        data_availability_status="signal_input_missing",
        existing_open_case_reference=None,
        historical_landmark_context=None,
    )


def _primary_disposition(assessment: PolicyAssessment) -> TriageDisposition:
    if assessment.eligibility and assessment.operational_label == "Priority Review":
        return "ELIGIBLE_PRIORITY"
    if assessment.eligibility and assessment.operational_label == "Review":
        return "ELIGIBLE_REVIEW"
    if assessment.eligibility or assessment.matched_rule_ids:
        return "MONITOR_ONLY"
    return "NO_ACTIONABLE_SIGNAL"


def _reason_codes_for_assessment(assessment: PolicyAssessment) -> tuple[str, ...]:
    reason_codes = [
        _RULE_REASON_CODES.get(rule_id, "POLICY_RULE_MET") for rule_id in assessment.matched_rule_ids
    ]
    if assessment.cooldown_applied:
        reason_codes.append("POLICY_COOLDOWN_ACTIVE")
    if not reason_codes:
        reason_codes.append("NO_POLICY_RULE_MET")
    return _unique_reason_codes(reason_codes)


def _timing_bucket(reference: TriageTimingEvidenceReference) -> str:
    if reference.source != "prospective_signal":
        raise ValueError("policy timing evidence must have source=prospective_signal")
    return f"prospective_timing_{reference.evaluation_status}"


def _signal_persistence(snapshot: SignalSnapshot) -> str:
    if snapshot.persistent_financial_stress_factors:
        return "persistent"
    if snapshot.financial_stress_factors:
        return "not_persistent"
    return "no_current_factor"


def _signal_stability(snapshot: SignalSnapshot) -> str:
    if snapshot.previous_as_of_month is None:
        return "initial"
    if snapshot.neighbor_jaccard_similarity is None:
        return "not_available"
    return "stable" if snapshot.neighbor_jaccard_similarity >= 0.5 else "changed"


def _validate_decision_inputs(
    decision_inputs: Sequence[TriageDecisionInput],
    expected_ids: Sequence[str],
    triage_as_of_month: int,
) -> None:
    input_ids = [decision_input.customer_id for decision_input in decision_inputs]
    duplicate_ids = _duplicate_ids(input_ids)
    if duplicate_ids:
        raise ValueError(f"duplicate triage decision input customer IDs: {list(duplicate_ids)}")
    unexpected_ids = tuple(sorted(set(input_ids) - set(expected_ids)))
    if unexpected_ids:
        raise ValueError(f"triage decision inputs include unexpected customer IDs: {list(unexpected_ids)}")
    mismatched_as_of_ids = tuple(
        sorted(
            decision_input.customer_id
            for decision_input in decision_inputs
            if decision_input.signal_snapshot.as_of_month != triage_as_of_month
        )
    )
    if mismatched_as_of_ids:
        raise ValueError(
            "triage decision inputs must share triage_as_of_month; mismatched customer IDs: "
            f"{list(mismatched_as_of_ids)}"
        )


def _reconcile_triage_universe(
    *,
    expected_ids: Sequence[str],
    candidates: Sequence[TriageCandidate],
    received_decision_input_count: int,
    missing_input_ids: tuple[str, ...],
) -> TriageUniverseReconciliation:
    result_ids = [candidate.customer_id for candidate in candidates]
    expected_id_set = set(expected_ids)
    result_id_set = set(result_ids)
    return TriageUniverseReconciliation(
        expected_customer_count=len(expected_ids),
        received_decision_input_count=received_decision_input_count,
        result_customer_count=len(result_ids),
        missing_decision_input_customer_ids=missing_input_ids,
        result_missing_customer_ids=tuple(sorted(expected_id_set - result_id_set)),
        result_unexpected_customer_ids=tuple(sorted(result_id_set - expected_id_set)),
        duplicate_result_customer_ids=_duplicate_ids(result_ids),
    )


def _normalize_expected_ids(customer_ids: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(sorted(str(customer_id) for customer_id in customer_ids))
    if not normalized or any(not customer_id.strip() for customer_id in normalized):
        raise ValueError("expected_customer_ids must be non-empty")
    duplicate_ids = _duplicate_ids(normalized)
    if duplicate_ids:
        raise ValueError(f"expected_customer_ids contain duplicates: {list(duplicate_ids)}")
    return normalized


def _duplicate_ids(customer_ids: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({customer_id for customer_id in customer_ids if customer_ids.count(customer_id) > 1}))


def _unique_reason_codes(reason_codes: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(reason_codes))


def _validate_month(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if not 1 <= value <= settings.TOTAL_MONTHS:
        raise ValueError(f"{label} must be between 1 and {settings.TOTAL_MONTHS}")
