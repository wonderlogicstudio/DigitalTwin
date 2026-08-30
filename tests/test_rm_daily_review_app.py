"""Tests for the Streamlit RM Daily Review mode boundaries."""

from __future__ import annotations

import inspect
import json
import os
from contextlib import nullcontext
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import app as app_module

from src.i18n import t
from src.rm_daily_review_loader import SavedDailyReviewLoadResult
from src.rm_review_store import REVIEW_COMPLETED, REVIEW_FOLLOW_UP, create_review_event


def _snapshot_artifact() -> dict[str, object]:
    return {
        "snapshot_id": "monthly-2026-08",
        "analysis_as_of_month": 12,
        "records": [
            {
                "customer_id": "C000001",
                "snapshot_id": "monthly-2026-08",
                "current_summary": {"current_status": "watch"},
                "breakpoint": {
                    "status": "found",
                    "months_from_current": 1,
                    "primary_factor": "cash_balance_ratio",
                },
                "evidence": {"available": True},
                "relationship_metadata": {
                    "relationship_priority": "CORE",
                    "relationship_label": "핵심관리",
                },
            }
        ],
    }


class _NoSnapshotSt:
    def __init__(self, *, query_clicked: bool = True) -> None:
        self.session_state: dict[str, object] = {}
        self.calls: list[tuple[str, str]] = []
        self.query_clicked = query_clicked

    def title(self, value: str) -> None:
        self.calls.append(("title", value))

    def caption(self, value: str) -> None:
        self.calls.append(("caption", value))

    def info(self, value: str) -> None:
        self.calls.append(("info", value))

    def warning(self, value: str) -> None:
        self.calls.append(("warning", value))

    def code(self, value: str, *, language: str) -> None:
        self.calls.append(("code", value))

    def button(self, value: str, *, key: str) -> bool:
        self.calls.append(("button", value))
        return self.query_clicked

    def spinner(self, value: str):
        self.calls.append(("spinner", value))
        return nullcontext()


class _CompletedRowsSt:
    def __init__(self) -> None:
        self.session_state: dict[str, object] = {}
        self.calls: list[tuple[str, str]] = []

    def columns(self, _widths: list[float]):
        return [nullcontext() for _ in range(4)]

    def markdown(self, value: str) -> None:
        self.calls.append(("markdown", value))

    def caption(self, value: str) -> None:
        self.calls.append(("caption", value))

    def button(self, value: str, *, key: str) -> bool:
        self.calls.append(("button", value))
        return False


def test_snapshot_loader_uses_latest_snapshot_and_ignores_workload_report(tmp_path: Path) -> None:
    older_path = tmp_path / "monthly-2026-07.json"
    newer_path = tmp_path / "monthly-2026-08.json"
    workload_path = tmp_path / "monthly-2026-08_workload_report.json"
    for path in (older_path, newer_path, workload_path):
        path.write_text(json.dumps(_snapshot_artifact()), encoding="utf-8")
    os.utime(older_path, (1_000, 1_000))
    os.utime(newer_path, (2_000, 2_000))
    os.utime(workload_path, (3_000, 3_000))

    result = app_module.load_latest_rm_snapshot_artifact(tmp_path)

    assert result is not None
    path, artifact = result
    assert path == newer_path
    assert artifact["snapshot_id"] == "monthly-2026-08"


def test_rm_worklist_reads_saved_snapshot_and_manual_completion_events(
    tmp_path: Path,
    monkeypatch,
) -> None:
    snapshot_path = tmp_path / "monthly-2026-08.json"
    snapshot_path.write_text(json.dumps(_snapshot_artifact()), encoding="utf-8")
    event = create_review_event(
        review_id="review-0001",
        customer_id="C000001",
        snapshot_id="monthly-2026-08",
        reviewed_at=datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc),
        result=REVIEW_COMPLETED,
    )
    monkeypatch.setattr(app_module, "load_review_events", lambda: (event,))

    worklist = app_module.build_rm_daily_review_worklist(
        _snapshot_artifact(),
        snapshot_path=snapshot_path,
        daily_date=date(2026, 8, 29),
    )

    assert worklist.today_items == ()
    assert [item.customer_id for item in worklist.completed_today] == ["C000001"]
    assert worklist.completed_today[0].timing_months == 1


