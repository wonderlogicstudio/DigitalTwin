"""Tests for the Streamlit-neutral RM Daily Review View Models."""

from __future__ import annotations

import ast
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

import src.rm_daily_review_view as daily_review_view
from src.daily_review import MONITOR, REVIEW_NOW, UPCOMING
from src.daily_worklist import (
    DailyWorklist,
    DailyWorklistItem,
    MonitorSummary,
    SnapshotFreshness,
    build_daily_review_plan,
)
from src.rm_daily_review_view import (
    RESULT_LABELS,
    build_rm_customer_detail_view,
    build_rm_completed_customer_list_view,
    build_rm_daily_review_view,
)
from src.rm_presentation_overlay import build_rm_presentation_overlay
from src.rm_review_store import REVIEW_COMPLETED, REVIEW_FOLLOW_UP, REVIEW_MONITOR


def _item(
    customer_id: str,
    state: str,
    relationship_priority: str,
    *,
    primary_factor: str | None,
    completed_today: bool = False,
) -> DailyWorklistItem:
    return DailyWorklistItem(
        customer_id=customer_id,
        snapshot_id="monthly-2026-08",
        review_state=state,  # type: ignore[arg-type]
        timing_months=1 if state != MONITOR else None,
        reason_code=(
            "NEAR_TIMING_WITH_CURRENT_OBSERVATION"
            if state == REVIEW_NOW
            else "NEAR_TIMING_CURRENTLY_HEALTHY"
            if state == UPCOMING
            else "INSUFFICIENT_GROUP_SIZE"
        ),
        primary_factor=primary_factor,
        current_status="watch" if state == REVIEW_NOW else "healthy",
        relationship_priority=relationship_priority,
        relationship_label=relationship_priority,
        completed_today=completed_today,
        current_summary={
            "current_status": "watch" if state == REVIEW_NOW else "healthy",
            "recent_savings_rate": 0.12,
            "recent_dsr": 0.34,
        },
        matched_count=200,
        outcome_summary={
            "outcomes": {
                "healthy": {"count": 100},
                "stress": {"count": 50},
            }
        },
        breakpoint_month=13 if state != MONITOR else None,
        breakpoint_status="found" if state != MONITOR else "insufficient_group_size",
        supporting_evidence={
            "available": state != MONITOR,
            "evidence_status": "available" if state != MONITOR else "insufficient_group_size",
            "current_change_cards": [
                {
                    "key": "cash_availability",
                    "value": 2,
                    "value_type": "consecutive_months",
                },
                {
                    "key": "debt_service_burden",
                    "value": 0.23,
                    "value_type": "ratio",
                },
            ],
            "cohort_path_chart": {
                "available": state != MONITOR,
                "metric": "cash_balance_ratio",
                "risk_path": [
                    {"month": 1, "mean": 0.62},
                    {"month": 13, "mean": 0.38},
                ],
                "avoidance_path": [
                    {"month": 1, "mean": 0.61},
                    {"month": 13, "mean": 0.70},
                ],
                "group_sizes": {"risk_path": 50, "avoidance_path": 150},
                "breakpoint_marker": {"month": 13},
            },
            "whatif_summary": {
                "available": state != MONITOR,
                "scenarios": [
                    {"scenario_name": "baseline"},
                    {"scenario_name": "variable_expense_cut_15"},
                ],
            },
        },
    )


