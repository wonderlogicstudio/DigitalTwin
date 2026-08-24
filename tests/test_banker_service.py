"""Application-service contracts for consistent human RM case operations."""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import src.banker_service as banker_service
from src.alert_case import AlertCase, TimingEvidenceReference, create_alert_case
from src.alert_repository import FileAlertCaseRepository
from src.audit_trail import FileAuditEventStore
from src.banker_service import (
    BankerApplicationService,
    BankerIdempotencyConflictError,
    BankerServiceError,
    BankerStateConflictError,
)
from src.recommended_followup import CaseOutcomeRecord


BASE_TIME = datetime(2026, 8, 23, 9, 0, tzinfo=timezone.utc)


def _case(alert_id: str = "ALT-000001") -> AlertCase:
    return create_alert_case(
        alert_id=alert_id,
        customer_id="C000001",
        policy_id="synthetic_early_warning_demo",
        policy_version="0.1.0",
        selection_policy_id="transparent_triage_selection_demo",
        selection_policy_version="0.1.0",
        signal_run_id="crossfit_seed42_5fold_asof12",
        signal_version="prospective_signal_snapshot.v1",
        signal_as_of_month=12,
        created_at=BASE_TIME,
        due_at=BASE_TIME + timedelta(days=2),
        operational_priority="PRIORITY_REVIEW",
        why_now_reason_codes=("CURRENT_STATUS_CONCERNING",),
        selection_reason_codes=("PRIORITY_BAND_PRIORITY_REVIEW",),
        timing_evidence_reference=TimingEvidenceReference(
            source="prospective_signal",
            candidate_month=12,
            evaluation_status="not_evaluated",
        ),
        episode_key="C000001:synthetic_early_warning_demo:12",
    )


def _service(tmp_path: Path, *, allow_reopen: bool = False) -> tuple[BankerApplicationService, FileAlertCaseRepository]:
    repository = FileAlertCaseRepository(tmp_path / "workflow")
    repository.create(_case())
    return (
        BankerApplicationService(
            repository,
            audit_store=FileAuditEventStore(tmp_path / "audit"),
            allow_closed_case_reopen=allow_reopen,
        ),
        repository,
    )


def _close_outcome(recorded_at: datetime) -> CaseOutcomeRecord:
    return CaseOutcomeRecord(
        alert_id="ALT-000001",
        customer_id="C000001",
        outcome="CONTACT_DOCUMENTED",
        recorded_at=recorded_at,
        recorded_by="rm-001",
        closure_reason="CONTACT_COMPLETED",
        action_references=("ACT-001",),
    )


def _move_to_follow_up(service: BankerApplicationService) -> None:
    acknowledged = service.acknowledge(
        "ALT-000001",
        expected_state="NEW",
        occurred_at=BASE_TIME + timedelta(minutes=1),
        actor_reference="rm-001",
        idempotency_token="ack-1",
    )
    assert acknowledged.current_state == "ACKNOWLEDGED"
    reviewed = service.start_review(
        "ALT-000001",
        expected_state="ACKNOWLEDGED",
        occurred_at=BASE_TIME + timedelta(minutes=2),
        actor_reference="rm-001",
        idempotency_token="review-1",
    )
    assert reviewed.current_state == "IN_REVIEW"
    followed = service.set_follow_up(
        "ALT-000001",
        expected_state="IN_REVIEW",
        occurred_at=BASE_TIME + timedelta(minutes=3),
        actor_reference="rm-001",
        idempotency_token="follow-1",
    )
    assert followed.current_state == "FOLLOW_UP"


