"""Leakage-safe rolling trajectory features at an explicit as-of month.

This module is separate from the legacy month-12 feature builder.  Every
feature is calculated from a complete trailing 12-calendar-month window ending
at ``as_of_month``.  No target columns from later months, ``persona``, or
``final_outcome`` are selected or merged.
"""

from __future__ import annotations

import pandas as pd

from config import settings
from src.feature_engineering import (
    calculate_cv,
    calculate_slope,
    count_large_expense_months,
    max_consecutive_declines,
)


AS_OF_HISTORY_MONTHS = 12
AS_OF_BASELINE_MONTHS = 3
AS_OF_RECENT_3_MONTHS = 3
AS_OF_RECENT_6_MONTHS = 6
AS_OF_REQUIRED_COLUMNS = (
    "customer_id",
    "month",
    "income",
    "total_expense",
    "savings_amount",
    "savings_rate",
    "fixed_expense_ratio",
    "dsr",
    "cash_balance",
)


class InsufficientHistoryError(ValueError):
    """Raised when a customer lacks the complete rolling feature window."""


def build_as_of_trajectory_features(
    monthly_df: pd.DataFrame,
    as_of_month: int,
) -> pd.DataFrame:
    """Build one leakage-safe trajectory feature row per observed customer.

    Definitions within the inclusive trailing 12-month window
    ``[as_of_month - 11, as_of_month]`` are:

    - ``baseline_3``: the first three calendar months in the window;
    - ``recent_3``: the final three calendar months in the window;
    - ``recent_6``: the final six calendar months in the window;
    - slopes, CVs, expense outlier count, and consecutive balance declines:
      all twelve calendar months;
    - DSR and balance changes: window start to window end.

    A complete 12-calendar-month history is required for every returned
    customer.  This explicit policy avoids silently mixing shorter histories
    with the legacy 12-month feature contract.  At as-of month 12, the window
    and all subwindows exactly match ``build_trajectory_features``.
    """

    normalized_as_of_month = _validate_as_of_month(as_of_month)
    _validate_required_columns(monthly_df)
    window_start_month = normalized_as_of_month - AS_OF_HISTORY_MONTHS + 1

    observed_df = monthly_df.loc[
        monthly_df["month"] <= normalized_as_of_month,
        AS_OF_REQUIRED_COLUMNS,
    ].copy()
    window_df = observed_df.loc[
        observed_df["month"].between(window_start_month, normalized_as_of_month)
    ].copy()
    window_df["customer_id"] = window_df["customer_id"].astype(str)
    window_df = window_df.sort_values(["customer_id", "month"])
    _validate_complete_history(window_df, window_start_month, normalized_as_of_month)

    feature_rows = [
        _build_as_of_customer_features(customer_id, group, normalized_as_of_month, window_start_month)
        for customer_id, group in window_df.groupby("customer_id", sort=True)
    ]
    features_df = pd.DataFrame(feature_rows, columns=settings.TRAJECTORY_FEATURE_COLUMNS)
    numeric_columns = [column for column in features_df.columns if column != "customer_id"]
    features_df[numeric_columns] = features_df[numeric_columns].astype(float)
    return features_df


def _validate_as_of_month(as_of_month: int) -> int:
    if isinstance(as_of_month, bool) or not isinstance(as_of_month, int):
        raise TypeError("as_of_month must be an integer")
    if as_of_month < AS_OF_HISTORY_MONTHS:
        raise InsufficientHistoryError(
            f"as_of_month={as_of_month} has insufficient history; at least "
            f"{AS_OF_HISTORY_MONTHS} months are required"
        )
    if as_of_month > settings.TOTAL_MONTHS:
        raise ValueError(
            f"as_of_month must not exceed configured total months ({settings.TOTAL_MONTHS})"
        )
    return as_of_month


def _validate_required_columns(monthly_df: pd.DataFrame) -> None:
    missing_columns = sorted(set(AS_OF_REQUIRED_COLUMNS) - set(monthly_df.columns))
    if missing_columns:
        raise ValueError(f"monthly_df is missing required as-of columns: {missing_columns}")


def _validate_complete_history(
    window_df: pd.DataFrame,
    window_start_month: int,
    as_of_month: int,
) -> None:
    if window_df.empty:
        raise InsufficientHistoryError("no customer rows are available in the requested as-of window")
    duplicate_rows = window_df.duplicated(["customer_id", "month"])
    if duplicate_rows.any():
        raise ValueError("as-of feature input has duplicate customer_id and month rows")

    expected_months = set(range(window_start_month, as_of_month + 1))
    incomplete: dict[str, list[int]] = {}
    for customer_id, group in window_df.groupby("customer_id", sort=True):
        present_months = set(pd.to_numeric(group["month"], errors="raise").astype(int))
        missing_months = sorted(expected_months - present_months)
        if missing_months:
            incomplete[str(customer_id)] = missing_months
    if incomplete:
        sample = list(incomplete.items())[:5]
        raise InsufficientHistoryError(
            "complete trailing 12-month history is required; "
            f"window={window_start_month}-{as_of_month}; missing={sample}"
        )


def _build_as_of_customer_features(
    customer_id: str,
    group: pd.DataFrame,
    as_of_month: int,
    window_start_month: int,
) -> dict[str, object]:
    group = group.sort_values("month")
    baseline_3 = group.loc[group["month"].between(window_start_month, window_start_month + 2)]
    recent_3 = group.loc[group["month"].between(as_of_month - 2, as_of_month)]
    recent_6 = group.loc[group["month"].between(as_of_month - 5, as_of_month)]
    window_start = group.loc[group["month"] == window_start_month].iloc[0]
    window_end = group.loc[group["month"] == as_of_month].iloc[0]

    baseline_expense_mean = float(baseline_3["total_expense"].mean())
    recent_expense_mean = float(recent_3["total_expense"].mean())
    return {
        "customer_id": str(customer_id),
        "avg_savings_rate_3m": float(recent_3["savings_rate"].mean()),
        "avg_dsr_3m": float(recent_3["dsr"].mean()),
        "avg_fixed_expense_ratio_3m": float(recent_3["fixed_expense_ratio"].mean()),
        "savings_rate_slope_12m": calculate_slope(group["month"], group["savings_rate"]),
        "expense_growth_12m": _change_ratio(recent_expense_mean, baseline_expense_mean),
        "dsr_change_12m": float(window_end["dsr"] - window_start["dsr"]),
        "balance_change_ratio_12m": _change_ratio(
            float(window_end["cash_balance"]),
            float(window_start["cash_balance"]),
        ),
        "income_cv_12m": calculate_cv(group["income"]),
        "expense_cv_12m": calculate_cv(group["total_expense"]),
        "max_consecutive_balance_decline_12m": float(
            max_consecutive_declines(group["cash_balance"])
        ),
        "recent_negative_savings_months_6m": float((recent_6["savings_amount"] < 0).sum()),
        "recent_large_expense_count_12m": float(count_large_expense_months(group["total_expense"])),
    }


def _change_ratio(current: float, previous: float) -> float:
    if previous > 0:
        return float((current - previous) / previous)
    return 0.0
