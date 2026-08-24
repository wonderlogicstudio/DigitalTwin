"""End-to-end gate for the triage-to-case Banker workflow and audit trail."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.alert_case import TimingEvidenceReference
from src.alert_cycle import AlertCycleRunner, TriageDecision
from src.alert_repository import FileAlertCaseRepository
from src.audit_trail import FileAuditEventStore
from src.banker_service import BankerApplicationService
from src.recommended_followup import CaseOutcomeRecord


BASE_TIME = datetime(2026, 8, 23, 9, 0, tzinfo=timezone.utc)


def _selected_decision(customer_id: str = "C000001") -> TriageDecision:
    return TriageDecision(
        customer_id=customer_id,
        triage_as_of_month=12,
        policy_id="synthetic_early_warning_demo",
        policy_version="0.1.0",
        signal_run_id="crossfit_seed42_5fold_asof12",
        signal_version="prospective_signal_snapshot.v1",
        selection_policy_id="transparent_triage_selection_demo",
        selection_policy_version="0.1.0",
        primary_disposition="PRIORITY_REVIEW",
        operational_label="Priority Review",
        eligible_for_review=True,
        queue_status="SELECTED_FOR_REVIEW",
        routing_action="CREATE_NEW_CASE",
        why_now_reason_codes=("CURRENT_STATUS_CONCERNING",),
        selection_reason_codes=("PRIORITY_BAND_PRIORITY_REVIEW",),
        timing_evidence_reference=TimingEvidenceReference(
            source="prospective_signal",
            candidate_month=12,
            evaluation_status="not_evaluated",
        ),
    )


def _service_from_selected_cycle(tmp_path: Path) -> tuple[BankerApplicationService, str]:
    repository = FileAlertCaseRepository(tmp_path / "workflow")
    created = AlertCycleRunner(repository).run(
        (_selected_decision(),),
        run_id="workflow-audit-e2e",
        mode="commit",
        occurred_at=BASE_TIME,
        expected_customer_ids=("C000001",),
    )
    assert created.reconciliation.is_exact is True
    assert created.counters.new_case == 1
    alert_id = created.decision_results[0].alert_id
    assert alert_id is not None
    return (
        BankerApplicationService(
            repository,
            audit_store=FileAuditEventStore(tmp_path / "audit"),
            allow_closed_case_reopen=True,
        ),
        alert_id,
    )


def _acknowledge_and_start_review(service: BankerApplicationService, alert_id: str) -> None:
    service.acknowledge(
        alert_id,
        expected_state="NEW",
        occurred_at=BASE_TIME + timedelta(minutes=1),
        actor_reference="rm-001",
        idempotency_token="acknowledge-once",
    )
    service.start_review(
        alert_id,
        expected_state="ACKNOWLEDGED",
        occurred_at=BASE_TIME + timedelta(minutes=2),
        actor_reference="rm-001",
        idempotency_token="start-review-once",
    )


def test_alert_to_follow_up_close_reopen_has_one_expected_audit_event_per_operation(
    tmp_path: Path,
) -> None:
    service, alert_id = _service_from_selected_cycle(tmp_path)
    _acknowledge_and_start_review(service, alert_id)
    follow_up = service.set_follow_up(
        alert_id,
        expected_state="IN_REVIEW",
        occurred_at=BASE_TIME + timedelta(minutes=3),
        actor_reference="rm-001",
        idempotency_token="follow-up-once",
    )
    action = service.record_action(
        alert_id,
        expected_state="FOLLOW_UP",
        action="CONTACT_PLANNED",
        occurred_at=BASE_TIME + timedelta(minutes=4),
        actor_reference="rm-001",
        idempotency_token="contact-plan-once",
    )
    replay = service.record_action(
        alert_id,
        expected_state="FOLLOW_UP",
        action="CONTACT_PLANNED",
        occurred_at=BASE_TIME + timedelta(minutes=4),
        actor_reference="rm-001",
        idempotency_token="contact-plan-once",
    )
    closed = service.close(
        alert_id,
        expected_state="FOLLOW_UP",
        occurred_at=BASE_TIME + timedelta(minutes=5),
        actor_reference="rm-001",
        idempotency_token="close-once",
        case_outcome=CaseOutcomeRecord(
            alert_id=alert_id,
            customer_id="C000001",
            outcome="CONTACT_DOCUMENTED",
            recorded_at=BASE_TIME + timedelta(minutes=5),
            recorded_by="rm-001",
            closure_reason="CONTACT_COMPLETED",
            action_references=("contact-plan-once",),
        ),
    )
    reopened = service.reopen(
        alert_id,
        expected_state="CLOSED",
        occurred_at=BASE_TIME + timedelta(minutes=6),
        actor_reference="rm-001",
        idempotency_token="reopen-once",
    )

    assert follow_up.current_state == "FOLLOW_UP"
    assert action.current_state == "FOLLOW_UP"
    assert replay.idempotent_replay is True
    assert replay.audit_event == action.audit_event
    assert closed.current_state == "CLOSED"
    assert closed.case_outcome is not None
    assert closed.case_outcome.to_dict()["scope"]["analytical_label_attached"] is False  # type: ignore[index]
    assert reopened.current_state == "NEW"
    assert reopened.reopened_from_alert_id == alert_id

    events = service.audit_store.list_events()
    assert [event.event_type for event in events] == [
        "BANKER_ACKNOWLEDGE_REQUESTED",
        "BANKER_START_REVIEW_REQUESTED",
        "BANKER_SET_FOLLOW_UP_REQUESTED",
        "BANKER_RECORD_ACTION_REQUESTED",
        "BANKER_CLOSE_REQUESTED",
        "BANKER_REOPEN_REQUESTED",
    ]
    assert [event.sequence for event in events] == [1, 2, 3, 4, 5, 6]
    assert all(event.metadata["transition_status"] == "REQUESTED" for event in events)
    assert all(event.policy_version == "0.1.0" for event in events)
    assert all(event.signal_version == "prospective_signal_snapshot.v1" for event in events)
    assert events[0].previous_state == "NEW" and events[0].new_state == "ACKNOWLEDGED"
    assert events[-1].alert_id == reopened.alert_case.alert_id
    assert events[-1].previous_state == "CLOSED" and events[-1].new_state == "NEW"


@pytest.mark.parametrize(
    ("action", "outcome", "closure_reason", "expected_state", "expected_event_types"),
    (
        ("MONITOR_ONLY", None, None, "IN_REVIEW", ("BANKER_RECORD_ACTION_REQUESTED",)),
        (
            "NO_ACTION_REQUIRED",
            "NO_ACTION_REQUIRED",
            "REVIEW_COMPLETE_NO_FURTHER_ACTION",
            "CLOSED",
            ("BANKER_RECORD_ACTION_REQUESTED", "BANKER_CLOSE_REQUESTED"),
        ),
        (
            "REFERRED",
            "REFERRED",
            "REFERRED_TO_SPECIALIST",
            "CLOSED",
            ("BANKER_RECORD_ACTION_REQUESTED", "BANKER_CLOSE_REQUESTED"),
        ),
    ),
)
def test_monitor_no_action_and_referral_remain_human_workflow_paths_with_audit(
    tmp_path: Path,
    action: str,
    outcome: str | None,
    closure_reason: str | None,
    expected_state: str,
    expected_event_types: tuple[str, ...],
) -> None:
    service, alert_id = _service_from_selected_cycle(tmp_path)
    _acknowledge_and_start_review(service, alert_id)
    action_response = service.record_action(
        alert_id,
        expected_state="IN_REVIEW",
        action=action,  # type: ignore[arg-type]
        occurred_at=BASE_TIME + timedelta(minutes=3),
        actor_reference="rm-001",
        idempotency_token=f"action-{action}",
    )
    responses = [action_response]
    if outcome is not None:
        responses.append(
            service.close(
                alert_id,
                expected_state="IN_REVIEW",
                occurred_at=BASE_TIME + timedelta(minutes=4),
                actor_reference="rm-001",
                idempotency_token=f"close-{action}",
                case_outcome=CaseOutcomeRecord(
                    alert_id=alert_id,
                    customer_id="C000001",
                    outcome=outcome,  # type: ignore[arg-type]
                    recorded_at=BASE_TIME + timedelta(minutes=4),
                    recorded_by="rm-001",
                    closure_reason=closure_reason,  # type: ignore[arg-type]
                    action_references=(f"action-{action}",),
                ),
            )
        )

    assert responses[-1].current_state == expected_state
    assert all(response.audit_event.metadata["operation"] for response in responses)
    events = service.audit_store.list_events()
    assert tuple(event.event_type for event in events[2:]) == expected_event_types
    assert all("financial_decision" not in event.event_type.lower() for event in events)
