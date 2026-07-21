"""Display-only formatting helpers for Korean financial UI labels.

These helpers never mutate source data or change stored units. Amounts remain
KRW in the data layer, ratios remain 0..1 floats, and months remain integers.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any


KRW_TEN_THOUSAND = 10_000
KRW_HUNDRED_MILLION = 100_000_000
KRW_MILLION = 1_000_000
KRW_BILLION = 1_000_000_000
KRW_AXIS_UNIT_THRESHOLD = KRW_HUNDRED_MILLION

MONEY_METRICS = {
    "income",
    "fixed_expense",
    "variable_expense",
    "debt_payment",
    "event_expense",
    "total_expense",
    "savings_amount",
    "cash_balance",
    "loan_balance",
    "ending_cash_balance",
    "minimum_cash_balance",
    "improvement_vs_baseline",
    "total_saved_expense",
}
RATIO_METRICS = {
    "savings_rate",
    "dsr",
    "fixed_expense_ratio",
    "variable_expense_ratio",
    "income_change_rate",
    "expense_change_rate",
    "balance_change_rate",
    "recent_savings_rate",
    "recent_dsr",
    "recent_fixed_expense_ratio",
    "risk_group_ratio",
    "healthy_ratio",
    "recovered_ratio",
    "stress_ratio",
    "delinquent_ratio",
    "average_savings_rate",
}
MULTIPLE_METRICS = {
    "cash_balance_ratio",
    "loan_balance_ratio",
    "debt_to_income_ratio",
    "emergency_months",
}


def format_krw_compact(value: float | int | None, language: str = "ko") -> str:
    """Format a KRW amount with compact Korean units for KPI-style display."""

    amount = _coerce_number(value)
    if amount is None:
        return "-"
    if language == "en":
        return _format_krw_compact_en(amount)
    rounded = int(round(amount))
    if rounded == 0:
        return "0원"

    sign = "-" if rounded < 0 else ""
    absolute = abs(rounded)
    if absolute < KRW_TEN_THOUSAND:
        return f"{sign}{absolute:,}원"
    if absolute < KRW_HUNDRED_MILLION:
        ten_thousand = int(round(absolute / KRW_TEN_THOUSAND))
        return f"{sign}{ten_thousand:,}만원"

    hundred_million = absolute // KRW_HUNDRED_MILLION
    remainder = absolute % KRW_HUNDRED_MILLION
    ten_thousand = int(round(remainder / KRW_TEN_THOUSAND))
    if ten_thousand == 10_000:
        hundred_million += 1
        ten_thousand = 0
    if ten_thousand:
        return f"{sign}{hundred_million:,}억 {ten_thousand:,}만원"
    return f"{sign}{hundred_million:,}억원"


def format_currency(value: float | int | None, language: str = "ko") -> str:
    """Format a KRW amount for the selected UI language."""

    return format_krw_compact(value, language=language)


def format_krw_full(value: float | int | None, language: str = "ko") -> str:
    """Format a KRW amount in full won units for hover details."""

    amount = _coerce_number(value)
    if amount is None:
        return "-"
    if language == "en":
        return f"KRW {int(round(amount)):,}"
    return f"{int(round(amount)):,}원"


def to_ten_thousand_won(value: float | int | None) -> float:
    """Convert KRW to ten-thousand-won units for display tables."""

    amount = _coerce_number(value)
    if amount is None:
        return math.nan
    return round(amount / KRW_TEN_THOUSAND, 1)


def to_million_krw(value: float | int | None) -> float:
    """Convert KRW to KRW million units for English display tables."""

    amount = _coerce_number(value)
    if amount is None:
        return math.nan
    return round(amount / KRW_MILLION, 1)


def select_krw_unit(values: Any) -> str:
    """Select a common graph unit from the largest absolute KRW value."""

    max_abs = 0.0
    for value in _iter_values(values):
        amount = _coerce_number(value)
        if amount is not None:
            max_abs = max(max_abs, abs(amount))
    return "억원" if max_abs >= KRW_AXIS_UNIT_THRESHOLD else "만원"


def select_currency_unit(values: Any, language: str = "ko") -> str:
    """Select a common graph unit for the selected UI language."""

    if language != "en":
        return select_krw_unit(values)
    max_abs = 0.0
    for value in _iter_values(values):
        amount = _coerce_number(value)
        if amount is not None:
            max_abs = max(max_abs, abs(amount))
    return "KRW billion" if max_abs >= KRW_BILLION else "KRW million"


def scale_krw_value(value: float | int | None, unit: str) -> float:
    """Scale a KRW value to the selected display unit."""

    amount = _coerce_number(value)
    if amount is None:
        return math.nan
    if unit == "억원":
        return amount / KRW_HUNDRED_MILLION
    return amount / KRW_TEN_THOUSAND


def scale_currency_value(value: float | int | None, unit: str, language: str = "ko") -> float:
    """Scale a KRW value to a selected language-aware display unit."""

    amount = _coerce_number(value)
    if amount is None:
        return math.nan
    if language == "en":
        if unit == "KRW billion":
            return amount / KRW_BILLION
        return amount / KRW_MILLION
    return scale_krw_value(amount, unit)


def format_percent(value: float | int | None, decimals: int = 1) -> str:
    """Format a ratio stored as 0..1 into a percent string."""

    ratio = _coerce_number(value)
    if ratio is None:
        return "-"
    return f"{ratio * 100:.{decimals}f}%"


def format_month_label(month: int, current_month: int = 12, language: str = "ko") -> str:
    """Format a technical month number relative to the current month."""

    month_int = int(month)
    current_int = int(current_month)
    if language == "en":
        if month_int == current_int:
            return f"Current · Month {month_int}"
        if month_int > current_int:
            return f"In {month_int - current_int} months · Month {month_int}"
        return f"{current_int - month_int} months ago · Month {month_int}"
    if month_int == current_int:
        return f"현재 · {month_int}개월 차"
    if month_int > current_int:
        return f"{month_int - current_int}개월 후 · {month_int}개월 차"
    return f"{current_int - month_int}개월 전 · {month_int}개월 차"


def format_metric_value(value: Any, metric: str, language: str = "ko") -> str:
    """Format a value according to a known metric's display unit."""

    if metric in MONEY_METRICS:
        return format_krw_compact(value, language=language)
    if metric in RATIO_METRICS:
        return format_percent(value)
    if metric in MULTIPLE_METRICS:
        number = _coerce_number(value)
        suffix = "x" if language == "en" else "배"
        return "-" if number is None else f"{number:.2f}{suffix}"
    number = _coerce_number(value)
    return "-" if number is None else f"{number:,.3f}"


def _format_krw_compact_en(amount: float) -> str:
    rounded = int(round(amount))
    if rounded == 0:
        return "KRW 0"
    sign = "-" if rounded < 0 else ""
    absolute = abs(float(rounded))
    if absolute < KRW_MILLION:
        return f"{sign}KRW {absolute / 1_000:.0f}K"
    return f"{sign}KRW {absolute / KRW_MILLION:.1f}M"


def _coerce_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _iter_values(values: Any) -> Iterable[Any]:
    if isinstance(values, (str, bytes)):
        return (values,)
    to_numpy = getattr(values, "to_numpy", None)
    if callable(to_numpy):
        try:
            array_values = to_numpy()
        except (TypeError, ValueError):
            pass
        else:
            to_list = getattr(array_values, "tolist", None)
            if callable(to_list):
                return _flatten(to_list())
            return _flatten(array_values)
    if isinstance(values, Iterable):
        return _flatten(values)
    return (values,)


def _flatten(values: Iterable[Any]) -> Iterable[Any]:
    for value in values:
        if isinstance(value, (str, bytes)):
            yield value
        elif isinstance(value, Iterable):
            yield from _flatten(value)
        else:
            yield value