def test_completion_moves_only_that_customer_for_the_same_snapshot_and_day(
    tmp_path: Path,
    monkeypatch,
) -> None:
    artifact = _snapshot_artifact()
    artifact["records"].append(
        {
            "customer_id": "C000002",
            "snapshot_id": "monthly-2026-08",
            "current_summary": {"current_status": "watch"},
            "breakpoint": {
                "status": "found",
                "months_from_current": 1,
                "primary_factor": "dsr",
            },
            "evidence": {"available": True},
            "relationship_metadata": {
                "relationship_priority": "STANDARD",
                "relationship_label": "일반관리",
            },
        }
    )
    snapshot_path = tmp_path / "monthly-2026-08.json"
    snapshot_path.write_text(json.dumps(artifact), encoding="utf-8")
    event = create_review_event(
        review_id="review-follow-up",
        customer_id="C000001",
        snapshot_id="monthly-2026-08",
        reviewed_at=datetime(2026, 8, 29, 9, 0, tzinfo=timezone.utc),
        result=REVIEW_FOLLOW_UP,
    )
    monkeypatch.setattr(app_module, "load_review_events", lambda: (event,))

    worklist = app_module.build_rm_daily_review_worklist(
        artifact,
        snapshot_path=snapshot_path,
        daily_date=date(2026, 8, 29),
    )

    assert [item.customer_id for item in worklist.today_items] == ["C000002"]
    assert [item.customer_id for item in worklist.completed_today] == ["C000001"]
    assert worklist.completed_today[0].snapshot_id == "monthly-2026-08"


def test_rm_mode_without_snapshot_shows_cli_guidance_only(monkeypatch) -> None:
    fake_st = _NoSnapshotSt()
    monkeypatch.setattr(app_module, "st", fake_st)
    monkeypatch.setattr(
        app_module,
        "load_saved_rm_daily_review",
        lambda **_kwargs: SavedDailyReviewLoadResult(
            status="MISSING_SNAPSHOT",
            message=app_module.t("rm.snapshot.none", "ko"),
            cli_command="python scripts/build_rm_monthly_snapshot.py --snapshot-id YYYY-MM",
        ),
    )

    app_module.render_rm_daily_review_mode(daily_date=date(2026, 8, 29))

    assert ("info", "저장된 월별 Snapshot이 없습니다. 아래 CLI로 먼저 Snapshot을 생성해 주세요.") in fake_st.calls
    assert (
        "code",
        "python scripts/build_rm_monthly_snapshot.py --snapshot-id YYYY-MM",
    ) in fake_st.calls
    assert {"button", "spinner"}.issubset(call_name for call_name, _ in fake_st.calls)
    assert not {"metric", "tabs"}.intersection(call_name for call_name, _ in fake_st.calls)


def test_rm_mode_requires_explicit_query_before_loading_saved_snapshot(monkeypatch) -> None:
    fake_st = _NoSnapshotSt(query_clicked=False)
    monkeypatch.setattr(app_module, "st", fake_st)
    monkeypatch.setattr(
        app_module,
        "load_saved_rm_daily_review",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("snapshot should not load before the explicit query")
        ),
    )

    app_module.render_rm_daily_review_mode(daily_date=date(2026, 8, 29))

    assert ("button", "오늘의 업무 조회") in fake_st.calls
    assert not {"spinner", "info", "warning", "code"}.intersection(
        call_name for call_name, _ in fake_st.calls
    )


