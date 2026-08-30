"""Streamlit-neutral View Models for the RM Daily Review screen."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from src.daily_review import MONITOR, REVIEW_NOW, UPCOMING
from src.daily_worklist import (
    DailyReviewPlan,
    DailyWorklist,
    DailyWorklistItem,
    MonitorSummary,
    SnapshotFreshness,
)
from src.display_tones import classify_current_metric_tone
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
    display_name: str
    display_owner_or_team: str | None
    presentation_label: str | None
    review_state_label: str
    relationship_badge: str
    why_today: str
    primary_change: str
    current_change_summary: tuple[str, ...]
    timing_months: int | None
    supporting_evidence_available: bool
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
class RmConversationStepView:
    """One optional, neutral RM conversation prompt from saved evidence."""

    number: int
    title: str
    question: str
    context: str
    saved_observations: tuple[str, ...]


@dataclass(frozen=True)
class RmResultRecordingView:
    """Inputs needed by a UI to record a manual review result later."""

    customer_id: str
    snapshot_id: str
    result_options: tuple[RmResultOptionView, ...]
    note_optional: bool = True


@dataclass(frozen=True)
class RmOutcomeDistributionBarView:
    """One saved similar-customer outcome count for a display-only bar chart."""

    label: str
    count: int
    tone: str


@dataclass(frozen=True)
class RmCurrentChangeCardView:
    """One saved current observation with a display-only semantic tone."""

    label: str
    value: str
    tone: str
    status_label: str


@dataclass(frozen=True)
class RmSupportingAnalysisView:
    """Saved, optional analysis evidence for a focused RM detail screen."""

    evidence_available: bool
    evidence_status_message: str
    current_change_cards: tuple[str, ...]
    current_change_card_views: tuple[RmCurrentChangeCardView, ...]
    current_summary: tuple[str, ...]
    outcome_distribution: tuple[RmOutcomeDistributionBarView, ...]
    matched_outcome_summary: tuple[str, ...]
    breakpoint_summary: str
    historical_cohort_chart: "RmHistoricalCohortChartView"
    whatif_summary: "RmWhatifSummaryView"
    additional_analysis_notice: str


@dataclass(frozen=True)
class RmHistoricalCohortPoint:
    """One already-saved historical aggregate point for the detail chart."""

    month: int
    mean: float


@dataclass(frozen=True)
class RmHistoricalCohortChartView:
    """Historical risk/avoidance comparison payload; never a forecast chart."""

    available: bool
    metric_key: str | None
    risk_path: tuple[RmHistoricalCohortPoint, ...]
    avoidance_path: tuple[RmHistoricalCohortPoint, ...]
    risk_group_size: int | None
    avoidance_group_size: int | None
    breakpoint_month: int | None
    unavailable_message: str | None = None


@dataclass(frozen=True)
class RmWhatifSummaryView:
    """Names of saved scenario summaries only; it never contains time series."""

    available: bool
    scenario_labels: tuple[str, ...]
    unavailable_message: str | None = None


@dataclass(frozen=True)
class RmCustomerDetailView:
    """A customer detail page composed only from saved Daily workflow data."""

    customer_id: str
    snapshot_id: str
    display_name: str
    display_owner_or_team: str | None
    presentation_label: str | None
    review_state_label: str
    why_today: str
    timing_months: int | None
    primary_change: str
    relationship_badge: str
    relationship_context: str
    conversation_preparation: tuple[str, ...]
    conversation_steps: tuple[RmConversationStepView, ...]
    supporting_analysis_evidence: tuple[str, ...]
    supporting_analysis: RmSupportingAnalysisView
    completed_today: bool
    result_recording: RmResultRecordingView


@dataclass(frozen=True)
class RmDailyReviewDashboardView:
    """First-screen View Model for the Daily Review workflow."""

    snapshot_id: str
    analysis_as_of_month: int
    freshness: SnapshotFreshness
    analysis_as_of_label: str
    snapshot_freshness_label: str
    today_count: int
    upcoming_count: int
    monitor_count: int
    completed_today_count: int
    today_items: tuple[RmDailyReviewListItemView, ...]
    upcoming_items: tuple[RmDailyReviewListItemView, ...]
    completed_items: tuple[RmDailyReviewListItemView, ...]
    monitor_summary: MonitorSummary
    relationship_priority_breakdown: dict[str, dict[str, int]]
    relationship_priority_filter: str | None
    customer_list: tuple[RmDailyReviewListItemView, ...]
    planning: "RmDailyPlanningView"


@dataclass(frozen=True)
class RmDailyPlanningView:
    """Display-only plan for today and forthcoming saved workflow items."""

    effective_workday: date
    next_workday: date
    previous_workday: date
    previous_workday_completed_count: int
    today_items: tuple[RmDailyReviewListItemView, ...]
    next_workday_items: tuple[RmDailyReviewListItemView, ...]
    this_month_items: tuple[RmDailyReviewListItemView, ...]
    next_month_items: tuple[RmDailyReviewListItemView, ...]


def build_rm_daily_review_view(
    worklist: DailyWorklist,
    *,
    relationship_priority_filter: str | None = None,
    presentation_metadata_by_customer: Mapping[str, Mapping[str, object]] | None = None,
    language: str = "ko",
) -> RmDailyReviewDashboardView:
    """Build dashboard counts and rows without Streamlit or analysis calls.

    The optional relationship filter only narrows the displayed list. It never
    changes the already-decided timing bucket counts.
    """

    normalized_filter = _normalize_relationship_filter(relationship_priority_filter)
    presentation_metadata = presentation_metadata_by_customer or {}
    planning = _build_daily_planning_view(
        worklist.work_plan,
        language=language,
        presentation_metadata_by_customer=presentation_metadata,
    )
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
        analysis_as_of_month=worklist.snapshot_freshness.analysis_as_of_month,
        freshness=worklist.snapshot_freshness,
        analysis_as_of_label=t(
            "rm.analysis_as_of",
            language,
            month=worklist.snapshot_freshness.analysis_as_of_month,
        ),
        snapshot_freshness_label=_freshness_label(
            worklist.snapshot_freshness.status,
            language,
        ),
        today_count=len(planning.today_items),
        upcoming_count=len(worklist.upcoming_items),
        monitor_count=len(worklist.monitor_items),
        completed_today_count=len(worklist.completed_today),
        today_items=planning.today_items,
        upcoming_items=tuple(
            _list_item_view(item, language, presentation_metadata)
            for item in worklist.upcoming_items
        ),
        completed_items=tuple(
            _list_item_view(item, language, presentation_metadata)
            for item in worklist.completed_today
        ),
        monitor_summary=worklist.monitor_summary,
        relationship_priority_breakdown={
            priority: dict(counts)
            for priority, counts in worklist.relationship_priority_breakdown.items()
        },
        relationship_priority_filter=normalized_filter,
        customer_list=tuple(
            _list_item_view(item, language, presentation_metadata)
            for item in visible_items
        ),
        planning=planning,
    )


def _build_daily_planning_view(
    plan: DailyReviewPlan,
    *,
    language: str,
    presentation_metadata_by_customer: Mapping[str, Mapping[str, object]],
) -> RmDailyPlanningView:
    """Translate the saved-work plan without altering its operational order."""

    return RmDailyPlanningView(
        effective_workday=plan.effective_workday,
        next_workday=plan.next_workday,
        previous_workday=plan.previous_workday,
        previous_workday_completed_count=plan.previous_workday_completed_count,
        today_items=tuple(
            _list_item_view(item, language, presentation_metadata_by_customer)
            for item in plan.today_items
        ),
        next_workday_items=tuple(
            _list_item_view(item, language, presentation_metadata_by_customer)
            for item in plan.next_workday_items
        ),
        this_month_items=tuple(
            _list_item_view(item, language, presentation_metadata_by_customer)
            for item in plan.this_month_items
        ),
        next_month_items=tuple(
            _list_item_view(item, language, presentation_metadata_by_customer)
            for item in plan.next_month_candidates
        ),
    )


def build_rm_customer_detail_view(
    worklist: DailyWorklist,
    customer_id: str,
    *,
    presentation_metadata_by_customer: Mapping[str, Mapping[str, object]] | None = None,
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
    presentation = (presentation_metadata_by_customer or {}).get(item.customer_id, {})
    return RmCustomerDetailView(
        customer_id=item.customer_id,
        snapshot_id=item.snapshot_id,
        display_name=_localized_presentation_name(
            presentation,
            customer_id=item.customer_id,
            language=language,
        ),
        display_owner_or_team=_localized_presentation_text(
            presentation,
            field="display_owner_or_team",
            language=language,
        ),
        presentation_label=_localized_presentation_label(presentation, language=language),
        review_state_label=_review_state_label(item.review_state, language),
        why_today=explanation.review_reason,
        timing_months=item.timing_months,
        primary_change=explanation.primary_change,
        relationship_badge=_relationship_badge(item, language),
        relationship_context=explanation.relationship_context,
        conversation_preparation=conversation.confirmation_points,
        conversation_steps=_build_conversation_steps(
            conversation.confirmation_points,
            primary_change=explanation.primary_change,
            saved_change_cards=supporting_analysis.current_change_cards,
            language=language,
        ),
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


def _build_conversation_steps(
    confirmation_points: tuple[str, ...],
    *,
    primary_change: str,
    saved_change_cards: tuple[str, ...],
    language: str,
) -> tuple[RmConversationStepView, ...]:
    """Create optional disclosure steps without inferring a customer response.

    Financial measures may move in different directions.  These steps present
    their stored observations alongside neutral questions; they do not label a
    customer, calculate a new score, or manufacture an answer.
    """

    titles = (
        t("rm.conversation.step.background", language),
        t("rm.conversation.step.balance", language),
        t("rm.conversation.step.customer_view", language),
    )
    contexts = (
        t("rm.conversation.saved_observation", language),
        t("rm.conversation.balance_notice", language),
        t("rm.conversation.no_customer_answer", language),
    )
    questions = tuple(confirmation_points[:3])
    while len(questions) < 3:
        questions = (*questions, t("rm.conversation.default", language))
    observations_by_step = (
        (primary_change,),
        saved_change_cards[:3],
        (),
    )
    return tuple(
        RmConversationStepView(
            number=index,
            title=titles[index - 1],
            question=questions[index - 1],
            context=contexts[index - 1],
            saved_observations=observations_by_step[index - 1],
        )
        for index in range(1, 4)
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


def _list_item_view(
    item: DailyWorklistItem,
    language: str,
    presentation_metadata_by_customer: Mapping[str, Mapping[str, object]],
) -> RmDailyReviewListItemView:
    explanation = build_rm_review_explanation(item, language=language)
    presentation = presentation_metadata_by_customer.get(item.customer_id, {})
    return RmDailyReviewListItemView(
        customer_id=item.customer_id,
        display_name=_localized_presentation_name(
            presentation,
            customer_id=item.customer_id,
            language=language,
        ),
        display_owner_or_team=_localized_presentation_text(
            presentation,
            field="display_owner_or_team",
            language=language,
        ),
        presentation_label=_localized_presentation_label(presentation, language=language),
        review_state_label=_review_state_label(item.review_state, language),
        relationship_badge=_relationship_badge(item, language),
        why_today=explanation.review_reason,
        primary_change=explanation.primary_change,
        current_change_summary=_saved_change_summary(item, language),
        timing_months=item.timing_months,
        supporting_evidence_available=_saved_evidence_available(item),
        completed_today=item.completed_today,
    )


def _display_text(value: object, fallback: str) -> str:
    normalized_value = _optional_display_text(value)
    return normalized_value or fallback


def _localized_presentation_name(
    presentation: Mapping[str, object],
    *,
    customer_id: str,
    language: str,
) -> str:
    """Return the display-only name matching the selected UI language.

    Legacy overlay artifacts contain a Korean ``display_name`` only.  English
    RM screens must not surface that value, so their explicit fallback is also
    English until the operator rebuilds the standalone presentation overlay.
    """

    if language == "en":
        localized_name = _optional_display_text(presentation.get("display_name_en"))
        if localized_name is not None:
            return localized_name
        legacy_name = _english_legacy_text(presentation.get("display_name"))
        return legacy_name or t(
            "rm.presentation.fallback_name", language, customer_id=customer_id
        )
    return _display_text(
        presentation.get("display_name_ko") or presentation.get("display_name"),
        customer_id,
    )


def _localized_presentation_text(
    presentation: Mapping[str, object],
    *,
    field: str,
    language: str,
) -> str | None:
    """Return an optional localized presentation-only text field."""

    if language == "en":
        localized_text = _optional_display_text(presentation.get(f"{field}_en"))
        return localized_text or _english_legacy_text(presentation.get(field))
    return _optional_display_text(
        presentation.get(f"{field}_ko") or presentation.get(field)
    )


def _localized_presentation_label(
    presentation: Mapping[str, object],
    *,
    language: str,
) -> str:
    """Use a localized PoC disclosure even for a legacy overlay artifact."""

    return _localized_presentation_text(
        presentation,
        field="presentation_label",
        language=language,
    ) or t("rm.detail.identity", language)


def _english_legacy_text(value: object) -> str | None:
    """Keep compatible legacy English text without leaking Korean display text."""

    normalized_value = _optional_display_text(value)
    if normalized_value is not None and normalized_value.isascii():
        return normalized_value
    return None


def _optional_display_text(value: object) -> str | None:
    if value is None:
        return None
    normalized_value = str(value).strip()
    return normalized_value or None


def _saved_evidence_available(item: DailyWorklistItem) -> bool:
    saved_evidence = item.supporting_evidence
    return isinstance(saved_evidence, Mapping) and saved_evidence.get("available") is True


def _saved_change_summary(item: DailyWorklistItem, language: str) -> tuple[str, ...]:
    """Show saved primary evidence before actionable supplemental cards.

    Snapshot card construction has a stable display order. A list row must not
    mistake that order for the analysis result, so the saved breakpoint primary
    factor is always the first visible change.  Explicit non-signals such as
    ``no recent consecutive decline`` are retained in the saved Snapshot but
    omitted from the RM-facing summary: they do not give the RM a useful
    follow-up topic.
    """

    primary_change = build_rm_review_explanation(item, language=language).primary_change
    saved_evidence = item.supporting_evidence
    if not isinstance(saved_evidence, Mapping):
        return (primary_change,)
    cards = saved_evidence.get("current_change_cards")
    if not isinstance(cards, (list, tuple)):
        return (primary_change,)
    summaries: list[str] = []
    for card in cards:
        if not isinstance(card, Mapping):
            continue
        summary = _format_saved_change_card(card, language)
        if summary is None:
            continue
        label = _saved_card_label(card.get("key"), language)
        if primary_change.rstrip().endswith(label):
            continue
        summaries.append(summary)
    return (primary_change, *summaries[:1])


def _format_saved_change_card(card: Mapping[str, object], language: str) -> str | None:
    label = _saved_card_label(card.get("key"), language)
    value = card.get("value")
    value_type = str(card.get("value_type") or "")
    if value_type == "ratio" and isinstance(value, (int, float)) and not isinstance(value, bool):
        return t("rm.change.ratio", language, label=label, value=f"{float(value) * 100:.1f}%")
    if value_type == "consecutive_months" and isinstance(value, int) and not isinstance(value, bool):
        if value <= 0:
            return None
        return t("rm.change.consecutive_decline", language, label=label, months=value)
    return None


def _saved_change_card_views(
    item: DailyWorklistItem,
    language: str,
) -> tuple[RmCurrentChangeCardView, ...]:
    """Turn saved observations into labelled display cards without new analysis."""

    saved_evidence = item.supporting_evidence
    if not isinstance(saved_evidence, Mapping):
        return ()
    cards = saved_evidence.get("current_change_cards")
    if not isinstance(cards, (list, tuple)):
        return ()

    views: list[RmCurrentChangeCardView] = []
    for card in cards:
        if not isinstance(card, Mapping):
            continue
        value = _saved_change_card_display_value(card, language)
        if value is None:
            continue
        tone = _saved_change_card_tone(card)
        views.append(
            RmCurrentChangeCardView(
                label=_saved_card_label(card.get("key"), language),
                value=value,
                tone=tone,
                status_label=t(_change_tone_status_key(tone), language),
            )
        )
    return tuple(views)


def _saved_change_card_display_value(
    card: Mapping[str, object],
    language: str,
) -> str | None:
    value = card.get("value")
    value_type = str(card.get("value_type") or "")
    if value_type == "ratio" and isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{float(value) * 100:.1f}%"
    if value_type == "consecutive_months" and isinstance(value, int) and not isinstance(value, bool):
        if value <= 0:
            return None
        return t("rm.change.consecutive_decline_value", language, months=value)
    return None


def _saved_change_card_tone(card: Mapping[str, object]) -> str:
    """Reuse existing current-metric bands for a saved display observation."""

    card_key = str(card.get("key") or "")
    value = card.get("value")
    if card_key == "cash_availability":
        return "danger" if isinstance(value, int) and value > 0 else "neutral"
    metric_by_card_key = {
        "debt_service_burden": "dsr",
        "fixed_expense": "fixed_expense_ratio",
        "savings_capacity": "savings_rate",
    }
    metric = metric_by_card_key.get(card_key)
    return classify_current_metric_tone(metric, value) if metric else "neutral"


def _change_tone_status_key(tone: str) -> str:
    return {
        "stable": "rm.change.status.stable",
        "watch": "rm.change.status.watch",
        "danger": "rm.change.status.danger",
    }.get(tone, "rm.change.status.neutral")


def _saved_card_label(card_key: object, language: str) -> str:
    key_by_card = {
        "cash_availability": "rm.change.cash_availability",
        "debt_service_burden": "rm.change.debt_service_burden",
        "fixed_expense": "rm.change.fixed_expense",
        "savings_capacity": "rm.change.savings_capacity",
    }
    return t(key_by_card.get(str(card_key), "rm.factor.unknown"), language)


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
    saved_evidence = item.supporting_evidence
    evidence_available = _saved_evidence_available(item)
    return RmSupportingAnalysisView(
        evidence_available=evidence_available,
        evidence_status_message=_saved_evidence_status_message(saved_evidence, language),
        current_change_cards=(
            _saved_change_summary(item, language) if evidence_available else ()
        ),
        current_change_card_views=(
            _saved_change_card_views(item, language) if evidence_available else ()
        ),
        current_summary=_current_summary_lines(item, language) if evidence_available else (),
        outcome_distribution=(
            _outcome_distribution(item, language) if evidence_available else ()
        ),
        matched_outcome_summary=(
            _matched_outcome_lines(item, language) if evidence_available else ()
        ),
        breakpoint_summary=(
            _breakpoint_summary(item, timing_evidence, language)
            if evidence_available
            else _saved_evidence_status_message(saved_evidence, language)
        ),
        historical_cohort_chart=_saved_historical_cohort_chart(saved_evidence, language),
        whatif_summary=_saved_whatif_summary(saved_evidence, language),
        additional_analysis_notice=t("rm.analysis.additional", language),
    )


def _saved_evidence_status_message(
    saved_evidence: Mapping[str, object] | None,
    language: str,
) -> str:
    if isinstance(saved_evidence, Mapping) and saved_evidence.get("available") is True:
        return t("rm.evidence.available", language)
    return t("rm.evidence.unavailable", language)


def _saved_historical_cohort_chart(
    saved_evidence: Mapping[str, object] | None,
    language: str,
) -> RmHistoricalCohortChartView:
    chart = _nested_mapping(saved_evidence, "cohort_path_chart")
    if (
        not isinstance(saved_evidence, Mapping)
        or saved_evidence.get("available") is not True
        or chart.get("available") is not True
    ):
        return RmHistoricalCohortChartView(
            available=False,
            metric_key=None,
            risk_path=(),
            avoidance_path=(),
            risk_group_size=None,
            avoidance_group_size=None,
            breakpoint_month=None,
            unavailable_message=t("rm.evidence.chart_unavailable", language),
        )

    risk_path = _cohort_points(chart.get("risk_path"))
    avoidance_path = _cohort_points(chart.get("avoidance_path"))
    metric_key = _optional_display_text(chart.get("metric"))
    breakpoint_month = _optional_int_value(_nested_mapping(chart, "breakpoint_marker").get("month"))
    group_sizes = _nested_mapping(chart, "group_sizes")
    if not metric_key or not risk_path or not avoidance_path or breakpoint_month is None:
        return RmHistoricalCohortChartView(
            available=False,
            metric_key=None,
            risk_path=(),
            avoidance_path=(),
            risk_group_size=None,
            avoidance_group_size=None,
            breakpoint_month=None,
            unavailable_message=t("rm.evidence.chart_unavailable", language),
        )
    return RmHistoricalCohortChartView(
        available=True,
        metric_key=metric_key,
        risk_path=risk_path,
        avoidance_path=avoidance_path,
        risk_group_size=_optional_int_value(group_sizes.get("risk_path")),
        avoidance_group_size=_optional_int_value(group_sizes.get("avoidance_path")),
        breakpoint_month=breakpoint_month,
    )


def _saved_whatif_summary(
    saved_evidence: Mapping[str, object] | None,
    language: str,
) -> RmWhatifSummaryView:
    summary = _nested_mapping(saved_evidence, "whatif_summary")
    scenarios = summary.get("scenarios")
    if (
        not isinstance(saved_evidence, Mapping)
        or saved_evidence.get("available") is not True
        or summary.get("available") is not True
        or not isinstance(scenarios, (list, tuple))
    ):
        return RmWhatifSummaryView(
            available=False,
            scenario_labels=(),
            unavailable_message=t("rm.evidence.whatif_unavailable", language),
        )
    scenario_labels = tuple(
        _whatif_scenario_label(scenario.get("scenario_name"), language)
        for scenario in scenarios
        if isinstance(scenario, Mapping)
    )
    return RmWhatifSummaryView(
        available=True,
        scenario_labels=tuple(label for label in scenario_labels if label),
    )


def _whatif_scenario_label(value: object, language: str) -> str | None:
    key_by_scenario = {
        "baseline": "rm.whatif.baseline",
        "variable_expense_cut_15": "rm.whatif.variable_expense_cut_15",
        "fixed_expense_cut_300k": "rm.whatif.fixed_expense_cut_300k",
        "debt_payment_cut_20": "rm.whatif.debt_payment_cut_20",
    }
    translation_key = key_by_scenario.get(str(value or ""))
    return t(translation_key, language) if translation_key else None


def _cohort_points(value: object) -> tuple[RmHistoricalCohortPoint, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    points: list[RmHistoricalCohortPoint] = []
    for raw_point in value:
        if not isinstance(raw_point, Mapping):
            return ()
        month = _optional_int_value(raw_point.get("month"))
        mean = raw_point.get("mean")
        if month is None or not isinstance(mean, (int, float)) or isinstance(mean, bool):
            return ()
        points.append(RmHistoricalCohortPoint(month=month, mean=float(mean)))
    return tuple(points)


def _nested_mapping(value: object, key: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        return {}
    nested_value = value.get(key)
    return nested_value if isinstance(nested_value, Mapping) else {}


def _optional_int_value(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


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


def _outcome_distribution(
    item: DailyWorklistItem,
    language: str,
) -> tuple[RmOutcomeDistributionBarView, ...]:
    """Expose only already-saved peer outcome counts for a small RM chart."""

    outcomes = _mapping_value(item.outcome_summary, "outcomes")
    bars: list[RmOutcomeDistributionBarView] = []
    for outcome, key, tone in (
        ("healthy", "rm.outcome.healthy", "stable"),
        ("recovered", "rm.outcome.recovered", "recovered"),
        ("stress", "rm.outcome.stress", "stress"),
        ("delinquent", "rm.outcome.delinquent", "delinquent"),
    ):
        count = _mapping_value(outcomes, outcome).get("count")
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            bars.append(
                RmOutcomeDistributionBarView(
                    label=t(key, language),
                    count=count,
                    tone=tone,
                )
            )
    return tuple(bars)


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
