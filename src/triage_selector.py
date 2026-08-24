"""Transparent, capacity-aware selection over an already-built triage universe.

This module does not evaluate policy rules.  It only orders the policy-eligible
triage records with a declared lexicographic tuple and optionally marks the
first ``max_reviews_per_cycle`` as review-ready.  Routing actions are inert
contract values; no case repository, notification provider, or external call
is implemented here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from src.triage_universe import TriageCandidate, TriageUniverse


TRIAGE_SELECTION_SCHEMA_VERSION = "triage_selection.v1"
SELECTION_POLICY_STATUSES = ("draft", "demo", "approved")
QUEUE_STATUSES = ("SELECTED_FOR_REVIEW", "DEFERRED_CAPACITY", "NOT_QUEUE_ELIGIBLE")
ROUTING_ACTIONS = ("ROUTE_EXISTING_CASE", "CREATE_NEW_CASE", "NO_ROUTING")
SELECTION_REASON_COPY = {
    "PRIORITY_BAND_PRIORITY_REVIEW": "Priority Review is ordered ahead of Review.",
    "PRIORITY_BAND_REVIEW": "Review is ordered after Priority Review.",
    "TIMING_PROSPECTIVE_SIGNAL_AVAILABLE": "A prospective timing reference exists at the signal month.",
    "PERSISTENCE_PRESENT": "Persistent financial stress is ordered before non-persistent stress.",
    "PERSISTENCE_NOT_PRESENT": "Current stress is not persistent across the available signal history.",
    "STABILITY_STABLE": "Stable reference neighbors are ordered before changed or unavailable neighbor sets.",
    "STABILITY_CHANGED": "Changed reference neighbors are ordered after stable neighbor sets.",
    "STABILITY_INITIAL": "Initial signal snapshots are ordered after stable or changed sequential evidence.",
    "STABILITY_NOT_AVAILABLE": "Unavailable neighbor stability is ordered after available stability evidence.",
    "EVIDENCE_SUFFICIENT": "Sufficient available evidence is required for operational review ranking.",
    "CAPACITY_UNBOUNDED": "No review-capacity limit was supplied; all eligible candidates are review-ready.",
    "CAPACITY_WITHIN_LIMIT": "Candidate falls within the caller-supplied review capacity.",
    "CAPACITY_DEFERRED": "Candidate is eligible but falls below the caller-supplied capacity cutoff.",
    "NOT_QUEUE_ELIGIBLE": "This triage disposition is not an operational review queue candidate.",
    "ROUTE_EXISTING_CASE": "A future workflow may route to the supplied existing case reference.",
    "CREATE_NEW_CASE": "A future workflow may create a case; this selector creates nothing.",
    "NO_ROUTING": "No operational routing is prepared for a non-selected candidate.",
}

SelectionPolicyStatus = Literal["draft", "demo", "approved"]
QueueStatus = Literal["SELECTED_FOR_REVIEW", "DEFERRED_CAPACITY", "NOT_QUEUE_ELIGIBLE"]
RoutingAction = Literal["ROUTE_EXISTING_CASE", "CREATE_NEW_CASE", "NO_ROUTING"]

_PRIORITY_BAND_ORDER = {"Priority Review": 0, "Review": 1}
_TIMING_BUCKET_ORDER = {"prospective_timing_not_evaluated": 0}
_PERSISTENCE_ORDER = {"persistent": 0, "not_persistent": 1, "no_current_factor": 2, "not_available": 3}
_STABILITY_ORDER = {"stable": 0, "changed": 1, "initial": 2, "not_available": 3}
_EVIDENCE_ORDER = {("sufficient", "sufficient"): 0}


@dataclass(frozen=True)
class RankingDimension:
    """One declared member of the lexicographic sort contract."""

    dimension_id: str
    source_fields: tuple[str, ...]
    direction: Literal["ascending", "descending"]
    rationale: str

    def __post_init__(self) -> None:
        if not str(self.dimension_id).strip() or not self.source_fields or not str(self.rationale).strip():
            raise ValueError("ranking dimension ID, source fields, and rationale must be non-empty")
        if self.direction not in {"ascending", "descending"}:
            raise ValueError("ranking dimension direction must be ascending or descending")

    def to_dict(self) -> dict[str, object]:
        return {
            "dimension_id": self.dimension_id,
            "source_fields": list(self.source_fields),
            "direction": self.direction,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class TriageSelectionPolicy:
    """Versioned selection contract with optional caller-supplied capacity."""

    policy_id: str
    version: str
    status: SelectionPolicyStatus
    max_reviews_per_cycle: int | None
    ranking_dimensions: tuple[RankingDimension, ...]
    rationale: str
    limitations: tuple[str, ...]
    workload_tradeoff_reference: str | None = None
    approval_evidence: str | None = None
    schema_version: str = TRIAGE_SELECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not str(self.policy_id).strip() or not str(self.version).strip():
            raise ValueError("policy_id and version must be non-empty")
        if self.status not in SELECTION_POLICY_STATUSES:
            raise ValueError(f"status must be one of {SELECTION_POLICY_STATUSES}")
        if self.max_reviews_per_cycle is not None and (
            isinstance(self.max_reviews_per_cycle, bool)
            or not isinstance(self.max_reviews_per_cycle, int)
            or self.max_reviews_per_cycle < 0
        ):
            raise ValueError("max_reviews_per_cycle must be a non-negative integer or None")
        if not self.ranking_dimensions:
            raise ValueError("ranking_dimensions must not be empty")
        dimension_ids = tuple(dimension.dimension_id for dimension in self.ranking_dimensions)
        if len(dimension_ids) != len(set(dimension_ids)):
            raise ValueError("ranking dimension IDs must be unique")
        if not str(self.rationale).strip() or not self.limitations:
            raise ValueError("rationale and at least one limitation are required")
        if any(not str(item).strip() for item in self.limitations):
            raise ValueError("limitations must be non-empty statements")
        if self.status == "approved" and not str(self.approval_evidence or "").strip():
            raise ValueError("approved selection policies require explicit approval_evidence")
        if self.schema_version != TRIAGE_SELECTION_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {TRIAGE_SELECTION_SCHEMA_VERSION}")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "version": self.version,
            "status": self.status,
            "max_reviews_per_cycle": self.max_reviews_per_cycle,
            "ranking_dimensions": [dimension.to_dict() for dimension in self.ranking_dimensions],
            "rationale": self.rationale,
            "limitations": list(self.limitations),
            "workload_tradeoff_reference": self.workload_tradeoff_reference,
            "approval_evidence": self.approval_evidence,
        }


@dataclass(frozen=True)
class TriageSelectionDecision:
    """One selector result; routing is a contract, not an executed side effect."""

    customer_id: str
    primary_disposition: str
    operational_label: str
    eligible_for_review: bool | None
    queue_status: QueueStatus
    review_priority_rank: int | None
    priority_tuple: tuple[int, int, int, int, int, str] | None
    why_now_reason_codes: tuple[str, ...]
    selection_reason_codes: tuple[str, ...]
    routing_action: RoutingAction
    existing_open_case_reference: str | None

    def __post_init__(self) -> None:
        if not str(self.customer_id).strip():
            raise ValueError("customer_id must be non-empty")
        if self.queue_status not in QUEUE_STATUSES or self.routing_action not in ROUTING_ACTIONS:
            raise ValueError("queue_status or routing_action is invalid")
        if not self.why_now_reason_codes or not self.selection_reason_codes:
            raise ValueError("why-now and selection reason codes must be non-empty")
        unknown_codes = sorted(set(self.selection_reason_codes) - set(SELECTION_REASON_COPY))
        if unknown_codes:
            raise ValueError(f"unknown selection reason codes: {unknown_codes}")
        if self.queue_status == "NOT_QUEUE_ELIGIBLE":
            if self.review_priority_rank is not None or self.priority_tuple is not None:
                raise ValueError("non-queue decisions cannot have a review rank")
            if self.routing_action != "NO_ROUTING":
                raise ValueError("non-queue decisions cannot have routing")
        else:
            if self.review_priority_rank is None or self.priority_tuple is None:
                raise ValueError("queue candidate decisions require rank and priority tuple")
            if self.queue_status == "DEFERRED_CAPACITY" and self.routing_action != "NO_ROUTING":
                raise ValueError("deferred decisions cannot have routing")
            if self.queue_status == "SELECTED_FOR_REVIEW" and self.routing_action == "NO_ROUTING":
                raise ValueError("selected decisions require a routing contract")

    def to_dict(self) -> dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "primary_disposition": self.primary_disposition,
            "operational_label": self.operational_label,
            "eligible_for_review": self.eligible_for_review,
            "queue_status": self.queue_status,
            "review_priority_rank": self.review_priority_rank,
            "priority_tuple": None if self.priority_tuple is None else list(self.priority_tuple),
            "why_now_reason_codes": list(self.why_now_reason_codes),
            "selection_reason_codes": list(self.selection_reason_codes),
            "selection_reason_copy": [
                SELECTION_REASON_COPY[code] for code in self.selection_reason_codes
            ],
            "routing_action": self.routing_action,
            "existing_open_case_reference": self.existing_open_case_reference,
            "scope": {
                "ranking": True,
                "rm_queue_selection": self.queue_status == "SELECTED_FOR_REVIEW",
                "case_creation_executed": False,
                "notification_sent": False,
            },
        }


@dataclass(frozen=True)
class TriageSelectionResult:
    """Complete deterministic selection view across every universe customer."""

    triage_as_of_month: int
    signal_run_id: str
    selection_policy: TriageSelectionPolicy
    decisions: tuple[TriageSelectionDecision, ...]
    eligible_review_count: int
    selected_for_review_count: int
    deferred_capacity_count: int
    not_queue_eligible_count: int
    schema_version: str = TRIAGE_SELECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.decisions, key=lambda decision: decision.customer_id))
        customer_ids = [decision.customer_id for decision in ordered]
        if len(customer_ids) != len(set(customer_ids)):
            raise ValueError("selection decisions must have unique customer IDs")
        if self.schema_version != TRIAGE_SELECTION_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {TRIAGE_SELECTION_SCHEMA_VERSION}")
        if self.eligible_review_count != sum(
            decision.queue_status != "NOT_QUEUE_ELIGIBLE" for decision in ordered
        ):
            raise ValueError("eligible_review_count does not match decisions")
        if self.selected_for_review_count != sum(
            decision.queue_status == "SELECTED_FOR_REVIEW" for decision in ordered
        ):
            raise ValueError("selected_for_review_count does not match decisions")
        if self.deferred_capacity_count != sum(
            decision.queue_status == "DEFERRED_CAPACITY" for decision in ordered
        ):
            raise ValueError("deferred_capacity_count does not match decisions")
        if self.not_queue_eligible_count != sum(
            decision.queue_status == "NOT_QUEUE_ELIGIBLE" for decision in ordered
        ):
            raise ValueError("not_queue_eligible_count does not match decisions")
        object.__setattr__(self, "decisions", ordered)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "triage_as_of_month": self.triage_as_of_month,
            "signal_run_id": self.signal_run_id,
            "selection_policy": self.selection_policy.to_dict(),
            "decisions": [decision.to_dict() for decision in self.decisions],
            "counts": {
                "eligible_review_count": self.eligible_review_count,
                "selected_for_review_count": self.selected_for_review_count,
                "deferred_capacity_count": self.deferred_capacity_count,
                "not_queue_eligible_count": self.not_queue_eligible_count,
            },
            "selection": {
                "automatic_capacity_choice": False,
                "case_repository_implemented": False,
                "notification_provider_implemented": False,
            },
        }


def default_triage_selection_policy(
    *,
    max_reviews_per_cycle: int | None = None,
    workload_tradeoff_reference: str | None = None,
) -> TriageSelectionPolicy:
    """Return a demo selector with no fixed operational capacity default."""

    return TriageSelectionPolicy(
        policy_id="transparent_triage_selection_demo",
        version="0.1.0",
        status="demo",
        max_reviews_per_cycle=max_reviews_per_cycle,
        ranking_dimensions=(
            RankingDimension(
                "operational_priority_band",
                ("operational_label", "primary_disposition"),
                "descending",
                "Priority Review is ordered before Review; other labels are excluded from the queue.",
            ),
            RankingDimension(
                "prospective_timing_bucket",
                ("timing_bucket",),
                "ascending",
                "Known prospective timing references are ordered by their declared bucket, never future lead time.",
            ),
            RankingDimension(
                "signal_persistence",
                ("signal_persistence",),
                "descending",
                "Persistent stress is ordered before non-persistent current stress.",
            ),
            RankingDimension(
                "neighbor_stability",
                ("signal_stability",),
                "descending",
                "Stable reference-neighbor evidence is ordered before changed or unavailable sets.",
            ),
            RankingDimension(
                "evidence_sufficiency_quality",
                ("evidence_sufficiency", "evidence_quality"),
                "descending",
                "Sufficient available evidence is required before a candidate can enter the queue.",
            ),
            RankingDimension(
                "stable_customer_tie_breaker",
                ("customer_id",),
                "ascending",
                "Customer ID provides a deterministic final tie-breaker only.",
            ),
        ),
        rationale=(
            "Rank policy-eligible review candidates by an explainable lexicographic tuple; "
            "do not create a composite risk score or select a capacity automatically."
        ),
        limitations=(
            "Synthetic policy eligibility is not a production approval or evidence of bank performance.",
            "Capacity is caller-supplied comparison input, not an approved workload standard.",
            "Routing actions are inert contracts; this module has no case repository or notification provider.",
        ),
        workload_tradeoff_reference=workload_tradeoff_reference,
    )


class TriageSelector:
    """Rank and select existing triage candidates without reevaluating policy."""

    def select(
        self,
        universe: TriageUniverse,
        selection_policy: TriageSelectionPolicy,
    ) -> TriageSelectionResult:
        if not universe.reconciliation.result_coverage_is_exact:
            raise ValueError("triage universe result coverage must reconcile exactly before selection")
        queue_candidates = tuple(
            candidate for candidate in universe.candidates if _is_operational_queue_candidate(candidate)
        )
        ordered_queue_candidates = tuple(sorted(queue_candidates, key=_priority_tuple))
        rank_by_customer_id = {
            candidate.customer_id: (rank, _priority_tuple(candidate))
            for rank, candidate in enumerate(ordered_queue_candidates, start=1)
        }
        selected_customer_ids = _selected_customer_ids(
            ordered_queue_candidates,
            selection_policy.max_reviews_per_cycle,
        )
        decisions = tuple(
            _build_decision(
                candidate=candidate,
                rank_and_key=rank_by_customer_id.get(candidate.customer_id),
                selected=candidate.customer_id in selected_customer_ids,
                capacity=selection_policy.max_reviews_per_cycle,
            )
            for candidate in universe.candidates
        )
        return TriageSelectionResult(
            triage_as_of_month=universe.triage_as_of_month,
            signal_run_id=universe.signal_run_id,
            selection_policy=selection_policy,
            decisions=decisions,
            eligible_review_count=len(ordered_queue_candidates),
            selected_for_review_count=len(selected_customer_ids),
            deferred_capacity_count=len(ordered_queue_candidates) - len(selected_customer_ids),
            not_queue_eligible_count=len(universe.candidates) - len(ordered_queue_candidates),
        )


def _is_operational_queue_candidate(candidate: TriageCandidate) -> bool:
    return bool(
        candidate.eligible_for_review
        and candidate.primary_disposition in {"ELIGIBLE_PRIORITY", "ELIGIBLE_REVIEW"}
        and candidate.operational_label in _PRIORITY_BAND_ORDER
        and candidate.data_availability_status == "available"
        and candidate.evidence_sufficiency == "sufficient"
        and candidate.evidence_quality == "sufficient"
        and candidate.timing_bucket in _TIMING_BUCKET_ORDER
        and candidate.signal_persistence in _PERSISTENCE_ORDER
        and candidate.signal_stability in _STABILITY_ORDER
    )


def _priority_tuple(candidate: TriageCandidate) -> tuple[int, int, int, int, int, str]:
    """Return a transparent lexicographic tuple; lower components rank first."""

    return (
        _PRIORITY_BAND_ORDER[candidate.operational_label],
        _TIMING_BUCKET_ORDER[candidate.timing_bucket],
        _PERSISTENCE_ORDER[candidate.signal_persistence],
        _STABILITY_ORDER[candidate.signal_stability],
        _EVIDENCE_ORDER[(candidate.evidence_sufficiency, candidate.evidence_quality)],
        candidate.customer_id,
    )


def _selected_customer_ids(
    ordered_candidates: tuple[TriageCandidate, ...],
    max_reviews_per_cycle: int | None,
) -> frozenset[str]:
    if max_reviews_per_cycle is None:
        return frozenset(candidate.customer_id for candidate in ordered_candidates)
    return frozenset(
        candidate.customer_id for candidate in ordered_candidates[:max_reviews_per_cycle]
    )


def _build_decision(
    *,
    candidate: TriageCandidate,
    rank_and_key: tuple[int, tuple[int, int, int, int, int, str]] | None,
    selected: bool,
    capacity: int | None,
) -> TriageSelectionDecision:
    if rank_and_key is None:
        return TriageSelectionDecision(
            customer_id=candidate.customer_id,
            primary_disposition=candidate.primary_disposition,
            operational_label=candidate.operational_label,
            eligible_for_review=candidate.eligible_for_review,
            queue_status="NOT_QUEUE_ELIGIBLE",
            review_priority_rank=None,
            priority_tuple=None,
            why_now_reason_codes=candidate.why_now_reason_codes,
            selection_reason_codes=("NOT_QUEUE_ELIGIBLE", "NO_ROUTING"),
            routing_action="NO_ROUTING",
            existing_open_case_reference=candidate.existing_open_case_reference,
        )
    rank, priority = rank_and_key
    if selected:
        routing_action: RoutingAction = (
            "ROUTE_EXISTING_CASE"
            if candidate.existing_open_case_reference is not None
            else "CREATE_NEW_CASE"
        )
        capacity_reason = "CAPACITY_UNBOUNDED" if capacity is None else "CAPACITY_WITHIN_LIMIT"
        queue_status: QueueStatus = "SELECTED_FOR_REVIEW"
    else:
        routing_action = "NO_ROUTING"
        capacity_reason = "CAPACITY_DEFERRED"
        queue_status = "DEFERRED_CAPACITY"
    return TriageSelectionDecision(
        customer_id=candidate.customer_id,
        primary_disposition=candidate.primary_disposition,
        operational_label=candidate.operational_label,
        eligible_for_review=candidate.eligible_for_review,
        queue_status=queue_status,
        review_priority_rank=rank,
        priority_tuple=priority,
        why_now_reason_codes=candidate.why_now_reason_codes,
        selection_reason_codes=(
            _priority_reason_code(candidate),
            "TIMING_PROSPECTIVE_SIGNAL_AVAILABLE",
            _persistence_reason_code(candidate),
            _stability_reason_code(candidate),
            "EVIDENCE_SUFFICIENT",
            capacity_reason,
            routing_action,
        ),
        routing_action=routing_action,
        existing_open_case_reference=candidate.existing_open_case_reference,
    )


def _priority_reason_code(candidate: TriageCandidate) -> str:
    return (
        "PRIORITY_BAND_PRIORITY_REVIEW"
        if candidate.operational_label == "Priority Review"
        else "PRIORITY_BAND_REVIEW"
    )


def _persistence_reason_code(candidate: TriageCandidate) -> str:
    return "PERSISTENCE_PRESENT" if candidate.signal_persistence == "persistent" else "PERSISTENCE_NOT_PRESENT"


def _stability_reason_code(candidate: TriageCandidate) -> str:
    return {
        "stable": "STABILITY_STABLE",
        "changed": "STABILITY_CHANGED",
        "initial": "STABILITY_INITIAL",
        "not_available": "STABILITY_NOT_AVAILABLE",
    }[candidate.signal_stability]
