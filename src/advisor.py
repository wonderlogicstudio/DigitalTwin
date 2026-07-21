"""Template-based explanation helpers for the Streamlit MVP.

The functions in this module only rephrase values already produced by the
pipeline. They do not call external LLM APIs and do not create new analysis
numbers beyond direct display summaries such as stress + delinquent ratio.
"""

from __future__ import annotations

from typing import Any

from src.copy import (
    BREAKPOINT_INSUFFICIENT_MESSAGE,
    BREAKPOINT_NOT_FOUND_MESSAGE,
    CASH_DEPLETION_NONE,
    cash_depletion_label,
)
from src.formatters import format_krw_compact, format_metric_value, format_month_label, format_percent
from src.labels import label_metric, label_scenario, label_status


def build_customer_brief(
    current_metrics: dict[str, Any],
    outcome_summary: dict[str, Any],
    breakpoint_result: dict[str, Any],
    whatif_results: dict[str, Any],
    language: str = "ko",
) -> str:
    """Build a customer-facing deterministic template explanation."""

    if language == "en":
        return _build_customer_brief_en(current_metrics, outcome_summary, breakpoint_result, whatif_results)

    matched_count = _matched_count(outcome_summary)
    risk_ratio = _risk_group_ratio(outcome_summary)
    best = _best_whatif_scenario(whatif_results)

    sentences = [
        (
            f"현재 재무 흐름은 저축률 {_format_ratio(current_metrics.get('recent_savings_rate'))}, "
            f"DSR {_format_ratio(current_metrics.get('recent_dsr'))}, "
            f"고정지출 비중 {_format_ratio(current_metrics.get('recent_fixed_expense_ratio'))}이며 "
            f"현재 상태는 {_format_status(current_metrics.get('current_status'))}, "
            f"현금 잔액은 {_format_money(current_metrics.get('current_cash_balance'))}입니다."
        ),
        f"유사 재무 흐름을 보인 고객은 {matched_count:,}명입니다.",
        f"이 집단에서 재무 스트레스 또는 연체 경로를 보인 비율은 {_format_ratio(risk_ratio)}입니다.",
        _customer_breakpoint_sentence(breakpoint_result),
        _customer_timing_sentence(breakpoint_result),
        _customer_whatif_sentence(best),
        "이 결과는 합성 데이터 기반 PoC이며 실제 신용평가가 아닌 상담 참고 자료입니다.",
    ]
    return "\n".join(sentences)


def build_staff_brief(
    current_metrics: dict[str, Any],
    outcome_summary: dict[str, Any],
    breakpoint_result: dict[str, Any],
    whatif_results: dict[str, Any],
    language: str = "ko",
) -> str:
    """Build a staff-facing deterministic template explanation."""

    if language == "en":
        return _build_staff_brief_en(current_metrics, outcome_summary, breakpoint_result, whatif_results)

    risk_ratio = _risk_group_ratio(outcome_summary)
    best = _best_whatif_scenario(whatif_results)

    sentences = [
        f"현재 고객 상태는 {_format_status(current_metrics.get('current_status'))}입니다.",
        (
            f"최근 3개월 평균은 저축률 {_format_ratio(current_metrics.get('recent_savings_rate'))}, "
            f"DSR {_format_ratio(current_metrics.get('recent_dsr'))}, "
            f"고정지출 비중 {_format_ratio(current_metrics.get('recent_fixed_expense_ratio'))}입니다."
        ),
        _trend_sentence(current_metrics),
        (
            f"유사 집단 {_matched_count(outcome_summary):,}명 중 재무 스트레스 또는 연체 경로 비율은 "
            f"{_format_ratio(risk_ratio)}입니다."
        ),
        _staff_breakpoint_sentence(breakpoint_result),
        _consultation_timing_sentence(breakpoint_result),
        _staff_whatif_sentence(best),
        "대출상환액 감소 시나리오는 실제 승인 여부나 계약 변경 가능성을 반영하지 않습니다.",
        "이 분석은 합성 데이터 기반 PoC이며 공식 신용평가나 상품 권유 기준이 아닙니다.",
    ]
    return "\n".join(sentences)


