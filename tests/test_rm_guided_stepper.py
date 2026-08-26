"""App and static contracts for the compact RM guided-workflow shell."""

from __future__ import annotations

import inspect
from pathlib import Path

import app as app_module
from streamlit.testing.v1 import AppTest

from src.presentation import GENERAL_MODE, PRESENTATION_MODE, get_presentation_tab_labels
from src.rm_guided_workflow import RMGuidedContext, build_rm_guided_workflow_state
from src.rm_workspace import RM_WORKSPACE_MODE, get_rm_workspace_tab_labels


def _english_rm_app() -> AppTest:
    at = AppTest.from_file(Path(app_module.__file__))
    at.run(timeout=45)
    at.selectbox(key="ui_language").set_value("en").run(timeout=45)
    at.sidebar.selectbox(key="app_mode").set_value(RM_WORKSPACE_MODE).run(timeout=45)
    assert not at.exception
    return at


def _text_values(at: AppTest) -> list[str]:
    return [
        str(element.value)
        for collection in (at.markdown, at.caption, at.info, at.warning)
        for element in collection
    ]


def test_app_test_guided_shell_preserves_mode_tab_and_language_contracts() -> None:
    at = _english_rm_app()

    assert [tab.label for tab in at.tabs] == get_rm_workspace_tab_labels("en")
    assert len(at.tabs) == 4
    assert any("Guided RM workflow" in value for value in _text_values(at))
    assert any("Current step: 1." in value for value in _text_values(at))
    assert not any("rm.guided." in value for value in _text_values(at))

    at.checkbox(key="rm_capacity_comparison_enabled").set_value(True).run(timeout=45)
    at.number_input(key="rm_capacity_comparison_value").set_value(2).run(timeout=45)
    at.checkbox(key="rm_guided_capacity_acknowledgement_control").set_value(True).run(timeout=45)

    assert not at.exception
    assert any("Current step: 2." in value for value in _text_values(at))
    assert any("representative comparison is not an operational" in value for value in _text_values(at))

    at.selectbox(key="ui_language").set_value("ko").run(timeout=45)
    at.selectbox(key="ui_language").set_value("en").run(timeout=45)

    assert not at.exception
    assert any("Current step: 2." in value for value in _text_values(at))
    assert not any("rm.guided." in value for value in _text_values(at))

    at.sidebar.selectbox(key="app_mode").set_value(PRESENTATION_MODE).run(timeout=45)
    assert not at.exception
    assert [tab.label for tab in at.tabs] == get_presentation_tab_labels("en")
    assert len(at.tabs) == 5
    assert not any("Guided RM workflow" in value for value in _text_values(at))

    at.sidebar.selectbox(key="app_mode").set_value(GENERAL_MODE).run(timeout=45)
    assert not at.exception
    assert list(at.tabs) == []
    assert not any("Guided RM workflow" in value for value in _text_values(at))


def test_app_test_no_case_block_is_visible_without_case_creation() -> None:
    source = '''\
import app
from src.rm_guided_workflow import RMGuidedContext, build_rm_guided_workflow_state

portfolio = {
    "available": True,
    "portfolio": {"reconciliation": {"is_exact": True}},
    "queue": {"rows": ({"customer_id": "C000001", "routing_disposition": "CREATE_NEW_CASE"},)},
}
review = {
    "available": True,
    "customer_id": "C000001",
    "header": {"context_type": "operational_queue"},
    "workflow_case": {"available": False},
}
state = build_rm_guided_workflow_state(
    RMGuidedContext(
        portfolio_queue_view_model=portfolio,
        customer_review_view_model=review,
        capacity_acknowledged=True,
        capacity_value=2,
        customer_id="C000001",
        customer_origin="operational_queue",
        current_case_metadata={"available": False},
        evidence_acknowledged=True,
    )
)
app._render_rm_guided_workflow_shell(state, language="en")
'''
    at = AppTest.from_string(source)
    at.run(timeout=30)

    assert not at.exception
    assert any("Current step: 4." in str(item.value) for item in at.markdown)
    assert any("No existing Alert/Case" in str(item.value) for item in at.warning)
    assert not any("rm.guided." in value for value in _text_values(at))


def test_guided_renderer_is_display_only_and_keeps_explicit_tab_fallback() -> None:
    source = "\n".join(
        (
            inspect.getsource(app_module.render_rm_workspace_mode),
            inspect.getsource(app_module._build_rm_guided_state),
            inspect.getsource(app_module._render_rm_guided_workflow_shell),
            inspect.getsource(app_module._render_rm_guided_tab_instruction),
        )
    )

    assert "build_rm_guided_workflow_state" in source
    assert "st.tabs(view_model[\"tabs\"])" in source
    assert "key=\"rm_guided" not in inspect.getsource(app_module.render_rm_workspace_mode)
    assert "run_customer_analysis" not in source
    assert "fit_matcher" not in source
    assert "build_capacity_comparison_report" not in source
    assert "FileAlertCaseRepository" not in source
    assert "FileAuditEventStore" not in source
    assert ".create(" not in source
    assert ".update(" not in source
    assert "unsafe_allow_html" not in source
    assert "JavaScript" not in source


def test_guided_shell_accepts_a_read_only_blocked_state_without_mutation() -> None:
    state = build_rm_guided_workflow_state(
        RMGuidedContext(portfolio_queue_view_model={"available": False})
    )

    assert state.current_step_id == "PORTFOLIO_CAPACITY"
    assert state.block_reason_key == "rm.guided.block.artifact_unavailable"
    assert state.scope == {
        "analytics_recomputed": False,
        "triage_recomputed": False,
        "capacity_approved": False,
        "queue_mutated": False,
        "case_created": False,
        "repository_mutated": False,
        "future_data_loaded": False,
    }
