"""Plain-language RM explanations derived only from saved Daily Worklist items."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from src.daily_review import MONITOR, REVIEW_NOW, UPCOMING
from src.daily_worklist import DailyWorklistItem


FACTOR_LABELS = {
    "cash_balance_ratio": "현금 여력",
    "dsr": "대출 상환 부담",
    "fixed_expense_ratio": "고정지출",
    "variable_expense_ratio": "변동지출",
    "savings_rate": "저축 여력",
    "loan_balance_ratio": "대출 잔액",
}
RELATIONSHIP_CONTEXT_LABELS = {
    "CORE": "핵심관리 고객",
    "PRIORITY": "우선관리 고객",
    "STANDARD": "일반관리 고객",
}
REASON_LABELS = {
    "EVIDENCE_UNAVAILABLE": "현재 Daily 업무로 올릴 timing 근거가 부족합니다.",
    "BREAKPOINT_NOT_FOUND": "유사 고객 경로의 분기 시점이 확인되지 않았습니다.",
    "INSUFFICIENT_GROUP_SIZE": "유사 고객 그룹의 비교 근거가 충분하지 않습니다.",
    "INVALID_TIMING_EVIDENCE": "분기 시점의 timing 근거를 확인할 수 없습니다.",
    "TIMING_5_OR_MORE_MONTHS": "분기 시점이 현재 업무 범위보다 더 뒤에 있습니다.",
    "CURRENT_OBSERVATION_UNAVAILABLE": "현재 관측값이 없어 timing을 업무로 전환하지 않았습니다.",
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


def build_rm_review_explanation(item: DailyWorklistItem) -> RmReviewExplanation:
    """Explain saved timing evidence without performing or implying new analysis."""

    factor_label = FACTOR_LABELS.get(item.primary_factor, "주요 변화 정보 확인 필요")
    primary_change = f"주요 변화: {factor_label}"
    timing_evidence = _timing_evidence(item.timing_months)
    return RmReviewExplanation(
        customer_id=item.customer_id,
        snapshot_id=item.snapshot_id,
        review_state=item.review_state,
        review_reason=_review_reason(item, primary_change),
        timing_evidence=timing_evidence,
        primary_change=primary_change,
        historical_comparison_notice=HISTORICAL_COMPARISON_NOTICE,
        relationship_context=_relationship_context(item),
    )


def build_rm_review_explanations(
    items: Iterable[DailyWorklistItem],
) -> tuple[RmReviewExplanation, ...]:
    """Build explanations in the existing worklist order without re-sorting tasks."""

    return tuple(build_rm_review_explanation(item) for item in items)


def _review_reason(item: DailyWorklistItem, primary_change: str) -> str:
    timing_label = _timing_label(item.timing_months)
    if item.review_state == REVIEW_NOW:
        return f"오늘 확인 근거: 분기 시점 {timing_label} · {primary_change}"
    if item.review_state == UPCOMING:
        return f"곧 확인 예정 근거: 분기 시점 {timing_label} · {primary_change}"
    if item.review_state == MONITOR:
        return f"모니터링 근거: {REASON_LABELS.get(item.reason_code, 'timing 근거를 추가로 확인합니다.')}"
    return "업무 근거: 저장된 Snapshot timing 정보를 확인합니다."


def _timing_evidence(timing_months: int | None) -> str:
    if (
        not isinstance(timing_months, int)
        or isinstance(timing_months, bool)
        or not 1 <= timing_months <= 24
    ):
        return "분기 시점의 timing 근거가 충분하지 않아 현재는 모니터링합니다."
    timing_label = _timing_label(timing_months)
    return (
        "유사 고객의 위험 경로와 위험 회피 경로가 역사적으로 갈라졌던 시점이 "
        f"{timing_label}로 가까워 지금 현재 변화를 확인할 가치가 있습니다."
    )


def _timing_label(timing_months: int | None) -> str:
    if isinstance(timing_months, int) and not isinstance(timing_months, bool):
        return f"{timing_months}개월 이내"
    return "확인 필요"


def _relationship_context(item: DailyWorklistItem) -> str:
    relationship_label = RELATIONSHIP_CONTEXT_LABELS.get(
        item.relationship_priority,
        item.relationship_label or "고객관계 미지정",
    )
    return f"고객관계: {relationship_label} · 합성 CRM 메타데이터"