def test_main_exits_into_rm_mode_before_loading_live_analytics(monkeypatch) -> None:
    calls: list[str] = []

    class _MainSt:
        session_state = {"app_mode": app_module.RM_DAILY_REVIEW_MODE}

    monkeypatch.setattr(app_module, "st", _MainSt())
    monkeypatch.setattr(app_module, "render_header", lambda: "ko")
    monkeypatch.setattr(
        app_module,
        "render_sidebar",
        lambda *_args, **_kwargs: app_module.SidebarSelection(
            customer_id="",
            selected_metric="",
            app_mode=app_module.RM_DAILY_REVIEW_MODE,
            presentation_mode=False,
            show_raw_samples=False,
            rm_daily_review_mode=True,
        ),
    )
    monkeypatch.setattr(
        app_module,
        "render_rm_daily_review_mode",
        lambda *_args, **_kwargs: calls.append("rm"),
    )
    monkeypatch.setattr(
        app_module,
        "load_monthly_data",
        lambda: (_ for _ in ()).throw(AssertionError("monthly data must not load")),
    )
    monkeypatch.setattr(
        app_module,
        "load_feature_data",
        lambda: (_ for _ in ()).throw(AssertionError("features must not load")),
    )
    monkeypatch.setattr(
        app_module,
        "load_matcher",
        lambda *_args: (_ for _ in ()).throw(AssertionError("matcher must not load")),
    )

    app_module.main()

    assert calls == ["rm"]


def test_rm_renderer_has_no_live_analysis_or_capacity_case_stepper_controls() -> None:
    source = inspect.getsource(app_module.render_rm_daily_review_mode)
    kpi_source = inspect.getsource(app_module._render_rm_daily_kpi_cards)
    panel_source = inspect.getsource(app_module._render_rm_daily_selected_panel)
    help_source = inspect.getsource(app_module._render_rm_daily_help)
    planning_source = inspect.getsource(app_module._render_rm_daily_planning_summary)

    for checked_source in (source, kpi_source, panel_source, help_source, planning_source):
        for forbidden_text in (
            "run_customer_analysis",
            "load_matcher",
            "load_monthly_data",
            "load_feature_data",
            "capacity",
            "queue",
            "case",
            "stepper",
            "model setting",
        ):
            assert forbidden_text not in checked_source.lower()
    assert 't("rm.filter.core_only", language)' in panel_source
    assert 't("rm.monitor.search", language)' in panel_source
    assert "rm.help.title" in planning_source
    assert 't("rm.query.button", language)' in source
    assert 'st.spinner(t("rm.query.loading", language))' in source
    assert "RM_DAILY_REVIEW_QUERY_LANGUAGE_STATE_KEY" in source
    assert "loaded_query_language != language" in source
    assert "st.session_state[query_language_state_key] = language" in source


def test_customer_detail_keeps_timing_and_crm_information_visually_separate() -> None:
    source = inspect.getsource(app_module._render_rm_customer_detail)
    brief_source = inspect.getsource(app_module._render_rm_detail_evidence_at_a_glance)
    section_order = (
        "rm.detail.relationship",
        "rm.detail.conversation",
        "rm.detail.analysis",
        "rm.detail.result",
        "rm.completed.already",
    )

    assert [source.index(section) for section in section_order] == sorted(
        source.index(section) for section in section_order
    )
    assert "rm.detail.why" in brief_source
    assert 't("rm.detail.relationship_separate", language)' in source
    assert "detail.relationship_badge" in source
    assert 't("rm.detail.relationship_badge_notice", language)' in source
    assert "st.expander" in source
    for forbidden_text in (
        "run_customer_analysis",
        "load_matcher",
        "load_monthly_data",
        "load_feature_data",
        "capacity",
        "queue",
        "case",
        "stepper",
        "risk score",
        "probability",
    ):
        assert forbidden_text not in source.lower()