def build_brief_with_fallback(
    audience: str,
    current_metrics: dict[str, Any],
    outcome_summary: dict[str, Any],
    breakpoint_result: dict[str, Any],
    whatif_results: dict[str, Any],
    llm_builder: Any | None = None,
    language: str = "ko",
) -> str:
    """Build a brief with deterministic template fallback for LLM/API failures."""

    if llm_builder is not None:
        try:
            brief = llm_builder(current_metrics, outcome_summary, breakpoint_result, whatif_results)
            if isinstance(brief, str) and brief.strip():
                return brief
        except Exception:  # noqa: BLE001
            pass

    if audience == "staff":
        return build_staff_brief(current_metrics, outcome_summary, breakpoint_result, whatif_results, language=language)
    return build_customer_brief(current_metrics, outcome_summary, breakpoint_result, whatif_results, language=language)


def _build_customer_brief_en(
    current_metrics: dict[str, Any],
    outcome_summary: dict[str, Any],
    breakpoint_result: dict[str, Any],
    whatif_results: dict[str, Any],
) -> str:
    matched_count = _matched_count(outcome_summary)
    risk_ratio = _risk_group_ratio(outcome_summary)
    best = _best_whatif_scenario(whatif_results)
    sentences = [
        (
            f"The current path shows a savings rate of {_format_ratio(current_metrics.get('recent_savings_rate'))}, "
            f"a debt service ratio of {_format_ratio(current_metrics.get('recent_dsr'))}, "
            f"a fixed expense ratio of {_format_ratio(current_metrics.get('recent_fixed_expense_ratio'))}, "
            f"a current status of {_format_status(current_metrics.get('current_status'), 'en')}, "
            f"and a cash balance of {_format_money(current_metrics.get('current_cash_balance'), 'en')}."
        ),
        f"The similar-customer cohort includes {matched_count:,} customers.",
        (
            f"Among this cohort, {_format_ratio(risk_ratio)} entered a financial stress or delinquency path."
        ),
        _customer_breakpoint_sentence_en(breakpoint_result),
        _customer_timing_sentence_en(breakpoint_result),
        _customer_whatif_sentence_en(best),
        "This is a synthetic-data proof of concept and a consultation reference, not an official credit assessment.",
    ]
    return "\n".join(sentences)


def _build_staff_brief_en(
    current_metrics: dict[str, Any],
    outcome_summary: dict[str, Any],
    breakpoint_result: dict[str, Any],
    whatif_results: dict[str, Any],
) -> str:
    risk_ratio = _risk_group_ratio(outcome_summary)
    best = _best_whatif_scenario(whatif_results)
    sentences = [
        f"The current customer status is {_format_status(current_metrics.get('current_status'), 'en')}.",
        (
            f"The recent 3-month averages are savings rate {_format_ratio(current_metrics.get('recent_savings_rate'))}, "
            f"debt service ratio {_format_ratio(current_metrics.get('recent_dsr'))}, "
            f"and fixed expense ratio {_format_ratio(current_metrics.get('recent_fixed_expense_ratio'))}."
        ),
        _trend_sentence_en(current_metrics),
        (
            f"Among {_matched_count(outcome_summary):,} similar customers, the financial stress or delinquency path ratio is "
            f"{_format_ratio(risk_ratio)}."
        ),
        _staff_breakpoint_sentence_en(breakpoint_result),
        _consultation_timing_sentence_en(breakpoint_result),
        _staff_whatif_sentence_en(best),
        "The reduced debt-payment scenario does not reflect approval or contract-change feasibility.",
        "This analysis is based on synthetic data and is not an official credit assessment or product recommendation.",
    ]
    return "\n".join(sentences)


def _matched_count(outcome_summary: dict[str, Any]) -> int:
    if outcome_summary.get("matched_count") is not None:
        return int(outcome_summary["matched_count"])
    outcomes = outcome_summary.get("outcomes", {})
    return int(sum(int(values.get("count", 0)) for values in outcomes.values()))


