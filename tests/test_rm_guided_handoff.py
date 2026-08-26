"""Contracts for the Portfolio capacity-to-Queue guided handoff."""

from __future__ import annotations

from pathlib import Path

import app as app_module
from streamlit.testing.v1 import AppTest

from src.capacity_scenarios import CapacityScenario, build_capacity_comparison_report
from src.presentation import GENERAL_MODE, PRESENTATION_MODE
from src.rm_guided_workflow import RMGuidedContext, build_rm_guided_workflow_state
from src.rm_workspace import (
    RM_WORKSPACE_MODE,
    build_rm_portfolio_queue_view_model,
    customer_context_from_queue_row,
    load_rm_alert_cases,
    load_rm_workspace_artifacts,
)


def _manifest() -> dict[str, object]:
    artifacts = load_rm_workspace_artifacts()
    assert isinstance(artifacts.selection_manifest, dict)
    return artifacts.selection_manifest


def _portfolio_model() -> dict[str, object]:
    artifacts = load_rm_workspace_artifacts()
    return build_rm_portfolio_queue_view_model(
        selection_manifest=_manifest(),
        representative_cohort=artifacts.representative_cohort,
        alert_cases=load_rm_alert_cases().cases,
        language="en",
    )


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


def test_capacity_acknowledgement_is_bound_to_the_entered_value() -> None:
    at = _english_rm_app()

    at.checkbox(key="rm_capacity_comparison_enabled").set_value(True).run(timeout=45)
    at.number_input(key="rm_capacity_comparison_value").set_value(2).run(timeout=45)
    at.checkbox(key="rm_guided_capacity_acknowledgement_control").set_value(True).run(
        timeout=45
    )

    assert not at.exception
    assert any("Current step: 2." in value for value in _text_values(at))
    assert any("Review Queue is unchanged" in value for value in _text_values(at))

    at.number_input(key="rm_capacity_comparison_value").set_value(3).run(timeout=45)

    assert not at.exception
    assert any("Current step: 1." in value for value in _text_values(at))
    assert at.checkbox(key="rm_guided_capacity_acknowledgement_control").value is False


def test_capacity_reconciliation_keeps_saved_queue_ids_count_and_rank_digest() -> None:
    manifest = _manifest()
    portfolio_model = _portfolio_model()
    report = build_capacity_comparison_report(
        manifest,
        (
            CapacityScenario("source", None, status="demo"),
            CapacityScenario("entered", 7, status="draft"),
        ),
    )

    reconciliation = app_module._build_rm_capacity_queue_reconciliation(
        portfolio_model=portfolio_model,
        selection_manifest=manifest,
        capacity_input=7,
        comparison_selected=report.scenarios[1].selected_count,
        comparison_deferred=report.scenarios[1].deferred_count,
        ranking_digest_before=report.scenarios[0].ranking_digest,
        ranking_digest_after=report.scenarios[1].ranking_digest,
        selected_customer_origin="none",
    )

    assert reconciliation["queue_customer_ids_before"] == reconciliation[
        "queue_customer_ids_after_capacity"
    ]
    assert reconciliation["queue_unfiltered_count_before"] == reconciliation[
        "queue_unfiltered_count_after_capacity"
    ]
    assert reconciliation["ranking_digest_before"] == reconciliation["ranking_digest_after"]
    assert reconciliation["comparison_selected"] == 7
    assert reconciliation["comparison_deferred"] + reconciliation["comparison_selected"] == len(
        reconciliation["queue_customer_ids_before"]
    )
    assert reconciliation["excluded_disposition_counts"]


