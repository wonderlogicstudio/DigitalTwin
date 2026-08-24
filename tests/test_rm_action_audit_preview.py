"""Focused contracts for RM UI action, audit, and offline-preview adapters."""

from __future__ import annotations

import ast
import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path

import app as app_module
from streamlit.testing.v1 import AppTest

from src.alert_case import TimingEvidenceReference, create_alert_case
from src.alert_repository import FileAlertCaseRepository
from src.audit_trail import FileAuditEventStore
from src.banker_service import BankerApplicationService
from src.notifications import PreviewNotificationService
from src.rm_workflow_ui import (
    RMWorkflowUIService,
    build_offline_notification_preview,
    build_rm_activity_history,
    make_submission_token,
    perform_rm_workflow_operation,
)


NOW = datetime(2026, 8, 23, 9, 0, tzinfo=timezone.utc)


def _case() -> object:
    return create_alert_case(
        alert_id="ALT-000001",
        customer_id="C000001",
        policy_id="synthetic_early_warning_demo",
        policy_version="0.1.0",
        selection_policy_id="transparent_triage_selection_demo",
        selection_policy_version="0.1.0",
        signal_run_id="crossfit_seed42_5fold_asof12",
        signal_version="prospective_signal_snapshot.v1",
        signal_as_of_month=12,
        created_at=NOW,
        due_at=NOW + timedelta(days=2),
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


def _service(tmp_path: Path) -> RMWorkflowUIService:
    repository = FileAlertCaseRepository(tmp_path / "workflow")
    repository.create(_case())
    audit_store = FileAuditEventStore(tmp_path / "audit")
    return RMWorkflowUIService(
        banker_service=BankerApplicationService(
            repository,
            audit_store=audit_store,
            allow_closed_case_reopen=True,
        ),
        audit_store=audit_store,
        preview_service=PreviewNotificationService(),
    )


def test_ui_adapter_uses_banker_service_for_idempotent_state_and_audit_sync(tmp_path: Path) -> None:
    service = _service(tmp_path)
    token = make_submission_token(
        alert_id="ALT-000001",
        expected_state="NEW",
        operation="ACKNOWLEDGE",
    )
    first = perform_rm_workflow_operation(
        service,
        operation="ACKNOWLEDGE",
        alert_id="ALT-000001",
        expected_state="NEW",
        occurred_at=NOW + timedelta(minutes=1),
        actor_reference="rm-demo",
        idempotency_token=token,
    )
    replay = perform_rm_workflow_operation(
        service,
        operation="ACKNOWLEDGE",
        alert_id="ALT-000001",
        expected_state="NEW",
        occurred_at=NOW + timedelta(minutes=1),
        actor_reference="rm-demo",
        idempotency_token=token,
    )

    assert first.current_state == "ACKNOWLEDGED"
    assert replay.idempotent_replay is True
    history = build_rm_activity_history(service, alert_id="ALT-000001")
    assert history["available"] is True
    assert [event["operation"] for event in history["events"]] == ["ACKNOWLEDGE"]
    assert history["events"][0]["previous_state"] == "NEW"
    assert history["events"][0]["new_state"] == "ACKNOWLEDGED"
    assert history["scope"] == {"audit_file_mutated": False}
    assert len(service.audit_store.list_events()) == 1


def test_close_and_reopen_remain_explicit_and_are_visible_in_chronological_history(tmp_path: Path) -> None:
    service = _service(tmp_path)
    acknowledged = perform_rm_workflow_operation(
        service,
        operation="ACKNOWLEDGE",
        alert_id="ALT-000001",
        expected_state="NEW",
        occurred_at=NOW + timedelta(minutes=1),
        actor_reference="rm-demo",
        idempotency_token="ack",
    )
    reviewed = perform_rm_workflow_operation(
        service,
        operation="START_REVIEW",
        alert_id="ALT-000001",
        expected_state=acknowledged.current_state,
        occurred_at=NOW + timedelta(minutes=2),
        actor_reference="rm-demo",
        idempotency_token="review",
    )
    followed_up = perform_rm_workflow_operation(
        service,
        operation="SET_FOLLOW_UP",
        alert_id="ALT-000001",
        expected_state=reviewed.current_state,
        occurred_at=NOW + timedelta(minutes=3),
        actor_reference="rm-demo",
        idempotency_token="follow-up",
    )
    closed = perform_rm_workflow_operation(
        service,
        operation="CLOSE",
        alert_id="ALT-000001",
        expected_state=followed_up.current_state,
        occurred_at=NOW + timedelta(minutes=4),
        actor_reference="rm-demo",
        idempotency_token="close",
        close_outcome="CONTACT_DOCUMENTED",
        closure_reason="CONTACT_COMPLETED",
    )
    reopened = perform_rm_workflow_operation(
        service,
        operation="REOPEN",
        alert_id="ALT-000001",
        expected_state=closed.current_state,
        occurred_at=NOW + timedelta(minutes=5),
        actor_reference="rm-demo",
        idempotency_token="reopen",
    )

    assert closed.current_state == "CLOSED"
    assert reopened.current_state == "NEW"
    history = build_rm_activity_history(service, customer_id="C000001")
    assert [event["operation"] for event in history["events"]] == [
        "ACKNOWLEDGE",
        "START_REVIEW",
        "SET_FOLLOW_UP",
        "CLOSE",
        "REOPEN",
    ]
    assert [event["timestamp"] for event in history["events"]] == sorted(
        event["timestamp"] for event in history["events"]
    )


def test_offline_preview_has_no_network_or_case_audit_mutation(tmp_path: Path) -> None:
    service = _service(tmp_path)
    alert_case = service.banker_service.repository.get("ALT-000001")
    assert alert_case is not None
    cases_before = service.banker_service.repository.list_cases()
    audit_before = service.audit_store.list_events()

    preview = build_offline_notification_preview(service, alert_case=alert_case)

    assert preview["status"] == "PREVIEW"
    assert preview["sent"] is False
    assert preview["external_delivery_attempted"] is False
    assert preview["scope"] == {
        "case_mutated": False,
        "audit_mutated": False,
        "network_called": False,
        "external_delivery_implemented": False,
    }
    assert "not sent" in str(preview["body"]).lower()
    assert service.banker_service.repository.list_cases() == cases_before
    assert service.audit_store.list_events() == audit_before
    assert "alert_id=ALT-000001" in str(preview["deep_link"])
    assert "customer_id=C000001" in str(preview["deep_link"])


def test_customer_action_renderer_has_no_direct_repository_or_audit_write() -> None:
    source = "\n".join(
        (
            inspect.getsource(app_module._render_rm_action_controls),
            inspect.getsource(app_module._submit_rm_action),
        )
    )

    assert "perform_rm_workflow_operation" in source
    assert "FileAlertCaseRepository" not in source
    assert "FileAuditEventStore" not in source
    assert ".create(" not in source
    assert ".update(" not in source
    assert "channel" not in source.lower()
    assert "sent" in source.lower()


def test_app_test_action_control_uses_service_and_refreshes_activity(tmp_path: Path) -> None:
    root = str(tmp_path).replace("\\", "\\\\")
    source = f'''\
from datetime import datetime, timedelta, timezone
from pathlib import Path
import streamlit as st
import app
from src.alert_case import TimingEvidenceReference, create_alert_case
from src.alert_repository import FileAlertCaseRepository
from src.audit_trail import FileAuditEventStore
from src.banker_service import BankerApplicationService
from src.notifications import PreviewNotificationService
from src.rm_workflow_ui import RMWorkflowUIService

now = datetime(2026, 8, 23, 9, tzinfo=timezone.utc)
if "rm_action_app_service" not in st.session_state:
    root = Path(r"{root}")
    repository = FileAlertCaseRepository(root / "workflow")
    case = create_alert_case(
        alert_id="ALT-UI-000001", customer_id="C000001",
        policy_id="synthetic_early_warning_demo", policy_version="0.1.0",
        selection_policy_id="transparent_triage_selection_demo", selection_policy_version="0.1.0",
        signal_run_id="crossfit_seed42_5fold_asof12", signal_version="prospective_signal_snapshot.v1",
        signal_as_of_month=12, created_at=now, due_at=now + timedelta(days=2),
        operational_priority="PRIORITY_REVIEW", why_now_reason_codes=("CURRENT_STATUS_CONCERNING",),
        selection_reason_codes=("PRIORITY_BAND_PRIORITY_REVIEW",),
        timing_evidence_reference=TimingEvidenceReference(source="prospective_signal", candidate_month=12, evaluation_status="not_evaluated"),
        episode_key="C000001:synthetic_early_warning_demo:12")
    repository.create(case)
    audit = FileAuditEventStore(root / "audit")
    st.session_state["rm_action_app_service"] = RMWorkflowUIService(
        banker_service=BankerApplicationService(repository, audit_store=audit, allow_closed_case_reopen=True),
        audit_store=audit, preview_service=PreviewNotificationService())
service = st.session_state["rm_action_app_service"]
case = service.banker_service.repository.get("ALT-UI-000001")
review = {{
    "customer_id": "C000001",
    "header": {{"operational_label": "Priority Review", "context_label": "Operational review queue", "case_state": case.state, "due_at": case.due_at.isoformat(), "selection_reason": "Manifest reason", "why_now": "Current observed signal"}},
    "provenance": {{"policy_id": "synthetic_early_warning_demo", "policy_version": "0.1.0", "selection_as_of_month": 12}},
    "current_signals": {{"available": False, "message": "unavailable"}},
    "chart_trajectory": None,
    "prospective_timing": {{"available": False, "message": "unavailable"}},
    "twin_evidence": {{"available": False, "message": "unavailable"}},
    "historical_landmark": {{"status": "not_found", "message": "unavailable", "caption": "historical only"}},
    "recommended_follow_up": {{"available": False, "message": "pending", "actions": (), "whatif_supporting_evidence": {{"available": False, "message": "unavailable"}}}},
    "workflow_case": {{"available": True, "alert_id": case.alert_id, "state": case.state}},
}}
app._render_rm_customer_review(review, language="en", workflow_service=service)
app._render_rm_activity_audit(review, language="en", workflow_service=service)
'''
    at = AppTest.from_string(source)
    at.run(timeout=30)

    assert not at.exception
    at.button(key="rm_action_acknowledge_ALT-UI-000001_NEW").click().run(timeout=30)
    assert not at.exception
    assert any("ACKNOWLEDGED" in str(item.value) for item in at.metric)
    assert len(at.dataframe) == 1


def test_rm_workflow_adapter_has_no_streamlit_or_external_delivery_import() -> None:
    import src.rm_workflow_ui as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = [
        alias.name.lower()
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    ]

    assert "streamlit" not in source.lower()
    assert "final_outcome" not in source
    assert "persona" not in source
    assert not any(
        marker in imported
        for imported in imported_modules
        for marker in ("requests", "socket", "smtp", "webhook", "slack", "teams")
    )
