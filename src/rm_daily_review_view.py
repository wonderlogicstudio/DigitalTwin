"""Streamlit-neutral View Models for the RM Daily Review screen."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from src.daily_review import MONITOR, REVIEW_NOW, UPCOMING
from src.daily_worklist import DailyWorklist, DailyWorklistItem
from src.i18n import t
from src.rm_review_explainability import (
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
    language: str = "ko",
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
        analysis_as_of_label=t(
            "rm.analysis_as_of",
            language,
            month=worklist.snapshot_freshness.analysis_as_of_month,
        ),
        snapshot_freshness_label=_freshness_label(
            worklist.snapshot_freshness.status,
            language,
        ),
        today_count=len(worklist.today_items),
        upcoming_count=len(worklist.upcoming_items),
        monitor_count=len(worklist.monitor_items),
        completed_today_count=len(worklist.completed_today),
        relationship_priority_filter=normalized_filter,
        customer_list=tuple(_list_item_view(item, language) for item in visible_items),
    )


def build_rm_customer_detail_view(
    worklist: DailyWorklist,
    customer_id: str,
    *,
    language: str = "ko",
) -> RmCustomerDetailView:
    """Build one customer detail View Model from an existing Daily Worklist item."""

    item = _find_worklist_item(worklist, customer_id)
    explanation = build_rm_review_explanation(item, language=language)
    conversation = build_rm_conversation_preparation(item, language=language)
    supporting_analysis = _build_supporting_analysis_view(
        item,
        explanation.timing_evidence,
        language,
    )
    return RmCustomerDetailView(
        customer_id=item.customer_id,
        snapshot_id=item.snapshot_id,
        review_state_label=_review_state_label(item.review_state, language),
        why_today=explanation.review_reason,
        relationship_badge=_relationship_badge(item, language),
        relationship_context=explanation.relationship_context,
        conversation_preparation=conversation.confirmation_points,
        supporting_analysis_evidence=(
            explanation.timing_evidence,
            explanation.primary_change,
            explanation.historical_comparison_notice,
        ),
        supporting_analysis=supporting_analysis,
        completed_today=item.completed_today,
        result_recording=RmResultRecordingView(
            customer_id=item.customer_id,
            snapshot_id=item.snapshot_id,
            result_options=tuple(
                RmResultOptionView(result=result, label=label)
                for result, label in _result_labels(language).items()
            ),
        ),
    )


def build_rm_completed_customer_list_view(
    worklist: DailyWorklist,
    *,
    language: str = "ko",
) -> tuple[RmCompletedCustomerListItemView, ...]:
    """Return only today's manually completed records in saved worklist order."""

    return tuple(
        RmCompletedCustomerListItemView(
            customer_id=item.customer_id,
            relationship_badge=_relationship_badge(item, language),
            completion_label=t("rm.completed.row", language),
        )
        for item in worklist.completed_today
    )


def _active_items(worklist: DailyWorklist) -> tuple[DailyWorklistItem, ...]:
    return (
        *worklist.today_items,
        *worklist.upcoming_items,
        *worklist.monitor_items,
    )