def test_happy_path_exposes_explicit_state_action_and_outcome_responses(tmp_path: Path) -> None:
    service, repository = _service(tmp_path)
    _move_to_follow_up(service)

    action = service.record_action(
        "ALT-000001",
        expected_state="FOLLOW_UP",
        action="CONTACT_PLANNED",
        occurred_at=BASE_TIME + timedelta(minutes=4),
        actor_reference="rm-001",
        idempotency_token="action-1",
        note="RM will confirm an appropriate contact channel.",
    )
    closed = service.close(
        "ALT-000001",
        expected_state="FOLLOW_UP",
        occurred_at=BASE_TIME + timedelta(minutes=5),
        actor_reference="rm-001",
        idempotency_token="close-1",
        case_outcome=_close_outcome(BASE_TIME + timedelta(minutes=5)),
    )

    assert action.operation == "RECORD_ACTION"
    assert action.previous_state == action.current_state == "FOLLOW_UP"
    assert action.action_record is not None and action.action_record.action == "CONTACT_PLANNED"
    assert closed.operation == "CLOSE"
    assert closed.previous_state == "FOLLOW_UP"
    assert closed.current_state == "CLOSED"
    assert closed.case_outcome is not None
    assert closed.alert_case.case_resolution == "CONTACT_COMPLETED"
    stored = repository.get("ALT-000001")
    assert stored == closed.alert_case
    audit_events = service.audit_store.list_events()
    assert [event.event_type for event in audit_events] == [
        "BANKER_ACKNOWLEDGE_REQUESTED",
        "BANKER_START_REVIEW_REQUESTED",
        "BANKER_SET_FOLLOW_UP_REQUESTED",
        "BANKER_RECORD_ACTION_REQUESTED",
        "BANKER_CLOSE_REQUESTED",
    ]
    assert all(event.metadata["transition_status"] == "REQUESTED" for event in audit_events)


def test_forbidden_and_stale_transitions_leave_repository_state_unchanged(tmp_path: Path) -> None:
    service, repository = _service(tmp_path)

    with pytest.raises(BankerStateConflictError, match="requires ACKNOWLEDGED"):
        service.start_review(
            "ALT-000001",
            expected_state="NEW",
            occurred_at=BASE_TIME + timedelta(minutes=1),
            actor_reference="rm-001",
            idempotency_token="forbidden-review",
        )
    assert repository.get("ALT-000001") == _case()

    service.acknowledge(
        "ALT-000001",
        expected_state="NEW",
        occurred_at=BASE_TIME + timedelta(minutes=1),
        actor_reference="rm-001",
        idempotency_token="ack-1",
    )
    with pytest.raises(BankerStateConflictError, match="stale state"):
        service.start_review(
            "ALT-000001",
            expected_state="NEW",
            occurred_at=BASE_TIME + timedelta(minutes=2),
            actor_reference="rm-001",
            idempotency_token="stale-review",
        )
    current = repository.get("ALT-000001")
    assert current is not None and current.state == "ACKNOWLEDGED"


def test_duplicate_submit_replays_response_without_duplicate_action_or_state_update(tmp_path: Path) -> None:
    service, repository = _service(tmp_path)
    occurred_at = BASE_TIME + timedelta(minutes=1)
    first = service.acknowledge(
        "ALT-000001",
        expected_state="NEW",
        occurred_at=occurred_at,
        actor_reference="rm-001",
        idempotency_token="ack-once",
    )
    replay = service.acknowledge(
        "ALT-000001",
        expected_state="NEW",
        occurred_at=occurred_at,
        actor_reference="rm-001",
        idempotency_token="ack-once",
    )

    assert first.idempotent_replay is False
    assert replay.idempotent_replay is True
    assert replay.alert_case == first.alert_case
    assert repository.get("ALT-000001") == first.alert_case
    with pytest.raises(BankerIdempotencyConflictError, match="different operation"):
        service.acknowledge(
            "ALT-000001",
            expected_state="ACKNOWLEDGED",
            occurred_at=BASE_TIME + timedelta(minutes=2),
            actor_reference="rm-001",
            idempotency_token="ack-once",
        )

    reviewed = service.start_review(
        "ALT-000001",
        expected_state="ACKNOWLEDGED",
        occurred_at=BASE_TIME + timedelta(minutes=2),
        actor_reference="rm-001",
        idempotency_token="review-1",
    )
    first_action = service.record_action(
        "ALT-000001",
        expected_state="IN_REVIEW",
        action="REVIEW_COMPLETED",
        occurred_at=BASE_TIME + timedelta(minutes=3),
        actor_reference="rm-001",
        idempotency_token="action-once",
    )
    replayed_action = service.record_action(
        "ALT-000001",
        expected_state="IN_REVIEW",
        action="REVIEW_COMPLETED",
        occurred_at=BASE_TIME + timedelta(minutes=3),
        actor_reference="rm-001",
        idempotency_token="action-once",
    )
    assert reviewed.current_state == "IN_REVIEW"
    assert first_action.action_record == replayed_action.action_record
    assert replayed_action.idempotent_replay is True
    assert len(service.audit_store.list_events()) == 3