def _risk_group_ratio(outcome_summary: dict[str, Any]) -> float | None:
    outcomes = outcome_summary.get("outcomes", {})
    if "stress" not in outcomes and "delinquent" not in outcomes:
        return None
    return float(outcomes.get("stress", {}).get("ratio", 0.0)) + float(
        outcomes.get("delinquent", {}).get("ratio", 0.0)
    )


def _outcome_distribution_sentence(outcome_summary: dict[str, Any]) -> str:
    outcomes = outcome_summary.get("outcomes", {})
    parts = []
    for key in ("healthy", "recovered", "stress", "delinquent"):
        if key not in outcomes:
            continue
        value = outcomes[key]
        parts.append(
            f"{label_status(key)} {int(value.get('count', 0)):,}명({_format_ratio(value.get('ratio'))})"
        )
    if not parts:
        return "결과 분포가 제공되지 않았습니다"
    return ", ".join(parts)


def _customer_breakpoint_sentence(breakpoint_result: dict[str, Any]) -> str:
    status = breakpoint_result.get("status", "not_found")
    if status == "found":
        return (
            f"위험 분기점은 {format_month_label(int(breakpoint_result['breakpoint_month']))}이며 "
            f"주요 차이는 {label_metric(breakpoint_result.get('primary_factor'))}에서 나타났고, "
            f"위험 경로 고객 평균은 {_format_breakpoint_metric(breakpoint_result, 'risk_group_mean')}, "
            f"위험 회피 고객 평균은 {_format_breakpoint_metric(breakpoint_result, 'avoidance_group_mean')}입니다."
        )
    if status == "insufficient_group_size":
        return BREAKPOINT_INSUFFICIENT_MESSAGE
    return BREAKPOINT_NOT_FOUND_MESSAGE


def _customer_breakpoint_sentence_en(breakpoint_result: dict[str, Any]) -> str:
    status = breakpoint_result.get("status", "not_found")
    if status == "found":
        return (
            f"The risk turning point is {format_month_label(int(breakpoint_result['breakpoint_month']), language='en')}, "
            f"and the largest difference appeared in {label_metric(breakpoint_result.get('primary_factor'), 'en')}; "
            f"the risk-path average was {_format_breakpoint_metric(breakpoint_result, 'risk_group_mean', 'en')} "
            f"and the risk-avoidance average was {_format_breakpoint_metric(breakpoint_result, 'avoidance_group_mean', 'en')}."
        )
    if status == "insufficient_group_size":
        return "There are not enough risk-path or risk-avoidance customers to compare a risk turning point."
    return "No clear divergence point was found between the risk path and risk-avoidance path in the current similar-customer group."


def _customer_timing_sentence(breakpoint_result: dict[str, Any]) -> str:
    if breakpoint_result.get("status") != "found":
        return "위험 분기점이 없거나 비교가 제한되어 남은 기간은 표시하지 않습니다."
    return (
        f"현재 12개월 차 기준으로 분기점까지 약 "
        f"{int(breakpoint_result.get('months_from_current'))}개월이 남아 있습니다."
    )


def _customer_timing_sentence_en(breakpoint_result: dict[str, Any]) -> str:
    if breakpoint_result.get("status") != "found":
        return "Because no clear turning point is available, time remaining is not shown."
    return (
        f"From the current point at month 12, about "
        f"{int(breakpoint_result.get('months_from_current'))} months remain until that point."
    )


def _customer_whatif_sentence(best: dict[str, Any] | None) -> str:
    if best is None:
        return "비교 가능한 대응 시나리오가 제공되지 않았습니다."
    return (
        f"가장 효과가 큰 대응안은 {_scenario_label(best)}이며 24개월 후 잔액은 "
        f"{_format_money(best.get('ending_cash_balance'))}, 기준 대비 개선액은 "
        f"{_format_money(best.get('improvement_vs_baseline'))}, "
        f"{_depletion_clause(best)}."
    )


