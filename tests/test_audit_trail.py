"""Contracts for the append-only RM workflow audit trail."""

from __future__ import annotations

import ast
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import src.audit_trail as audit_trail
from src.alert_case import AlertCase, TimingEvidenceReference, create_alert_case
from src.alert_repository import AlertCaseRepositoryConflictError, FileAlertCaseRepository
from src.audit_trail import (
    AUDIT_CONSISTENCY_POLICY,
    AuditEvent,
    AuditEventStore,
    AuditTrailCorruptError,
    AuditTrailDuplicateError,
    AuditTrailError,
    FileAuditEventStore,
    build_banker_audit_event,
)
from src.banker_service import BankerApplicationService, BankerStateConflictError


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


def _event(*, operation: str = "ACKNOWLEDGE", fingerprint: str = "token-1") -> AuditEvent:
    return build_banker_audit_event(
        _case(),
        operation=operation,
        operation_fingerprint=fingerprint,
        timestamp=BASE_TIME + timedelta(minutes=1),
        actor_reference="rm-001",
        previous_state="NEW",
        new_state="ACKNOWLEDGED",
    )


def test_jsonl_store_preserves_append_order_and_reuses_identical_event_once(tmp_path: Path) -> None:
    store = FileAuditEventStore(tmp_path / "audit")
    first = store.append(_event(fingerprint="token-1"))
    second = store.append(_event(operation="START_REVIEW", fingerprint="token-2"))
    replay = store.append(_event(fingerprint="token-1"))

    assert first.sequence == 1
    assert second.sequence == 2
    assert replay == first
    assert store.list_events() == (first, second)
    assert store.storage_path.read_text(encoding="utf-8").count("\n") == 2
    assert not hasattr(store, "update")
    assert not hasattr(store, "delete")


def test_event_id_cannot_be_reused_for_different_content(tmp_path: Path) -> None:
    store = FileAuditEventStore(tmp_path / "audit")
    original = _event()
    store.append(original)

    with pytest.raises(AuditTrailDuplicateError, match="event_id already exists"):
        store.append(replace(original, customer_id="C000002"))


def test_corrupt_or_partially_written_log_fails_explicitly(tmp_path: Path) -> None:
    store = FileAuditEventStore(tmp_path / "audit")
    store.storage_dir.mkdir(parents=True)
    store.storage_path.write_text('{"sequence": 1', encoding="utf-8")

    with pytest.raises(AuditTrailCorruptError, match="invalid append-only event"):
        store.list_events()


def test_metadata_and_actor_reject_contact_or_secret_like_content() -> None:
    with pytest.raises(ValueError, match="metadata keys are not allowed"):
        build_banker_audit_event(
            _case(),
            operation="ACKNOWLEDGE",
            operation_fingerprint="token-1",
            timestamp=BASE_TIME,
            actor_reference="rm-001",
            previous_state="NEW",
            new_state="ACKNOWLEDGED",
            metadata={"email": "person@example.test"},
        )
    with pytest.raises(ValueError, match="actor_reference"):
        build_banker_audit_event(
            _case(),
            operation="ACKNOWLEDGE",
            operation_fingerprint="token-1",
            timestamp=BASE_TIME,
            actor_reference="person@example.test",
            previous_state="NEW",
            new_state="ACKNOWLEDGED",
        )


def test_audit_store_rejects_analytics_and_workflow_repository_paths() -> None:
    from config import settings

    with pytest.raises(ValueError, match="separate"):
        FileAuditEventStore(settings.DATA_DEMO_DIR)
    with pytest.raises(ValueError, match="separate"):
        FileAuditEventStore(settings.BASE_DIR / "artifacts" / "workflow")


class _FailingAuditStore:
    def append(self, event: AuditEvent) -> AuditEvent:
        raise AuditTrailError("forced audit append failure")

    def list_events(self) -> tuple[AuditEvent, ...]:
        return ()


class _FailingUpdateRepository:
    """Delegates reads but fails before any business-state persistence."""

    def __init__(self, delegate: FileAlertCaseRepository) -> None:
        self.delegate = delegate

    def get(self, alert_id: str) -> AlertCase | None:
        return self.delegate.get(alert_id)

    def list_cases(self) -> tuple[AlertCase, ...]:
        return self.delegate.list_cases()

    def create(self, alert_case: AlertCase) -> AlertCase:
        return self.delegate.create(alert_case)

    def update(self, alert_case: AlertCase, *, expected_updated_at: datetime) -> AlertCase:
        raise AlertCaseRepositoryConflictError("forced repository conflict")

    def open_by_episode(self, customer_id: str, episode_key: str) -> AlertCase | None:
        return self.delegate.open_by_episode(customer_id, episode_key)


def test_audit_failure_is_fail_closed_before_business_state_mutation(tmp_path: Path) -> None:
    repository = FileAlertCaseRepository(tmp_path / "workflow")
    repository.create(_case())
    service = BankerApplicationService(repository, audit_store=_FailingAuditStore())

    with pytest.raises(AuditTrailError, match="forced audit append failure"):
        service.acknowledge(
            "ALT-000001",
            expected_state="NEW",
            occurred_at=BASE_TIME + timedelta(minutes=1),
            actor_reference="rm-001",
            idempotency_token="ack-fail-audit",
        )
    stored = repository.get("ALT-000001")
    assert stored is not None and stored.state == "NEW"


def test_repository_failure_leaves_requested_audit_without_claiming_state_change(tmp_path: Path) -> None:
    delegate = FileAlertCaseRepository(tmp_path / "workflow")
    delegate.create(_case())
    audit_store = FileAuditEventStore(tmp_path / "audit")
    service = BankerApplicationService(_FailingUpdateRepository(delegate), audit_store=audit_store)

    with pytest.raises(BankerStateConflictError, match="forced repository conflict"):
        service.acknowledge(
            "ALT-000001",
            expected_state="NEW",
            occurred_at=BASE_TIME + timedelta(minutes=1),
            actor_reference="rm-001",
            idempotency_token="ack-fail-repository",
        )
    stored = delegate.get("ALT-000001")
    assert stored is not None and stored.state == "NEW"
    event = audit_store.list_events()[0]
    assert event.metadata["consistency_policy"] == AUDIT_CONSISTENCY_POLICY
    assert event.metadata["transition_status"] == "REQUESTED"
    assert event.previous_state == "NEW"
    assert event.new_state == "ACKNOWLEDGED"


def test_audit_module_is_append_only_and_has_no_database_or_delivery_dependency() -> None:
    source = Path(audit_trail.__file__).read_text(encoding="utf-8")
    source_tree = ast.parse(source)
    imported_modules = [
        alias.name
        for node in ast.walk(source_tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    ]

    assert "final_outcome" not in source
    assert "streamlit" not in source.lower()
    assert not any(
        marker in module.lower()
        for module in imported_modules
        for marker in ("sql", "database", "orm", "notification", "provider", "smtp", "webhook")
    )
    assert hasattr(AuditEventStore, "append")
    assert hasattr(AuditEventStore, "list_events")
    assert not hasattr(AuditEventStore, "update")
    assert not hasattr(AuditEventStore, "delete")