def _list_item_view(item: DailyWorklistItem, language: str) -> RmDailyReviewListItemView:
    explanation = build_rm_review_explanation(item, language=language)
    return RmDailyReviewListItemView(
        customer_id=item.customer_id,
        review_state_label=_review_state_label(item.review_state, language),
        relationship_badge=_relationship_badge(item, language),
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


def _review_state_label(review_state: str, language: str) -> str:
    key_by_state = {
        REVIEW_NOW: "rm.state.review_now",
        UPCOMING: "rm.state.upcoming",
        MONITOR: "rm.state.monitor",
    }
    return t(key_by_state.get(review_state, "rm.state.unknown"), language)


def _relationship_badge(item: DailyWorklistItem, language: str) -> str:
    key_by_priority = {
        "CORE": "rm.relationship.core",
        "PRIORITY": "rm.relationship.priority",
        "STANDARD": "rm.relationship.standard",
    }
    return t(key_by_priority.get(item.relationship_priority, "rm.relationship.unspecified"), language)


def _build_supporting_analysis_view(
    item: DailyWorklistItem,
    timing_evidence: str,
    language: str,
) -> RmSupportingAnalysisView:
    return RmSupportingAnalysisView(
        current_summary=_current_summary_lines(item, language),
        matched_outcome_summary=_matched_outcome_lines(item, language),
        breakpoint_summary=_breakpoint_summary(item, timing_evidence, language),
        additional_analysis_notice=t("rm.analysis.additional", language),
    )


def _current_summary_lines(item: DailyWorklistItem, language: str) -> tuple[str, ...]:
    summary = item.current_summary
    lines = [
        t(
            "rm.current.prefix",
            language,
            status=t(
                {
                    "healthy": "rm.current.healthy",
                    "watch": "rm.current.watch",
                    "stress": "rm.current.stress",
                    "delinquent": "rm.current.delinquent",
                }.get(item.current_status, "rm.current.unknown"),
                language,
            ),
        )
    ]
    for field, key in (
        ("recent_savings_rate", "rm.current.savings"),
        ("recent_dsr", "rm.current.dsr"),
        ("recent_fixed_expense_ratio", "rm.current.fixed_expense"),
    ):
        formatted_value = _format_saved_ratio(summary.get(field))
        if formatted_value is not None:
            lines.append(
                f"{t(key, language)}: {formatted_value} "
                f"({t('rm.current.monthly_summary', language)})"
            )
    return tuple(lines)


def _matched_outcome_lines(item: DailyWorklistItem, language: str) -> tuple[str, ...]:
    lines: list[str] = []
    if item.matched_count:
        lines.append(t("rm.matched", language, count=f"{item.matched_count:,}"))

    outcomes = _mapping_value(item.outcome_summary, "outcomes")
    outcome_counts: list[str] = []
    for outcome, key in (
        ("healthy", "rm.outcome.healthy"),
        ("recovered", "rm.outcome.recovered"),
        ("stress", "rm.outcome.stress"),
        ("delinquent", "rm.outcome.delinquent"),
    ):
        count = _mapping_value(outcomes, outcome).get("count")
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            if language != "en":
                outcome_counts.append(f"{t(key, language)} {count:,}명")
            else:
                outcome_counts.append(f"{t(key, language)}: {count:,}")
    if outcome_counts:
        lines.append(t("rm.outcome.history", language, outcomes=" · ".join(outcome_counts)))
    elif not lines:
        lines.append(t("rm.outcome.unavailable", language))
    return tuple(lines)


def _breakpoint_summary(item: DailyWorklistItem, timing_evidence: str, language: str) -> str:
    if item.breakpoint_status == "found" and item.breakpoint_month is not None:
        return t(
            "rm.breakpoint.found",
            language,
            month=item.breakpoint_month,
            timing_evidence=timing_evidence,
        )
    return t("rm.breakpoint.default", language, timing_evidence=timing_evidence)


def _freshness_label(status: str, language: str) -> str:
    key_by_status = {
        "CURRENT_MONTH": "rm.freshness.current",
        "PRIOR_MONTH": "rm.freshness.prior",
        "FUTURE_PUBLICATION_DATE": "rm.freshness.future",
        "UNKNOWN": "rm.freshness.unknown",
    }
    return t(key_by_status.get(status, "rm.freshness.unknown"), language)


def _result_labels(language: str) -> dict[str, str]:
    return {
        REVIEW_COMPLETED: t("rm.result.completed", language),
        REVIEW_FOLLOW_UP: t("rm.result.follow_up", language),
        REVIEW_MONITOR: t("rm.result.monitor", language),
    }


def _mapping_value(value: object, key: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        return {}
    nested = value.get(key)
    return nested if isinstance(nested, Mapping) else {}


def _format_saved_ratio(value: object) -> str | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{float(value) * 100:.1f}%"
    return None
