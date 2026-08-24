"""Offline cross-boundary regression for the P0 Population-to-RM prototype.

This is intentionally a small synthetic fixture for the executable flow.  The
separate checked-in 5,000-customer artifacts are verified for exact coverage
in the companion test below, so normal test execution never rewrites or
recomputes canonical population outputs.
"""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.alert_case import TimingEvidenceReference
from src.alert_cycle import AlertCycleRunner, TriageDecision
from src.alert_repository import FileAlertCaseRepository
from src.audit_trail import FileAuditEventStore
from src.banker_service import BankerApplicationService
from src.crossfit_backtest import run_deterministic_crossfit_backtest
from src.data_generator import generate_dataset
from src.demo_policy import assess_policy_snapshot, default_demo_policy
from src.models import GeneratorConfig
from src.notifications import PreviewNotificationService
from src.population_artifacts import load_population_artifacts
from src.rm_workflow_ui import RMWorkflowUIService, build_offline_notification_preview
from src.selection_manifest import load_selection_artifacts
from src.timing_evidence import (
    CandidateAlertMoment,
    HistoricalBreakpointLandmark,
    build_timing_evidence,
)
from src.triage_selector import TriageSelector, default_triage_selection_policy
from src.triage_universe import TriageDecisionInput, TriageCandidate, build_triage_universe
from src.prospective_evaluator import extract_synthetic_future_event_anchors


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUN_AT = datetime(2026, 8, 24, 9, 0, tzinfo=timezone.utc)


def _alert_decision(
    *,
    selected_decision: object,
    candidate: TriageCandidate,
    selection_policy_id: str,
    selection_policy_version: str,
) -> TriageDecision:
    """Adapt a selected triage result at the explicit Alert boundary only."""

    timing = candidate.timing_evidence_reference
    assert timing is not None
    return TriageDecision(
        customer_id=str(getattr(selected_decision, "customer_id")),
        triage_as_of_month=candidate.triage_as_of_month,
        policy_id=str(candidate.policy_id),
        policy_version=str(candidate.policy_version),
        signal_run_id=candidate.signal_run_id,
        signal_version="prospective_signal_snapshot.v1",
        selection_policy_id=selection_policy_id,
        selection_policy_version=selection_policy_version,
        primary_disposition=str(getattr(selected_decision, "primary_disposition")),
        operational_label=str(getattr(selected_decision, "operational_label")),
        eligible_for_review=getattr(selected_decision, "eligible_for_review"),
        queue_status=getattr(selected_decision, "queue_status"),
        routing_action=getattr(selected_decision, "routing_action"),
        why_now_reason_codes=getattr(selected_decision, "why_now_reason_codes"),
        selection_reason_codes=getattr(selected_decision, "selection_reason_codes"),
        timing_evidence_reference=TimingEvidenceReference(
            source=timing.source,
            candidate_month=timing.candidate_month,
            evaluation_status=timing.evaluation_status,
        ),
        existing_case_reference=getattr(selected_decision, "existing_open_case_reference"),
    )


def test_checked_in_5k_population_triage_and_representative_artifacts_reconcile_exactly() -> None:
    population = load_population_artifacts(
        PROJECT_ROOT / "artifacts" / "population" / "seed42_full_run"
    )
    selection = load_selection_artifacts(
        PROJECT_ROOT / "artifacts" / "triage" / "seed42_crossfit_5fold_asof12_unbounded"
    )
    population_manifest = population["manifest"]
    selection_manifest = selection["selection_manifest"]
    reconciliation = selection_manifest["reconciliation"]
    records = selection_manifest["records"]
    representative_records = selection["representative_cohort"]["records"]

    assert population_manifest["counters"] == {
        "expected": 5000,
        "processed": 5000,
        "succeeded": 5000,
        "partial_failure": 0,
        "hard_failure": 0,
        "failed": 0,
    }
    assert population_manifest["reconciliation"]["expected_ids_sha256"] == reconciliation[
        "expected_ids_sha256"
    ]
    assert population_manifest["reconciliation"]["output_ids_sha256"] == reconciliation[
        "output_ids_sha256"
    ]
    assert reconciliation["is_exact"] is True
    assert reconciliation["funnel_reconciles"] is True
    assert len(records) == 5000
    assert sum(record["selected_for_review"] for record in records) == selection_manifest["funnel"][
        "selected_queue_ready"
    ]

    # Representative comparison records stay display-only and carry neither
    # a target future label nor a persona used for selection.
    for record in representative_records:
        payload = str(record).lower()
        assert "final_outcome" not in payload
        assert "persona" not in payload
        assert record["status"] in {"selected", "unavailable"}


