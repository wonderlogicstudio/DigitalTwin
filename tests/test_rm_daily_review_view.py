"""Tests for the Streamlit-neutral RM Daily Review View Models."""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest

import src.rm_daily_review_view as daily_review_view
from src.daily_review import MONITOR, REVIEW_NOW, UPCOMING
from src.daily_worklist import DailyWorklist, DailyWorklistItem, MonitorSummary, SnapshotFreshness
from src.rm_daily_review_view import (
    RESULT_LABELS,
    build_rm_customer_detail_view,
    build_rm_daily_review_view,
)
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
    )


def _worklist() -> DailyWorklist:
    return DailyWorklist(
        snapshot_id="monthly-2026-08",
        daily_date=date(2026, 8, 29),
        today_items=(_item("C000001", REVIEW_NOW, "CORE", primary_factor="cash_balance_ratio"),),
        upcoming_items=(_item("C000002", UPCOMING, "PRIORITY", primary_factor="dsr"),),
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
    )


def test_dashboard_exposes_actual_worklist_counts_and_easy_customer_list() -> None:
    view = build_rm_daily_review_view(_worklist())

    assert view.analysis_as_of_label == "월별 분석 기준: 관측 12개월차"
    assert view.snapshot_freshness_label == "이번 달 Snapshot"
    assert (view.today_count, view.upcoming_count, view.monitor_count, view.completed_today_count) == (1, 1, 1, 1)
    assert [row.customer_id for row in view.customer_list] == ["C000001", "C000002", "C000003"]
    assert view.customer_list[0].review_state_label == "오늘 먼저 확인"
    assert view.customer_list[0].relationship_badge == "핵심관리"
    assert view.customer_list[0].why_today == "오늘 확인 근거: 분기 시점 1개월 이내 · 주요 변화: 현금 여력"
    assert "cash_balance_ratio" not in view.customer_list[0].primary_change


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

    assert detail.why_today == "오늘 확인 근거: 분기 시점 1개월 이내 · 주요 변화: 현금 여력"
    assert detail.relationship_badge == "핵심관리"
    assert detail.relationship_context == "고객관계: 핵심관리 고객 · 합성 CRM 메타데이터"
    assert len(detail.conversation_preparation) == 3
    assert detail.supporting_analysis_evidence[1] == "주요 변화: 현금 여력"
    assert "cash_balance_ratio" not in " ".join(detail.supporting_analysis_evidence)
    assert detail.result_recording.customer_id == "C000001"
    assert detail.result_recording.snapshot_id == "monthly-2026-08"
    assert [(option.result, option.label) for option in detail.result_recording.result_options] == [
        (REVIEW_COMPLETED, RESULT_LABELS[REVIEW_COMPLETED]),
        (REVIEW_FOLLOW_UP, RESULT_LABELS[REVIEW_FOLLOW_UP]),
        (REVIEW_MONITOR, RESULT_LABELS[REVIEW_MONITOR]),
    ]


def test_completed_customer_detail_is_available_but_not_in_active_customer_list() -> None:
    view = build_rm_daily_review_view(_worklist())
    detail = build_rm_customer_detail_view(_worklist(), "C000004")

    assert "C000004" not in [row.customer_id for row in view.customer_list]
    assert detail.completed_today is True
    with pytest.raises(ValueError, match="not present"):
        build_rm_customer_detail_view(_worklist(), "C999999")


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
            "src.daily_review",
            "src.daily_worklist",
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