def _worklist() -> DailyWorklist:
    today_items = (
        _item("C000001", REVIEW_NOW, "CORE", primary_factor="cash_balance_ratio"),
    )
    upcoming_items = (
        _item("C000002", UPCOMING, "PRIORITY", primary_factor="dsr"),
    )
    return DailyWorklist(
        snapshot_id="monthly-2026-08",
        daily_date=date(2026, 8, 29),
        today_items=today_items,
        upcoming_items=upcoming_items,
        monitor_items=(_item("C000003", MONITOR, "STANDARD", primary_factor=None),),
        monitor_summary=MonitorSummary(item_count=1, reason_counts={"INSUFFICIENT_GROUP_SIZE": 1}),
        completed_today=(
            _item(
                "C000004",
                REVIEW_NOW,
                "CORE",
                primary_factor="savings_rate",
                completed_today=True,
            ),
        ),
        snapshot_freshness=SnapshotFreshness(
            snapshot_id="monthly-2026-08",
            analysis_as_of_month=12,
            daily_date=date(2026, 8, 29),
            snapshot_published_on=date(2026, 8, 1),
            age_days=28,
            status="CURRENT_MONTH",
        ),
        relationship_priority_breakdown={},
        work_plan=build_daily_review_plan(
            today_items=today_items,
            upcoming_items=upcoming_items,
            daily_date=date(2026, 8, 29),
        ),
    )


def test_dashboard_exposes_actual_worklist_counts_and_easy_customer_list() -> None:
    view = build_rm_daily_review_view(
        _worklist(),
        presentation_metadata_by_customer={
            "C000001": {
                "display_name": "합성 고객 가-01",
                "display_owner_or_team": "RM 업무팀 1",
                "presentation_label": "PoC 합성 표시",
            }
        },
    )

    assert view.analysis_as_of_label == "월별 분석 기준: 관측 12개월차"
    assert view.snapshot_freshness_label == "이번 달 Snapshot"
    assert (view.today_count, view.upcoming_count, view.monitor_count, view.completed_today_count) == (1, 1, 1, 1)
    assert [row.customer_id for row in view.customer_list] == ["C000001", "C000002", "C000003"]
    assert view.customer_list[0].review_state_label == "업무 기준일 미완료"
    assert view.customer_list[0].relationship_badge == "핵심관리"
    assert view.customer_list[0].why_today == "오늘 확인 이유: 분기 시점 1개월 이내 · 주요 변화: 현금 여력"
    assert "cash_balance_ratio" not in view.customer_list[0].primary_change
    assert view.analysis_as_of_month == 12
    assert view.freshness.status == "CURRENT_MONTH"
    assert [row.customer_id for row in view.today_items] == ["C000001"]
    assert [row.customer_id for row in view.upcoming_items] == ["C000002"]
    assert [row.customer_id for row in view.completed_items] == ["C000004"]
    assert view.monitor_summary.item_count == 1
    assert view.freshness.daily_date == date(2026, 8, 29)
    assert view.planning.effective_workday == date(2026, 8, 31)
    assert view.planning.next_workday == date(2026, 9, 1)
    assert view.planning.previous_workday == date(2026, 8, 28)
    assert view.planning.previous_workday_completed_count == 0
    assert [row.customer_id for row in view.planning.today_items] == ["C000001"]
    assert [row.customer_id for row in view.planning.next_month_items] == ["C000002"]
    assert view.customer_list[0].display_name == "합성 고객 가-01"
    assert view.customer_list[0].display_owner_or_team == "RM 업무팀 1"
    assert view.customer_list[0].timing_months == 1
    assert view.customer_list[0].supporting_evidence_available is True
    assert view.customer_list[0].current_change_summary == (
        "주요 변화: 현금 여력",
        "대출 상환 부담 23.0%",
    )


def test_missing_presentation_metadata_uses_customer_id_without_changing_timing() -> None:
    view = build_rm_daily_review_view(_worklist())

    assert view.customer_list[0].display_name == "C000001"
    assert view.customer_list[0].timing_months == 1
    assert view.customer_list[0].review_state_label == "업무 기준일 미완료"


def test_dashboard_receives_the_rebuilt_synthetic_display_name() -> None:
    overlay = build_rm_presentation_overlay(
        [f"C{index:06d}" for index in range(1, 301)]
    )
    presentation_metadata = {
        customer.customer_id: customer.as_dict()
        for customer in overlay.customers
    }

    view = build_rm_daily_review_view(
        _worklist(),
        presentation_metadata_by_customer=presentation_metadata,
    )

    assert view.today_items[0].display_name.startswith("합성 고객 ")
    assert "??" not in view.today_items[0].display_name
    assert view.today_items[0].presentation_label == "PoC용 합성 고객 표시 정보"