def test_offline_fixture_flow_keeps_selection_before_evaluation_and_case_preview_offline(
    tmp_path: Path,
) -> None:
    _, monthly_df = generate_dataset(GeneratorConfig(customer_count=30, random_seed=42))
    crossfit = run_deterministic_crossfit_backtest(
        monthly_df,
        as_of_months=(12,),
        fold_count=3,
        top_k=5,
    )
    assert crossfit.manifest.reconciliation.is_exact is True
    assert not crossfit.failures

    policy = default_demo_policy()
    decision_inputs = tuple(
        TriageDecisionInput(
            record.snapshot.customer_id,
            record.snapshot,
            assess_policy_snapshot(policy, record.snapshot),
        )
        for record in crossfit.scored_records
    )
    customer_ids = tuple(sorted(monthly_df["customer_id"].astype(str).unique()))
    universe = build_triage_universe(
        expected_customer_ids=customer_ids,
        triage_as_of_month=12,
        signal_run_id="offline-e2e-crossfit-asof12",
        decision_inputs=decision_inputs,
    )
    selection = TriageSelector().select(
        universe,
        default_triage_selection_policy(max_reviews_per_cycle=1),
    )
    assert universe.reconciliation.result_coverage_is_exact is True
    assert selection.selected_for_review_count == 1
    assert selection.deferred_capacity_count > 0

    selected = next(
        decision for decision in selection.decisions if decision.queue_status == "SELECTED_FOR_REVIEW"
    )
    candidate = next(
        item for item in universe.candidates if item.customer_id == selected.customer_id
    )

    # Evaluation may use the synthetic future-event anchor only after triage
    # has selected a candidate. It cannot change the prior triage decision.
    selection_before_evaluation = selection.to_dict()
    timing = build_timing_evidence(
        customer_ids=(selected.customer_id,),
        candidate_alert_moments=(CandidateAlertMoment(selected.customer_id, 12),),
        synthetic_event_anchors=extract_synthetic_future_event_anchors(
            monthly_df,
            customer_ids=(selected.customer_id,),
        ),
        historical_landmarks=(
            HistoricalBreakpointLandmark(selected.customer_id, "not_found", None),
        ),
    )
    assert selection.to_dict() == selection_before_evaluation
    assert timing.prospective_records[0].source == "prospective_signal"
    assert timing.historical_landmarks[0].source == "historical_landmark"
    assert timing.historical_landmarks[0].to_dict()["is_live_alert_trigger"] is False

    candidate_by_id = {item.customer_id: item for item in universe.candidates}
    cycle_decisions = tuple(
        _alert_decision(
            selected_decision=decision,
            candidate=candidate_by_id[decision.customer_id],
            selection_policy_id=selection.selection_policy.policy_id,
            selection_policy_version=selection.selection_policy.version,
        )
        for decision in selection.decisions
    )
    repository = FileAlertCaseRepository(tmp_path / "workflow")
    cycle = AlertCycleRunner(repository).run(
        cycle_decisions,
        run_id="offline-e2e-alert-cycle",
        mode="commit",
        occurred_at=RUN_AT,
        expected_customer_ids=customer_ids,
    )
    assert cycle.reconciliation.is_exact is True
    assert cycle.counters.triage_received == len(customer_ids)
    assert cycle.counters.selected == 1
    assert cycle.counters.new_case == 1
    assert cycle.counters.deferred_or_nonreview == len(customer_ids) - 1
    assert cycle.counters.failed == 0

    alert_id = next(result.alert_id for result in cycle.decision_results if result.alert_id is not None)
    assert alert_id is not None
    audit_store = FileAuditEventStore(tmp_path / "audit")
    banker = BankerApplicationService(repository, audit_store=audit_store)
    banker.acknowledge(
        alert_id,
        expected_state="NEW",
        occurred_at=RUN_AT + timedelta(minutes=1),
        actor_reference="rm-001",
        idempotency_token="offline-e2e-ack",
    )
    banker.start_review(
        alert_id,
        expected_state="ACKNOWLEDGED",
        occurred_at=RUN_AT + timedelta(minutes=2),
        actor_reference="rm-001",
        idempotency_token="offline-e2e-review",
    )
    action = banker.record_action(
        alert_id,
        expected_state="IN_REVIEW",
        action="CONTACT_PLANNED",
        occurred_at=RUN_AT + timedelta(minutes=3),
        actor_reference="rm-001",
        idempotency_token="offline-e2e-action",
    )
    assert action.current_state == "IN_REVIEW"
    assert len(audit_store.list_events()) == 3

    current_case = repository.get(alert_id)
    assert current_case is not None
    before_preview = current_case.to_dict()
    preview = build_offline_notification_preview(
        RMWorkflowUIService(
            banker_service=banker,
            audit_store=audit_store,
            preview_service=PreviewNotificationService(),
        ),
        alert_case=current_case,
    )
    assert preview["status"] == "PREVIEW"
    assert preview["sent"] is False
    assert preview["external_delivery_attempted"] is False
    assert preview["scope"]["network_called"] is False
    reloaded_case = repository.get(alert_id)
    assert reloaded_case is not None
    assert reloaded_case.to_dict() == before_preview
    assert len(audit_store.list_events()) == 3


def test_p0_runtime_boundaries_import_no_network_delivery_client() -> None:
    """Keep external transport and credential clients out of P0 production code."""

    module_paths = (
        "src/alert_case.py",
        "src/alert_cycle.py",
        "src/alert_repository.py",
        "src/audit_trail.py",
        "src/banker_service.py",
        "src/notifications.py",
        "src/rm_workflow_ui.py",
        "src/rm_workspace.py",
        "scripts/run_triage_selection_manifest.py",
    )
    forbidden_import_roots = {
        "requests",
        "httpx",
        "smtplib",
        "socket",
        "openai",
        "msal",
        "msgraph",
        "slack_sdk",
        "teams",
    }
    imported_roots: set[str] = set()
    p0_source = ""
    for relative_path in module_paths:
        source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        p0_source += source.lower()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".")[0])

    assert forbidden_import_roots.isdisjoint(imported_roots)
    assert not any(
        marker in p0_source
        for marker in ("email", "phone", "address", "social_security", "account_number")
    )
