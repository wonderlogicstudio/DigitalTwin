"""Regression locks for the boundary between Guided RM and Workflow Demo."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import shutil

from config import settings
from src.i18n import t
from src.rm_guided_workflow import RMGuidedContext, build_rm_guided_workflow_state
from src.rm_workflow_ui import build_offline_notification_preview, load_rm_workflow_case, utc_now
from src.workflow_demo import WORKFLOW_DEMO_FIXTURE_FILENAME, WorkflowDemoPaths
from src.workflow_demo_ui import (
    WORKFLOW_DEMO_OPEN_KEY,
    WORKFLOW_DEMO_PREVIEW_KEY,
    WORKFLOW_DEMO_SELECTED_ALERT_KEY,
    enter_workflow_demo,
    exit_workflow_demo,
    get_workflow_demo_ui_service,
    initialize_or_reset_workflow_demo,
    perform_workflow_demo_operation,
    prepare_workflow_demo_reset,
)


def _tree_digest(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    for item in sorted((candidate for candidate in path.rglob("*") if candidate.is_file()), key=str):
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(item.read_bytes())
    return digest.hexdigest()


def _normal_guided_context() -> RMGuidedContext:
    return RMGuidedContext(
        portfolio_queue_view_model={
            "available": True,
            "portfolio": {"reconciliation": {"is_exact": True}},
            "queue": {
                "rows": (
                    {"customer_id": "C000001", "routing_disposition": "CREATE_NEW_CASE"},
                )
            },
        },
        customer_review_view_model={
            "available": True,
            "customer_id": "C000001",
            "stale": False,
            "header": {"context_type": "operational_queue"},
            "workflow_case": {"available": True, "alert_id": "ALT-000001", "state": "IN_REVIEW"},
        },
        capacity_acknowledged=True,
        capacity_value=7,
        customer_id="C000001",
        customer_origin="operational_queue",
        evidence_acknowledged=True,
        current_case_metadata={"available": True, "alert_id": "ALT-000001"},
        activity_audit_metadata={"available": True, "events": ()},
        last_banker_operation_metadata={"success": True},
    )


def _guided_session_snapshot() -> dict[str, object]:
    return {
        "rm_queue_scope": "selected",
        "rm_queue_search": "C000001",
        "rm_queue_priority_filter": "Priority Review",
        "rm_capacity_comparison_enabled": True,
        "rm_capacity_comparison_value": 7,
        "rm_guided_capacity_acknowledged": True,
        "rm_guided_capacity_acknowledged_value": 7,
        "rm_guided_capacity_acknowledgement_control": True,
        "rm_customer_context": "C000001",
        "rm_guided_customer_id": "C000001",
        "rm_guided_customer_origin": "operational_queue",
        "rm_guided_evidence_acknowledged_C000001": True,
        "rm_guided_audit_acknowledged_ALT-001": True,
    }


def _injected_demo_paths(tmp_path: Path) -> WorkflowDemoPaths:
    source_fixture = (
        Path(__file__).resolve().parents[1]
        / "artifacts"
        / "workflow_demo"
        / "fixture_v1"
        / WORKFLOW_DEMO_FIXTURE_FILENAME
    )
    fixture_path = tmp_path / "fixture" / WORKFLOW_DEMO_FIXTURE_FILENAME
    fixture_path.parent.mkdir(parents=True)
    shutil.copyfile(source_fixture, fixture_path)
    return WorkflowDemoPaths(fixture_path=fixture_path, runtime_root=tmp_path / "runtime")


def test_demo_entry_reset_and_exit_preserve_the_complete_guided_rm_snapshot() -> None:
    """The optional practice branch cannot alter normal RM continuity state."""

    session: dict[str, object] = _guided_session_snapshot()
    expected = deepcopy(session)

    enter_workflow_demo(session)
    assert session[WORKFLOW_DEMO_OPEN_KEY] is True
    assert session["rm_customer_context"] == "C000001"

    # These represent demo-local selection, action feedback, and Preview only.
    session[WORKFLOW_DEMO_SELECTED_ALERT_KEY] = "ALT-DEMO-001"
    session[WORKFLOW_DEMO_PREVIEW_KEY] = {
        "status": "PREVIEW",
        "sent": False,
        "network": False,
    }
    prepare_workflow_demo_reset(session)
    exit_workflow_demo(session)

    assert session == expected
    assert not any(key.startswith("rm_workflow_demo_") for key in session)


def test_full_demo_lifecycle_preserves_guided_state_and_default_roots(tmp_path: Path) -> None:
    """Demo initialization, action, Preview, reset, and exit remain isolated."""

    paths = _injected_demo_paths(tmp_path)
    protected = (
        settings.BASE_DIR / "artifacts" / "workflow",
        settings.BASE_DIR / "artifacts" / "audit",
    )
    roots_before = {path: _tree_digest(path) for path in protected}
    session: dict[str, object] = _guided_session_snapshot()
    expected = deepcopy(session)

    enter_workflow_demo(session)
    shell = initialize_or_reset_workflow_demo(paths=paths)
    assert shell.is_ready and len(shell.cases) == 3 and shell.selected_case is not None
    service = get_workflow_demo_ui_service(session, paths=paths)
    assert service is not None
    case = shell.selected_case
    response = perform_workflow_demo_operation(
        session,
        service,
        operation="ACKNOWLEDGE",
        alert_id=case.alert_id,
        expected_state="NEW",
        occurred_at=utc_now(),
        actor_reference="synthetic-workflow-demo",
        idempotency_token="guided-demo-lifecycle-acknowledgement",
        paths=paths,
    )
    assert response.current_state == "ACKNOWLEDGED"
    current_case = load_rm_workflow_case(service, alert_id=case.alert_id)
    assert current_case is not None
    preview = build_offline_notification_preview(service, alert_case=current_case)
    assert preview["status"] == "PREVIEW"
    assert preview["sent"] is False
    assert preview["scope"]["network_called"] is False
    session[WORKFLOW_DEMO_PREVIEW_KEY] = {"alert_id": case.alert_id, "result": preview}

    prepare_workflow_demo_reset(session)
    restored = initialize_or_reset_workflow_demo(paths=paths)
    assert restored.is_ready and [item.state for item in restored.cases] == ["NEW", "NEW", "NEW"]
    exit_workflow_demo(session)

    assert session == expected
    assert {path: _tree_digest(path) for path in protected} == roots_before


def test_demo_session_keys_cannot_change_a_normal_guided_state() -> None:
    """Guided validity is derived from the preserved default context only."""

    context = _normal_guided_context()
    before = build_rm_guided_workflow_state(context).to_dict()

    session: dict[str, object] = {}
    enter_workflow_demo(session)
    session[WORKFLOW_DEMO_SELECTED_ALERT_KEY] = "ALT-DEMO-001"
    session[WORKFLOW_DEMO_PREVIEW_KEY] = {"status": "PREVIEW", "sent": False, "network": False}
    exit_workflow_demo(session)

    assert session == {}
    assert build_rm_guided_workflow_state(context).to_dict() == before


def test_normal_guided_state_build_does_not_initialize_or_write_demo_or_default_roots() -> None:
    """Normal Guided RM is read-only with respect to every workflow-demo root."""

    demo_paths = WorkflowDemoPaths.default()
    protected = (
        settings.BASE_DIR / "artifacts" / "workflow",
        settings.BASE_DIR / "artifacts" / "audit",
        demo_paths.runtime_root,
    )
    before = {path: _tree_digest(path) for path in protected}

    state = build_rm_guided_workflow_state(_normal_guided_context())

    assert state.current_step_id == "AUDIT_PREVIEW"
    assert {path: _tree_digest(path) for path in protected} == before


def test_demo_copy_makes_the_practice_boundary_available_in_korean_and_english() -> None:
    assert t("rm.workflow_demo.separation", "ko") == "기본 RM 업무와 분리된 연습용 화면입니다."
    assert t("rm.workflow_demo.cta_caption", "ko") == "최대 3건의 합성 Case · 실제 운영 Alert 아님 · 실제 발송 없음"
    assert t("rm.workflow_demo.breadcrumb", "ko") == "RM Workspace > 합성 Workflow Demo"
    assert t("rm.workflow_demo.separation", "en") == "A practice context separate from default RM work."
    assert t("rm.workflow_demo.breadcrumb", "en") == "RM Workspace > Synthetic Workflow Demo"
