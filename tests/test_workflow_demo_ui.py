"""UI-adapter and AppTest contracts for explicit workflow-demo entry/return."""

from __future__ import annotations

import ast
import hashlib
import inspect
import shutil
from pathlib import Path

import app as app_module
from streamlit.testing.v1 import AppTest

from config import settings
from src.presentation import GENERAL_MODE, PRESENTATION_MODE, get_presentation_tab_labels
from src.rm_workspace import RM_WORKSPACE_MODE, get_rm_workspace_tab_labels
from src.workflow_demo import WORKFLOW_DEMO_FIXTURE_FILENAME, WorkflowDemoPaths
from src.workflow_demo_ui import (
    WORKFLOW_DEMO_OPEN_KEY,
    WORKFLOW_DEMO_SELECTED_ALERT_KEY,
    enter_workflow_demo,
    exit_workflow_demo,
    initialize_or_reset_workflow_demo,
    is_workflow_demo_open,
    load_workflow_demo_shell,
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


def _digest(path: Path) -> str | None:
    return None if not path.exists() else hashlib.sha256(path.read_bytes()).hexdigest()


def test_session_entry_return_and_reset_keep_default_rm_context_isolated() -> None:
    session: dict[str, object] = {
        "rm_customer_context": "C000003",
        "rm_queue_scope": "selected",
        "presentation_customer_selector": "demo:1:C002608",
        "customer_selector": "C002608",
    }

    enter_workflow_demo(session)

    assert is_workflow_demo_open(session) is True
    assert session["rm_customer_context"] == "C000003"
    assert session["rm_queue_scope"] == "selected"
    assert session["presentation_customer_selector"] == "demo:1:C002608"
    prepare_workflow_demo_reset(session)
    assert session[WORKFLOW_DEMO_OPEN_KEY] is True
    assert WORKFLOW_DEMO_SELECTED_ALERT_KEY not in session

    exit_workflow_demo(session)

    assert is_workflow_demo_open(session) is False
    assert not [key for key in session if key.startswith("rm_workflow_demo_")]
    assert session["rm_customer_context"] == "C000003"
    assert session["customer_selector"] == "C002608"


def test_demo_shell_is_read_only_until_explicit_initialize_and_reset_isolated(tmp_path: Path) -> None:
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

    unopened = load_workflow_demo_shell(paths=paths)
    assert unopened.status == "DEMO_NOT_INITIALIZED"
    assert not paths.runtime_root.exists()

    initialized = initialize_or_reset_workflow_demo(paths=paths)
    assert initialized.is_ready
    assert len(initialized.cases) == 3
    assert all(case.state == "NEW" for case in initialized.cases)
    assert initialized.selected_case is not None
    assert initialized.snapshot is not None
    assert initialized.snapshot.manifest is not None
    assert initialized.snapshot.manifest.default_workflow_root_used is False
    assert initialized.snapshot.manifest.default_audit_root_used is False

    reset = initialize_or_reset_workflow_demo(paths=paths)
    assert reset.is_ready
    assert [case.to_dict() for case in reset.cases] == [case.to_dict() for case in initialized.cases]
    assert {path: _digest(path) for path in protected} == before


def test_shell_keeps_fixture_runtime_and_stale_selection_errors_in_demo_context(tmp_path: Path) -> None:
    missing_paths = WorkflowDemoPaths(
        fixture_path=tmp_path / "missing" / WORKFLOW_DEMO_FIXTURE_FILENAME,
        runtime_root=tmp_path / "runtime-missing",
    )
    assert load_workflow_demo_shell(paths=missing_paths).status == "DEMO_FIXTURE_UNAVAILABLE"

    paths = _paths(tmp_path)
    ready = initialize_or_reset_workflow_demo(paths=paths)
    stale = load_workflow_demo_shell(paths=paths, selected_alert_id="ALT-DEMO-NOT-PRESENT")
    assert ready.is_ready
    assert stale.status == "DEMO_STALE_SELECTION"
    assert stale.cases == ready.cases

    paths.runtime_manifest_path.write_text("{bad", encoding="utf-8")
    assert load_workflow_demo_shell(paths=paths).status == "DEMO_CORRUPT"


def test_workflow_demo_modules_are_ui_boundary_only_without_network_or_analytics_imports() -> None:
    for module_path in (
        PROJECT_ROOT / "src" / "workflow_demo.py",
        PROJECT_ROOT / "src" / "workflow_demo_ui.py",
    ):
        source = module_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_roots: set[str] = set()
        imported_modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".")[0])
                imported_modules.add(node.module)
        assert {"streamlit", "requests", "httpx", "urllib", "socket", "pandas"}.isdisjoint(imported_roots)
        assert not any(
            forbidden in module
            for module in imported_modules
            for forbidden in ("data_generator", "crossfit", "matcher", "evaluator", "scorer")
        )
        assert "final_outcome" not in source
        assert "persona" not in source


