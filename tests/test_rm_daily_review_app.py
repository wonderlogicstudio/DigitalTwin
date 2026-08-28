"""Tests for the Streamlit RM Daily Review mode boundaries."""

from __future__ import annotations

import inspect
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

import app as app_module

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
    def __init__(self) -> None:
        self.session_state: dict[str, object] = {}
        self.calls: list[tuple[str, str]] = []

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
    monkeypatch.setattr(app_module, "load_latest_rm_snapshot_artifact", lambda: None)

    app_module.render_rm_daily_review_mode(daily_date=date(2026, 8, 29))

    assert ("info", "저장된 월별 Snapshot이 없습니다. 아래 CLI로 먼저 Snapshot을 생성해 주세요.") in fake_st.calls
    assert (
        "code",
        "python scripts/build_rm_monthly_snapshot.py --snapshot-id YYYY-MM",
    ) in fake_st.calls
    assert not {"metric", "tabs", "button"}.intersection(call_name for call_name, _ in fake_st.calls)


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
        assert forbidden_text not in source.lower()
    assert 't("rm.filter.core_only", language)' in source
    assert 't("rm.monitor.search", language)' in source
    assert 't("rm.help.title", language)' in source


def test_customer_detail_keeps_timing_and_crm_information_visually_separate() -> None:
    source = inspect.getsource(app_module._render_rm_customer_detail)
    section_order = (
        "rm.detail.why",
        "rm.detail.relationship",
        "rm.detail.conversation",
        "rm.detail.analysis",
        "rm.detail.result",
        "rm.completed.already",
    )

    assert [source.index(section) for section in section_order] == sorted(
        source.index(section) for section in section_order
    )
    assert 't("rm.detail.relationship_separate", language)' in source
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
    ):
        assert forbidden_text not in source.lower()


def test_customer_detail_save_requests_rerun_and_keeps_follow_up_as_an_rm_record() -> None:
    source = inspect.getsource(app_module._render_rm_customer_detail)

    assert source.count("st.selectbox(") == 1
    assert source.count("st.text_area(") == 1
    assert "append_review_event(event)" in source
    assert 'st.session_state.pop("rm_selected_customer_id", None)' in source
    assert "rm_daily_review_completion_message" in source
    assert "st.rerun()" in source
    assert 't("rm.follow_up.note", language)' in source


def test_rm_renderer_has_a_separate_completed_area() -> None:
    source = inspect.getsource(app_module.render_rm_daily_review_mode)

    assert 't("rm.completed.title", language' in source
    assert "build_rm_completed_customer_list_view" in source
    assert "_render_rm_completed_customer_rows" in source


def test_rm_first_screen_keeps_today_first_and_help_collapsed() -> None:
    source = inspect.getsource(app_module.render_rm_daily_review_mode)

    assert source.index('t("rm.metric.today", language)') < source.index(
        't("rm.metric.upcoming", language)'
    )
    assert source.index('t("rm.metric.upcoming", language)') < source.index(
        't("rm.metric.monitor", language)'
    )
    assert 'st.expander(t("rm.help.title", language), expanded=False)' in source
    assert "gradient" not in source.lower()
    assert "unsafe_allow_html" not in source