def test_customer_detail_renders_saved_historical_evidence_without_a_new_analysis() -> None:
    detail_source = inspect.getsource(app_module._render_rm_customer_detail)
    glance_source = inspect.getsource(app_module._render_rm_detail_evidence_at_a_glance)
    change_card_source = inspect.getsource(app_module._render_rm_current_change_cards)
    chart_source = inspect.getsource(app_module._render_rm_historical_cohort_chart)
    outcome_source = inspect.getsource(app_module._render_rm_outcome_distribution_chart)
    whatif_source = inspect.getsource(app_module._render_rm_whatif_summary)

    assert "_render_rm_detail_evidence_at_a_glance" in detail_source
    assert detail_source.index("_render_rm_detail_evidence_at_a_glance") < detail_source.index(
        "t('rm.detail.relationship', language)"
    )
    assert "_render_rm_historical_cohort_chart" in glance_source
    assert "_render_rm_current_change_cards" in glance_source
    assert "render_rm_review_brief_html" in glance_source
    assert "detail.conversation_steps[:3]" in glance_source
    assert "st.columns([0.9, 1.1])" in glance_source
    assert "st.columns([1.35, 0.85])" in glance_source
    assert "current_change_card_views[:3]" in change_card_source
    assert "render_info_cards_html" in change_card_source
    assert "change_card.status_label" in change_card_source
    assert "_render_rm_outcome_distribution_chart" in detail_source
    assert "_render_rm_whatif_summary" in detail_source
    assert "_render_framed_plotly_chart" in chart_source
    assert "_render_framed_plotly_chart" in outcome_source
    assert "go.Bar" in outcome_source
    assert "chart.risk_path" in chart_source
    assert "chart.avoidance_path" in chart_source
    assert 'annotation_text=t("term.breakpoint", language)' not in chart_source
    assert "label_metric(chart.metric_key, language)" in chart_source
    assert '"t": 84' in chart_source
    assert "chart.breakpoint_month" in chart_source
    assert "full time series" in whatif_source
    for source in (detail_source, glance_source, change_card_source, chart_source, outcome_source, whatif_source):
        for forbidden_text in ("run_customer_analysis", "load_matcher", "feature_engineering", "pipeline"):
            assert forbidden_text not in source.lower()


def test_rm_historical_chart_keeps_help_text_and_value_labels_outside_plot_area(monkeypatch) -> None:
    class _ChartCaptureSt:
        def __init__(self) -> None:
            self.figure = None

        def plotly_chart(self, figure, **_kwargs) -> None:
            self.figure = figure

        def container(self, *, border: bool):
            assert border is True
            return nullcontext()

        def caption(self, _value: str) -> None:
            pass

    chart_capture = _ChartCaptureSt()
    detail = SimpleNamespace(
        customer_id="C000001",
        supporting_analysis=SimpleNamespace(
            historical_cohort_chart=SimpleNamespace(
                available=True,
                metric_key="dsr",
                risk_path=(
                    SimpleNamespace(month=12, mean=0.36),
                    SimpleNamespace(month=13, mean=0.42),
                ),
                avoidance_path=(
                    SimpleNamespace(month=12, mean=0.31),
                    SimpleNamespace(month=13, mean=0.34),
                ),
                risk_group_size=150,
                avoidance_group_size=50,
                breakpoint_month=13,
            )
        ),
    )
    monkeypatch.setattr(app_module, "st", chart_capture)

    app_module._render_rm_historical_cohort_chart(
        detail,
        language="en",
        show_heading=False,
        chart_height=310,
    )

    figure = chart_capture.figure
    assert figure is not None
    assert all(annotation.text != t("term.breakpoint", "en") for annotation in figure.layout.annotations)
    assert figure.layout.margin.l >= 70
    assert figure.layout.margin.t >= 64
    assert figure.layout.margin.b >= 58
    assert figure.layout.legend.yanchor == "bottom"
    assert figure.layout.legend.y >= 1.08
    assert figure.layout.yaxis.title.text == app_module.label_metric("dsr", "en")


def test_rm_outcome_chart_uses_the_same_safe_frame_margins(monkeypatch) -> None:
    class _ChartCaptureSt:
        def __init__(self) -> None:
            self.figure = None

        def markdown(self, _value: str) -> None:
            pass

        def caption(self, _value: str) -> None:
            pass

        def plotly_chart(self, figure, **_kwargs) -> None:
            self.figure = figure

        def container(self, *, border: bool):
            assert border is True
            return nullcontext()

    chart_capture = _ChartCaptureSt()
    detail = SimpleNamespace(
        customer_id="C000001",
        supporting_analysis=SimpleNamespace(
            outcome_distribution=(
                SimpleNamespace(label="Risk path", count=150, tone="stress"),
                SimpleNamespace(label="Risk-avoidance path", count=50, tone="stable"),
            )
        ),
    )
    monkeypatch.setattr(app_module, "st", chart_capture)

    app_module._render_rm_outcome_distribution_chart(detail, language="en")

    figure = chart_capture.figure
    assert figure is not None
    assert figure.layout.margin.l >= 72
    assert figure.layout.margin.r >= 48
    assert figure.layout.margin.t >= 56
    assert figure.layout.margin.b >= 56
    assert figure.data[0].cliponaxis is False
    assert figure.layout.xaxis.automargin is True
    assert figure.layout.yaxis.automargin is True


