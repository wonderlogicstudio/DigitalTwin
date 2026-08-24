"""Idempotent Alert/Case orchestration over already-versioned triage decisions.

This boundary accepts neither raw signal snapshots nor policy-eligibility
results.  It only turns an explicit, versioned triage decision into a
side-effect-free plan or a file-repository lifecycle update.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Sequence
from uuid import NAMESPACE_URL, uuid5

from src.alert_case import AlertCase, TimingEvidenceReference, create_alert_case
from src.alert_episode import (
    AlertEpisodeService,
    EpisodeAction,
    EpisodeHandlingResult,
    EpisodeLifecyclePolicy,
    default_episode_lifecycle_policy,
)
from src.alert_repository import AlertCaseRepository


ALERT_CYCLE_SCHEMA_VERSION = "alert_cycle.v1"
TRIAGE_DECISION_SCHEMA_VERSION = "triage_decision.v1"
ALERT_CYCLE_MODES = ("dry_run", "commit")
ALERT_CREATION_POLICY_STATUSES = ("draft", "demo", "approved")
QUEUE_STATUSES = ("SELECTED_FOR_REVIEW", "DEFERRED_CAPACITY", "NOT_QUEUE_ELIGIBLE")
ROUTING_ACTIONS = ("ROUTE_EXISTING_CASE", "CREATE_NEW_CASE", "NO_ROUTING")
OPERATIONAL_LABELS = ("Priority Review", "Review")

AlertCycleMode = Literal["dry_run", "commit"]
AlertCreationPolicyStatus = Literal["draft", "demo", "approved"]
QueueStatus = Literal["SELECTED_FOR_REVIEW", "DEFERRED_CAPACITY", "NOT_QUEUE_ELIGIBLE"]
RoutingAction = Literal["ROUTE_EXISTING_CASE", "CREATE_NEW_CASE", "NO_ROUTING"]


@dataclass(frozen=True)
class TriageDecision:
    """The complete, auditable input accepted by the Alert/Case cycle."""

    customer_id: str
    triage_as_of_month: int
    policy_id: str
    policy_version: str
    signal_run_id: str
    signal_version: str
    selection_policy_id: str
    selection_policy_version: str
    primary_disposition: str
    operational_label: str
    eligible_for_review: bool | None
    queue_status: QueueStatus
    routing_action: RoutingAction
    why_now_reason_codes: tuple[str, ...]
    selection_reason_codes: tuple[str, ...]
    timing_evidence_reference: TimingEvidenceReference | None
    existing_case_reference: str | None = None
    schema_version: str = TRIAGE_DECISION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty(
            {
                "customer_id": self.customer_id,
                "policy_id": self.policy_id,
                "policy_version": self.policy_version,
                "signal_run_id": self.signal_run_id,
                "signal_version": self.signal_version,
                "selection_policy_id": self.selection_policy_id,
                "selection_policy_version": self.selection_policy_version,
                "primary_disposition": self.primary_disposition,
                "operational_label": self.operational_label,
            }
        )
        if not isinstance(self.triage_as_of_month, int) or isinstance(self.triage_as_of_month, bool):
            raise ValueError("triage_as_of_month must be an integer")
        if not 1 <= self.triage_as_of_month <= 36:
            raise ValueError("triage_as_of_month must be between 1 and 36")
        if self.queue_status not in QUEUE_STATUSES:
            raise ValueError(f"queue_status must be one of {QUEUE_STATUSES}")
        if self.routing_action not in ROUTING_ACTIONS:
            raise ValueError(f"routing_action must be one of {ROUTING_ACTIONS}")
        _validate_reason_codes(self.why_now_reason_codes, "why_now_reason_codes")
        _validate_reason_codes(self.selection_reason_codes, "selection_reason_codes")
        if self.timing_evidence_reference is not None and (
            self.timing_evidence_reference.candidate_month != self.triage_as_of_month
        ):
            raise ValueError("timing evidence candidate_month must match triage_as_of_month")
        if self.schema_version != TRIAGE_DECISION_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {TRIAGE_DECISION_SCHEMA_VERSION}")

        if self.queue_status == "SELECTED_FOR_REVIEW":
            if self.eligible_for_review is not True:
                raise ValueError("selected decisions require eligible_for_review=True")
            if self.operational_label not in OPERATIONAL_LABELS:
                raise ValueError("selected decisions require a review operational_label")
            if self.routing_action == "NO_ROUTING":
                raise ValueError("selected decisions require a routing_action")
            if self.timing_evidence_reference is None:
                raise ValueError("selected decisions require timing_evidence_reference")
            if self.routing_action == "ROUTE_EXISTING_CASE" and not str(
                self.existing_case_reference or ""
            ).strip():
                raise ValueError("ROUTE_EXISTING_CASE requires existing_case_reference")
            if self.routing_action == "CREATE_NEW_CASE" and self.existing_case_reference is not None:
                raise ValueError("CREATE_NEW_CASE cannot include existing_case_reference")
        else:
            if self.routing_action != "NO_ROUTING":
                raise ValueError("non-selected decisions cannot route to an AlertCase")
            if self.existing_case_reference is not None:
                raise ValueError("non-selected decisions cannot include existing_case_reference")

    @property
    def episode_key(self) -> str:
        """Return the stable episode identity for this customer and signal run."""

        return ":".join(
            (
                self.customer_id,
                self.policy_id,
                self.policy_version,
                self.signal_run_id,
                self.signal_version,
                str(self.triage_as_of_month),
            )
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "customer_id": self.customer_id,
            "triage_as_of_month": self.triage_as_of_month,
            "policy_reference": {
                "policy_id": self.policy_id,
                "policy_version": self.policy_version,
            },
            "signal_reference": {
                "signal_run_id": self.signal_run_id,
                "signal_version": self.signal_version,
            },
            "selection_reference": {
                "selection_policy_id": self.selection_policy_id,
                "selection_policy_version": self.selection_policy_version,
                "selection_reason_codes": list(self.selection_reason_codes),
            },
            "primary_disposition": self.primary_disposition,
            "operational_label": self.operational_label,
            "eligible_for_review": self.eligible_for_review,
            "queue_status": self.queue_status,
            "routing_action": self.routing_action,
            "why_now_reason_codes": list(self.why_now_reason_codes),
            "timing_evidence_reference": (
                None
                if self.timing_evidence_reference is None
                else self.timing_evidence_reference.to_dict()
            ),
            "existing_case_reference": self.existing_case_reference,
            "scope": {
                "raw_signal_accepted": False,
                "selection_required": True,
                "case_creation_executed": False,
            },
        }


@dataclass(frozen=True)
class AlertCreationPolicy:
    """Versioned demo due-window contract for the in-app RM work queue.

    ``due_in_hours`` is a caller-configured demonstration parameter.  It is
    never an automatically approved bank SLA and does not represent an
    external-message delivery promise.
    """

    policy_id: str
    version: str
    due_in_hours: int = 24
    status: AlertCreationPolicyStatus = "draft"
    rationale: str = "Caller-supplied in-app review due window; not a bank SLA."
    limitations: tuple[str, ...] = ("No external delivery or bank-SLA approval is implied.",)
    approval_evidence: str | None = None
    schema_version: str = ALERT_CYCLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty({"policy_id": self.policy_id, "version": self.version})
        if isinstance(self.due_in_hours, bool) or not isinstance(self.due_in_hours, int):
            raise ValueError("due_in_hours must be an integer")
        if self.due_in_hours < 0:
            raise ValueError("due_in_hours must be non-negative")
        if self.status not in ALERT_CREATION_POLICY_STATUSES:
            raise ValueError(f"status must be one of {ALERT_CREATION_POLICY_STATUSES}")
        if not str(self.rationale).strip():
            raise ValueError("rationale must be non-empty")
        if not self.limitations or any(not str(item).strip() for item in self.limitations):
            raise ValueError("limitations must contain at least one non-empty statement")
        if self.status == "approved" and not str(self.approval_evidence or "").strip():
            raise ValueError("approved AlertCreationPolicy requires approval_evidence")
        if self.schema_version != ALERT_CYCLE_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {ALERT_CYCLE_SCHEMA_VERSION}")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "version": self.version,
            "due_in_hours": self.due_in_hours,
            "status": self.status,
            "rationale": self.rationale,
            "limitations": list(self.limitations),
            "approval_evidence": self.approval_evidence,
            "delivery_definition": "in_app_rm_work_queue_case",
        }


def default_alert_creation_policy() -> AlertCreationPolicy:
    """Return an explicit demo workflow policy without changing triage selection."""

    return AlertCreationPolicy(
        policy_id="alert_case_creation_demo",
        version="0.1.0",
        due_in_hours=24,
        status="demo",
        rationale=(
            "Use a fixed 24-hour demo review window after a selected triage decision "
            "creates or routes an in-app RM case."
        ),
        limitations=(
            "The 24-hour value is a demo parameter, not an approved bank SLA or workload standard.",
            "An in-app RM work-queue case is not evidence of successful external message delivery.",
        ),
    )


@dataclass(frozen=True)
class AlertCycleCounters:
    """Counters whose identities expose every received triage decision."""

    triage_received: int
    selected: int
    new_case: int
    existing_case_routed: int
    deferred_or_nonreview: int
    noop: int
    failed: int

    def __post_init__(self) -> None:
        values = (
            self.triage_received,
            self.selected,
            self.new_case,
            self.existing_case_routed,
            self.deferred_or_nonreview,
            self.noop,
            self.failed,
        )
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
            raise ValueError("AlertCycleCounters values must be non-negative integers")
        if self.triage_received != self.selected + self.deferred_or_nonreview:
            raise ValueError("triage_received must reconcile selected and deferred_or_nonreview")
        if self.selected != self.new_case + self.existing_case_routed + self.failed:
            raise ValueError("selected must reconcile new, existing, and failed cases")
        if self.noop > self.existing_case_routed:
            raise ValueError("noop cannot exceed existing_case_routed")

    def to_dict(self) -> dict[str, int]:
        return {
            "triage_received": self.triage_received,
            "selected": self.selected,
            "new_case": self.new_case,
            "existing_case_routed": self.existing_case_routed,
            "deferred_or_nonreview": self.deferred_or_nonreview,
            "noop": self.noop,
            "failed": self.failed,
        }


@dataclass(frozen=True)
class AlertCycleFailure:
    customer_id: str
    error_category: str
    message: str

    def __post_init__(self) -> None:
        _require_non_empty(
            {
                "customer_id": self.customer_id,
                "error_category": self.error_category,
                "message": self.message,
            }
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "customer_id": self.customer_id,
            "error_category": self.error_category,
            "message": self.message,
        }


@dataclass(frozen=True)
class AlertCycleDecisionResult:
    customer_id: str
    queue_status: QueueStatus
    routing_action: RoutingAction
    outcome: str
    alert_id: str | None
    error_category: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "customer_id": self.customer_id,
            "queue_status": self.queue_status,
            "routing_action": self.routing_action,
            "outcome": self.outcome,
            "alert_id": self.alert_id,
            "error_category": self.error_category,
        }


@dataclass(frozen=True)
class AlertCycleReconciliation:
    """Exact customer-set reconciliation against an optional selection manifest."""

    expected_customer_ids: tuple[str, ...] | None
    received_customer_ids: tuple[str, ...]
    missing_customer_ids: tuple[str, ...]
    unexpected_customer_ids: tuple[str, ...]
    is_exact: bool | None

    def to_dict(self) -> dict[str, object]:
        return {
            "expected_customer_ids": (
                None if self.expected_customer_ids is None else list(self.expected_customer_ids)
            ),
            "received_customer_ids": list(self.received_customer_ids),
            "missing_customer_ids": list(self.missing_customer_ids),
            "unexpected_customer_ids": list(self.unexpected_customer_ids),
            "is_exact": self.is_exact,
        }


@dataclass(frozen=True)
class AlertCycleRunResult:
    run_id: str
    mode: AlertCycleMode
    occurred_at: datetime
    alert_creation_policy: AlertCreationPolicy
    episode_lifecycle_policy: EpisodeLifecyclePolicy
    counters: AlertCycleCounters
    decision_results: tuple[AlertCycleDecisionResult, ...]
    failures: tuple[AlertCycleFailure, ...]
    reconciliation: AlertCycleReconciliation
    schema_version: str = ALERT_CYCLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty({"run_id": self.run_id})
        _validate_aware_datetime(self.occurred_at, "occurred_at")
        if self.mode not in ALERT_CYCLE_MODES:
            raise ValueError(f"mode must be one of {ALERT_CYCLE_MODES}")
        if self.schema_version != ALERT_CYCLE_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {ALERT_CYCLE_SCHEMA_VERSION}")
        result_ids = tuple(result.customer_id for result in self.decision_results)
        if result_ids != tuple(sorted(result_ids)) or len(result_ids) != len(set(result_ids)):
            raise ValueError("decision_results must have unique customer IDs in deterministic order")
        if self.counters.triage_received != len(self.decision_results):
            raise ValueError("counters.triage_received must equal decision_results")
        if self.counters.failed != len(self.failures):
            raise ValueError("counters.failed must equal failures")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "mode": self.mode,
            "occurred_at": self.occurred_at.isoformat(),
            "alert_creation_policy": self.alert_creation_policy.to_dict(),
            "episode_lifecycle_policy": self.episode_lifecycle_policy.to_dict(),
            "counters": self.counters.to_dict(),
            "decision_results": [item.to_dict() for item in self.decision_results],
            "failures": [item.to_dict() for item in self.failures],
            "reconciliation": self.reconciliation.to_dict(),
            "scope": {
                "dry_run_mutates_repository": False,
                "raw_signal_input_accepted": False,
                "selection_required": True,
                "external_delivery_implemented": False,
            },
        }


class AlertCycleRunner:
    """Run a bounded, idempotent Alert/Case cycle over versioned decisions only."""

    def __init__(
        self,
        repository: AlertCaseRepository,
        *,
        alert_creation_policy: AlertCreationPolicy | None = None,
        episode_lifecycle_policy: EpisodeLifecyclePolicy | None = None,
    ) -> None:
        self.repository = repository
        self.alert_creation_policy = alert_creation_policy or default_alert_creation_policy()
        self.episode_lifecycle_policy = (
            episode_lifecycle_policy or default_episode_lifecycle_policy()
        )

    def run(
        self,
        decisions: Sequence[TriageDecision],
        *,
        run_id: str,
        mode: AlertCycleMode,
        occurred_at: datetime,
        expected_customer_ids: Sequence[str] | None = None,
    ) -> AlertCycleRunResult:
        """Process one manifest-aligned cycle, isolating per-customer failures."""

        _require_non_empty({"run_id": run_id})
        _validate_aware_datetime(occurred_at, "occurred_at")
        if mode not in ALERT_CYCLE_MODES:
            raise ValueError(f"mode must be one of {ALERT_CYCLE_MODES}")
        ordered_decisions = _ordered_unique_decisions(decisions)
        reconciliation = _reconcile(ordered_decisions, expected_customer_ids)
        active_repository: AlertCaseRepository
        if mode == "dry_run":
            active_repository = _InMemoryAlertCaseRepository(self.repository.list_cases())
        else:
            active_repository = self.repository
        episode_service = AlertEpisodeService(active_repository, self.episode_lifecycle_policy)

        results: list[AlertCycleDecisionResult] = []
        failures: list[AlertCycleFailure] = []
        new_case = 0
        existing_case_routed = 0
        deferred_or_nonreview = 0
        noop = 0

        for decision in ordered_decisions:
            if decision.queue_status != "SELECTED_FOR_REVIEW":
                deferred_or_nonreview += 1
                results.append(
                    AlertCycleDecisionResult(
                        customer_id=decision.customer_id,
                        queue_status=decision.queue_status,
                        routing_action=decision.routing_action,
                        outcome="SKIPPED_DEFERRED_OR_NONREVIEW",
                        alert_id=None,
                    )
                )
                continue

            try:
                handling = self._handle_selected(
                    decision,
                    episode_service=episode_service,
                    repository=active_repository,
                    occurred_at=occurred_at,
                )
            except Exception as error:  # Customer failure must not discard other decisions.
                failure = AlertCycleFailure(
                    customer_id=decision.customer_id,
                    error_category=type(error).__name__,
                    message=str(error) or type(error).__name__,
                )
                failures.append(failure)
                results.append(
                    AlertCycleDecisionResult(
                        customer_id=decision.customer_id,
                        queue_status=decision.queue_status,
                        routing_action=decision.routing_action,
                        outcome="FAILED",
                        alert_id=None,
                        error_category=failure.error_category,
                    )
                )
                continue

            if handling.created:
                new_case += 1
            else:
                existing_case_routed += 1
            if handling.action.startswith("NOOP_"):
                noop += 1
            results.append(
                AlertCycleDecisionResult(
                    customer_id=decision.customer_id,
                    queue_status=decision.queue_status,
                    routing_action=decision.routing_action,
                    outcome=handling.action,
                    alert_id=handling.related_alert_id,
                )
            )

        selected = sum(item.queue_status == "SELECTED_FOR_REVIEW" for item in ordered_decisions)
        counters = AlertCycleCounters(
            triage_received=len(ordered_decisions),
            selected=selected,
            new_case=new_case,
            existing_case_routed=existing_case_routed,
            deferred_or_nonreview=deferred_or_nonreview,
            noop=noop,
            failed=len(failures),
        )
        return AlertCycleRunResult(
            run_id=run_id,
            mode=mode,
            occurred_at=occurred_at,
            alert_creation_policy=self.alert_creation_policy,
            episode_lifecycle_policy=self.episode_lifecycle_policy,
            counters=counters,
            decision_results=tuple(results),
            failures=tuple(failures),
            reconciliation=reconciliation,
        )

    def _handle_selected(
        self,
        decision: TriageDecision,
        *,
        episode_service: AlertEpisodeService,
        repository: AlertCaseRepository,
        occurred_at: datetime,
    ) -> EpisodeHandlingResult:
        candidate = _candidate_from_decision(
            decision,
            occurred_at=occurred_at,
            due_in_hours=self.alert_creation_policy.due_in_hours,
        )
        if decision.routing_action == "ROUTE_EXISTING_CASE":
            assert decision.existing_case_reference is not None
            existing = repository.get(decision.existing_case_reference)
            if existing is None:
                raise LookupError("existing_case_reference was not found")
            if existing.state == "CLOSED":
                raise ValueError("ROUTE_EXISTING_CASE requires an open AlertCase")
            if existing.customer_id != decision.customer_id:
                raise ValueError("existing_case_reference customer_id does not match triage decision")
            if existing.episode_key != decision.episode_key:
                raise ValueError("existing_case_reference episode_key does not match triage decision")
        return episode_service.handle(candidate, occurred_at=occurred_at)


class _InMemoryAlertCaseRepository:
    """Private repository clone used only to prove dry-run has no file mutation."""

    def __init__(self, cases: Sequence[AlertCase]) -> None:
        self._cases = {case.alert_id: case for case in cases}
        if len(self._cases) != len(cases):
            raise ValueError("repository snapshot contains duplicate alert IDs")

    def get(self, alert_id: str) -> AlertCase | None:
        return self._cases.get(alert_id)

    def list_cases(self) -> tuple[AlertCase, ...]:
        return tuple(sorted(self._cases.values(), key=lambda item: item.alert_id))

    def create(self, alert_case: AlertCase) -> AlertCase:
        if alert_case.alert_id in self._cases:
            raise ValueError("alert_id already exists")
        if self.open_by_episode(alert_case.customer_id, alert_case.episode_key) is not None:
            raise ValueError("an open AlertCase already exists for customer and episode")
        self._cases[alert_case.alert_id] = alert_case
        return alert_case

    def update(self, alert_case: AlertCase, *, expected_updated_at: datetime) -> AlertCase:
        current = self._cases.get(alert_case.alert_id)
        if current is None:
            raise KeyError(f"unknown alert_id: {alert_case.alert_id}")
        if current.updated_at != expected_updated_at:
            raise ValueError("stale AlertCase update")
        if alert_case.customer_id != current.customer_id or alert_case.episode_key != current.episode_key:
            raise ValueError("customer_id and episode_key are immutable repository identities")
        if alert_case.updated_at <= current.updated_at:
            raise ValueError("updated_at must advance beyond the current version")
        self._cases[alert_case.alert_id] = alert_case
        return alert_case

    def open_by_episode(self, customer_id: str, episode_key: str) -> AlertCase | None:
        matches = sorted(
            (
                item
                for item in self._cases.values()
                if item.customer_id == customer_id
                and item.episode_key == episode_key
                and item.state != "CLOSED"
            ),
            key=lambda item: item.alert_id,
        )
        if len(matches) > 1:
            raise ValueError("more than one open AlertCase exists for customer and episode")
        return None if not matches else matches[0]


def _candidate_from_decision(
    decision: TriageDecision,
    *,
    occurred_at: datetime,
    due_in_hours: int,
) -> AlertCase:
    assert decision.timing_evidence_reference is not None
    return create_alert_case(
        alert_id=_candidate_alert_id(decision, occurred_at),
        customer_id=decision.customer_id,
        policy_id=decision.policy_id,
        policy_version=decision.policy_version,
        selection_policy_id=decision.selection_policy_id,
        selection_policy_version=decision.selection_policy_version,
        signal_run_id=decision.signal_run_id,
        signal_version=decision.signal_version,
        signal_as_of_month=decision.triage_as_of_month,
        created_at=occurred_at,
        due_at=occurred_at + timedelta(hours=due_in_hours),
        operational_priority=(
            "PRIORITY_REVIEW" if decision.operational_label == "Priority Review" else "REVIEW"
        ),
        why_now_reason_codes=decision.why_now_reason_codes,
        selection_reason_codes=decision.selection_reason_codes,
        timing_evidence_reference=decision.timing_evidence_reference,
        episode_key=decision.episode_key,
    )


def _candidate_alert_id(decision: TriageDecision, occurred_at: datetime) -> str:
    identifier = "|".join(
        (
            decision.customer_id,
            decision.episode_key,
            decision.selection_policy_id,
            decision.selection_policy_version,
            occurred_at.isoformat(),
        )
    )
    return f"ALT-{uuid5(NAMESPACE_URL, identifier).hex.upper()}"


def _ordered_unique_decisions(decisions: Sequence[TriageDecision]) -> tuple[TriageDecision, ...]:
    if any(not isinstance(item, TriageDecision) for item in decisions):
        raise TypeError("AlertCycleRunner accepts only versioned TriageDecision inputs")
    ordered = tuple(sorted(decisions, key=lambda item: item.customer_id))
    customer_ids = tuple(item.customer_id for item in ordered)
    if len(customer_ids) != len(set(customer_ids)):
        raise ValueError("triage decisions must have unique customer IDs")
    return ordered


def _reconcile(
    decisions: Sequence[TriageDecision], expected_customer_ids: Sequence[str] | None
) -> AlertCycleReconciliation:
    received = tuple(item.customer_id for item in decisions)
    if expected_customer_ids is None:
        return AlertCycleReconciliation(
            expected_customer_ids=None,
            received_customer_ids=received,
            missing_customer_ids=(),
            unexpected_customer_ids=(),
            is_exact=None,
        )
    expected = tuple(sorted(str(item) for item in expected_customer_ids))
    if any(not item.strip() for item in expected) or len(expected) != len(set(expected)):
        raise ValueError("expected_customer_ids must be unique non-empty IDs")
    expected_set = set(expected)
    received_set = set(received)
    missing = tuple(sorted(expected_set - received_set))
    unexpected = tuple(sorted(received_set - expected_set))
    return AlertCycleReconciliation(
        expected_customer_ids=expected,
        received_customer_ids=received,
        missing_customer_ids=missing,
        unexpected_customer_ids=unexpected,
        is_exact=not missing and not unexpected,
    )


def _validate_reason_codes(values: tuple[str, ...], label: str) -> None:
    if not values or any(not str(value).strip() for value in values):
        raise ValueError(f"{label} must contain non-empty values")
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


def _require_non_empty(values: dict[str, str]) -> None:
    missing = sorted(name for name, value in values.items() if not str(value).strip())
    if missing:
        raise ValueError(f"required fields must be non-empty: {', '.join(missing)}")


def _validate_aware_datetime(value: datetime, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be a timezone-aware datetime")
