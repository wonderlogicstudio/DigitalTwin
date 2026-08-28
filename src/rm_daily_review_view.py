"""Streamlit-neutral View Models for the RM Daily Review screen."""

from __future__ import annotations

from collections.abc import Mapping
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
CURRENT_STATUS_LABELS = {
    "healthy": "현재 상태는 안정적으로 관찰됩니다.",
    "watch": "현재 상태는 확인이 필요한 흐름입니다.",
    "stress": "현재 상태에서 재무 부담 변화를 확인할 필요가 있습니다.",
    "delinquent": "현재 상환 상태를 확인할 필요가 있습니다.",
}
CURRENT_SUMMARY_RATIO_LABELS = (
    ("recent_savings_rate", "최근 저축 여력"),
    ("recent_dsr", "최근 대출 상환 부담"),
    ("recent_fixed_expense_ratio", "최근 고정지출"),
)
OUTCOME_LABELS = (
    ("healthy", "안정 경로"),
    ("recovered", "회복 경로"),
    ("stress", "부담 경로"),
    ("delinquent", "연체 경로"),
)


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
class RmCompletedCustomerListItemView:
    """A compact completed-review row, separate from active timing work."""

    customer_id: str
    relationship_badge: str
    completion_label: str


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
class RmSupportingAnalysisView:
    """Saved, optional analysis evidence for a focused RM detail screen."""

    current_summary: tuple[str, ...]
    matched_outcome_summary: tuple[str, ...]
    breakpoint_summary: str
    additional_analysis_notice: str


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
    supporting_analysis: RmSupportingAnalysisView
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
    supporting_analysis = _build_supporting_analysis_view(item, explanation.timing_evidence)
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
        supporting_analysis=supporting_analysis,
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


def build_rm_completed_customer_list_view(
    worklist: DailyWorklist,
) -> tuple[RmCompletedCustomerListItemView, ...]:
    """Return only today's manually completed records in saved worklist order."""

    return tuple(
        RmCompletedCustomerListItemView(
            customer_id=item.customer_id,
            relationship_badge=_relationship_badge(item),
            completion_label="오늘 검토 결과 기록됨",
        )
        for item in worklist.completed_today
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


def _build_supporting_analysis_view(
    item: DailyWorklistItem,
    timing_evidence: str,
) -> RmSupportingAnalysisView:
    return RmSupportingAnalysisView(
        current_summary=_current_summary_lines(item),
        matched_outcome_summary=_matched_outcome_lines(item),
        breakpoint_summary=_breakpoint_summary(item, timing_evidence),
        additional_analysis_notice=(
            "이 화면은 저장된 월별 분석 요약만 읽습니다. 기존 차트와 시나리오 분석은 "
            "일반 분석 화면에서 별도로 확인하며, 여기서 다시 계산하지 않습니다."
        ),
    )


def _current_summary_lines(item: DailyWorklistItem) -> tuple[str, ...]:
    summary = item.current_summary
    lines = [
        "현재 요약: "
        + CURRENT_STATUS_LABELS.get(
            item.current_status,
            "저장된 현재 상태를 추가로 확인해 주세요.",
        )
    ]
    for field, label in CURRENT_SUMMARY_RATIO_LABELS:
        formatted_value = _format_saved_ratio(summary.get(field))
        if formatted_value is not None:
            lines.append(f"{label}: {formatted_value} (저장된 월별 요약)")
    return tuple(lines)


def _matched_outcome_lines(item: DailyWorklistItem) -> tuple[str, ...]:
    lines: list[str] = []
    if item.matched_count:
        lines.append(f"참고한 유사 고객: {item.matched_count:,}명")

    outcomes = _mapping_value(item.outcome_summary, "outcomes")
    outcome_counts: list[str] = []
    for outcome, label in OUTCOME_LABELS:
        count = _mapping_value(outcomes, outcome).get("count")
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            outcome_counts.append(f"{label} {count:,}명")
    if outcome_counts:
        lines.append("유사 고객의 과거 결과: " + " · ".join(outcome_counts))
    elif not lines:
        lines.append("유사 고객 결과 요약이 저장되지 않았습니다.")
    return tuple(lines)


def _breakpoint_summary(item: DailyWorklistItem, timing_evidence: str) -> str:
    if item.breakpoint_status == "found" and item.breakpoint_month is not None:
        return (
            f"분기점: 유사 고객 경로가 역사적으로 갈라진 분석 월은 "
            f"{item.breakpoint_month}개월차입니다. {timing_evidence}"
        )
    return f"분기점: {timing_evidence}"


def _mapping_value(value: object, key: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        return {}
    nested = value.get(key)
    return nested if isinstance(nested, Mapping) else {}


def _format_saved_ratio(value: object) -> str | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{float(value) * 100:.1f}%"
    return None