def test_all_plotly_charts_use_one_native_frame_without_an_inner_css_border(monkeypatch) -> None:
    class _FrameCaptureSt:
        def __init__(self) -> None:
            self.container_calls = 0
            self.figure = None

        def container(self, *, border: bool):
            assert border is True
            self.container_calls += 1
            return nullcontext()

        def plotly_chart(self, figure, **_kwargs) -> None:
            self.figure = figure

    frame_capture = _FrameCaptureSt()
    monkeypatch.setattr(app_module, "st", frame_capture)

    app_module._render_framed_plotly_chart(object(), chart_key="chart-frame-test")

    assert frame_capture.container_calls == 1
    assert frame_capture.figure is not None
    assert inspect.getsource(app_module).count("st.plotly_chart") == 1


def test_conversation_preparation_reveals_optional_neutral_prompts_without_forcing_answers() -> None:
    detail_source = inspect.getsource(app_module._render_rm_customer_detail)
    conversation_source = inspect.getsource(app_module._render_rm_conversation_steps)

    assert "_render_rm_conversation_steps" in detail_source
    assert detail_source.index("_render_rm_conversation_steps") < detail_source.index(
        "rm.detail.analysis"
    )
    assert "detail.conversation_steps" in conversation_source
    assert "st.expander" in conversation_source
    assert "rm.conversation.question" in conversation_source
    assert "rm.conversation.observations" in conversation_source
    for prohibited_text in (
        "st.radio",
        "st.selectbox",
        "risk score",
        "probability",
        "case",
        "must",
    ):
        assert prohibited_text not in conversation_source.lower()


def test_customer_detail_save_requests_rerun_and_keeps_follow_up_as_an_rm_record() -> None:
    source = inspect.getsource(app_module._render_rm_customer_detail)

    assert source.count("st.selectbox(") == 1
    assert source.count("st.text_area(") == 1
    assert "append_review_event(event)" in source
    assert 'st.session_state.pop("rm_selected_customer_id", None)' in source
    assert "rm_daily_review_completion_message" in source
    assert 'st.session_state["rm_daily_review_refresh_after_review"] = True' in source
    assert "st.rerun()" in source
    assert 't("rm.follow_up.note", language)' in source


def test_rm_renderer_has_a_separate_completed_area() -> None:
    kpi_source = inspect.getsource(app_module._render_rm_daily_kpi_cards)
    panel_source = inspect.getsource(app_module._render_rm_daily_selected_panel)
    completed_rows_source = inspect.getsource(app_module._render_rm_completed_customer_rows)

    assert "RM_DAILY_PANEL_COMPLETED" in kpi_source
    assert 't("rm.completed.title", language' in panel_source
    assert "_render_rm_completed_customer_rows" in panel_source
    assert "row.display_name" in completed_rows_source
    assert 't("rm.completed.row", language)' in completed_rows_source
    assert "row.completion_label" not in completed_rows_source
    assert "RM_DAILY_SELECTED_COMPLETED_CUSTOMER_STATE_KEY" in completed_rows_source


def test_completed_record_view_supports_saved_record_edit_and_confirmed_cancellation() -> None:
    record_source = inspect.getsource(app_module._render_rm_completed_record)
    editor_source = inspect.getsource(app_module._render_rm_review_record_editor)
    finish_source = inspect.getsource(app_module._finish_rm_review_record_change)

    assert "find_latest_review_event" in record_source
    assert "load_review_events" in record_source
    assert "rm.record.title" in record_source
    assert "rm.record.result" in record_source
    assert "rm.record.note" in record_source
    assert "rm.record.cancel_confirm" in record_source
    assert "cancel_customer_review" in record_source
    assert "rm.record.save_error" in record_source
    assert "replace_customer_review" in editor_source
    assert "rm.record.edit_result" in editor_source
    assert "rm.record.edit_note" in editor_source
    assert "rm.record.save_error" in editor_source
    assert "rm_daily_review_refresh_after_review" in finish_source
    for source in (record_source, editor_source, finish_source):
        for forbidden_text in (
            "run_customer_analysis",
            "load_matcher",
            "load_monthly_data",
            "load_feature_data",
            "feature_engineering",
            "pipeline",
            "risk score",
            "probability",
        ):
            assert forbidden_text not in source.lower()


