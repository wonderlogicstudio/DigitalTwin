"""Contracts for the triage-only, idempotent Alert/Case batch cycle."""

from __future__ import annotations

import ast
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import src.alert_cycle as alert_cycle
from src.alert_case import TimingEvidenceReference
from src.alert_cycle import AlertCycleRunner, TriageDecision
from src.alert_repository import FileAlertCaseRepository


RUN_AT = datetime(2026, 8, 23, 9, 0, tzinfo=timezone.utc)


def _decision(customer_id: str = "C000001", **overrides: object) -> TriageDecision:
    values: dict[str, object] = {
        "customer_id": customer_id,
        "triage_as_of_month": 12,
        "policy_id": "synthetic_early_warning_demo",
        "policy_version": "0.1.0",
        "signal_run_id": "crossfit_seed42_5fold_asof12",
        "signal_version": "prospective_signal_snapshot.v1",
        "selection_policy_id": "transparent_triage_selection_demo",
        "selection_policy_version": "0.1.0",
        "primary_disposition": "PRIORITY_REVIEW",
        "operational_label": "Priority Review",
        "eligible_for_review": True,
        "queue_status": "SELECTED_FOR_REVIEW",
        "routing_action": "CREATE_NEW_CASE",
        "why_now_reason_codes": ("CURRENT_STATUS_CONCERNING",),
        "selection_reason_codes": ("PRIORITY_BAND_PRIORITY_REVIEW",),
        "timing_evidence_reference": TimingEvidenceReference(
            source="prospective_signal",
            candidate_month=12,
            evaluation_status="not_evaluated",
        ),
        "existing_case_reference": None,
    }
    values.update(overrides)
    return TriageDecision(**values)  # type: ignore[arg-type]


def _runner(tmp_path: Path) -> tuple[AlertCycleRunner, FileAlertCaseRepository]:
    repository = FileAlertCaseRepository(tmp_path / "workflow")
    return AlertCycleRunner(repository), repository


def test_dry_run_plans_a_case_without_mutating_the_file_repository(tmp_path: Path) -> None:
    runner, repository = _runner(tmp_path)

    result = runner.run(
        (_decision(),),
        run_id="cycle-dry-run",
        mode="dry_run",
        occurred_at=RUN_AT,
        expected_customer_ids=("C000001",),
    )

    assert result.counters.to_dict() == {
        "triage_received": 1,
        "selected": 1,
        "new_case": 1,
        "existing_case_routed": 0,
        "deferred_or_nonreview": 0,
        "noop": 0,
        "failed": 0,
    }
    assert result.reconciliation.is_exact is True
    assert repository.list_cases() == ()
    assert not repository.storage_path.exists()


def test_commit_double_run_is_idempotent_and_keeps_selection_evidence(tmp_path: Path) -> None:
    runner, repository = _runner(tmp_path)
    decision = _decision()

    first = runner.run(
        (decision,),
        run_id="cycle-commit-1",
        mode="commit",
        occurred_at=RUN_AT,
    )
    second = runner.run(
        (decision,),
        run_id="cycle-commit-2",
        mode="commit",
        occurred_at=RUN_AT,
    )

    assert first.counters.new_case == 1
    assert second.counters.new_case == 0
    assert second.counters.existing_case_routed == 1
    assert second.counters.noop == 1
    assert len(repository.list_cases()) == 1
    case = repository.list_cases()[0]
    assert case.policy_version == "0.1.0"
    assert case.signal_version == "prospective_signal_snapshot.v1"
    assert case.selection_policy_version == "0.1.0"
    assert case.selection_reason_codes == ("PRIORITY_BAND_PRIORITY_REVIEW",)


