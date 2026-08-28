"""Streamlit-neutral View Models for the RM Daily Review screen."""

from __future__ import annotations

from dataclasses import dataclass

from src.daily_review import MONITOR, REVIEW_NOW, UPCOMING
from src.daily_worklist import DailyWorklist, DailyWorklistItem
from src.rm_review_explainability import (
    HISTORICAL_COMPARISON_NOTICE,
    build_rm_conversation_preparation,
    build_rm_review_explanation,
)
from src.rm_review_store import (
    REVIEW_COMPLETED,
    REVIEW_FOLLOW_UP,
    REVIEW_MONITOR,
)


REVIEW_STATE_LABELS = {
    REVIEW_NOW: "오늘 먼저 확인",
    UPCOMING: "곧 확인 예정",
    MONITOR: "모니터링",
}
RELATIONSHIP_BADGE_LABELS = {
    "CORE": "핵심관리",
    "PRIORITY": "우선관리",
    "STANDARD": "일반관리",
}
FRESHNESS_LABELS = {
    "CURRENT_MONTH": "이번 달 Snapshot",
    "PRIOR_MONTH": "이전 달 Snapshot",
    "FUTURE_PUBLICATION_DATE": "Snapshot 공개일 확인 필요",
    "UNKNOWN": "Snapshot 공개일 미확인",
}
RESULT_LABELS = {
    REVIEW_COMPLETED: "확인 완료",
    REVIEW_FOLLOW_UP: "추가 상담 검토",
    REVIEW_MONITOR: "추후 모니터링",
}


@dataclass(frozen=True)
class RmDailyReviewListItemView:
    """A compact customer row for the RM Daily Review list."""

    customer_id: str
    review_state_label: str
    relationship_badge: str
    why_today: str
    primary_change: str
    completed_today: bool


@dataclass(frozen=True)
class RmResultOptionView:
    """A selectable manual review result, with no automatic outcome."""

    result: str
    label: str


@dataclass(frozen=True)
class RmResultRecordingView:
    """Inputs needed by a UI to record a manual review result later."""

    customer_id: str
    snapshot_id: str
    result_options: tuple[RmResultOptionView, ...]
    note_optional: bool = True


@dataclass(frozen=True)
class RmCustomerDetailView:
    """A customer detail page composed only from saved Daily workflow data."""

    customer_id: str
    snapshot_id: str
    review_state_label: str
    why_today: str
    relationship_badge: str
    relationship_context: str
    conversation_preparation: tuple[str, ...]
    supporting_analysis_evidence: tuple[str, ...]
    completed_today: bool
    result_recording: RmResultRecordingView


@dataclass(frozen=True)
class RmDailyReviewDashboardView:
    """First-screen View Model for the Daily Review workflow."""

    snapshot_id: str
    analysis_as_of_label: str
    snapshot_freshness_label: str
    today_count: int
    upcoming_count: int
    monitor_count: int
    completed_today_count: int
    relationship_priority_filter: str | None
    customer_list: tuple[RmDailyReviewListItemView, ...]


def build_rm_daily_review_view(
    worklist: DailyWorklist,
    *,
    relationship_priority_filter: str | None = None,
) -> RmDailyReviewDashboardView:
    """Build dashboard counts and rows without Streamlit or analysis calls.

    The optional relationship filter only narrows the displayed list. It never
    changes the already-decided timing bucket counts.
    """

    normalized_filter = _normalize_relationship_filter(relationship_priority_filter)
    active_items = _active_items(worklist)
    visible_items = (
        active_items
        if normalized_filter is None
        else tuple(
            item
            for item in active_items
            if item.relationship_priority == normalized_filter
        )
    )
    return RmDailyReviewDashboardView(
        snapshot_id=worklist.snapshot_id,
        analysis_as_of_label=(
            f"월별 분석 기준: 관측 {worklist.snapshot_freshness.analysis_as_of_month}개월차"
        ),
        snapshot_freshness_label=FRESHNESS_LABELS.get(
            worklist.snapshot_freshness.status,
            "Snapshot freshness 확인 필요",
        ),
        today_count=len(worklist.today_items),
        upcoming_count=len(worklist.upcoming_items),
        monitor_count=len(worklist.monitor_items),
        completed_today_count=len(worklist.completed_today),
        relationship_priority_filter=normalized_filter,
        customer_list=tuple(_list_item_view(item) for item in visible_items),
    )


def build_rm_customer_detail_view(
    worklist: DailyWorklist,
    customer_id: str,
) -> RmCustomerDetailView:
    """Build one customer detail View Model from an existing Daily Worklist item."""

    item = _find_worklist_item(worklist, customer_id)
    explanation = build_rm_review_explanation(item)
    conversation = build_rm_conversation_preparation(item)
    return RmCustomerDetailView(
        customer_id=item.customer_id,
        snapshot_id=item.snapshot_id,
        review_state_label=_review_state_label(item.review_state),
        why_today=explanation.review_reason,
        relationship_badge=_relationship_badge(item),
        relationship_context=explanation.relationship_context,
        conversation_preparation=conversation.confirmation_points,
        supporting_analysis_evidence=(
            explanation.timing_evidence,
            explanation.primary_change,
            HISTORICAL_COMPARISON_NOTICE,
        ),
        completed_today=item.completed_today,
        result_recording=RmResultRecordingView(
            customer_id=item.customer_id,
            snapshot_id=item.snapshot_id,
            result_options=tuple(
                RmResultOptionView(result=result, label=label)
                for result, label in RESULT_LABELS.items()
            ),
        ),
    )


def _active_items(worklist: DailyWorklist) -> tuple[DailyWorklistItem, ...]:
    return (
        *worklist.today_items,
        *worklist.upcoming_items,
        *worklist.monitor_items,
    )


def _list_item_view(item: DailyWorklistItem) -> RmDailyReviewListItemView:
    explanation = build_rm_review_explanation(item)
    return RmDailyReviewListItemView(
        customer_id=item.customer_id,
        review_state_label=_review_state_label(item.review_state),
        relationship_badge=_relationship_badge(item),
        why_today=explanation.review_reason,
        primary_change=explanation.primary_change,
        completed_today=item.completed_today,
    )


def _find_worklist_item(worklist: DailyWorklist, customer_id: str) -> DailyWorklistItem:
    normalized_customer_id = str(customer_id).strip()
    for item in (*_active_items(worklist), *worklist.completed_today):
        if item.customer_id == normalized_customer_id:
            return item
    raise ValueError(f"customer_id is not present in this Daily Worklist: {customer_id}")


def _normalize_relationship_filter(value: str | None) -> str | None:
    if value is None:
        return None
    normalized_value = str(value).strip().upper()
    if not normalized_value:
        return None
    if normalized_value not in RELATIONSHIP_BADGE_LABELS:
        raise ValueError("relationship_priority_filter must be CORE, PRIORITY, or STANDARD.")
    return normalized_value


def _review_state_label(review_state: str) -> str:
    return REVIEW_STATE_LABELS.get(review_state, "업무 상태 확인 필요")


def _relationship_badge(item: DailyWorklistItem) -> str:
    return RELATIONSHIP_BADGE_LABELS.get(
        item.relationship_priority,
        item.relationship_label or "관계 중요도 미지정",
    )