def test_completed_panel_renders_dashboard_rows_without_a_completion_label(monkeypatch) -> None:
    fake_st = _CompletedRowsSt()
    monkeypatch.setattr(app_module, "st", fake_st)

    app_module._render_rm_completed_customer_rows(
        (
            SimpleNamespace(
                customer_id="C000004",
                display_name="Synthetic customer 04",
                relationship_badge="Core",
            ),
        ),
        language="en",
    )

    assert ("markdown", "**Synthetic customer 04**") in fake_st.calls
    assert ("caption", "C000004") in fake_st.calls
    assert ("caption", "Recorded today") in fake_st.calls


def test_rm_first_screen_keeps_today_first_and_help_collapsed() -> None:
    source = inspect.getsource(app_module.render_rm_daily_review_mode)
    kpi_source = inspect.getsource(app_module._render_rm_daily_kpi_cards)
    planning_source = inspect.getsource(app_module._render_rm_daily_planning_summary)
    card_source = inspect.getsource(app_module._build_rm_daily_kpi_cards)
    panel_source = inspect.getsource(app_module._render_rm_daily_selected_panel)
    help_source = inspect.getsource(app_module._render_rm_daily_help)

    assert "_render_rm_daily_panel_selector" not in source
    assert "active_panel = _render_rm_daily_kpi_cards" in source
    assert "_render_rm_daily_selected_panel" in source
    assert "rm.status.title" in source
    assert 't("rm.today_review_criterion", language)' in source
    assert "_render_rm_daily_planning_summary" in source
    assert "gradient" not in source.lower()
    assert "unsafe_allow_html" not in source
    assert "st.columns(4)" in kpi_source
    assert "st.button(" in kpi_source
    assert "RM_DAILY_PANEL_COMPLETED" in kpi_source
    assert "fpt-rm-panel-copy" not in kpi_source
    assert 't("rm.panel.help.description", language)' in help_source
    assert "st.expander" not in help_source
    assert "rm_daily_help_link" in planning_source
    assert "RM_DAILY_HELP_STATE_KEY" in planning_source
    assert "rm.planning.previous_completed" in planning_source
    assert "rm.planning.non_business_day_notice" in planning_source
    assert "RM_DAILY_PANEL_NONE" in kpi_source
    assert 't("rm.panel.close", language)' in kpi_source
    assert "disabled=" not in kpi_source
    assert "if active_panel != RM_DAILY_PANEL_NONE:" in source
    assert '"rm.planning.next_workday.list"' in panel_source
    assert '"rm.planning.this_month.list"' in panel_source
    assert '"rm.planning.next_month.list"' in panel_source
    assert "render_kpi_cards_html" in kpi_source
    assert "grid_columns=4" in kpi_source
    assert "unsafe_allow_html=True" in kpi_source
    assert "st.container" not in kpi_source
    assert "render_info_cards_html" in planning_source
    assert "dashboard.planning" in planning_source
    assert card_source.index('t("rm.metric.today", language)') < card_source.index(
        't("rm.metric.upcoming", language)'
    )
    assert card_source.index('t("rm.metric.upcoming", language)') < card_source.index(
        't("rm.metric.monitor", language)'
    )
    assert card_source.index('t("rm.metric.monitor", language)') < card_source.index(
        't("rm.metric.completed", language)'
    )
    assert "dashboard.today_count" in card_source
    assert "dashboard.upcoming_count" in card_source
    assert "dashboard.monitor_count" in card_source
    assert "dashboard.completed_today_count" in card_source
    assert "rm.summary.completed_on" in card_source
    assert "t(\"rm.people\", language, count=count)" in card_source
    assert '"danger"' not in card_source
    assert '"watch"' in card_source
    assert '"neutral"' in card_source
    assert '"stable"' in card_source
    assert '"rm.date_context"' in source
    assert '"rm.planning.today.detail"' in planning_source
    assert "plan.effective_workday" in planning_source