def test_selected_existing_route_updates_only_the_referenced_open_case(tmp_path: Path) -> None:
    runner, repository = _runner(tmp_path)
    decision = _decision()
    created = runner.run(
        (decision,),
        run_id="cycle-create",
        mode="commit",
        occurred_at=RUN_AT,
    )
    alert_id = created.decision_results[0].alert_id
    assert alert_id is not None
    route_existing = replace(
        decision,
        routing_action="ROUTE_EXISTING_CASE",
        existing_case_reference=alert_id,
        selection_policy_version="0.2.0",
        selection_reason_codes=("CAPACITY_WITHIN_LIMIT",),
    )

    routed = runner.run(
        (route_existing,),
        run_id="cycle-route-existing",
        mode="commit",
        occurred_at=RUN_AT + timedelta(hours=1),
    )

    assert routed.counters.new_case == 0
    assert routed.counters.existing_case_routed == 1
    assert routed.decision_results[0].outcome == "UPDATED_OPEN_EPISODE"
    assert len(repository.list_cases()) == 1
    updated = repository.get(alert_id)
    assert updated is not None
    assert updated.selection_policy_version == "0.2.0"
    assert updated.selection_reason_codes == ("CAPACITY_WITHIN_LIMIT",)


def test_deferred_monitor_and_no_actionable_decisions_never_create_cases(tmp_path: Path) -> None:
    runner, repository = _runner(tmp_path)
    deferred = _decision(
        "C000001",
        queue_status="DEFERRED_CAPACITY",
        routing_action="NO_ROUTING",
        existing_case_reference=None,
    )
    monitor = _decision(
        "C000002",
        primary_disposition="MONITOR_ONLY",
        operational_label="Monitor",
        eligible_for_review=False,
        queue_status="NOT_QUEUE_ELIGIBLE",
        routing_action="NO_ROUTING",
        existing_case_reference=None,
    )
    no_signal = _decision(
        "C000003",
        primary_disposition="NO_ACTIONABLE_SIGNAL",
        operational_label="No Signal",
        eligible_for_review=False,
        queue_status="NOT_QUEUE_ELIGIBLE",
        routing_action="NO_ROUTING",
        existing_case_reference=None,
    )

    result = runner.run(
        (deferred, monitor, no_signal),
        run_id="cycle-non-review",
        mode="commit",
        occurred_at=RUN_AT,
    )

    assert result.counters.selected == 0
    assert result.counters.deferred_or_nonreview == 3
    assert result.counters.new_case == 0
    assert repository.list_cases() == ()
    assert {item.outcome for item in result.decision_results} == {"SKIPPED_DEFERRED_OR_NONREVIEW"}


def test_cycle_counters_reconcile_exactly_to_a_selection_manifest_customer_set(tmp_path: Path) -> None:
    runner, repository = _runner(tmp_path)
    decisions = (
        _decision("C000004"),
        _decision(
            "C000001",
            queue_status="DEFERRED_CAPACITY",
            routing_action="NO_ROUTING",
            existing_case_reference=None,
        ),
        _decision(
            "C000003",
            primary_disposition="MONITOR_ONLY",
            operational_label="Monitor",
            eligible_for_review=False,
            queue_status="NOT_QUEUE_ELIGIBLE",
            routing_action="NO_ROUTING",
            existing_case_reference=None,
        ),
        _decision(
            "C000002",
            primary_disposition="INSUFFICIENT_EVIDENCE",
            operational_label="Insufficient Evidence",
            eligible_for_review=None,
            queue_status="NOT_QUEUE_ELIGIBLE",
            routing_action="NO_ROUTING",
            existing_case_reference=None,
        ),
    )

    result = runner.run(
        decisions,
        run_id="cycle-manifest-reconciliation",
        mode="commit",
        occurred_at=RUN_AT,
        expected_customer_ids=("C000001", "C000002", "C000003", "C000004"),
    )

    assert result.reconciliation.is_exact is True
    assert result.reconciliation.missing_customer_ids == ()
    assert result.reconciliation.unexpected_customer_ids == ()
    assert result.counters.triage_received == 4
    assert result.counters.selected == 1
    assert result.counters.new_case == 1
    assert result.counters.deferred_or_nonreview == 3
    assert result.counters.failed == 0
    assert len(repository.list_cases()) == 1


