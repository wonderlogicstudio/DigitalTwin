"""Comparison-only capacity scenarios over an existing triage selection export.

This module consumes saved, already-ranked triage records.  It never reruns
policy or scoring, changes the source manifest, selects an operational default,
or creates Alert/Case work.  A capacity changes only the prefix cutoff of the
saved lexicographic rank order.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


CAPACITY_COMPARISON_SCHEMA_VERSION = "capacity_scenario_comparison.v1"
CapacityScenarioStatus = Literal["draft", "demo", "approved"]
_ALLOWED_STATUSES = frozenset({"draft", "demo", "approved"})
_QUEUE_LABELS = frozenset({"Priority Review", "Review"})


@dataclass(frozen=True)
class CapacityScenario:
    """A caller-supplied comparison input, never an automatic workload decision."""

    scenario_id: str
    max_reviews_per_cycle: int | None
    status: CapacityScenarioStatus = "draft"
    scope: str = "comparison_only"
    approval_evidence_reference: str | None = None

    def __post_init__(self) -> None:
        scenario_id = str(self.scenario_id)
        if not scenario_id or any(not (char.isalnum() or char in "_-" ) for char in scenario_id):
            raise ValueError("scenario_id must contain only letters, digits, underscores, or hyphens")
        capacity = self.max_reviews_per_cycle
        if capacity is not None and (
            isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 0
        ):
            raise ValueError("max_reviews_per_cycle must be a non-negative integer or None")
        if self.status not in _ALLOWED_STATUSES:
            raise ValueError("status must be draft, demo, or approved")
        if self.scope != "comparison_only":
            raise ValueError("capacity scenarios are comparison_only")
        evidence = self.approval_evidence_reference
        if evidence is not None and not str(evidence).strip():
            raise ValueError("approval_evidence_reference must be non-empty when supplied")
        if self.status == "approved" and evidence is None:
            raise ValueError("approved capacity scenarios require approval_evidence_reference")

    @property
    def is_unbounded_reference(self) -> bool:
        return self.max_reviews_per_cycle is None

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "max_reviews_per_cycle": self.max_reviews_per_cycle,
            "status": self.status,
            "scope": self.scope,
            "approval_evidence_reference": self.approval_evidence_reference,
            "is_unbounded_reference": self.is_unbounded_reference,
        }


@dataclass(frozen=True)
class CapacityScenarioResult:
    """One deterministic cutoff comparison derived from saved ranked records."""

    scenario: CapacityScenario
    eligible_count: int
    selected_count: int
    deferred_count: int
    eligible_priority_count: int
    eligible_review_count: int
    selected_priority_count: int
    selected_review_count: int
    deferred_priority_count: int
    deferred_review_count: int
    selected_customer_ids: tuple[str, ...]
    deferred_customer_ids: tuple[str, ...]
    ranking_digest: str

    @property
    def coverage_percent(self) -> float | None:
        if self.eligible_count == 0:
            return None
        return round(self.selected_count / self.eligible_count * 100.0, 2)

    @property
    def estimated_carry_over_count(self) -> int:
        """One-cycle deferred count; it is not an RM productivity or SLA estimate."""

        return self.deferred_count

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario": self.scenario.to_dict(),
            "eligible_count": self.eligible_count,
            "selected_count": self.selected_count,
            "deferred_count": self.deferred_count,
            "composition": {
                "eligible_priority": self.eligible_priority_count,
                "eligible_review": self.eligible_review_count,
                "selected_priority": self.selected_priority_count,
                "selected_review": self.selected_review_count,
                "deferred_priority": self.deferred_priority_count,
                "deferred_review": self.deferred_review_count,
            },
            "coverage_percent": self.coverage_percent,
            "estimated_carry_over_count": self.estimated_carry_over_count,
            "selected_customer_ids": list(self.selected_customer_ids),
            "deferred_customer_ids": list(self.deferred_customer_ids),
            "ranking_digest": self.ranking_digest,
            "selection_method": "saved_rank_prefix_cutoff_only",
            "limitations": [
                "This is a comparison-only scenario, not an approved operational workload.",
                "Carry-over is a one-cycle count, not an RM productivity or SLA estimate.",
                "No policy, triage ranking, Alert/Case, or source artifact is changed.",
            ],
        }


@dataclass(frozen=True)
class CapacityComparisonReport:
    """A reproducible set of capacity-cutoff comparisons for one saved manifest."""

    source: Mapping[str, object]
    reconciliation: Mapping[str, object]
    scenarios: tuple[CapacityScenarioResult, ...]
    schema_version: str = CAPACITY_COMPARISON_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": dict(self.source),
            "reconciliation": dict(self.reconciliation),
            "scenarios": [scenario.to_dict() for scenario in self.scenarios],
            "selection": {
                "automatic_capacity_choice": False,
                "source_ranking_recomputed": False,
                "source_manifest_mutated": False,
                "operational_queue_mutated": False,
                "alert_creation": False,
            },
            "limitations": [
                "Capacity values are caller-supplied comparison inputs only.",
                "A scenario is not approved without explicit approval evidence.",
                "Synthetic results are not bank workload, productivity, or customer-outcome claims.",
            ],
        }


def build_capacity_comparison_report(
    selection_manifest: Mapping[str, object],
    scenarios: Iterable[CapacityScenario],
) -> CapacityComparisonReport:
    """Compare supplied cutoffs against one saved rank order without re-ranking."""

    ranked_records, source, reconciliation = _validated_ranked_records(selection_manifest)
    normalized_scenarios = tuple(scenarios)
    scenario_ids = [scenario.scenario_id for scenario in normalized_scenarios]
    if not normalized_scenarios:
        raise ValueError("at least one capacity scenario is required")
    if len(scenario_ids) != len(set(scenario_ids)):
        raise ValueError("capacity scenario IDs must be unique")
    return CapacityComparisonReport(
        source=source,
        reconciliation=reconciliation,
        scenarios=tuple(
            _compare_saved_rank_order(ranked_records, scenario)
            for scenario in normalized_scenarios
        ),
    )


def build_capacity_comparison_view_model(
    selection_manifest: Mapping[str, object],
    scenario: CapacityScenario,
) -> dict[str, object]:
    """Return a UI-ready comparison without making a capacity recommendation."""

    report = build_capacity_comparison_report(selection_manifest, (scenario,))
    result = report.scenarios[0]
    return {
        "available": True,
        "comparison_only": True,
        "scenario": result.to_dict(),
        "source": dict(report.source),
        "reconciliation": dict(report.reconciliation),
        "message_key": "rm.capacity.comparison_only",
    }


def export_capacity_comparison_report(
    report: CapacityComparisonReport,
    output_path: Path,
) -> Path:
    """Atomically write a Post-P0 comparison artifact without touching source data."""

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    payload = json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, destination)
    except OSError:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
        raise
    return destination


def _validated_ranked_records(
    selection_manifest: Mapping[str, object],
) -> tuple[tuple[Mapping[str, object], ...], dict[str, object], dict[str, object]]:
    records = selection_manifest.get("records") if isinstance(selection_manifest, Mapping) else None
    funnel = selection_manifest.get("funnel") if isinstance(selection_manifest, Mapping) else None
    if not isinstance(records, list) or not isinstance(funnel, Mapping):
        raise ValueError("selection manifest must contain records and funnel mappings")
    normalized_records = tuple(record for record in records if isinstance(record, Mapping))
    if len(normalized_records) != len(records):
        raise ValueError("selection manifest records must all be mappings")
    customer_ids = tuple(_customer_id(record) for record in normalized_records)
    if len(customer_ids) != len(set(customer_ids)):
        raise ValueError("selection manifest customer IDs must be unique")
    ranked = tuple(
        sorted(
            (record for record in normalized_records if record.get("review_priority_rank") is not None),
            key=lambda record: _rank(record),
        )
    )
    expected_ranks = tuple(range(1, len(ranked) + 1))
    if tuple(_rank(record) for record in ranked) != expected_ranks:
        raise ValueError("saved triage ranks must be unique and contiguous")
    if any(record.get("eligible_for_review") is not True for record in ranked):
        raise ValueError("saved ranked records must be policy-eligible")
    if any(str(record.get("eligibility_label")) not in _QUEUE_LABELS for record in ranked):
        raise ValueError("saved ranked records must have Priority Review or Review labels")
    monitored_total = _non_negative_count(funnel.get("monitored_total"), "funnel.monitored_total")
    eligible_total = _non_negative_count(funnel.get("eligible_total"), "funnel.eligible_total")
    if monitored_total != len(normalized_records) or eligible_total != len(ranked):
        raise ValueError("detail-derived manifest reconciliation is not exact")
    source = {
        "run_id": selection_manifest.get("run_id"),
        "schema_version": selection_manifest.get("schema_version"),
        "signal_run_id": selection_manifest.get("signal_run_id"),
        "triage_as_of_month": selection_manifest.get("triage_as_of_month"),
        "selection_policy": selection_manifest.get("selection_policy"),
    }
    reconciliation = {
        "is_exact": True,
        "record_count": len(normalized_records),
        "monitored_total": monitored_total,
        "ranked_eligible_count": len(ranked),
        "eligible_total": eligible_total,
        "customer_id_digest": _digest(customer_ids),
        "ranked_customer_id_digest": _digest(tuple(_customer_id(record) for record in ranked)),
    }
    return ranked, source, reconciliation


def _compare_saved_rank_order(
    ranked_records: Sequence[Mapping[str, object]],
    scenario: CapacityScenario,
) -> CapacityScenarioResult:
    eligible_count = len(ranked_records)
    selected_limit = eligible_count if scenario.max_reviews_per_cycle is None else min(
        scenario.max_reviews_per_cycle,
        eligible_count,
    )
    selected_records = tuple(ranked_records[:selected_limit])
    deferred_records = tuple(ranked_records[selected_limit:])
    return CapacityScenarioResult(
        scenario=scenario,
        eligible_count=eligible_count,
        selected_count=len(selected_records),
        deferred_count=len(deferred_records),
        eligible_priority_count=_count_label(ranked_records, "Priority Review"),
        eligible_review_count=_count_label(ranked_records, "Review"),
        selected_priority_count=_count_label(selected_records, "Priority Review"),
        selected_review_count=_count_label(selected_records, "Review"),
        deferred_priority_count=_count_label(deferred_records, "Priority Review"),
        deferred_review_count=_count_label(deferred_records, "Review"),
        selected_customer_ids=tuple(_customer_id(record) for record in selected_records),
        deferred_customer_ids=tuple(_customer_id(record) for record in deferred_records),
        ranking_digest=_digest(tuple(_customer_id(record) for record in ranked_records)),
    )


def _rank(record: Mapping[str, object]) -> int:
    value = record.get("review_priority_rank")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("review_priority_rank must be a positive integer for ranked records")
    return value


def _customer_id(record: Mapping[str, object]) -> str:
    value = record.get("customer_id")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("selection manifest customer_id must be non-empty")
    return value


def _non_negative_count(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _count_label(records: Sequence[Mapping[str, object]], label: str) -> int:
    return sum(record.get("eligibility_label") == label for record in records)


def _digest(customer_ids: Sequence[str]) -> str:
    return hashlib.sha256("\n".join(customer_ids).encode("utf-8")).hexdigest()