def _customer_whatif_sentence_en(best: dict[str, Any] | None) -> str:
    if best is None:
        return "No comparable action-scenario result is available."
    return (
        f"The largest cash-flow improvement appears under {_scenario_label(best, 'en')}; "
        f"the 24-month ending balance is {_format_money(best.get('ending_cash_balance'), 'en')}, "
        f"the improvement versus no action is {_format_money(best.get('improvement_vs_baseline'), 'en')}, "
        f"and {_depletion_clause(best, 'en')}."
    )


def _staff_breakpoint_sentence(breakpoint_result: dict[str, Any]) -> str:
    status = breakpoint_result.get("status", "not_found")
    if status == "found":
        return (
            f"위험 분기점은 {format_month_label(int(breakpoint_result['breakpoint_month']))}이고 "
            f"주요 차이는 {label_metric(breakpoint_result.get('primary_factor'))}에서 나타났으며, "
            f"위험 경로 고객 평균은 {_format_breakpoint_metric(breakpoint_result, 'risk_group_mean')}, "
            f"위험 회피 고객 평균은 {_format_breakpoint_metric(breakpoint_result, 'avoidance_group_mean')}입니다."
        )
    if status == "insufficient_group_size":
        return BREAKPOINT_INSUFFICIENT_MESSAGE
    return BREAKPOINT_NOT_FOUND_MESSAGE


def _staff_breakpoint_sentence_en(breakpoint_result: dict[str, Any]) -> str:
    status = breakpoint_result.get("status", "not_found")
    if status == "found":
        return (
            f"The risk turning point is {format_month_label(int(breakpoint_result['breakpoint_month']), language='en')}, "
            f"with the largest difference in {label_metric(breakpoint_result.get('primary_factor'), 'en')}; "
            f"the risk-path average was {_format_breakpoint_metric(breakpoint_result, 'risk_group_mean', 'en')} "
            f"and the risk-avoidance average was {_format_breakpoint_metric(breakpoint_result, 'avoidance_group_mean', 'en')}."
        )
    if status == "insufficient_group_size":
        return "There are not enough risk-path or risk-avoidance customers to compare a risk turning point."
    return "No clear divergence point was found between the risk path and risk-avoidance path in the current similar-customer group."


def _consultation_timing_sentence(breakpoint_result: dict[str, Any]) -> str:
    if breakpoint_result.get("status") == "found":
        return (
            f"분기점까지 {breakpoint_result.get('months_from_current')}개월이 남은 것으로 표시되어 "
            "현재 시점의 현금흐름 점검 상담을 검토할 수 있습니다."
        )
    if breakpoint_result.get("status") == "insufficient_group_size":
        return "비교 고객 수가 충분하지 않아 분기점 기준 상담 시점은 표시하지 않습니다."
    return "뚜렷한 분기점이 없어 정기 점검 관점의 상담을 검토합니다."


def _consultation_timing_sentence_en(breakpoint_result: dict[str, Any]) -> str:
    if breakpoint_result.get("status") == "found":
        return (
            f"The displayed time remaining is {breakpoint_result.get('months_from_current')} months, "
            "so a cash-flow review can be considered at the current point."
        )
    if breakpoint_result.get("status") == "insufficient_group_size":
        return "Because the comparison group is limited, no turning-point-based engagement timing is shown."
    return "Without a clear turning point, regular monitoring is the appropriate engagement frame."


def _staff_whatif_sentence(best: dict[str, Any] | None) -> str:
    if best is None:
        return "검토 가능한 대응 시나리오 결과가 제공되지 않았습니다."
    return (
        f"현금흐름 개선 효과가 가장 큰 대응안은 {_scenario_label(best)}이며 "
        f"24개월 후 잔액은 {_format_money(best.get('ending_cash_balance'))}, "
        f"최소 잔액은 {_format_money(best.get('minimum_cash_balance'))}, "
        f"기준 대비 개선액은 {_format_money(best.get('improvement_vs_baseline'))}, "
        f"{_depletion_clause(best)}."
    )


