"""Tests for the Streamlit RM Daily Review mode boundaries."""

from __future__ import annotations

import inspect
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

import app as app_module

from src.rm_review_store import REVIEW_COMPLETED, create_review_event


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
    monkeypatch.setattr(app_module, "render_rm_daily_review_mode", lambda: calls.append("rm"))
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
    assert "핵심관리만 보기" in source
    assert "모니터링 고객 ID 검색" in source