def test_close_and_explicit_reopen_create_one_new_case_and_preserve_closed_history(tmp_path: Path) -> None:
    blocked_service, repository = _service(tmp_path)
    _move_to_follow_up(blocked_service)
    closed = blocked_service.close(
        "ALT-000001",
        expected_state="FOLLOW_UP",
        occurred_at=BASE_TIME + timedelta(minutes=5),
        actor_reference="rm-001",
        idempotency_token="close-1",
        case_outcome=_close_outcome(BASE_TIME + timedelta(minutes=5)),
    )
    with pytest.raises(BankerServiceError, match="not enabled"):
        blocked_service.reopen(
            "ALT-000001",
            expected_state="CLOSED",
            occurred_at=BASE_TIME + timedelta(minutes=6),
            actor_reference="rm-001",
            idempotency_token="reopen-1",
        )

    service = BankerApplicationService(
        repository,
        audit_store=blocked_service.audit_store,
        allow_closed_case_reopen=True,
    )
    reopened = service.reopen(
        "ALT-000001",
        expected_state="CLOSED",
        occurred_at=BASE_TIME + timedelta(minutes=6),
        actor_reference="rm-001",
        idempotency_token="reopen-1",
    )
    replay = service.reopen(
        "ALT-000001",
        expected_state="CLOSED",
        occurred_at=BASE_TIME + timedelta(minutes=6),
        actor_reference="rm-001",
        idempotency_token="reopen-1",
    )

    assert closed.current_state == "CLOSED"
    assert reopened.current_state == "NEW"
    assert reopened.reopened_from_alert_id == "ALT-000001"
    assert reopened.alert_case.alert_id != "ALT-000001"
    assert repository.get("ALT-000001") == closed.alert_case
    assert len(repository.list_cases()) == 2
    assert replay.idempotent_replay is True
    assert replay.alert_case == reopened.alert_case


def test_close_rejects_mismatched_or_nonterminal_outcomes_before_state_mutation(tmp_path: Path) -> None:
    service, repository = _service(tmp_path)
    _move_to_follow_up(service)
    mismatched = CaseOutcomeRecord(
        alert_id="ALT-OTHER",
        customer_id="C000001",
        outcome="CONTACT_DOCUMENTED",
        recorded_at=BASE_TIME + timedelta(minutes=4),
        recorded_by="rm-001",
        closure_reason="CONTACT_COMPLETED",
    )
    with pytest.raises(ValueError, match="identify the current"):
        service.close(
            "ALT-000001",
            expected_state="FOLLOW_UP",
            occurred_at=BASE_TIME + timedelta(minutes=4),
            actor_reference="rm-001",
            idempotency_token="bad-close",
            case_outcome=mismatched,
        )
    current = repository.get("ALT-000001")
    assert current is not None and current.state == "FOLLOW_UP"


def test_service_module_is_ui_free_and_keeps_repository_writes_behind_the_service() -> None:
    source = Path(banker_service.__file__).read_text(encoding="utf-8")
    source_tree = ast.parse(source)
    imported_modules = [
        alias.name
        for node in ast.walk(source_tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    ]

    assert "streamlit" not in source.lower()
    assert "final_outcome" not in source
    assert "persona" not in source
    assert not any("notification" in module or "provider" in module for module in imported_modules)
    assert "self.repository.update" in source
    assert "self.repository.create" in source