def test_rm_kpi_labels_distinguish_work_date_from_record_date() -> None:
    dashboard = SimpleNamespace(
        today_count=3,
        upcoming_count=105,
        monitor_count=183,
        completed_today_count=2,
        freshness=SimpleNamespace(daily_date=date(2026, 8, 30)),
    )

    cards = app_module._build_rm_daily_kpi_cards(dashboard, language="en")

    assert cards[0]["title"] == "Outstanding for work date"
    assert "still outstanding for the work date" in cards[0]["description"]
    assert cards[3]["title"] == "Recorded today"
    assert cards[3]["description"] == "Review results recorded on 2026-08-30."


def test_rm_first_screen_renders_the_selected_customer_brief_before_the_open_list() -> None:
    source = inspect.getsource(app_module.render_rm_daily_review_mode)
    row_source = inspect.getsource(app_module._render_rm_customer_rows)
    kpi_source = inspect.getsource(app_module._render_rm_daily_kpi_cards)
    panel_source = inspect.getsource(app_module._render_rm_daily_selected_panel)

    assert 't("rm.dashboard.title", language)' in source
    assert "st.columns(4)" in kpi_source
    assert "RM_DAILY_PANEL_TODAY" in kpi_source
    assert "RM_DAILY_PANEL_UPCOMING" in kpi_source
    assert "RM_DAILY_PANEL_MONITOR" in kpi_source
    assert "RM_DAILY_PANEL_COMPLETED" in kpi_source
    assert panel_source.index("dashboard.today_items") < panel_source.index(
        "dashboard.upcoming_items"
    )
    assert panel_source.index("dashboard.upcoming_items") < panel_source.index(
        "rm.monitor.search"
    )
    assert source.index("_render_rm_customer_detail") < source.index(
        "_render_rm_daily_selected_panel"
    )
    assert "st.session_state.pop(\"rm_selected_customer_id\", None)" in kpi_source
    for row_key in (
        "rm.row.customer",
        "rm.row.relationship",
        "rm.row.reason",
        "rm.row.timing",
        "rm.row.change",
        "rm.row.action",
    ):
        assert row_key in row_source
    assert "current_change_summary" in row_source
    assert "display_name" in row_source
    assert "display_owner_or_team" not in row_source
    assert 'st.session_state["rm_selected_customer_id"] = row.customer_id' in row_source
    assert "st.rerun()" in row_source


def test_rm_today_and_upcoming_rows_are_revealed_in_five_customer_batches(monkeypatch) -> None:
    rows = tuple(f"C{index:06d}" for index in range(12))
    row_source = inspect.getsource(app_module._render_rm_customer_rows)

    class _BatchStateSt:
        session_state = {
            "rm_daily_visible_snapshot_id": "monthly-old",
            "rm_today_visible_count": 10,
            "rm_upcoming_visible_count": 10,
        }

    batch_state_st = _BatchStateSt()
    monkeypatch.setattr(app_module, "st", batch_state_st)

    assert app_module.RM_DAILY_ROW_BATCH_SIZE == 5
    assert app_module._rm_daily_visible_row_count(None, total_rows=len(rows)) == 5
    assert app_module._rm_daily_visible_row_count(10, total_rows=len(rows)) == 10
    assert app_module._rm_daily_visible_row_count(999, total_rows=len(rows)) == len(rows)
    assert app_module._visible_rm_daily_rows(rows, visible_count=5) == rows[:5]
    assert app_module._visible_rm_daily_rows(rows, visible_count=10) == rows[:10]
    app_module._reset_rm_daily_row_batches_for_snapshot("monthly-new")
    assert batch_state_st.session_state == {"rm_daily_visible_snapshot_id": "monthly-new"}
    assert 't("rm.list.show_more", language, count=next_batch_count)' in row_source
    assert 't("rm.list.collapse", language, count=RM_DAILY_ROW_BATCH_SIZE)' in row_source
    assert "RM_DAILY_ROW_BATCH_SIZE" in row_source
