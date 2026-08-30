"""Shared Korean display labels for UI, charts, and brief templates."""

from __future__ import annotations

from typing import Any, Mapping

from src.copy import TERM_EXPLANATIONS
from src.i18n import t


STATUS_LABELS = {
    "healthy": "안정",
    "recovered": "회복",
    "watch": "주의",
    "stress": "재무 스트레스",
    "delinquent": "연체",
}

PERSONA_LABELS = {
    "stable": "안정형",
    "gradual_deterioration": "점진적 악화형",
    "event_shock": "이벤트 충격형",
    "recovery": "회복형",
    "overspending": "과소비형",
    "self_employed": "사업 소득 변동형(합성)",
    "asset_resilient": "여유자금 보유형(합성)",
    "financially_constrained": "재무 여력 제약형(합성)",
}

METRIC_LABELS = {
    "income": "월 소득",
    "fixed_expense": "월 고정지출",
    "variable_expense": "월 변동지출",
    "debt_payment": "월 대출상환액",
    "event_expense": "이벤트 지출",
    "total_expense": "월 총지출",
    "savings_amount": "월 저축액",
    "cash_balance": "현금 잔액",
    "savings_rate": "저축률",
    "dsr": "DSR",
    "fixed_expense_ratio": "고정지출 비중",
    "variable_expense_ratio": "변동지출 비중",
    "loan_balance": "대출 잔액",
    "cash_balance_ratio": "소득 대비 현금 보유 수준",
    "loan_balance_ratio": "소득 대비 대출 수준",
    "debt_to_income_ratio": "소득 대비 대출 수준",
    "emergency_months": "비상자금 지속 가능 기간",
    "avg_savings_rate_3m": "최근 3개월 평균 저축률",
    "avg_dsr_3m": "최근 3개월 평균 DSR",
    "avg_fixed_expense_ratio_3m": "최근 3개월 평균 고정지출 비중",
    "savings_rate_slope_12m": "저축률 추세",
    "expense_growth_12m": "총지출 증가율",
    "dsr_change_12m": "DSR 변화",
    "balance_change_ratio_12m": "현금 잔액 변화율",
    "income_cv_12m": "월 소득 변동성",
    "expense_cv_12m": "월 지출 변동성",
    "max_consecutive_balance_decline_12m": "최장 연속 잔액 감소",
}

SCENARIO_LABELS = {
    "baseline": "아무 조치 없음",
    "variable_expense_cut_15": "변동지출 15% 절감",
    "fixed_expense_cut_300k": "고정지출 월 30만원 절감",
    "debt_payment_cut_20": "대출상환액 20% 감소",
}

TERM_HELP_TEXT = {
    "dsr": TERM_EXPLANATIONS["dsr"],
    "savings_rate": TERM_EXPLANATIONS["savings_rate"],
    "fixed_expense_ratio": TERM_EXPLANATIONS["fixed_expense_ratio"],
    "stress": TERM_EXPLANATIONS["stress"],
    "breakpoint": TERM_EXPLANATIONS["breakpoint"],
}

STATUS_COLORS = {
    "healthy": "#008a78",
    "recovered": "#2f855a",
    "watch": "#b7791f",
    "stress": "#c43d3d",
    "delinquent": "#7a3e8e",
}

OUTCOME_ORDER = ("healthy", "recovered", "stress", "delinquent")


def safe_label(mapping: Mapping[str, str], value: Any) -> str:
    """Return a display label with a safe fallback for unknown values."""

    if value is None or value == "":
        return "-"
    key = str(value)
    return mapping.get(key, key)


def _translated_label(prefix: str, mapping: Mapping[str, str], value: Any, language: str) -> str:
    if value is None or value == "":
        return "-"
    key = str(value)
    if key not in mapping:
        return key
    return t(f"{prefix}.{key}", language)


def label_status(value: Any, language: str = "ko") -> str:
    return _translated_label("status", STATUS_LABELS, value, language)


def label_persona(value: Any, language: str = "ko") -> str:
    return _translated_label("persona", PERSONA_LABELS, value, language)


def label_metric(value: Any, language: str = "ko") -> str:
    return _translated_label("metric", METRIC_LABELS, value, language)


def label_scenario(value: Any, language: str = "ko") -> str:
    return _translated_label("scenario", SCENARIO_LABELS, value, language)


def term_help_text(term: str, language: str = "ko") -> str:
    """Return a short help text for a financial term."""

    if term not in TERM_HELP_TEXT:
        return "-"
    return t(f"term.{term}", language)
