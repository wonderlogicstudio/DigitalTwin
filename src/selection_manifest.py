"""Auditable triage-selection artifacts and universe-only demo representatives.

Operational selection and representative-demo selection deliberately have
different inputs: the former records a :class:`TriageSelectionResult`, while
the latter reads only the fixed-as-of :class:`TriageUniverse`.  Neither path
opens customer future data or changes the legacy demo artifacts.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping

from config import settings
from src.triage_selector import TriageSelectionDecision, TriageSelectionResult
from src.triage_universe import TriageCandidate, TriageUniverse


TRIAGE_ARTIFACT_DIR = settings.BASE_DIR / "artifacts" / "triage"
SELECTION_MANIFEST_SCHEMA_VERSION = "rm_selection_manifest.v1"
REPRESENTATIVE_COHORT_SCHEMA_VERSION = "rm_representative_cohort.v1"
SELECTION_MANIFEST_FILENAME = "rm_selection_manifest.json"
REPRESENTATIVE_COHORT_FILENAME = "rm_representative_cohort.json"
REPRESENTATIVE_CATEGORY_IDS = (
    "priority_review",
    "early_signal_review",
    "monitor_no_alert_comparison",
    "insufficient_or_landmark_not_found",
)

RepresentativeStatus = Literal["selected", "unavailable"]


@dataclass(frozen=True)
class SelectionArtifactPaths:
    """Two separate, non-canonical outputs of one selection export."""

    selection_manifest_json: Path
    representative_cohort_json: Path

    def to_dict(self) -> dict[str, str]:
        return {
            "selection_manifest_json": str(self.selection_manifest_json),
            "representative_cohort_json": str(self.representative_cohort_json),
        }


@dataclass(frozen=True)
class SelectionManifestRecord:
    """One auditable selection row for exactly one triage-universe customer."""

    customer_id: str
    as_of_month: int
    signal_as_of_month: int
    signal_run_id: str
    policy_id: str | None
    policy_version: str | None
    eligible_for_review: bool | None
    eligibility_label: str
    primary_disposition: str
    review_priority_rank: int | None
    selected_for_review: bool
    selection_disposition: str
    routing_disposition: str
    why_now_reason_codes: tuple[str, ...]
    selection_reason_codes: tuple[str, ...]
    capacity_scenario_id: str | None
    max_reviews_per_cycle: int | None
    timing_bucket: str
    timing_evidence_reference: dict[str, object] | None
    signal_persistence: str
    signal_stability: str
    evidence_quality: str
    evidence_sufficiency: str
    data_availability_status: str
    historical_landmark_context: dict[str, object] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "as_of_month": self.as_of_month,
            "signal_as_of_month": self.signal_as_of_month,
            "signal_run_id": self.signal_run_id,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "eligible_for_review": self.eligible_for_review,
            "eligibility_label": self.eligibility_label,
            "primary_disposition": self.primary_disposition,
            "review_priority_rank": self.review_priority_rank,
            "selected_for_review": self.selected_for_review,
            "selection_disposition": self.selection_disposition,
            "routing_disposition": self.routing_disposition,
            "why_now_reason_codes": list(self.why_now_reason_codes),
            "selection_reason_codes": list(self.selection_reason_codes),
            "capacity_scenario_id": self.capacity_scenario_id,
            "max_reviews_per_cycle": self.max_reviews_per_cycle,
            "timing_bucket": self.timing_bucket,
            "timing_evidence_reference": self.timing_evidence_reference,
            "signal_persistence": self.signal_persistence,
            "signal_stability": self.signal_stability,
            "evidence_quality": self.evidence_quality,
            "evidence_sufficiency": self.evidence_sufficiency,
            "data_availability_status": self.data_availability_status,
            "historical_landmark_context": self.historical_landmark_context,
        }


@dataclass(frozen=True)
class OperationalSelectionManifest:
    """5,000-customer selection detail, funnel, and exact reconciliation."""

    run_id: str
    triage_as_of_month: int
    signal_run_id: str
    selection_policy: dict[str, object]
    capacity_scenario_id: str | None
    max_reviews_per_cycle: int | None
    records: tuple[SelectionManifestRecord, ...]
    funnel: dict[str, int]
    reconciliation: dict[str, object]
    schema_version: str = SELECTION_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not str(self.run_id).strip() or not str(self.signal_run_id).strip():
            raise ValueError("run_id and signal_run_id must be non-empty")
        if self.schema_version != SELECTION_MANIFEST_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SELECTION_MANIFEST_SCHEMA_VERSION}")
        ordered = tuple(sorted(self.records, key=lambda record: record.customer_id))
        customer_ids = [record.customer_id for record in ordered]
        if len(customer_ids) != len(set(customer_ids)):
            raise ValueError("selection manifest records must have unique customer IDs")
        if any(record.as_of_month != self.triage_as_of_month for record in ordered):
            raise ValueError("selection manifest records must share triage_as_of_month")
        if any(record.signal_run_id != self.signal_run_id for record in ordered):
            raise ValueError("selection manifest records must share signal_run_id")
        if not bool(self.reconciliation.get("is_exact")):
            raise ValueError("selection manifest reconciliation must be exact")
        object.__setattr__(self, "records", ordered)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "triage_as_of_month": self.triage_as_of_month,
            "signal_run_id": self.signal_run_id,
            "selection_policy": self.selection_policy,
            "capacity_scenario": {
                "scenario_id": self.capacity_scenario_id,
                "max_reviews_per_cycle": self.max_reviews_per_cycle,
                "automatically_chosen": False,
            },
            "records": [record.to_dict() for record in self.records],
            "funnel": self.funnel,
            "reconciliation": self.reconciliation,
            "scope": {
                "all_universe_customers_recorded": True,
                "case_repository_implemented": False,
                "notification_provider_implemented": False,
            },
        }


@dataclass(frozen=True)
class RepresentativeCohortRecord:
    """One deterministic, display-only representative category outcome."""

    category_id: str
    status: RepresentativeStatus
    customer_id: str | None
    selection_reason_codes: tuple[str, ...]
    selection_explanation: str
    source_primary_disposition: str | None
    source_operational_label: str | None
    source_signal_run_id: str
    source_as_of_month: int
    timing_bucket: str | None
    evidence_sufficiency: str | None

    def __post_init__(self) -> None:
        if self.category_id not in REPRESENTATIVE_CATEGORY_IDS:
            raise ValueError(f"unknown representative category: {self.category_id}")
        if self.status not in {"selected", "unavailable"}:
            raise ValueError("representative status must be selected or unavailable")
        if self.status == "selected" and not self.customer_id:
            raise ValueError("selected representative records require a customer_id")
        if self.status == "unavailable" and self.customer_id is not None:
            raise ValueError("unavailable representative records cannot include a customer_id")
        if not self.selection_reason_codes or not str(self.selection_explanation).strip():
            raise ValueError("representative reasons and explanation must be non-empty")

    def to_dict(self) -> dict[str, object]:
        return {
            "category_id": self.category_id,
            "status": self.status,
            "customer_id": self.customer_id,
            "selection_reason_codes": list(self.selection_reason_codes),
            "selection_explanation": self.selection_explanation,
            "source_primary_disposition": self.source_primary_disposition,
            "source_operational_label": self.source_operational_label,
            "source_signal_run_id": self.source_signal_run_id,
            "source_as_of_month": self.source_as_of_month,
            "timing_bucket": self.timing_bucket,
            "evidence_sufficiency": self.evidence_sufficiency,
        }


@dataclass(frozen=True)
class RepresentativeDemoCohort:
    """Universe-only cohort; operational capacity and RM selection are ignored."""

    cohort_id: str
    triage_as_of_month: int
    signal_run_id: str
    records: tuple[RepresentativeCohortRecord, ...]
    schema_version: str = REPRESENTATIVE_COHORT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not str(self.cohort_id).strip() or not str(self.signal_run_id).strip():
            raise ValueError("cohort_id and signal_run_id must be non-empty")
        if self.schema_version != REPRESENTATIVE_COHORT_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {REPRESENTATIVE_COHORT_SCHEMA_VERSION}")
        by_category = {record.category_id: record for record in self.records}
        if len(by_category) != len(self.records) or tuple(by_category) != REPRESENTATIVE_CATEGORY_IDS:
            raise ValueError("representative cohort must have every category exactly once in declared order")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "cohort_id": self.cohort_id,
            "triage_as_of_month": self.triage_as_of_month,
            "signal_run_id": self.signal_run_id,
            "records": [record.to_dict() for record in self.records],
            "selection_rules": {
                "uses_triage_universe_only": True,
                "uses_operational_selection_result": False,
                "capacity_independent": True,
                "stable_tie_breaker": "customer_id ascending after category evidence order",
                "unavailable_category_policy": "record unavailable; do not alter customer conditions",
            },
        }


def build_operational_selection_manifest(
    universe: TriageUniverse,
    selection_result: TriageSelectionResult,
    *,
    run_id: str,
    capacity_scenario_id: str | None = None,
) -> OperationalSelectionManifest:
    """Join all universe records to selection decisions and reconcile every count."""

    if not str(run_id).strip():
        raise ValueError("run_id must be non-empty")
    if capacity_scenario_id is not None and not str(capacity_scenario_id).strip():
        raise ValueError("capacity_scenario_id must be non-empty or None")
    if not universe.reconciliation.result_coverage_is_exact:
        raise ValueError("triage universe must reconcile exactly before manifest creation")
    if (
        selection_result.triage_as_of_month != universe.triage_as_of_month
        or selection_result.signal_run_id != universe.signal_run_id
    ):
        raise ValueError("selection result must reference the same triage universe")

    decision_by_id = _validate_selection_decisions(universe, selection_result)
    records = tuple(
        _manifest_record(
            candidate=candidate,
            decision=decision_by_id[candidate.customer_id],
            capacity_scenario_id=capacity_scenario_id,
            max_reviews_per_cycle=selection_result.selection_policy.max_reviews_per_cycle,
        )
        for candidate in universe.candidates
    )
    funnel = _build_funnel(records)
    reconciliation = _build_manifest_reconciliation(universe, records, funnel, selection_result)
    return OperationalSelectionManifest(
        run_id=str(run_id),
        triage_as_of_month=universe.triage_as_of_month,
        signal_run_id=universe.signal_run_id,
        selection_policy=selection_result.selection_policy.to_dict(),
        capacity_scenario_id=capacity_scenario_id,
        max_reviews_per_cycle=selection_result.selection_policy.max_reviews_per_cycle,
        records=records,
        funnel=funnel,
        reconciliation=reconciliation,
    )


def select_representative_demo_cohort(
    universe: TriageUniverse,
    *,
    cohort_id: str = "triage_representative_demo",
) -> RepresentativeDemoCohort:
    """Select four deterministic representatives from triage/evidence fields only."""

    if not universe.reconciliation.result_coverage_is_exact:
        raise ValueError("triage universe must reconcile exactly before cohort selection")
    category_records = tuple(
        _representative_record(universe, category_id) for category_id in REPRESENTATIVE_CATEGORY_IDS
    )
    return RepresentativeDemoCohort(
        cohort_id=cohort_id,
        triage_as_of_month=universe.triage_as_of_month,
        signal_run_id=universe.signal_run_id,
        records=category_records,
    )


def export_selection_artifacts(
    universe: TriageUniverse,
    selection_result: TriageSelectionResult,
    *,
    run_id: str,
    output_dir: Path | None = None,
    capacity_scenario_id: str | None = None,
    cohort_id: str | None = None,
    created_at: str | None = None,
    code_ref: str | None = None,
) -> SelectionArtifactPaths:
    """Atomically write a separate selection manifest and representative cohort."""

    destination = Path(output_dir) if output_dir is not None else TRIAGE_ARTIFACT_DIR / str(run_id)
    _assert_separate_output_dir(destination)
    manifest = build_operational_selection_manifest(
        universe,
        selection_result,
        run_id=run_id,
        capacity_scenario_id=capacity_scenario_id,
    )
    cohort = select_representative_demo_cohort(
        universe,
        cohort_id=cohort_id or f"representative_{run_id}",
    )
    paths = SelectionArtifactPaths(
        selection_manifest_json=destination / SELECTION_MANIFEST_FILENAME,
        representative_cohort_json=destination / REPRESENTATIVE_COHORT_FILENAME,
    )
    timestamp = created_at or datetime.now(timezone.utc).isoformat()
    manifest_payload = {
        **manifest.to_dict(),
        "created_at": timestamp,
        "code_ref": code_ref if code_ref is not None else _resolve_code_ref(),
        "output_paths": paths.to_dict(),
    }
    cohort_payload = {
        **cohort.to_dict(),
        "run_id": run_id,
        "created_at": timestamp,
        "selection_manifest_reference": str(paths.selection_manifest_json),
    }
    destination.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(paths.selection_manifest_json, manifest_payload)
    _atomic_write_json(paths.representative_cohort_json, cohort_payload)
    return paths


def load_selection_artifacts(output_dir: Path) -> dict[str, Any]:
    """Load and validate both required triage-selection artifact files."""

    paths = SelectionArtifactPaths(
        selection_manifest_json=Path(output_dir) / SELECTION_MANIFEST_FILENAME,
        representative_cohort_json=Path(output_dir) / REPRESENTATIVE_COHORT_FILENAME,
    )
    missing_paths = [path for path in paths.to_dict().values() if not Path(path).exists()]
    if missing_paths:
        raise FileNotFoundError(f"Incomplete selection artifact set: {missing_paths}")
    manifest = _read_json(paths.selection_manifest_json)
    cohort = _read_json(paths.representative_cohort_json)
    _validate_loaded_selection_manifest(manifest)
    _validate_loaded_representative_cohort(cohort, manifest)
    return {"paths": paths, "selection_manifest": manifest, "representative_cohort": cohort}


def _manifest_record(
    *,
    candidate: TriageCandidate,
    decision: TriageSelectionDecision,
    capacity_scenario_id: str | None,
    max_reviews_per_cycle: int | None,
) -> SelectionManifestRecord:
    candidate_payload = candidate.to_dict()
    return SelectionManifestRecord(
        customer_id=candidate.customer_id,
        as_of_month=candidate.triage_as_of_month,
        signal_as_of_month=candidate.signal_as_of_month,
        signal_run_id=candidate.signal_run_id,
        policy_id=candidate.policy_id,
        policy_version=candidate.policy_version,
        eligible_for_review=candidate.eligible_for_review,
        eligibility_label=candidate.operational_label,
        primary_disposition=candidate.primary_disposition,
        review_priority_rank=decision.review_priority_rank,
        selected_for_review=decision.queue_status == "SELECTED_FOR_REVIEW",
        selection_disposition=decision.queue_status,
        routing_disposition=decision.routing_action,
        why_now_reason_codes=decision.why_now_reason_codes,
        selection_reason_codes=decision.selection_reason_codes,
        capacity_scenario_id=capacity_scenario_id,
        max_reviews_per_cycle=max_reviews_per_cycle,
        timing_bucket=candidate.timing_bucket,
        timing_evidence_reference=candidate_payload["timing_evidence_reference"],
        signal_persistence=candidate.signal_persistence,
        signal_stability=candidate.signal_stability,
        evidence_quality=candidate.evidence_quality,
        evidence_sufficiency=candidate.evidence_sufficiency,
        data_availability_status=candidate.data_availability_status,
        historical_landmark_context=candidate_payload["historical_landmark_context"],
    )


def _validate_selection_decisions(
    universe: TriageUniverse,
    selection_result: TriageSelectionResult,
) -> dict[str, TriageSelectionDecision]:
    decisions = selection_result.decisions
    decision_ids = [decision.customer_id for decision in decisions]
    if len(decision_ids) != len(set(decision_ids)):
        raise ValueError("selection decisions contain duplicate customer IDs")
    expected_ids = {candidate.customer_id for candidate in universe.candidates}
    actual_ids = set(decision_ids)
    if expected_ids != actual_ids:
        raise ValueError("selection decisions must exactly cover triage universe customer IDs")
    return {decision.customer_id: decision for decision in decisions}


def _build_funnel(records: Iterable[SelectionManifestRecord]) -> dict[str, int]:
    normalized = tuple(records)
    primary_counts = Counter(record.primary_disposition for record in normalized)
    selection_counts = Counter(record.selection_disposition for record in normalized)
    return {
        "monitored_total": len(normalized),
        "eligible_priority": primary_counts["ELIGIBLE_PRIORITY"],
        "eligible_review": primary_counts["ELIGIBLE_REVIEW"],
        "eligible_total": primary_counts["ELIGIBLE_PRIORITY"] + primary_counts["ELIGIBLE_REVIEW"],
        "selected_queue_ready": selection_counts["SELECTED_FOR_REVIEW"],
        "deferred_capacity": selection_counts["DEFERRED_CAPACITY"],
        "monitor_only": primary_counts["MONITOR_ONLY"],
        "no_actionable_signal": primary_counts["NO_ACTIONABLE_SIGNAL"],
        "insufficient_evidence": primary_counts["INSUFFICIENT_EVIDENCE"],
        "data_unavailable": primary_counts["DATA_UNAVAILABLE"],
    }


def _build_manifest_reconciliation(
    universe: TriageUniverse,
    records: tuple[SelectionManifestRecord, ...],
    funnel: Mapping[str, int],
    selection_result: TriageSelectionResult,
) -> dict[str, object]:
    expected_ids = tuple(candidate.customer_id for candidate in universe.candidates)
    output_ids = tuple(record.customer_id for record in records)
    duplicate_ids = _duplicates(output_ids)
    missing_ids = tuple(sorted(set(expected_ids) - set(output_ids)))
    unexpected_ids = tuple(sorted(set(output_ids) - set(expected_ids)))
    disposition_total = sum(
        funnel[key]
        for key in (
            "eligible_priority",
            "eligible_review",
            "monitor_only",
            "no_actionable_signal",
            "insufficient_evidence",
            "data_unavailable",
        )
    )
    selection_total = funnel["selected_queue_ready"] + funnel["deferred_capacity"]
    funnel_reconciles = (
        funnel["monitored_total"] == len(records) == disposition_total
        and funnel["eligible_total"] == selection_total
        and funnel["eligible_total"] == selection_result.eligible_review_count
        and funnel["selected_queue_ready"] == selection_result.selected_for_review_count
        and funnel["deferred_capacity"] == selection_result.deferred_capacity_count
    )
    is_exact = not (missing_ids or unexpected_ids or duplicate_ids) and funnel_reconciles
    return {
        "expected_id_count": len(expected_ids),
        "output_id_count": len(output_ids),
        "missing_ids": list(missing_ids),
        "unexpected_ids": list(unexpected_ids),
        "duplicate_output_ids": list(duplicate_ids),
        "expected_ids_sha256": _id_digest(expected_ids),
        "output_ids_sha256": _id_digest(output_ids),
        "funnel_reconciles": funnel_reconciles,
        "is_exact": is_exact,
    }


def _representative_record(
    universe: TriageUniverse,
    category_id: str,
) -> RepresentativeCohortRecord:
    candidates = tuple(candidate for candidate in universe.candidates if _in_category(candidate, category_id))
    if not candidates:
        return RepresentativeCohortRecord(
            category_id=category_id,
            status="unavailable",
            customer_id=None,
            selection_reason_codes=("CATEGORY_UNAVAILABLE",),
            selection_explanation=(
                f"No customer in the fixed triage universe met the {category_id} category rule; "
                "no customer condition was changed."
            ),
            source_primary_disposition=None,
            source_operational_label=None,
            source_signal_run_id=universe.signal_run_id,
            source_as_of_month=universe.triage_as_of_month,
            timing_bucket=None,
            evidence_sufficiency=None,
        )
    selected = min(candidates, key=lambda candidate: _representative_sort_key(candidate, category_id))
    return RepresentativeCohortRecord(
        category_id=category_id,
        status="selected",
        customer_id=selected.customer_id,
        selection_reason_codes=_representative_reason_codes(selected, category_id),
        selection_explanation=(
            f"Selected deterministically from {len(universe.candidates)} fixed triage records for "
            f"{category_id}: disposition={selected.primary_disposition}, "
            f"label={selected.operational_label}, timing={selected.timing_bucket}, "
            f"persistence={selected.signal_persistence}, evidence={selected.evidence_sufficiency}; "
            "customer_id ascending resolves any remaining tie."
        ),
        source_primary_disposition=selected.primary_disposition,
        source_operational_label=selected.operational_label,
        source_signal_run_id=selected.signal_run_id,
        source_as_of_month=selected.triage_as_of_month,
        timing_bucket=selected.timing_bucket,
        evidence_sufficiency=selected.evidence_sufficiency,
    )


def _in_category(candidate: TriageCandidate, category_id: str) -> bool:
    if category_id == "priority_review":
        return candidate.primary_disposition == "ELIGIBLE_PRIORITY" and candidate.operational_label == "Priority Review"
    if category_id == "early_signal_review":
        return (
            candidate.primary_disposition == "ELIGIBLE_REVIEW"
            and candidate.operational_label == "Review"
            and candidate.timing_bucket.startswith("prospective_timing_")
        )
    if category_id == "monitor_no_alert_comparison":
        return candidate.primary_disposition in {"MONITOR_ONLY", "NO_ACTIONABLE_SIGNAL"}
    assert category_id == "insufficient_or_landmark_not_found"
    return bool(
        candidate.primary_disposition == "INSUFFICIENT_EVIDENCE"
        or (
            candidate.historical_landmark_context is not None
            and candidate.historical_landmark_context.breakpoint_status != "found"
        )
    )


def _representative_sort_key(candidate: TriageCandidate, category_id: str) -> tuple[int, int, int, int, str]:
    category_rank = 0
    if category_id == "monitor_no_alert_comparison":
        category_rank = 0 if candidate.primary_disposition == "MONITOR_ONLY" else 1
    elif category_id == "insufficient_or_landmark_not_found":
        category_rank = 0 if candidate.primary_disposition == "INSUFFICIENT_EVIDENCE" else 1
    return (
        category_rank,
        {"persistent": 0, "not_persistent": 1, "no_current_factor": 2, "not_available": 3}.get(
            candidate.signal_persistence, 4
        ),
        {"stable": 0, "changed": 1, "initial": 2, "not_available": 3}.get(
            candidate.signal_stability, 4
        ),
        {"sufficient": 0, "insufficient": 1, "unknown": 2}.get(candidate.evidence_sufficiency, 3),
        candidate.customer_id,
    )


def _representative_reason_codes(
    candidate: TriageCandidate,
    category_id: str,
) -> tuple[str, ...]:
    category_code = {
        "priority_review": "CATEGORY_PRIORITY_REVIEW",
        "early_signal_review": "CATEGORY_EARLY_SIGNAL_REVIEW",
        "monitor_no_alert_comparison": "CATEGORY_MONITOR_NO_ALERT",
        "insufficient_or_landmark_not_found": "CATEGORY_INSUFFICIENT_OR_LANDMARK_NOT_FOUND",
    }[category_id]
    return (
        category_code,
        f"DISPOSITION_{candidate.primary_disposition}",
        f"PERSISTENCE_{candidate.signal_persistence.upper()}",
        f"STABILITY_{candidate.signal_stability.upper()}",
        f"EVIDENCE_{candidate.evidence_sufficiency.upper()}",
        "TIE_BREAKER_CUSTOMER_ID_ASC",
    )


def _assert_separate_output_dir(output_dir: Path) -> None:
    resolved_output = output_dir.resolve()
    canonical_dirs = (
        settings.DATA_RAW_DIR,
        settings.DATA_PROCESSED_DIR,
        settings.DATA_DEMO_DIR,
        settings.REPORTS_DIR,
    )
    for canonical_dir in canonical_dirs:
        try:
            resolved_output.relative_to(canonical_dir.resolve())
        except ValueError:
            continue
        raise ValueError("selection artifacts must be written outside canonical analytics and demo directories")


def _validate_loaded_selection_manifest(manifest: Mapping[str, Any]) -> None:
    if manifest.get("schema_version") != SELECTION_MANIFEST_SCHEMA_VERSION:
        raise ValueError("Unexpected selection manifest schema version")
    records = manifest.get("records")
    reconciliation = manifest.get("reconciliation")
    funnel = manifest.get("funnel")
    if not isinstance(records, list) or not isinstance(reconciliation, dict) or not isinstance(funnel, dict):
        raise ValueError("Selection manifest is missing records, funnel, or reconciliation")
    record_ids = [str(record.get("customer_id", "")) for record in records if isinstance(record, dict)]
    if len(record_ids) != len(records) or _duplicates(record_ids):
        raise ValueError("Selection manifest records must have unique customer IDs")
    expected_reconciliation = {
        "expected_id_count": len(record_ids),
        "output_id_count": len(record_ids),
        "missing_ids": [],
        "unexpected_ids": [],
        "duplicate_output_ids": [],
        "expected_ids_sha256": _id_digest(record_ids),
        "output_ids_sha256": _id_digest(record_ids),
        "is_exact": True,
    }
    if any(reconciliation.get(key) != value for key, value in expected_reconciliation.items()):
        raise ValueError("Selection manifest reconciliation does not match detail")
    rebuilt_funnel = _build_funnel_from_dicts(records)
    if funnel != rebuilt_funnel or not reconciliation.get("funnel_reconciles"):
        raise ValueError("Selection manifest funnel does not reconcile with detail")


def _validate_loaded_representative_cohort(
    cohort: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> None:
    if cohort.get("schema_version") != REPRESENTATIVE_COHORT_SCHEMA_VERSION:
        raise ValueError("Unexpected representative cohort schema version")
    records = cohort.get("records")
    if not isinstance(records, list) or [record.get("category_id") for record in records if isinstance(record, dict)] != list(
        REPRESENTATIVE_CATEGORY_IDS
    ):
        raise ValueError("Representative cohort categories are incomplete or unordered")
    manifest_ids = {str(record["customer_id"]) for record in manifest["records"]}
    for record in records:
        if not isinstance(record, dict) or record.get("status") not in {"selected", "unavailable"}:
            raise ValueError("Representative cohort contains an invalid record")
        customer_id = record.get("customer_id")
        if record["status"] == "selected" and str(customer_id) not in manifest_ids:
            raise ValueError("Representative cohort customer is outside the selection manifest")
        if record["status"] == "unavailable" and customer_id is not None:
            raise ValueError("Unavailable representative cohort record cannot contain a customer ID")


def _build_funnel_from_dicts(records: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    primary_counts = Counter(str(record.get("primary_disposition")) for record in records)
    selection_counts = Counter(str(record.get("selection_disposition")) for record in records)
    return {
        "monitored_total": sum(primary_counts.values()),
        "eligible_priority": primary_counts["ELIGIBLE_PRIORITY"],
        "eligible_review": primary_counts["ELIGIBLE_REVIEW"],
        "eligible_total": primary_counts["ELIGIBLE_PRIORITY"] + primary_counts["ELIGIBLE_REVIEW"],
        "selected_queue_ready": selection_counts["SELECTED_FOR_REVIEW"],
        "deferred_capacity": selection_counts["DEFERRED_CAPACITY"],
        "monitor_only": primary_counts["MONITOR_ONLY"],
        "no_actionable_signal": primary_counts["NO_ACTIONABLE_SIGNAL"],
        "insufficient_evidence": primary_counts["INSUFFICIENT_EVIDENCE"],
        "data_unavailable": primary_counts["DATA_UNAVAILABLE"],
    }


def _duplicates(customer_ids: Iterable[str]) -> tuple[str, ...]:
    counts = Counter(str(customer_id) for customer_id in customer_ids)
    return tuple(sorted(customer_id for customer_id, count in counts.items() if count > 1))


def _id_digest(customer_ids: Iterable[str]) -> str:
    payload = "\n".join(sorted(str(customer_id) for customer_id in customer_ids))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary_path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        temporary_path.replace(path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return value


def _resolve_code_ref() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=settings.BASE_DIR,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() or None