def test_english_dashboard_uses_english_synthetic_name_not_korean_legacy_name() -> None:
    overlay = build_rm_presentation_overlay(
        [f"C{index:06d}" for index in range(1, 301)]
    )
    presentation_metadata = {
        customer.customer_id: customer.as_dict()
        for customer in overlay.customers
    }

    view = build_rm_daily_review_view(
        _worklist(),
        presentation_metadata_by_customer=presentation_metadata,
        language="en",
    )
    legacy_only_view = build_rm_daily_review_view(
        _worklist(),
        presentation_metadata_by_customer={
            "C000001": {"display_name": "합성 고객 가람-01"}
        },
        language="en",
    )

    assert view.today_items[0].display_name.startswith("Synthetic customer ")
    assert view.today_items[0].display_name.isascii()
    assert view.today_items[0].presentation_label == (
        "Synthetic customer display information for this PoC"
    )
    assert legacy_only_view.today_items[0].display_name == "Synthetic customer C000001"


def test_core_filter_changes_only_visible_rows_not_timing_bucket_counts() -> None:
    unfiltered = build_rm_daily_review_view(_worklist())
    core_only = build_rm_daily_review_view(_worklist(), relationship_priority_filter="core")

    assert core_only.relationship_priority_filter == "CORE"
    assert [row.customer_id for row in core_only.customer_list] == ["C000001"]
    assert (core_only.today_count, core_only.upcoming_count, core_only.monitor_count) == (
        unfiltered.today_count,
        unfiltered.upcoming_count,
        unfiltered.monitor_count,
    )
    with pytest.raises(ValueError, match="CORE, PRIORITY, or STANDARD"):
        build_rm_daily_review_view(_worklist(), relationship_priority_filter="VIP")


def test_customer_detail_composes_explanation_conversation_evidence_and_result_options() -> None:
    detail = build_rm_customer_detail_view(_worklist(), "C000001")

    assert detail.why_today == "오늘 확인 이유: 분기 시점 1개월 이내 · 주요 변화: 현금 여력"
    assert detail.relationship_badge == "핵심관리"
    assert detail.relationship_context == "고객관계: 핵심관리 고객 · 합성 CRM 메타데이터"
    assert len(detail.conversation_preparation) == 3
    assert [step.number for step in detail.conversation_steps] == [1, 2, 3]
    assert detail.conversation_steps[0].saved_observations == ("주요 변화: 현금 여력",)
    assert detail.conversation_steps[1].saved_observations == (
        "주요 변화: 현금 여력",
        "대출 상환 부담 23.0%",
    )
    assert detail.conversation_steps[2].saved_observations == ()
    assert "한 항목만으로 고객 상황을 판단하지 않습니다" in detail.conversation_steps[1].context
    assert "고객의 답을 시스템이 대신 정하지 않습니다" in detail.conversation_steps[2].context
    assert detail.supporting_analysis_evidence[1] == "주요 변화: 현금 여력"
    assert "cash_balance_ratio" not in " ".join(detail.supporting_analysis_evidence)
    assert [
        (card.label, card.value, card.tone, card.status_label)
        for card in detail.supporting_analysis.current_change_card_views
    ] == [
        ("현금 여력", "최근 2개월 연속 감소", "danger", "부담 확인"),
        ("대출 상환 부담", "23.0%", "stable", "안정 범위"),
    ]
    assert detail.supporting_analysis.current_summary == (
        "현재 요약: 현재 상태는 확인이 필요한 흐름입니다.",
        "최근 저축 여력: 12.0% (저장된 월별 요약)",
        "최근 대출 상환 부담: 34.0% (저장된 월별 요약)",
    )
    assert detail.supporting_analysis.matched_outcome_summary == (
        "참고한 유사 고객: 200명",
        "유사 고객의 과거 결과: 안정 경로 100명 · 부담 경로 50명",
    )
    assert "13개월차" in detail.supporting_analysis.breakpoint_summary
    assert "다시 계산하지 않습니다" in detail.supporting_analysis.additional_analysis_notice
    assert detail.result_recording.customer_id == "C000001"
    assert detail.result_recording.snapshot_id == "monthly-2026-08"
    assert [(option.result, option.label) for option in detail.result_recording.result_options] == [
        (REVIEW_COMPLETED, RESULT_LABELS[REVIEW_COMPLETED]),
        (REVIEW_FOLLOW_UP, RESULT_LABELS[REVIEW_FOLLOW_UP]),
        (REVIEW_MONITOR, RESULT_LABELS[REVIEW_MONITOR]),
    ]


