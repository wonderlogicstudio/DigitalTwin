"""Tests for the explicit, read-only RM Daily Review query loader."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import src.breakpoint_analyzer as breakpoint_analyzer
import src.customer_analysis as customer_analysis
import src.demo_selector as demo_selector
import src.feature_engineering as feature_engineering
import src.monthly_review_snapshot as monthly_review_snapshot
import src.pipeline as pipeline
import src.whatif_simulator as whatif_simulator
from src.matcher import TrajectoryMatcher
from src.rm_daily_review_loader import (
    ControlledLoadingAdapter,
    load_saved_rm_daily_review,
)
from src.rm_review_store import (
    REVIEW_COMPLETED,
    REVIEW_FOLLOW_UP,
    REVIEW_MONITOR,
    append_review_event,
    cancel_customer_review,
    create_review_event,
    load_review_events,
)


def _record(
    customer_id: str,
    *,
    relationship_priority: str,
    relationship_label: str,
    months_from_current: int | None,
    current_status: str,
    breakpoint_status: str = "found",
) -> dict[str, object]:
    return {
        "customer_id": customer_id,
        "snapshot_id": "monthly-2026-08",
        "current_summary": {"current_status": current_status},
        "matched_count": 200,
        "breakpoint": {
            "status": breakpoint_status,
            "breakpoint_month": 13 if breakpoint_status == "found" else None,
            "months_from_current": months_from_current,
            "primary_factor": "cash_balance_ratio",
        },
        "evidence": {"available": True, "status": "available", "errors": {}},
        "relationship_metadata": {
            "source": "synthetic_crm_overlay",
            "rm_portfolio_id": "RM-POC-001",
            "relationship_priority": relationship_priority,
            "relationship_label": relationship_label,
        },
        "outcome_summary": {"matched_count": 200, "outcomes": {}},
        "supporting_evidence": {
            "available": breakpoint_status == "found",
            "evidence_status": "available"
            if breakpoint_status == "found"
            else "insufficient_group_size",
            "why_now": {"months_from_current": months_from_current},
        },
    }


def _snapshot() -> dict[str, object]:
    return {
        "snapshot_id": "monthly-2026-08",
        "analysis_as_of_month": 12,
        "records": [
            _record(
                "C000001",
                relationship_priority="STANDARD",
                relationship_label="일반관리",
                months_from_current=1,
                current_status="watch",
            ),
            _record(
                "C000002",
                relationship_priority="CORE",
                relationship_label="핵심관리",
                months_from_current=3,
                current_status="healthy",
            ),
            _record(
                "C000003",
                relationship_priority="PRIORITY",
                relationship_label="우선관리",
                months_from_current=None,
                current_status="healthy",
                breakpoint_status="insufficient_group_size",
            ),
        ],
    }


def _write_snapshot(snapshot_directory: Path) -> Path:
    snapshot_directory.mkdir(parents=True)
    snapshot_path = snapshot_directory / "monthly-2026-08.json"
    snapshot_path.write_text(json.dumps(_snapshot()), encoding="utf-8")
    os.utime(snapshot_path, (datetime(2026, 8, 20).timestamp(),) * 2)
    return snapshot_path


def _adapter(sleeps: list[float]) -> ControlledLoadingAdapter:
    return ControlledLoadingAdapter(
        sleep=sleeps.append,
        monotonic=lambda: 0.0,
    )


def test_explicit_query_builds_deterministic_view_from_saved_artifacts_only(tmp_path: Path) -> None:
    snapshot_directory = tmp_path / "monthly"
    _write_snapshot(snapshot_directory)
    overlay_path = tmp_path / "presentation.json"
    overlay_path.write_text(
        json.dumps(
            {
                "customers": [
                    {
                        "customer_id": "C000001",
                        "display_name": "합성 고객 가-01",
                        "display_name_en": "Synthetic customer Avery-01",
                        "display_owner_or_team": "RM 업무팀 1",
                        "display_owner_or_team_en": "RM Review Team 1",
                        "presentation_label": "PoC 합성 표시",
                        "presentation_label_en": "Synthetic customer display information for this PoC",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    first_sleeps: list[float] = []
    second_sleeps: list[float] = []

    first = load_saved_rm_daily_review(
        daily_date=date(2026, 8, 29),
        snapshot_directory=snapshot_directory,
        presentation_overlay_path=overlay_path,
        review_events_loader=lambda: (),
        loading_adapter=_adapter(first_sleeps),
    )
    second = load_saved_rm_daily_review(
        daily_date=date(2026, 8, 29),
        snapshot_directory=snapshot_directory,
        presentation_overlay_path=overlay_path,
        review_events_loader=lambda: (),
        loading_adapter=_adapter(second_sleeps),
    )

    assert first.status == second.status == "READY"
    assert first.dashboard == second.dashboard
    assert first.worklist == second.worklist
    assert first_sleeps == second_sleeps == [1.5]
    assert first.dashboard is not None
    assert first.dashboard.snapshot_id == "monthly-2026-08"
    assert first.dashboard.analysis_as_of_month == 12
    assert first.dashboard.freshness.status == "CURRENT_MONTH"
    assert [item.customer_id for item in first.dashboard.today_items] == ["C000001"]
    assert [item.customer_id for item in first.dashboard.upcoming_items] == ["C000002"]
    assert first.dashboard.monitor_summary.item_count == 1
    assert first.dashboard.today_items[0].display_name == "합성 고객 가-01"
    assert first.dashboard.today_items[0].supporting_evidence_available is True

    english = load_saved_rm_daily_review(
        daily_date=date(2026, 8, 29),
        snapshot_directory=snapshot_directory,
        presentation_overlay_path=overlay_path,
        review_events_loader=lambda: (),
        loading_adapter=_adapter([]),
        language="en",
    )

    assert english.dashboard is not None
    assert english.dashboard.today_items[0].display_name == "Synthetic customer Avery-01"
    assert english.dashboard.today_items[0].display_owner_or_team == "RM Review Team 1"


def test_loader_does_not_call_financial_analytics_or_snapshot_builder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot_directory = tmp_path / "monthly"
    _write_snapshot(snapshot_directory)

    def blocked(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("Daily query must not invoke analytics.")

    monkeypatch.setattr(feature_engineering, "build_trajectory_features", blocked)
    monkeypatch.setattr(TrajectoryMatcher, "fit", blocked)
    monkeypatch.setattr(TrajectoryMatcher, "match", blocked)
    monkeypatch.setattr(demo_selector, "build_final_outcome_lookup", blocked)
    monkeypatch.setattr(demo_selector, "summarize_matched_outcomes", blocked)
    monkeypatch.setattr(breakpoint_analyzer, "find_breakpoint", blocked)
    monkeypatch.setattr(whatif_simulator, "build_whatif_results", blocked)
    monkeypatch.setattr(pipeline, "run_pipeline", blocked)
    monkeypatch.setattr(customer_analysis, "run_customer_analysis", blocked)
    monkeypatch.setattr(monthly_review_snapshot, "build_monthly_review_snapshot", blocked)

    result = load_saved_rm_daily_review(
        daily_date=date(2026, 8, 29),
        snapshot_directory=snapshot_directory,
        review_events_loader=lambda: (),
        loading_adapter=_adapter([]),
    )

    assert result.status == "READY"


def test_missing_or_stale_snapshot_returns_only_guidance_and_never_builds(tmp_path: Path) -> None:
    sleeps: list[float] = []
    missing = load_saved_rm_daily_review(
        daily_date=date(2026, 8, 29),
        snapshot_directory=tmp_path / "missing",
        loading_adapter=_adapter(sleeps),
    )

    assert missing.status == "MISSING_SNAPSHOT"
    assert "build_rm_monthly_snapshot.py" in missing.cli_command
    assert sleeps == [1.5]

    snapshot_directory = tmp_path / "monthly"
    _write_snapshot(snapshot_directory)
    stale = load_saved_rm_daily_review(
        daily_date=date(2026, 9, 15),
        snapshot_directory=snapshot_directory,
        review_events_loader=lambda: (),
        loading_adapter=_adapter([]),
    )

    assert stale.status == "READY"
    assert stale.dashboard is not None
    assert stale.dashboard.freshness.status == "PRIOR_MONTH"


def test_date_changes_do_not_change_saved_timing_buckets() -> None:
    # The view receives the same saved artifact; only freshness may differ.
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as raw_directory:
        snapshot_directory = Path(raw_directory) / "monthly"
        _write_snapshot(snapshot_directory)
        august = load_saved_rm_daily_review(
            daily_date=date(2026, 8, 29),
            snapshot_directory=snapshot_directory,
            review_events_loader=lambda: (),
            loading_adapter=_adapter([]),
        )
        september = load_saved_rm_daily_review(
            daily_date=date(2026, 9, 1),
            snapshot_directory=snapshot_directory,
            review_events_loader=lambda: (),
            loading_adapter=_adapter([]),
        )

    assert august.dashboard is not None
    assert september.dashboard is not None
    assert [(row.customer_id, row.timing_months) for row in august.dashboard.today_items] == [
        (row.customer_id, row.timing_months) for row in september.dashboard.today_items
    ]
    assert [(row.customer_id, row.review_state_label) for row in august.dashboard.upcoming_items] == [
        (row.customer_id, row.review_state_label) for row in september.dashboard.upcoming_items
    ]


def test_completion_moves_only_the_matching_customer_for_same_day_and_snapshot(
    tmp_path: Path,
) -> None:
    snapshot_directory = tmp_path / "monthly"
    _write_snapshot(snapshot_directory)
    event = create_review_event(
        review_id="review-0001",
        customer_id="C000001",
        snapshot_id="monthly-2026-08",
        reviewed_at=datetime(2026, 8, 29, 9, tzinfo=timezone.utc),
        result=REVIEW_COMPLETED,
    )

    result = load_saved_rm_daily_review(
        daily_date=date(2026, 8, 29),
        snapshot_directory=snapshot_directory,
        review_events_loader=lambda: (event,),
        loading_adapter=_adapter([]),
    )

    assert result.status == "READY"
    assert result.dashboard is not None
    assert result.worklist is not None
    assert result.dashboard.today_count == 0
    assert result.dashboard.upcoming_count == 1
    assert result.dashboard.completed_today_count == 1
    assert [item.customer_id for item in result.worklist.completed_today] == ["C000001"]

    rerun = load_saved_rm_daily_review(
        daily_date=date(2026, 8, 29),
        snapshot_directory=snapshot_directory,
        review_events_loader=lambda: (event,),
        loading_adapter=_adapter([]),
    )
    assert rerun.dashboard is not None
    assert rerun.dashboard.completed_today_count == 1
    assert rerun.dashboard.today_count == 0


def test_cancelled_review_returns_only_that_customer_to_saved_worklist(
    tmp_path: Path,
) -> None:
    snapshot_directory = tmp_path / "monthly"
    _write_snapshot(snapshot_directory)
    review_path = tmp_path / "reviews" / "review_events.jsonl"
    completed = create_review_event(
        review_id="review-to-cancel",
        customer_id="C000001",
        snapshot_id="monthly-2026-08",
        reviewed_at=datetime(2026, 8, 29, 9, tzinfo=timezone.utc),
        result=REVIEW_COMPLETED,
    )
    assert append_review_event(completed, review_path) == review_path

    before_cancellation = load_saved_rm_daily_review(
        daily_date=date(2026, 8, 29),
        snapshot_directory=snapshot_directory,
        review_events_loader=lambda: load_review_events(review_path),
        loading_adapter=_adapter([]),
    )
    assert before_cancellation.dashboard is not None
    assert before_cancellation.dashboard.today_count == 0
    assert before_cancellation.dashboard.completed_today_count == 1

    assert cancel_customer_review(
        customer_id="C000001",
        snapshot_id="monthly-2026-08",
        output_path=review_path,
    ) == 1
    after_cancellation = load_saved_rm_daily_review(
        daily_date=date(2026, 8, 29),
        snapshot_directory=snapshot_directory,
        review_events_loader=lambda: load_review_events(review_path),
        loading_adapter=_adapter([]),
    )

    assert after_cancellation.dashboard is not None
    assert [item.customer_id for item in after_cancellation.dashboard.today_items] == ["C000001"]
    assert after_cancellation.dashboard.completed_today_count == 0


def test_completed_review_stays_out_of_later_same_snapshot_work_plans(
    tmp_path: Path,
) -> None:
    snapshot_directory = tmp_path / "monthly"
    _write_snapshot(snapshot_directory)
    event = create_review_event(
        review_id="review-previous-day",
        customer_id="C000001",
        snapshot_id="monthly-2026-08",
        reviewed_at=datetime(2026, 8, 28, 9, tzinfo=timezone.utc),
        result=REVIEW_COMPLETED,
    )

    result = load_saved_rm_daily_review(
        daily_date=date(2026, 8, 31),
        snapshot_directory=snapshot_directory,
        review_events_loader=lambda: (event,),
        loading_adapter=_adapter([]),
    )

    assert result.status == "READY"
    assert result.dashboard is not None
    assert result.worklist is not None
    assert result.dashboard.today_count == 0
    assert result.dashboard.completed_today_count == 0
    assert result.worklist.work_plan.today_items == ()
    assert result.worklist.work_plan.previous_workday == date(2026, 8, 28)
    assert result.worklist.work_plan.previous_workday_completed_count == 1


def test_completion_for_another_snapshot_does_not_change_this_snapshot_worklist(
    tmp_path: Path,
) -> None:
    snapshot_directory = tmp_path / "monthly"
    _write_snapshot(snapshot_directory)
    other_snapshot_event = create_review_event(
        review_id="review-other-snapshot",
        customer_id="C000001",
        snapshot_id="monthly-2026-07",
        reviewed_at=datetime(2026, 8, 29, 9, tzinfo=timezone.utc),
        result=REVIEW_COMPLETED,
    )

    result = load_saved_rm_daily_review(
        daily_date=date(2026, 8, 29),
        snapshot_directory=snapshot_directory,
        review_events_loader=lambda: (other_snapshot_event,),
        loading_adapter=_adapter([]),
    )

    assert result.dashboard is not None
    assert result.dashboard.today_count == 1
    assert result.dashboard.completed_today_count == 0


@pytest.mark.parametrize("result_name", [REVIEW_COMPLETED, REVIEW_FOLLOW_UP, REVIEW_MONITOR])
def test_each_manual_review_result_completes_only_its_snapshot_customer(
    tmp_path: Path,
    result_name: str,
) -> None:
    snapshot_directory = tmp_path / "monthly"
    _write_snapshot(snapshot_directory)
    event = create_review_event(
        review_id=f"review-{result_name.lower()}",
        customer_id="C000001",
        snapshot_id="monthly-2026-08",
        reviewed_at=datetime(2026, 8, 29, 9, tzinfo=timezone.utc),
        result=result_name,
        note="optional review note",
    )

    loaded = load_saved_rm_daily_review(
        daily_date=date(2026, 8, 29),
        snapshot_directory=snapshot_directory,
        review_events_loader=lambda: (event,),
        loading_adapter=_adapter([]),
    )

    assert loaded.dashboard is not None
    assert loaded.dashboard.today_count == 0
    assert loaded.dashboard.completed_today_count == 1