def test_snoozed_episode_resumes_without_creating_a_second_case(tmp_path: Path) -> None:
    runner, repository = _runner(tmp_path)
    decision = _decision()
    created = runner.run(
        (decision,),
        run_id="cycle-create-before-snooze",
        mode="commit",
        occurred_at=RUN_AT,
    )
    alert_id = created.decision_results[0].alert_id
    assert alert_id is not None
    current = repository.get(alert_id)
    assert current is not None
    snoozed = current.transition_to(
        "SNOOZED",
        occurred_at=RUN_AT + timedelta(hours=1),
        state_change_reason="TEST_SNOOZE",
        snoozed_until=RUN_AT + timedelta(hours=3),
    )
    repository.update(snoozed, expected_updated_at=current.updated_at)

    resumed = runner.run(
        (decision,),
        run_id="cycle-after-snooze",
        mode="commit",
        occurred_at=RUN_AT + timedelta(hours=4),
    )

    assert resumed.counters.new_case == 0
    assert resumed.counters.existing_case_routed == 1
    assert resumed.decision_results[0].outcome == "UPDATED_SNOOZE_EXPIRED"
    assert len(repository.list_cases()) == 1
    stored = repository.get(alert_id)
    assert stored is not None
    assert stored.state == "ACKNOWLEDGED"


def test_one_selected_customer_failure_is_collected_without_corrupting_the_run(tmp_path: Path) -> None:
    runner, repository = _runner(tmp_path)
    missing_route = _decision(
        "C000001",
        routing_action="ROUTE_EXISTING_CASE",
        existing_case_reference="ALT-DOES-NOT-EXIST",
    )
    create_other = _decision("C000002")

    result = runner.run(
        (missing_route, create_other),
        run_id="cycle-failure-isolation",
        mode="commit",
        occurred_at=RUN_AT,
    )

    assert result.counters.selected == 2
    assert result.counters.new_case == 1
    assert result.counters.failed == 1
    assert len(result.failures) == 1
    assert result.failures[0].customer_id == "C000001"
    assert result.failures[0].error_category == "LookupError"
    assert len(repository.list_cases()) == 1


def test_triage_decision_requires_selected_routing_and_versioned_references() -> None:
    with pytest.raises(ValueError, match="selected decisions require a routing_action"):
        _decision(routing_action="NO_ROUTING")
    with pytest.raises(ValueError, match="ROUTE_EXISTING_CASE requires existing_case_reference"):
        _decision(routing_action="ROUTE_EXISTING_CASE", existing_case_reference=None)
    with pytest.raises(ValueError, match="required fields"):
        _decision(signal_version="")
    payload = _decision().to_dict()
    assert payload["selection_reference"] == {
        "selection_policy_id": "transparent_triage_selection_demo",
        "selection_policy_version": "0.1.0",
        "selection_reason_codes": ["PRIORITY_BAND_PRIORITY_REVIEW"],
    }
    assert payload["scope"]["raw_signal_accepted"] is False  # type: ignore[index]


def test_cycle_rejects_raw_or_unversioned_inputs_before_repository_mutation(tmp_path: Path) -> None:
    runner, repository = _runner(tmp_path)

    with pytest.raises(TypeError, match="only versioned TriageDecision"):
        runner.run(
            ({"customer_id": "C000001"},),  # type: ignore[arg-type]
            run_id="cycle-invalid-input",
            mode="commit",
            occurred_at=RUN_AT,
        )

    assert repository.list_cases() == ()


def test_cycle_module_stays_at_the_triage_case_boundary_without_external_dependencies() -> None:
    source_path = Path(alert_cycle.__file__)
    source = source_path.read_text(encoding="utf-8")
    ast.parse(source)
    lowered = source.lower()
    forbidden = (
        "final_outcome",
        "persona",
        "prospective_evaluator",
        "notification",
        "provider",
        "streamlit",
    )
    assert all(token not in lowered for token in forbidden)
    assert "from src.prospective_signals" not in source
    assert "from src.demo_policy" not in source