def test_customer_detail_hides_a_saved_zero_change_card_but_keeps_the_next_actionable_observation() -> None:
    baseline = _worklist()
    neutral_cash_item = replace(
        baseline.today_items[0],
        primary_factor="variable_expense_ratio",
        supporting_evidence={
            **dict(baseline.today_items[0].supporting_evidence or {}),
            "current_change_cards": [
                {
                    "key": "cash_availability",
                    "value": 0,
                    "value_type": "consecutive_months",
                },
                {
                    "key": "debt_service_burden",
                    "value": 0.23,
                    "value_type": "ratio",
                },
            ],
        },
    )
    detail = build_rm_customer_detail_view(
        replace(baseline, today_items=(neutral_cash_item,)),
        "C000001",
        language="en",
    )

    rendered_observations = " ".join(
        (*detail.supporting_analysis.current_change_cards, *detail.conversation_steps[1].saved_observations)
    ).lower()
    assert "no recent consecutive decline" not in rendered_observations
    assert "debt-payment burden 23.0%" in rendered_observations


def test_customer_detail_uses_saved_presentation_and_historical_evidence_only() -> None:
    detail = build_rm_customer_detail_view(
        _worklist(),
        "C000001",
        presentation_metadata_by_customer={
            "C000001": {
                "display_name": "Synthetic customer 01",
                "display_owner_or_team": "RM team A",
                "presentation_label": "Synthetic customer display information for this PoC",
            }
        },
        language="en",
    )

    assert detail.display_name == "Synthetic customer 01"
    assert detail.display_owner_or_team == "RM team A"
    assert detail.presentation_label == "Synthetic customer display information for this PoC"
    assert detail.timing_months == 1
    assert detail.primary_change == "Primary change: cash capacity"
    assert [
        (card.label, card.value, card.tone, card.status_label)
        for card in detail.supporting_analysis.current_change_card_views
    ] == [
        ("cash capacity", "declining for 2 consecutive months", "danger", "Burden to confirm"),
        ("debt-payment burden", "23.0%", "stable", "Within the documented range"),
    ]
    assert detail.supporting_analysis.evidence_available is True
    chart = detail.supporting_analysis.historical_cohort_chart
    assert chart.available is True
    assert [(point.month, point.mean) for point in chart.risk_path] == [(1, 0.62), (13, 0.38)]
    assert [(point.month, point.mean) for point in chart.avoidance_path] == [(1, 0.61), (13, 0.70)]
    assert (chart.risk_group_size, chart.avoidance_group_size, chart.breakpoint_month) == (50, 150, 13)
    assert detail.supporting_analysis.whatif_summary.available is True
    assert detail.supporting_analysis.whatif_summary.scenario_labels == (
        "Baseline scenario",
        "Variable-expense adjustment scenario",
    )
    assert [
        (bar.label, bar.count, bar.tone)
        for bar in detail.supporting_analysis.outcome_distribution
    ] == [
        ("stable path", 100, "stable"),
        ("financial-burden path", 50, "stress"),
    ]
    detail_text = " ".join(
        (*detail.conversation_preparation, *detail.supporting_analysis.current_change_cards)
    ).lower()
    for forbidden in ("risk score", "probability", "must contact", "call now", "loan"):
        assert forbidden not in detail_text


