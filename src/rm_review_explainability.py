"""Plain-language RM explanations derived only from saved Daily Worklist items."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from src.daily_review import MONITOR, REVIEW_NOW, UPCOMING
from src.daily_worklist import DailyWorklistItem
from src.i18n import t


FACTOR_LABELS = {
    "cash_balance_ratio": "현금 여력",
    "dsr": "대출 상환 부담",
    "fixed_expense_ratio": "고정지출",
    "variable_expense_ratio": "변동지출",
    "savings_rate": "저축 여력",
    "loan_balance_ratio": "대출 잔액",
}
FACTOR_TRANSLATION_KEYS = {
    "cash_balance_ratio": "rm.factor.cash_balance_ratio",
    "dsr": "rm.factor.dsr",
    "fixed_expense_ratio": "rm.factor.fixed_expense_ratio",
    "variable_expense_ratio": "rm.factor.variable_expense_ratio",
    "savings_rate": "rm.factor.savings_rate",
    "loan_balance_ratio": "rm.factor.loan_balance_ratio",
}
RELATIONSHIP_CONTEXT_LABELS = {
    "CORE": "핵심관리 고객",
    "PRIORITY": "우선관리 고객",
    "STANDARD": "일반관리 고객",
}
RELATIONSHIP_CONTEXT_TRANSLATION_KEYS = {
    "CORE": "rm.relationship.customer.core",
    "PRIORITY": "rm.relationship.customer.priority",
    "STANDARD": "rm.relationship.customer.standard",
}
CONVERSATION_PROMPTS_BY_FACTOR = {
    "cash_balance_ratio": "최근 현금 여력 감소에 일시적인 지출이나 이벤트가 있었는지 확인해 보세요.",
    "dsr": "최근 상환 부담에 변화가 있었는지 확인해 보세요.",
    "fixed_expense_ratio": "최근 고정지출에 큰 변화가 있었는지 확인해 보세요.",
    "variable_expense_ratio": "최근 변동지출에 큰 변화가 있었는지 확인해 보세요.",
    "savings_rate": "최근 저축 여력 변화가 일시적인지 확인해 보세요.",
    "loan_balance_ratio": "최근 대출 잔액이나 상환 일정에 변화가 있었는지 확인해 보세요.",
}
CONVERSATION_PROMPT_TRANSLATION_KEYS = {
    "cash_balance_ratio": "rm.conversation.cash",
    "dsr": "rm.conversation.dsr",
    "fixed_expense_ratio": "rm.conversation.fixed_expense",
    "variable_expense_ratio": "rm.conversation.variable_expense",
    "savings_rate": "rm.conversation.savings",
    "loan_balance_ratio": "rm.conversation.loan_balance",
}
DEFAULT_CONVERSATION_PROMPT = (
    "최근 현금 여력, 지출 또는 상환 부담에 변화가 있었는지 확인해 보세요."
)
REASON_LABELS = {
    "EVIDENCE_UNAVAILABLE": "현재 Daily 업무로 올릴 timing 근거가 부족합니다.",
    "BREAKPOINT_NOT_FOUND": "유사 고객 경로의 분기 시점이 확인되지 않았습니다.",
    "INSUFFICIENT_GROUP_SIZE": "유사 고객 그룹의 비교 근거가 충분하지 않습니다.",
    "INVALID_TIMING_EVIDENCE": "분기 시점의 timing 근거를 확인할 수 없습니다.",
    "TIMING_5_OR_MORE_MONTHS": "분기 시점이 현재 업무 범위보다 더 뒤에 있습니다.",
    "CURRENT_OBSERVATION_UNAVAILABLE": "현재 관측값이 없어 timing을 업무로 전환하지 않았습니다.",
}
REASON_TRANSLATION_KEYS = {
    "EVIDENCE_UNAVAILABLE": "rm.reason.evidence_unavailable",
    "BREAKPOINT_NOT_FOUND": "rm.reason.breakpoint_not_found",
    "INSUFFICIENT_GROUP_SIZE": "rm.reason.insufficient_group_size",
    "INVALID_TIMING_EVIDENCE": "rm.reason.invalid_timing",
    "TIMING_5_OR_MORE_MONTHS": "rm.reason.distant_timing",
    "CURRENT_OBSERVATION_UNAVAILABLE": "rm.reason.current_unavailable",
}
HISTORICAL_COMPARISON_NOTICE = (
    "이 근거는 유사 고객의 과거 경로 비교에 따른 timing 정보이며, "
    "미래 사건 발생일이나 새로운 예측이 아닙니다."
)


@dataclass(frozen=True)
class RmReviewExplanation:
    """Plain-language explanation for one existing Daily Worklist item."""

    customer_id: str
    snapshot_id: str
    review_state: str
    review_reason: str
    timing_evidence: str
    primary_change: str
    historical_comparison_notice: str
    relationship_context: str


@dataclass(frozen=True)
class RmConversationPreparation:
    """Three concise confirmation points for a customer conversation."""

    customer_id: str
    snapshot_id: str
    primary_change: str
    confirmation_points: tuple[str, ...]


def build_rm_review_explanation(
    item: DailyWorklistItem,
    *,
    language: str = "ko",
) -> RmReviewExplanation:
    """Explain saved timing evidence without performing or implying new analysis."""

    factor_label = _factor_label(item.primary_factor, language)
    primary_change = t("rm.primary_change", language, factor=factor_label)
    timing_evidence = _timing_evidence(item.timing_months, language)
    return RmReviewExplanation(
        customer_id=item.customer_id,
        snapshot_id=item.snapshot_id,
        review_state=item.review_state,
        review_reason=_review_reason(item, primary_change, language),
        timing_evidence=timing_evidence,
        primary_change=primary_change,
        historical_comparison_notice=(
            HISTORICAL_COMPARISON_NOTICE
            if language != "en"
            else t("rm.history.notice", language)
        ),
        relationship_context=_relationship_context(item, language),
    )


def build_rm_review_explanations(
    items: Iterable[DailyWorklistItem],
    *,
    language: str = "ko",
) -> tuple[RmReviewExplanation, ...]:
    """Build explanations in the existing worklist order without re-sorting tasks."""

    return tuple(build_rm_review_explanation(item, language=language) for item in items)


def build_rm_conversation_preparation(
    item: DailyWorklistItem,
    *,
    language: str = "ko",
) -> RmConversationPreparation:
    """Prepare neutral confirmation points without contact or product advice."""

    factor_label = _factor_label(item.primary_factor, language)
    return RmConversationPreparation(
        customer_id=item.customer_id,
        snapshot_id=item.snapshot_id,
        primary_change=t("rm.primary_change", language, factor=factor_label),
        confirmation_points=(
            t("rm.conversation.change_persistent", language),
            t("rm.conversation.income_change", language),
            _conversation_prompt(item.primary_factor, language),
        ),
    )


def _review_reason(item: DailyWorklistItem, primary_change: str, language: str) -> str:
    timing_label = _timing_label(item.timing_months, language)
    if item.review_state == REVIEW_NOW:
        return t("rm.review_reason.today", language, timing=timing_label, primary_change=primary_change)
    if item.review_state == UPCOMING:
        return t("rm.review_reason.upcoming", language, timing=timing_label, primary_change=primary_change)
    if item.review_state == MONITOR:
        return t(
            "rm.review_reason.monitor",
            language,
            reason=_reason_label(item.reason_code, language),
        )
    return t("rm.review_reason.default", language)


def _timing_evidence(timing_months: int | None, language: str) -> str:
    if (
        not isinstance(timing_months, int)
        or isinstance(timing_months, bool)
        or not 1 <= timing_months <= 24
    ):
        return t("rm.timing.unavailable", language)
    return t("rm.timing.evidence", language, timing=_timing_label(timing_months, language))


def _timing_label(timing_months: int | None, language: str) -> str:
    if isinstance(timing_months, int) and not isinstance(timing_months, bool):
        if timing_months == 1:
            return t("rm.timing.within_month", language)
        return t("rm.timing.within_months", language, months=timing_months)
    return t("rm.timing.check_needed", language)


def _relationship_context(item: DailyWorklistItem, language: str) -> str:
    key = RELATIONSHIP_CONTEXT_TRANSLATION_KEYS.get(
        item.relationship_priority,
        "rm.relationship.customer.unknown",
    )
    relationship_label = t(key, language)
    return t("rm.relationship.context", language, label=relationship_label)


def _factor_label(primary_factor: str | None, language: str) -> str:
    return t(FACTOR_TRANSLATION_KEYS.get(primary_factor, "rm.factor.unknown"), language)


def _conversation_prompt(primary_factor: str | None, language: str) -> str:
    if language != "en":
        return CONVERSATION_PROMPTS_BY_FACTOR.get(
            primary_factor,
            DEFAULT_CONVERSATION_PROMPT,
        )
    return t(
        CONVERSATION_PROMPT_TRANSLATION_KEYS.get(primary_factor, "rm.conversation.default"),
        language,
    )


def _reason_label(reason_code: str, language: str) -> str:
    return t(REASON_TRANSLATION_KEYS.get(reason_code, "rm.reason.default"), language)