def _staff_whatif_sentence_en(best: dict[str, Any] | None) -> str:
    if best is None:
        return "No action-scenario result is available for review."
    return (
        f"The largest cash-flow improvement appears under {_scenario_label(best, 'en')}; "
        f"the 24-month ending balance is {_format_money(best.get('ending_cash_balance'), 'en')}, "
        f"the minimum balance is {_format_money(best.get('minimum_cash_balance'), 'en')}, "
        f"the improvement versus no action is {_format_money(best.get('improvement_vs_baseline'), 'en')}, "
        f"and {_depletion_clause(best, 'en')}."
    )


def _trend_sentence(current_metrics: dict[str, Any]) -> str:
    fragments = []
    if current_metrics.get("savings_rate_slope_6m") is not None:
        fragments.append(f"최근 6개월 저축률 변화 {_format_ratio_point(current_metrics.get('savings_rate_slope_6m'))}")
    if current_metrics.get("balance_decline_run_6m") is not None:
        fragments.append(f"잔액 감소 지속 {int(current_metrics['balance_decline_run_6m'])}개월")
    if fragments:
        return "주요 추세는 " + ", ".join(fragments) + "입니다."
    return "주요 추세 지표는 제공되지 않았습니다."


def _trend_sentence_en(current_metrics: dict[str, Any]) -> str:
    fragments = []
    if current_metrics.get("savings_rate_slope_6m") is not None:
        fragments.append(f"recent 6-month savings-rate change {_format_ratio_point(current_metrics.get('savings_rate_slope_6m'))}")
    if current_metrics.get("balance_decline_run_6m") is not None:
        fragments.append(f"cash-balance decline persisted for {int(current_metrics['balance_decline_run_6m'])} months")
    if fragments:
        return "Key trend signals include " + ", ".join(fragments) + "."
    return "No key trend signal is available."


def _best_whatif_scenario(whatif_results: dict[str, Any]) -> dict[str, Any] | None:
    candidates = [
        scenario
        for scenario in whatif_results.get("scenarios", [])
        if scenario.get("scenario_name") != "baseline"
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda scenario: float(scenario.get("improvement_vs_baseline", 0.0)))


def _scenario_label(scenario: dict[str, Any], language: str = "ko") -> str:
    name = str(scenario.get("scenario_name", ""))
    if not name:
        return "Unavailable" if language == "en" else "제공되지 않음"
    return label_scenario(name, language)


def _depletion_sentence(scenario: dict[str, Any]) -> str:
    return f"{_depletion_clause(scenario)}."


def _depletion_clause(scenario: dict[str, Any], language: str = "ko") -> str:
    label = cash_depletion_label(scenario.get("cash_depletion_month"), language)
    if language == "en":
        if label == "Not observed":
            return "cash depletion is not observed"
        return f"cash depletion is shown {label.lower()}"
    if label == CASH_DEPLETION_NONE:
        return "현금 고갈 시점은 발생하지 않음으로 표시됩니다"
    return f"현금 고갈 시점은 {label}입니다"


def _format_money(value: Any, language: str = "ko") -> str:
    if value is None:
        return "Unavailable" if language == "en" else "제공되지 않음"
    return format_krw_compact(value, language=language)


def _format_ratio(value: Any) -> str:
    if value is None:
        return "제공되지 않음"
    return format_percent(value)


def _format_number(value: Any) -> str:
    if value is None:
        return "제공되지 않음"
    return f"{float(value):.3f}"


def _format_ratio_point(value: Any) -> str:
    if value is None:
        return "제공되지 않음"
    return format_percent(value).replace("%", "%p")


def _format_missing(value: Any) -> str:
    if value is None or value == "":
        return "제공되지 않음"
    return str(value)


def _format_status(value: Any, language: str = "ko") -> str:
    if value is None or value == "":
        return "Unavailable" if language == "en" else "제공되지 않음"
    return label_status(value, language)


def _format_breakpoint_metric(breakpoint_result: dict[str, Any], key: str, language: str = "ko") -> str:
    value = breakpoint_result.get(key)
    metric = breakpoint_result.get("primary_factor")
    if value is None or metric is None:
        return "Unavailable" if language == "en" else "제공되지 않음"
    return format_metric_value(value, str(metric), language=language)
