"""Isolated, synthetic-only rehearsal of the RM pilot protocol.

This module reads existing selection and representative artifacts without
changing them. It applies one caller-supplied capacity comparison, exercises
only a small synthetic workflow fixture, and writes aggregate evidence below a
separate Post-P0 output root. It is not an RM pilot, a policy approval, or a
customer-outcome evaluation.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

from config import settings
from src.alert_case import TimingEvidenceReference
from src.alert_cycle import AlertCycleRunner, TriageDecision
from src.alert_repository import FileAlertCaseRepository
from src.audit_trail import FileAuditEventStore
from src.banker_service import BankerApplicationService
from src.capacity_scenarios import CapacityScenario, build_capacity_comparison_report
from src.notifications import NullNotificationService, PreviewNotificationService
from src.recommended_followup import CaseOutcomeRecord
from src.rm_pilot_protocol import (
    PilotMeasurement,
    build_pilot_measurement_summary,
    export_pilot_metadata,
)
from src.rm_workflow_ui import RMWorkflowUIService, build_offline_notification_preview


SYNTHETIC_RM_PILOT_DRY_RUN_SCHEMA_VERSION = "synthetic_rm_pilot_dry_run.v1"
PILOT_DRY_RUN_ARTIFACT_DIR = settings.BASE_DIR / "artifacts" / "post_p0" / "pilot_dry_run"
_SYNTHETIC_ACTOR = "rm-synthetic-01"


class SyntheticPilotDryRunError(ValueError):
    """The requested rehearsal crosses the isolated synthetic-run contract."""


@dataclass(frozen=True)
class SyntheticPilotDryRunResult:
    """Aggregate-only evidence from one isolated rehearsal."""

    run_id: str
    output_dir: Path
    payload: Mapping[str, object]

    def to_dict(self) -> dict[str, object]:
        return dict(self.payload)


def run_synthetic_rm_pilot_dry_run(
    *,
    selection_manifest_path: Path,
    representative_cohort_path: Path,
    output_dir: Path,
    max_reviews_per_cycle: int,
    occurred_at: datetime,
    run_id: str = "synthetic_rm_pilot_dry_run",
    allowed_output_root: Path | None = None,
    reset_output: bool = True,
) -> SyntheticPilotDryRunResult:
    """Run one deterministic workflow rehearsal without changing source artifacts.

    ``max_reviews_per_cycle`` is a caller-supplied comparison value only. The
    function neither selects an operational default nor promotes a result to a
    policy or capacity approval.
    """

    _require_non_empty(run_id, "run_id")
    _validate_aware_datetime(occurred_at, "occurred_at")
    if (
        isinstance(max_reviews_per_cycle, bool)
        or not isinstance(max_reviews_per_cycle, int)
        or max_reviews_per_cycle <= 0
    ):
        raise SyntheticPilotDryRunError("max_reviews_per_cycle must be a positive integer")
    if not isinstance(reset_output, bool):
        raise SyntheticPilotDryRunError("reset_output must be a boolean")

    selection_source = Path(selection_manifest_path)
    representative_source = Path(representative_cohort_path)
    destination = Path(output_dir)
    root = Path(allowed_output_root) if allowed_output_root is not None else PILOT_DRY_RUN_ARTIFACT_DIR
    _assert_isolated_output_dir(destination, root, selection_source, representative_source)

    selection_before = _read_json_object(selection_source, "selection manifest")
    representative_before = _read_json_object(representative_source, "representative cohort")
    source_checksums_before = {
        "selection_manifest_sha256": _sha256_file(selection_source),
        "representative_cohort_sha256": _sha256_file(representative_source),
    }
    _validate_representatives(representative_before, selection_before)
    scenario = CapacityScenario(
        scenario_id=f"synthetic_pilot_capacity_{max_reviews_per_cycle}",
        max_reviews_per_cycle=max_reviews_per_cycle,
        status="draft",
    )
    capacity_report = build_capacity_comparison_report(selection_before, (scenario,))
    capacity_result = capacity_report.scenarios[0]
    if capacity_result.deferred_count <= 0:
        raise SyntheticPilotDryRunError(
            "dry-run capacity must leave at least one eligible record deferred for rehearsal"
        )

    records_by_id = _records_by_customer_id(selection_before)
    selected_records = tuple(records_by_id[customer_id] for customer_id in capacity_result.selected_customer_ids)
    if len(selected_records) < 3:
        raise SyntheticPilotDryRunError(
            "dry-run capacity must select at least three synthetic records for the workflow rehearsal"
        )
    reset_performed = _reset_isolated_output(destination) if reset_output else False
    destination.mkdir(parents=True, exist_ok=True)
    workflow_records = selected_records[:3]
    monitor_record = _required_record_by_disposition(records_by_id.values(), "MONITOR_ONLY")
    no_action_record = _required_record_by_disposition(records_by_id.values(), "NO_ACTIONABLE_SIGNAL")
    decisions = tuple(
        _triage_decision_from_record(record, capacity_scenario_id=scenario.scenario_id)
        for record in (*workflow_records, monitor_record, no_action_record)
    )
    expected_rehearsal_ids = tuple(sorted(decision.customer_id for decision in decisions))

    workflow_dir = destination / "workflow"
    audit_dir = destination / "audit"
    repository = FileAlertCaseRepository(workflow_dir)
    audit_store = FileAuditEventStore(audit_dir)
    runner = AlertCycleRunner(repository)
    first_cycle = runner.run(
        decisions,
        run_id=f"{run_id}-initial",
        mode="commit",
        occurred_at=occurred_at,
        expected_customer_ids=expected_rehearsal_ids,
    )
    if first_cycle.reconciliation.is_exact is not True or first_cycle.counters.failed:
        raise SyntheticPilotDryRunError("initial Alert cycle did not reconcile exactly")
    if first_cycle.counters.new_case != len(workflow_records):
        raise SyntheticPilotDryRunError("selected rehearsal decisions did not create the expected cases")

    selected_decisions = tuple(
        decision for decision in decisions if decision.queue_status == "SELECTED_FOR_REVIEW"
    )
    duplicate_cycle = runner.run(
        selected_decisions,
        run_id=f"{run_id}-duplicate-signal",
        mode="commit",
        occurred_at=occurred_at + timedelta(minutes=1),
        expected_customer_ids=tuple(decision.customer_id for decision in selected_decisions),
    )
    if duplicate_cycle.counters.new_case != 0 or duplicate_cycle.counters.failed:
        raise SyntheticPilotDryRunError("duplicate signal created a case or failed")

    alert_by_customer = {
        result.customer_id: result.alert_id
        for result in first_cycle.decision_results
        if result.alert_id is not None
    }
    selected_alert_ids = tuple(alert_by_customer[record["customer_id"]] for record in workflow_records)
    if len(selected_alert_ids) != 3:
        raise SyntheticPilotDryRunError("dry-run requires exactly three selected synthetic workflow cases")

    snooze_alert_id = selected_alert_ids[2]
    snooze_case = repository.get(snooze_alert_id)
    if snooze_case is None:
        raise SyntheticPilotDryRunError("snooze fixture case is unavailable")
    snoozed_case = snooze_case.transition_to(
        "SNOOZED",
        occurred_at=occurred_at + timedelta(minutes=2),
        state_change_reason="SYNTHETIC_DRY_RUN_SNOOZE_FIXTURE",
        snoozed_until=occurred_at + timedelta(hours=4),
    )
    repository.update(snoozed_case, expected_updated_at=snooze_case.updated_at)
    snooze_cycle = runner.run(
        (selected_decisions[2],),
        run_id=f"{run_id}-snooze-active",
        mode="commit",
        occurred_at=occurred_at + timedelta(minutes=3),
        expected_customer_ids=(selected_decisions[2].customer_id,),
    )
    if snooze_cycle.counters.new_case != 0 or snooze_cycle.decision_results[0].outcome != "NOOP_SNOOZE_ACTIVE":
        raise SyntheticPilotDryRunError("active snooze did not suppress duplicate case creation")

    banker = BankerApplicationService(repository, audit_store=audit_store)
    priority_alert_id, monitor_alert_id = selected_alert_ids[:2]
    _exercise_follow_up_and_close(
        banker,
        priority_alert_id,
        occurred_at=occurred_at + timedelta(minutes=4),
    )
    _exercise_monitor_action(
        banker,
        monitor_alert_id,
        occurred_at=occurred_at + timedelta(minutes=4),
    )

    preview_case = repository.get(monitor_alert_id)
    if preview_case is None:
        raise SyntheticPilotDryRunError("preview fixture case is unavailable")
    preview_service = RMWorkflowUIService(
        banker_service=banker,
        audit_store=audit_store,
        preview_service=PreviewNotificationService(),
    )
    available_preview = build_offline_notification_preview(preview_service, alert_case=preview_case)
    before_unavailable_preview = preview_case.to_dict()
    unavailable_preview_error = _assert_preview_unavailable_preserves_case(
        banker=banker,
        audit_store=audit_store,
        alert_case=preview_case,
    )
    after_unavailable_preview = repository.get(monitor_alert_id)
    if after_unavailable_preview is None or after_unavailable_preview.to_dict() != before_unavailable_preview:
        raise SyntheticPilotDryRunError("unavailable preview changed a synthetic case")

    measurements = _synthetic_measurements()
    measurement_summary = build_pilot_measurement_summary(
        measurements,
        declared_review_period_count=1,
    )
    source_checksums_after = {
        "selection_manifest_sha256": _sha256_file(selection_source),
        "representative_cohort_sha256": _sha256_file(representative_source),
    }
    checksum_unchanged = source_checksums_before == source_checksums_after
    if not checksum_unchanged:
        raise SyntheticPilotDryRunError("source selection or representative artifact changed")

    cases = repository.list_cases()
    audit_events = audit_store.list_events()
    payload = {
        "schema_version": SYNTHETIC_RM_PILOT_DRY_RUN_SCHEMA_VERSION,
        "run_id": run_id,
        "run_mode": "synthetic_operational_rehearsal_only",
        "occurred_at": occurred_at.isoformat(),
        "reset_performed": reset_performed,
        "input_artifacts": {
            "selection_manifest_path": str(selection_source),
            "representative_cohort_path": str(representative_source),
            "checksums_before": source_checksums_before,
            "checksums_after": source_checksums_after,
            "canonical_source_artifacts_unchanged": checksum_unchanged,
        },
        "capacity_comparison": {
            "scenario": scenario.to_dict(),
            "eligible_count": capacity_result.eligible_count,
            "selected_count": capacity_result.selected_count,
            "deferred_count": capacity_result.deferred_count,
            "workflow_rehearsal_selected_sample_count": len(workflow_records),
            "selected_prefix_digest": _digest_identifiers(capacity_result.selected_customer_ids),
            "deferred_prefix_digest": _digest_identifiers(capacity_result.deferred_customer_ids),
            "selection_method": "saved_rank_prefix_cutoff_only",
            "automatically_approved": False,
        },
        "representative_cohort": _representative_summary(representative_before),
        "alert_cycles": {
            "initial": first_cycle.counters.to_dict(),
            "duplicate_signal": duplicate_cycle.counters.to_dict(),
            "snooze_active": snooze_cycle.counters.to_dict(),
            "initial_reconciliation_exact": first_cycle.reconciliation.is_exact,
            "duplicate_reconciliation_exact": duplicate_cycle.reconciliation.is_exact,
            "snooze_reconciliation_exact": snooze_cycle.reconciliation.is_exact,
        },
        "workflow": {
            "synthetic_case_count": len(cases),
            "closed_case_count": sum(case.state == "CLOSED" for case in cases),
            "in_review_case_count": sum(case.state == "IN_REVIEW" for case in cases),
            "snoozed_case_count": sum(case.state == "SNOOZED" for case in cases),
            "append_only_audit_event_count": len(audit_events),
            "synthetic_actor_reference": _SYNTHETIC_ACTOR,
            "time_instrumentation_seconds": 600,
            "productivity_or_sla_claimed": False,
        },
        "measurements": measurement_summary.to_dict(),
        "failure_scenarios": {
            "no_historical_landmark": {
                "status": "handled_without_live_trigger",
                "historical_landmark_used_as_trigger": False,
            },
            "insufficient_evidence": {
                "status": "recorded_as_synthetic_measurement_only",
                "case_created": False,
            },
            "duplicate_signal": {
                "status": "no_duplicate_case",
                "new_case_count": duplicate_cycle.counters.new_case,
            },
            "snoozed_case": {
                "status": "active_snooze_noop",
                "new_case_count": snooze_cycle.counters.new_case,
            },
            "no_action_required": {
                "status": "nonreview_decision_skipped_no_new_case",
                "new_case_count": 0,
            },
            "preview_unavailable": {
                "status": "handled_without_case_or_audit_mutation",
                "error_type": unavailable_preview_error,
            },
        },
        "notification_preview": {
            "status": available_preview["status"],
            "sent": available_preview["sent"],
            "external_delivery_attempted": available_preview["external_delivery_attempted"],
            "network_called": available_preview["scope"]["network_called"],
        },
        "safety": {
            "actual_rm_participants": False,
            "actual_customer_data": False,
            "external_notification_delivery": False,
            "automatic_policy_approval": False,
            "automatic_capacity_approval": False,
            "customer_financial_outcome_improvement_claimed": False,
            "canonical_analytics_mutated": False,
        },
        "limitations": [
            "This is a deterministic synthetic rehearsal, not an RM productivity or customer-outcome result.",
            "The capacity value is caller supplied for comparison only and is not an approved workload.",
        ],
    }
    export_pilot_metadata(
        payload,
        destination / "run_manifest.json",
        allowed_root=root,
    )
    export_pilot_metadata(
        measurement_summary.to_dict(),
        destination / "measurement_summary.json",
        allowed_root=root,
    )
    return SyntheticPilotDryRunResult(run_id=run_id, output_dir=destination, payload=payload)


def _triage_decision_from_record(
    record: Mapping[str, object],
    *,
    capacity_scenario_id: str,
) -> TriageDecision:
    timing_payload = _mapping(record.get("timing_evidence_reference"), "timing_evidence_reference")
    policy = _require_text(record.get("policy_id"), "policy_id")
    selection_reason_codes = tuple(str(item) for item in _list(record.get("selection_reason_codes")))
    added_reason = f"PILOT_DRY_RUN_CAPACITY_{capacity_scenario_id.upper()}"
    if added_reason not in selection_reason_codes:
        selection_reason_codes = (*selection_reason_codes, added_reason)
    selected = record.get("selection_disposition") == "SELECTED_FOR_REVIEW"
    return TriageDecision(
        customer_id=_require_text(record.get("customer_id"), "customer_id"),
        triage_as_of_month=_integer(record.get("as_of_month"), "as_of_month"),
        policy_id=policy,
        policy_version=_require_text(record.get("policy_version"), "policy_version"),
        signal_run_id=_require_text(record.get("signal_run_id"), "signal_run_id"),
        signal_version="prospective_signal_snapshot.v1",
        selection_policy_id="synthetic_pilot_saved_rank_prefix",
        selection_policy_version="1",
        primary_disposition=_require_text(record.get("primary_disposition"), "primary_disposition"),
        operational_label=_require_text(record.get("eligibility_label"), "eligibility_label"),
        eligible_for_review=(True if selected else record.get("eligible_for_review")),
        queue_status=("SELECTED_FOR_REVIEW" if selected else "NOT_QUEUE_ELIGIBLE"),
        routing_action=("CREATE_NEW_CASE" if selected else "NO_ROUTING"),
        why_now_reason_codes=tuple(str(item) for item in _list(record.get("why_now_reason_codes"))),
        selection_reason_codes=selection_reason_codes,
        timing_evidence_reference=TimingEvidenceReference(
            source=_require_text(timing_payload.get("source"), "timing source"),
            candidate_month=_integer(timing_payload.get("candidate_month"), "candidate_month"),
            evaluation_status=_require_text(
                timing_payload.get("evaluation_status"),
                "timing evaluation_status",
            ),
        ),
    )


def _exercise_follow_up_and_close(
    banker: BankerApplicationService,
    alert_id: str,
    *,
    occurred_at: datetime,
) -> None:
    acknowledged = banker.acknowledge(
        alert_id,
        expected_state="NEW",
        occurred_at=occurred_at,
        actor_reference=_SYNTHETIC_ACTOR,
        idempotency_token="pilot-followup-ack",
    )
    in_review = banker.start_review(
        alert_id,
        expected_state=acknowledged.current_state,
        occurred_at=occurred_at + timedelta(minutes=1),
        actor_reference=_SYNTHETIC_ACTOR,
        idempotency_token="pilot-followup-review",
    )
    banker.record_action(
        alert_id,
        expected_state=in_review.current_state,
        action="CONTACT_PLANNED",
        occurred_at=occurred_at + timedelta(minutes=2),
        actor_reference=_SYNTHETIC_ACTOR,
        idempotency_token="pilot-followup-contact-plan",
    )
    follow_up = banker.set_follow_up(
        alert_id,
        expected_state=in_review.current_state,
        occurred_at=occurred_at + timedelta(minutes=3),
        actor_reference=_SYNTHETIC_ACTOR,
        idempotency_token="pilot-followup-set",
    )
    banker.record_action(
        alert_id,
        expected_state=follow_up.current_state,
        action="FOLLOW_UP_CREATED",
        occurred_at=occurred_at + timedelta(minutes=4),
        actor_reference=_SYNTHETIC_ACTOR,
        idempotency_token="pilot-followup-created",
    )
    banker.record_action(
        alert_id,
        expected_state=follow_up.current_state,
        action="CONTACT_COMPLETED",
        occurred_at=occurred_at + timedelta(minutes=5),
        actor_reference=_SYNTHETIC_ACTOR,
        idempotency_token="pilot-followup-contact-completed",
    )
    current = banker.repository.get(alert_id)
    if current is None:
        raise SyntheticPilotDryRunError("synthetic follow-up case disappeared")
    banker.close(
        alert_id,
        expected_state=follow_up.current_state,
        occurred_at=occurred_at + timedelta(minutes=6),
        actor_reference=_SYNTHETIC_ACTOR,
        idempotency_token="pilot-followup-close",
        case_outcome=CaseOutcomeRecord(
            alert_id=alert_id,
            customer_id=current.customer_id,
            outcome="CONTACT_DOCUMENTED",
            recorded_at=occurred_at + timedelta(minutes=6),
            recorded_by=_SYNTHETIC_ACTOR,
            closure_reason="CONTACT_COMPLETED",
            action_references=("SYNTHETIC_CONTACT_COMPLETED",),
        ),
    )


def _exercise_monitor_action(
    banker: BankerApplicationService,
    alert_id: str,
    *,
    occurred_at: datetime,
) -> None:
    acknowledged = banker.acknowledge(
        alert_id,
        expected_state="NEW",
        occurred_at=occurred_at,
        actor_reference=_SYNTHETIC_ACTOR,
        idempotency_token="pilot-monitor-ack",
    )
    in_review = banker.start_review(
        alert_id,
        expected_state=acknowledged.current_state,
        occurred_at=occurred_at + timedelta(minutes=1),
        actor_reference=_SYNTHETIC_ACTOR,
        idempotency_token="pilot-monitor-review",
    )
    banker.record_action(
        alert_id,
        expected_state=in_review.current_state,
        action="MONITOR_ONLY",
        occurred_at=occurred_at + timedelta(minutes=2),
        actor_reference=_SYNTHETIC_ACTOR,
        idempotency_token="pilot-monitor-action",
    )


def _assert_preview_unavailable_preserves_case(
    *,
    banker: BankerApplicationService,
    audit_store: FileAuditEventStore,
    alert_case: object,
) -> str:
    if not hasattr(alert_case, "alert_id"):
        raise SyntheticPilotDryRunError("preview fixture requires an AlertCase")
    unavailable_service = RMWorkflowUIService(
        banker_service=banker,
        audit_store=audit_store,
        preview_service=NullNotificationService(),
    )
    try:
        build_offline_notification_preview(unavailable_service, alert_case=alert_case)  # type: ignore[arg-type]
    except RuntimeError as error:
        return type(error).__name__
    raise SyntheticPilotDryRunError("Null preview service unexpectedly reported a preview")


def _synthetic_measurements() -> tuple[PilotMeasurement, ...]:
    return (
        PilotMeasurement(
            case_reference="CASE_SYN_REVIEW_01",
            alert_reference="ALERT_SYN_REVIEW_01",
            reviewer_pseudonymous_reference="RM_SYN_01",
            review_period="SYNTHETIC_CYCLE_01",
            evidence_usefulness_rating=4,
            actionability_rating=4,
            perceived_timeliness_rating=4,
            review_completed=True,
            review_completion_seconds=360,
            review_outcome="REVIEWED",
            recommendation_decision="ACCEPTED",
            recommendation_reason_code=None,
            follow_up_status="COMPLETED",
            insufficient_evidence=False,
            sanitized_feedback_code="EVIDENCE_CLEAR",
        ),
        PilotMeasurement(
            case_reference="CASE_SYN_MONITOR_01",
            alert_reference="ALERT_SYN_MONITOR_01",
            reviewer_pseudonymous_reference="RM_SYN_01",
            review_period="SYNTHETIC_CYCLE_01",
            evidence_usefulness_rating=3,
            actionability_rating=3,
            perceived_timeliness_rating=3,
            review_completed=True,
            review_completion_seconds=180,
            review_outcome="MONITOR",
            recommendation_decision="MODIFIED",
            recommendation_reason_code="CAPACITY_CONSTRAINT",
            follow_up_status="NOT_CREATED",
            insufficient_evidence=False,
            human_override=True,
            override_reason_code="HUMAN_CONTEXT_OVERRIDE",
            sanitized_feedback_code="WORKLOAD_CONSTRAINED",
        ),
        PilotMeasurement(
            case_reference="CASE_SYN_NO_ACTION_01",
            alert_reference="ALERT_SYN_NOT_CREATED_01",
            reviewer_pseudonymous_reference="RM_SYN_01",
            review_period="SYNTHETIC_CYCLE_01",
            evidence_usefulness_rating=None,
            actionability_rating=None,
            perceived_timeliness_rating=None,
            review_completed=False,
            review_completion_seconds=None,
            review_outcome="NO_ACTION",
            recommendation_decision="NOT_APPLICABLE",
            recommendation_reason_code=None,
            follow_up_status="NOT_APPLICABLE",
            insufficient_evidence=True,
            sanitized_feedback_code="EVIDENCE_INSUFFICIENT",
        ),
    )


def _representative_summary(cohort: Mapping[str, object]) -> dict[str, object]:
    records = _list(cohort.get("records"))
    selected = sum(_mapping(record, "representative record").get("status") == "selected" for record in records)
    unavailable = sum(_mapping(record, "representative record").get("status") == "unavailable" for record in records)
    return {
        "record_count": len(records),
        "selected_count": selected,
        "unavailable_count": unavailable,
        "used_for_operational_selection": False,
        "manual_cherry_picking": False,
    }


def _validate_representatives(
    cohort: Mapping[str, object],
    selection_manifest: Mapping[str, object],
) -> None:
    records_by_id = _records_by_customer_id(selection_manifest)
    records = _list(cohort.get("records"))
    if not records:
        raise SyntheticPilotDryRunError("representative cohort must contain category records")
    for raw in records:
        record = _mapping(raw, "representative record")
        status = record.get("status")
        customer_id = record.get("customer_id")
        if status == "selected":
            if not isinstance(customer_id, str) or customer_id not in records_by_id:
                raise SyntheticPilotDryRunError("selected representative must exist in selection manifest")
        elif status != "unavailable" or customer_id is not None:
            raise SyntheticPilotDryRunError("representative record status/customer reference is invalid")


def _records_by_customer_id(selection_manifest: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    records = _list(selection_manifest.get("records"))
    normalized = tuple(_mapping(record, "selection record") for record in records)
    by_id = {_require_text(record.get("customer_id"), "customer_id"): record for record in normalized}
    if len(by_id) != len(normalized):
        raise SyntheticPilotDryRunError("selection manifest customer IDs must be unique")
    return by_id


def _required_record_by_disposition(
    records: Sequence[Mapping[str, object]],
    disposition: str,
) -> Mapping[str, object]:
    matches = sorted(
        (record for record in records if record.get("primary_disposition") == disposition),
        key=lambda record: _require_text(record.get("customer_id"), "customer_id"),
    )
    if not matches:
        raise SyntheticPilotDryRunError(f"selection manifest has no {disposition} rehearsal record")
    return matches[0]


def _reset_isolated_output(destination: Path) -> bool:
    if not destination.exists():
        return False
    shutil.rmtree(destination)
    return True


def _assert_isolated_output_dir(
    destination: Path,
    allowed_root: Path,
    selection_source: Path,
    representative_source: Path,
) -> None:
    resolved_destination = destination.resolve()
    resolved_root = allowed_root.resolve()
    if resolved_destination == resolved_root or not _is_within(resolved_destination, resolved_root):
        raise SyntheticPilotDryRunError("output_dir must be a child of the injected pilot dry-run root")
    if _is_within(selection_source.resolve(), resolved_destination) or _is_within(
        representative_source.resolve(), resolved_destination
    ):
        raise SyntheticPilotDryRunError("pilot dry-run output cannot contain a source artifact")
    forbidden_roots = (
        settings.DATA_RAW_DIR.resolve(),
        settings.DATA_PROCESSED_DIR.resolve(),
        settings.DATA_DEMO_DIR.resolve(),
        settings.BASE_DIR.joinpath("artifacts", "population").resolve(),
        settings.BASE_DIR.joinpath("artifacts", "validation").resolve(),
        settings.BASE_DIR.joinpath("artifacts", "triage").resolve(),
    )
    if any(_is_within(resolved_destination, root) for root in forbidden_roots):
        raise SyntheticPilotDryRunError("pilot dry-run output must be isolated from canonical artifacts")


def _read_json_object(path: Path, label: str) -> dict[str, object]:
    if not path.is_file():
        raise SyntheticPilotDryRunError(f"{label} path does not exist: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SyntheticPilotDryRunError(f"cannot read {label}") from error
    if not isinstance(value, dict):
        raise SyntheticPilotDryRunError(f"{label} must be a JSON object")
    return {str(key): item for key, item in value.items()}


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest_identifiers(values: Sequence[str]) -> str:
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SyntheticPilotDryRunError(f"{label} must be a mapping")
    return {str(key): item for key, item in value.items()}


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise SyntheticPilotDryRunError("expected a JSON list")
    return value


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SyntheticPilotDryRunError(f"{label} must be non-empty text")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SyntheticPilotDryRunError(f"{label} must be an integer")
    return value


def _require_non_empty(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise SyntheticPilotDryRunError(f"{label} must be non-empty")


def _validate_aware_datetime(value: datetime, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise SyntheticPilotDryRunError(f"{label} must be timezone-aware")


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True