def test_only_a_valid_visible_queue_row_can_apply_operational_context() -> None:
    portfolio_model = _portfolio_model()
    queue = portfolio_model["queue"]
    assert isinstance(queue, dict)
    rows = queue["rows"]
    assert isinstance(rows, tuple)
    valid_target = customer_context_from_queue_row(
        portfolio_model, str(rows[0]["customer_id"])
    )
    assert valid_target is not None

    session: dict[str, object] = {
        "rm_customer_context": "C000001",
        "rm_guided_customer_id": "C000001",
        "rm_guided_customer_origin": "representative_comparison",
        "rm_guided_evidence_acknowledged_C000001": True,
        "rm_guided_audit_acknowledged_alert-old": True,
        "rm_notification_preview_result:alert-old": {"sent": False},
        "rm_submission:alert-old:NEW:record": {"token": "old"},
        "rm_workflow_feedback": {"alert_id": "alert-old"},
        "rm_guided_capacity_acknowledged": True,
    }

    assert app_module._apply_rm_guided_customer_handoff(
        session,
        target=valid_target,
        origin="operational_queue",
    )
    assert session["rm_customer_context"] == valid_target
    assert session["rm_guided_customer_id"] == valid_target
    assert session["rm_guided_customer_origin"] == "operational_queue"
    assert session["rm_guided_queue_handoff_reconciliation"] == {
        "selected_customer_id": valid_target,
        "selected_customer_origin": "operational_queue",
    }
    assert "rm_workflow_feedback" not in session
    assert not any(
        key.startswith(
            (
                "rm_guided_evidence_acknowledged_",
                "rm_guided_audit_acknowledged_",
                "rm_notification_preview_result:",
                "rm_submission:",
            )
        )
        for key in session
    )
    assert session["rm_guided_capacity_acknowledged"] is True

    before_stale_selection = dict(session)
    stale_target = customer_context_from_queue_row(portfolio_model, "C999999")
    assert stale_target is None
    if stale_target is not None:
        app_module._apply_rm_guided_customer_handoff(
            session,
            target=stale_target,
            origin="operational_queue",
        )
    assert session == before_stale_selection


def test_representative_context_never_completes_queue_selection_or_changes_queue_count() -> None:
    portfolio_model = _portfolio_model()
    queue = portfolio_model["queue"]
    assert isinstance(queue, dict)
    count_before = queue["unfiltered_count"]
    ids_before = queue["unfiltered_customer_ids"]
    session: dict[str, object] = {}

    assert app_module._apply_rm_guided_customer_handoff(
        session,
        target="C000001",
        origin="representative_comparison",
    )
    state = build_rm_guided_workflow_state(
        RMGuidedContext(
            portfolio_queue_view_model=portfolio_model,
            capacity_acknowledged=True,
            capacity_value=2,
            customer_id="C000001",
            customer_origin=str(session["rm_guided_customer_origin"]),
        )
    )

    assert state.steps[1].status == "CURRENT"
    assert state.steps[1].block_reason_key == "rm.guided.block.representative_not_operational"
    assert queue["unfiltered_count"] == count_before
    assert queue["unfiltered_customer_ids"] == ids_before


def test_non_operational_manifest_records_never_gain_visible_queue_context() -> None:
    manifest = _manifest()
    portfolio_model = _portfolio_model()
    queue = portfolio_model["queue"]
    assert isinstance(queue, dict)
    queue_ids = set(queue["unfiltered_customer_ids"])
    records = manifest["records"]
    assert isinstance(records, list)
    excluded_records = [record for record in records if not record["selected_for_review"]]

    assert excluded_records
    assert queue_ids.isdisjoint({record["customer_id"] for record in excluded_records})
    for record in excluded_records[:20]:
        assert customer_context_from_queue_row(portfolio_model, str(record["customer_id"])) is None


def test_empty_queue_remains_honestly_blocked_without_reinclusion() -> None:
    state = build_rm_guided_workflow_state(
        RMGuidedContext(
            portfolio_queue_view_model={
                "available": True,
                "portfolio": {"reconciliation": {"is_exact": True}},
                "queue": {"rows": ()},
            },
            capacity_acknowledged=True,
            capacity_value=0,
        )
    )

    assert state.steps[1].status == "BLOCKED"
    assert state.steps[1].block_reason_key == "rm.guided.block.queue_empty"
    assert state.current_step_id == "QUEUE_SELECTION"


def test_handoff_changes_preserve_non_rm_modes() -> None:
    at = _english_rm_app()
    at.sidebar.selectbox(key="app_mode").set_value(PRESENTATION_MODE).run(timeout=45)
    assert not at.exception
    at.sidebar.selectbox(key="app_mode").set_value(GENERAL_MODE).run(timeout=45)
    assert not at.exception