def test_detail_with_unavailable_saved_evidence_shows_no_invented_cards_or_chart() -> None:
    detail = build_rm_customer_detail_view(_worklist(), "C000003", language="en")

    assert detail.supporting_analysis.evidence_available is False
    assert detail.supporting_analysis.current_change_cards == ()
    assert detail.supporting_analysis.current_change_card_views == ()
    assert detail.supporting_analysis.current_summary == ()
    assert detail.conversation_steps[1].saved_observations == ()
    assert detail.supporting_analysis.outcome_distribution == ()
    assert detail.supporting_analysis.matched_outcome_summary == ()
    assert detail.supporting_analysis.historical_cohort_chart.available is False
    assert detail.supporting_analysis.whatif_summary.available is False


def test_completed_customer_detail_is_available_but_not_in_active_customer_list() -> None:
    view = build_rm_daily_review_view(
        _worklist(),
        presentation_metadata_by_customer={"C000004": {"display_name": "Completed synthetic customer"}},
    )
    detail = build_rm_customer_detail_view(
        _worklist(),
        "C000004",
        presentation_metadata_by_customer={"C000004": {"display_name": "Completed synthetic customer"}},
    )

    assert "C000004" not in [row.customer_id for row in view.customer_list]
    assert view.completed_items[0].display_name == "Completed synthetic customer"
    assert detail.display_name == "Completed synthetic customer"
    assert detail.completed_today is True
    with pytest.raises(ValueError, match="not present"):
        build_rm_customer_detail_view(_worklist(), "C999999")


def test_completed_customer_list_is_separate_from_active_timing_work() -> None:
    worklist = _worklist()

    completed = build_rm_completed_customer_list_view(worklist)

    assert [(row.customer_id, row.relationship_badge, row.completion_label) for row in completed] == [
        ("C000004", "핵심관리", "오늘 기록 완료"),
    ]
    active_ids = [row.customer_id for row in build_rm_daily_review_view(worklist).customer_list]
    assert completed[0].customer_id not in active_ids


def test_english_rm_view_uses_matching_display_copy() -> None:
    dashboard = build_rm_daily_review_view(_worklist(), language="en")
    detail = build_rm_customer_detail_view(_worklist(), "C000001", language="en")
    completed = build_rm_completed_customer_list_view(_worklist(), language="en")

    assert dashboard.analysis_as_of_label == "Monthly analysis as of: observation month 12"
    assert dashboard.snapshot_freshness_label == "This month's Snapshot"
    assert dashboard.customer_list[0].review_state_label == "Outstanding for work date"
    assert dashboard.customer_list[0].relationship_badge == "Core"
    assert dashboard.customer_list[0].current_change_summary == (
        "Primary change: cash capacity",
        "debt-payment burden 23.0%",
    )
    assert detail.supporting_analysis.current_summary[0] == "Current summary: The current status warrants a check."
    assert completed[0].completion_label == "Recorded today"


def test_view_module_has_no_streamlit_or_analysis_dependencies() -> None:
    module_path = Path(daily_review_view.__file__)
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert imported_modules.issubset(
        {
            "__future__",
                "collections.abc",
                "dataclasses",
                "datetime",
                "src.daily_review",
                "src.display_tones",
                "src.daily_worklist",
            "src.i18n",
            "src.rm_review_explainability",
            "src.rm_review_store",
        }
    )
    assert "primary_factor" not in source
    fields = set(daily_review_view.RmCustomerDetailView.__dataclass_fields__)
    assert not {
        "capacity",
        "case",
        "stepper",
        "raw_smd",
        "probability",
        "risk_score",
    }.intersection(fields)
