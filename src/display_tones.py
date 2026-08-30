"""Shared display-only tone rules for already available current metrics."""

from __future__ import annotations

from typing import Any


def classify_current_metric_tone(metric: str, value: Any) -> str:
    """Return a presentation tone from documented current-metric bands.

    This is deliberately a display rule, not a risk score or a prediction.  It
    accepts a value that has already been calculated and stored elsewhere.
    """

    number = _safe_float(value)
    if number is None:
        return "neutral"
    if metric == "cash_balance":
        return "danger" if number < 0 else "neutral"
    if metric == "dsr":
        if number >= 0.45:
            return "danger"
        if number >= 0.35:
            return "watch"
        return "stable"
    if metric == "savings_rate":
        return "watch" if number < 0.05 else "neutral"
    if metric == "fixed_expense_ratio":
        if number >= 0.55:
            return "danger"
        if number >= 0.45:
            return "watch"
    return "neutral"


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