def test_app_test_explicit_entry_and_return_keep_rm_four_tabs_and_default_roots_unchanged(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Exercise an uninitialized demo through a test-owned runtime only.

    A user may have already initialized the optional synthetic demo in the
    default runtime.  That must not turn this AppTest into a state-dependent
    test, nor may the test remove or reset that user-owned runtime.  Patching
    the path factory keeps the application's normal explicit-entry contract
    intact while giving this test a fresh, injected fixture/runtime pair.
    """

    demo_paths = _paths(tmp_path)
    monkeypatch.setattr(
        WorkflowDemoPaths,
        "default",
        classmethod(lambda cls: demo_paths),
    )
    protected = (
        settings.BASE_DIR / "artifacts" / "workflow",
        settings.BASE_DIR / "artifacts" / "audit",
    )
    before = {path: _digest(path) for path in protected}
    at = AppTest.from_file(Path(app_module.__file__))
    at.run(timeout=45)
    at.sidebar.selectbox(key="app_mode").set_value(RM_WORKSPACE_MODE).run(timeout=45)

    assert not at.exception
    assert [tab.label for tab in at.tabs] == get_rm_workspace_tab_labels("ko")
    assert any(caption.value == "기본 RM 업무와 분리된 연습용 화면입니다." for caption in at.caption)
    assert any(
        caption.value == "최대 3건의 합성 Case · 실제 운영 Alert 아님 · 실제 발송 없음"
        for caption in at.caption
    )
    assert [button.key for button in at.button if button.key == "rm_workflow_demo_open_cta"] == [
        "rm_workflow_demo_open_cta"
    ]

    at.button(key="rm_workflow_demo_open_cta").click().run(timeout=45)

    assert not at.exception
    assert list(at.tabs) == []
    assert any(caption.value == "RM Workspace > 합성 Workflow Demo" for caption in at.caption)
    assert any(caption.value == "기본 RM 업무와 분리된 연습용 화면입니다." for caption in at.caption)
    assert not demo_paths.runtime_root.exists()
    assert [button.key for button in at.button if button.key == "rm_workflow_demo_initialize"] == [
        "rm_workflow_demo_initialize"
    ]
    assert {path: _digest(path) for path in protected} == before

    at.button(key="rm_workflow_demo_back").click().run(timeout=45)

    assert not at.exception
    assert [tab.label for tab in at.tabs] == get_rm_workspace_tab_labels("ko")
    assert not demo_paths.runtime_root.exists()
    assert {path: _digest(path) for path in protected} == before


def test_app_test_workflow_demo_entry_keeps_english_copy_and_return_contract() -> None:
    at = AppTest.from_file(Path(app_module.__file__))
    at.run(timeout=45)
    at.selectbox(key="ui_language").set_value("en").run(timeout=45)
    at.sidebar.selectbox(key="app_mode").set_value(RM_WORKSPACE_MODE).run(timeout=45)

    assert at.button(key="rm_workflow_demo_open_cta").label == "Open Synthetic Workflow Demo"
    assert any(caption.value == "A practice context separate from default RM work." for caption in at.caption)
    at.button(key="rm_workflow_demo_open_cta").click().run(timeout=45)

    assert not at.exception
    assert [header.value for header in at.subheader] == ["Synthetic Workflow Demo"]
    assert any(caption.value == "RM Workspace > Synthetic Workflow Demo" for caption in at.caption)
    assert any(caption.value == "A practice context separate from default RM work." for caption in at.caption)
    assert at.button(key="rm_workflow_demo_back").label == "Return to default RM workspace"
    at.button(key="rm_workflow_demo_back").click().run(timeout=45)
    assert [tab.label for tab in at.tabs] == get_rm_workspace_tab_labels("en")


def test_all_three_default_app_modes_keep_default_workflow_and_audit_roots_unchanged() -> None:
    protected = (
        settings.BASE_DIR / "artifacts" / "workflow",
        settings.BASE_DIR / "artifacts" / "audit",
    )
    before = {path: _digest(path) for path in protected}
    at = AppTest.from_file(Path(app_module.__file__))
    at.run(timeout=45)

    assert not at.exception
    at.sidebar.selectbox(key="app_mode").set_value(GENERAL_MODE).run(timeout=45)
    assert not at.exception
    assert list(at.tabs) == []
    at.sidebar.selectbox(key="app_mode").set_value(PRESENTATION_MODE).run(timeout=45)
    assert not at.exception
    assert [tab.label for tab in at.tabs] == get_presentation_tab_labels("ko")
    at.sidebar.selectbox(key="app_mode").set_value(RM_WORKSPACE_MODE).run(timeout=45)
    assert not at.exception
    assert [tab.label for tab in at.tabs] == get_rm_workspace_tab_labels("ko")
    assert {path: _digest(path) for path in protected} == before


def test_demo_renderer_uses_isolated_service_adapter_for_banker_actions() -> None:
    source = inspect.getsource(app_module._render_workflow_demo_context)
    initialize_source = inspect.getsource(app_module._render_workflow_demo_initialize_button)

    assert "initialize_or_reset_workflow_demo" in initialize_source
    assert "FileAlertCaseRepository" not in source + initialize_source
    assert "FileAuditEventStore" not in source + initialize_source
    assert "get_workflow_demo_ui_service" in source
    assert "_render_workflow_demo_action_controls" in source
    assert "_render_workflow_demo_activity_audit" in source
