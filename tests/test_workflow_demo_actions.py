"""Focused action, audit, and Preview contracts for the isolated demo only."""

from __future__ import annotations

import ast
import hashlib
import inspect
import shutil
from datetime import timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import app as app_module
from config import settings
from src.banker_service import BankerIdempotencyConflictError, BankerStateConflictError
from src.rm_workflow_ui import (
    build_offline_notification_preview,
    build_rm_activity_history,
    load_rm_workflow_case,
    make_submission_token,
    perform_rm_workflow_operation,
    utc_now,
)
from src.workflow_demo import (
    WORKFLOW_DEMO_FIXTURE_FILENAME,
    WorkflowDemoPaths,
    load_demo_runtime,
    reset_demo,
)
from src.workflow_demo_ui import (
    WORKFLOW_DEMO_PATHS_KEY,
    WORKFLOW_DEMO_SERVICE_KEY,
    WorkflowDemoStaleServiceError,
    get_workflow_demo_ui_service,
    perform_workflow_demo_operation,
    prepare_workflow_demo_reset,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_FIXTURE = (
    PROJECT_ROOT / "artifacts" / "workflow_demo" / "fixture_v1" / WORKFLOW_DEMO_FIXTURE_FILENAME
)


def _paths(tmp_path: Path) -> WorkflowDemoPaths:
    fixture_path = tmp_path / "fixture" / WORKFLOW_DEMO_FIXTURE_FILENAME
    fixture_path.parent.mkdir(parents=True)
    shutil.copyfile(SOURCE_FIXTURE, fixture_path)
    return WorkflowDemoPaths(fixture_path=fixture_path, runtime_root=tmp_path / "runtime")


def _digest(path: Path) -> str:
    if not path.exists():
        return "<absent>"
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    digest = hashlib.sha256()
    for child in sorted(path.rglob("*")):
        digest.update(str(child.relative_to(path)).encode("utf-8"))
        if child.is_file():
            digest.update(child.read_bytes())
    return digest.hexdigest()


def test_demo_service_injects_only_the_initialized_runtime_and_clears_on_reset(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    session: dict[str, object] = {}

    assert get_workflow_demo_ui_service(session, paths=paths) is None
    reset_demo(paths)
    first = get_workflow_demo_ui_service(session, paths=paths)
    second = get_workflow_demo_ui_service(session, paths=paths)

    assert first is not None
    assert first is second
    assert first.banker_service.repository.storage_path.parent == paths.workflow_root
    assert first.audit_store.storage_path.parent == paths.audit_root
    assert WORKFLOW_DEMO_SERVICE_KEY in session
    assert session[WORKFLOW_DEMO_PATHS_KEY] == paths

    prepare_workflow_demo_reset(session)
    assert WORKFLOW_DEMO_SERVICE_KEY not in session
    assert WORKFLOW_DEMO_PATHS_KEY not in session
    reset_demo(paths)
    replacement = get_workflow_demo_ui_service(session, paths=paths)
    assert replacement is not None
    assert replacement is not first


def test_demo_actions_are_idempotent_state_aware_and_reconcile_with_append_only_audit(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    protected = (
        settings.BASE_DIR / "artifacts" / "workflow",
        settings.BASE_DIR / "artifacts" / "audit",
        settings.DATA_RAW_DIR / "customer_master.csv",
        settings.BASE_DIR
        / "artifacts"
        / "triage"
        / "seed42_crossfit_5fold_asof12_unbounded"
        / "rm_selection_manifest.json",
    )
    before = {path: _digest(path) for path in protected}
    reset_demo(paths)
    service = get_workflow_demo_ui_service({}, paths=paths)
    assert service is not None
    initial = load_demo_runtime(paths)
    case = initial.cases[0]
    now = utc_now()
    acknowledgement_token = make_submission_token(
        namespace="workflow_demo",
        alert_id=case.alert_id,
        expected_state="NEW",
        operation="ACKNOWLEDGE",
    )

    acknowledged = perform_rm_workflow_operation(
        service,
        operation="ACKNOWLEDGE",
        alert_id=case.alert_id,
        expected_state="NEW",
        occurred_at=now,
        actor_reference="synthetic-workflow-demo",
        idempotency_token=acknowledgement_token,
    )
    replay = perform_rm_workflow_operation(
        service,
        operation="ACKNOWLEDGE",
        alert_id=case.alert_id,
        expected_state="NEW",
        occurred_at=now,
        actor_reference="synthetic-workflow-demo",
        idempotency_token=acknowledgement_token,
    )

    assert acknowledged.current_state == "ACKNOWLEDGED"
    assert replay.idempotent_replay is True
    assert len(service.audit_store.list_events()) == 1
    with pytest.raises(BankerIdempotencyConflictError):
        perform_rm_workflow_operation(
            service,
            operation="START_REVIEW",
            alert_id=case.alert_id,
            expected_state="ACKNOWLEDGED",
            occurred_at=now + timedelta(minutes=1),
            actor_reference="synthetic-workflow-demo",
            idempotency_token=acknowledgement_token,
        )
    with pytest.raises(BankerStateConflictError):
        perform_rm_workflow_operation(
            service,
            operation="ACKNOWLEDGE",
            alert_id=case.alert_id,
            expected_state="NEW",
            occurred_at=now + timedelta(minutes=1),
            actor_reference="synthetic-workflow-demo",
            idempotency_token="different-stale-token",
        )

    reviewed = perform_rm_workflow_operation(
        service,
        operation="START_REVIEW",
        alert_id=case.alert_id,
        expected_state="ACKNOWLEDGED",
        occurred_at=now + timedelta(minutes=2),
        actor_reference="synthetic-workflow-demo",
        idempotency_token=make_submission_token(
            namespace="workflow_demo",
            alert_id=case.alert_id,
            expected_state="ACKNOWLEDGED",
            operation="START_REVIEW",
        ),
    )
    recorded = perform_rm_workflow_operation(
        service,
        operation="RECORD_ACTION",
        alert_id=case.alert_id,
        expected_state=reviewed.current_state,
        action="CONTACT_PLANNED",
        occurred_at=now + timedelta(minutes=3),
        actor_reference="synthetic-workflow-demo",
        idempotency_token=make_submission_token(
            namespace="workflow_demo",
            alert_id=case.alert_id,
            expected_state=reviewed.current_state,
            operation="RECORD_ACTION",
            action="CONTACT_PLANNED",
        ),
    )
    followed_up = perform_rm_workflow_operation(
        service,
        operation="SET_FOLLOW_UP",
        alert_id=case.alert_id,
        expected_state=recorded.current_state,
        occurred_at=now + timedelta(minutes=4),
        actor_reference="synthetic-workflow-demo",
        idempotency_token=make_submission_token(
            namespace="workflow_demo",
            alert_id=case.alert_id,
            expected_state=recorded.current_state,
            operation="SET_FOLLOW_UP",
        ),
    )
    closed = perform_rm_workflow_operation(
        service,
        operation="CLOSE",
        alert_id=case.alert_id,
        expected_state=followed_up.current_state,
        close_outcome="CONTACT_DOCUMENTED",
        closure_reason="CONTACT_COMPLETED",
        occurred_at=now + timedelta(minutes=5),
        actor_reference="synthetic-workflow-demo",
        idempotency_token=make_submission_token(
            namespace="workflow_demo",
            alert_id=case.alert_id,
            expected_state=followed_up.current_state,
            operation="CLOSE",
            action="CONTACT_DOCUMENTED",
        ),
    )

    current = load_rm_workflow_case(service, alert_id=case.alert_id)
    history = build_rm_activity_history(service, alert_id=case.alert_id)
    assert closed.current_state == "CLOSED"
    assert current is not None and current.state == "CLOSED"
    assert [event["operation"] for event in history["events"]] == [
        "ACKNOWLEDGE",
        "START_REVIEW",
        "RECORD_ACTION",
        "SET_FOLLOW_UP",
        "CLOSE",
    ]
    assert [event["sequence"] for event in history["events"]] == [1, 2, 3, 4, 5]
    assert len(load_demo_runtime(paths).cases) == 3
    assert {path: _digest(path) for path in protected} == before


def test_demo_preview_is_offline_and_reset_restores_the_initial_fixture(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    session: dict[str, object] = {}
    reset_demo(paths)
    service = get_workflow_demo_ui_service(session, paths=paths)
    assert service is not None
    case = load_demo_runtime(paths).cases[0]
    cases_before = service.banker_service.repository.list_cases()
    audit_before = service.audit_store.list_events()

    preview = build_offline_notification_preview(service, alert_case=case)

    assert preview["status"] == "PREVIEW"
    assert preview["sent"] is False
    assert preview["external_delivery_attempted"] is False
    assert preview["scope"]["case_mutated"] is False
    assert preview["scope"]["audit_mutated"] is False
    assert preview["scope"]["network_called"] is False
    assert service.banker_service.repository.list_cases() == cases_before
    assert service.audit_store.list_events() == audit_before

    now = utc_now()
    perform_rm_workflow_operation(
        service,
        operation="ACKNOWLEDGE",
        alert_id=case.alert_id,
        expected_state="NEW",
        occurred_at=now,
        actor_reference="synthetic-workflow-demo",
        idempotency_token="demo-reset-acknowledgement",
    )
    prepare_workflow_demo_reset(session)
    reset_demo(paths)
    restored = load_demo_runtime(paths)
    assert [item.state for item in restored.cases] == ["NEW", "NEW", "NEW"]
    assert not paths.audit_root.joinpath("audit_events.jsonl").exists()
    assert get_workflow_demo_ui_service(session, paths=paths) is not None


def test_reset_invalidates_stale_demo_service_before_it_can_write_to_the_new_runtime(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    session: dict[str, object] = {}
    reset_demo(paths)
    stale_service = get_workflow_demo_ui_service(session, paths=paths)
    assert stale_service is not None
    stale_case = load_demo_runtime(paths).cases[0]

    prepare_workflow_demo_reset(session)
    reset_demo(paths)
    before = (
        (paths.workflow_root / "alert_cases.json").read_bytes(),
        paths.audit_root.joinpath("audit_events.jsonl").exists(),
    )
    with pytest.raises(WorkflowDemoStaleServiceError, match="stale"):
        perform_workflow_demo_operation(
            session,
            stale_service,
            operation="ACKNOWLEDGE",
            alert_id=stale_case.alert_id,
            expected_state="NEW",
            occurred_at=utc_now(),
            actor_reference="synthetic-workflow-demo",
            idempotency_token="stale-service-attempt",
            paths=paths,
        )

    restored = load_demo_runtime(paths)
    assert [case.state for case in restored.cases] == ["NEW", "NEW", "NEW"]
    assert (
        (paths.workflow_root / "alert_cases.json").read_bytes(),
        paths.audit_root.joinpath("audit_events.jsonl").exists(),
    ) == before


def test_demo_action_renderer_uses_application_adapter_and_demo_namespaced_widget_keys() -> None:
    source = "\n".join(
        (
            inspect.getsource(app_module._render_workflow_demo_action_controls),
            inspect.getsource(app_module._submit_workflow_demo_action),
            inspect.getsource(app_module._render_workflow_demo_activity_audit),
        )
    )

    assert "perform_workflow_demo_operation" in source
    assert "namespace=\"workflow_demo\"" in source
    assert "FileAlertCaseRepository" not in source
    assert "FileAuditEventStore" not in source
    assert ".create(" not in source
    assert ".update(" not in source
    assert "rm_workflow_demo_" in source
    assert "channel" not in source.lower()


def test_demo_action_controls_render_and_mutate_only_an_injected_runtime(tmp_path: Path) -> None:
    root = str(tmp_path).replace("\\", "\\\\")
    fixture = str(SOURCE_FIXTURE).replace("\\", "\\\\")
    source = f'''\
from pathlib import Path
import streamlit as st
import app
from src.workflow_demo import WorkflowDemoPaths, load_demo_runtime, reset_demo
from src.workflow_demo_ui import get_workflow_demo_ui_service

paths = WorkflowDemoPaths(
    fixture_path=Path(r"{fixture}"),
    runtime_root=Path(r"{root}") / "runtime",
)
if "demo_initialized" not in st.session_state:
    reset_demo(paths)
    st.session_state["demo_initialized"] = True
service = get_workflow_demo_ui_service(st.session_state, paths=paths)
case = load_demo_runtime(paths).cases[0]
app._render_workflow_demo_action_controls(case, language="en", workflow_service=service)
app._render_workflow_demo_activity_audit(case, language="en", workflow_service=service)
'''
    at = AppTest.from_string(source)
    at.run(timeout=30)

    assert not at.exception
    assert [button.key for button in at.button if "acknowledge" in button.key] == [
        "rm_workflow_demo_action_acknowledge_ALT-DEMO-C000001_NEW"
    ]
    at.button(key="rm_workflow_demo_notification_preview_ALT-DEMO-C000001_NEW").click().run(timeout=30)
    assert not at.exception
    assert any("not sent" in str(item.value).lower() for item in at.markdown)
    at.button(key="rm_workflow_demo_action_acknowledge_ALT-DEMO-C000001_NEW").click().run(timeout=30)
    assert not at.exception
    assert [
        button.key
        for button in at.button
        if button.key == "rm_workflow_demo_action_start_review_ALT-DEMO-C000001_ACKNOWLEDGED"
    ] == ["rm_workflow_demo_action_start_review_ALT-DEMO-C000001_ACKNOWLEDGED"]


def test_demo_ui_and_fixture_modules_remain_streamlit_network_and_label_independent() -> None:
    for module in ("src/workflow_demo.py", "src/workflow_demo_ui.py"):
        source = (PROJECT_ROOT / module).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_roots = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported_roots.update(
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        assert {"streamlit", "requests", "httpx", "socket"}.isdisjoint(imported_roots)
        assert "final_outcome" not in source
        assert "persona" not in source
