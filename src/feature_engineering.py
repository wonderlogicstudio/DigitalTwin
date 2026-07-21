"""Trajectory feature generation from observation-window monthly data."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from config import settings


def build_trajectory_features(
    monthly_df: pd.DataFrame,
    observation_end_month: int = settings.OBSERVATION_END_MONTH,
) -> pd.DataFrame:
    """Build one trajectory feature row per customer using months 1..12 only."""

    observation_df = monthly_df.loc[monthly_df["month"] <= observation_end_month].copy()
    observation_df = observation_df.sort_values(["customer_id", "month"])
    feature_rows = [
        _build_customer_features(customer_id, group)
        for customer_id, group in observation_df.groupby("customer_id", sort=True)
    ]
    features_df = pd.DataFrame(feature_rows, columns=settings.TRAJECTORY_FEATURE_COLUMNS)
    numeric_columns = [column for column in features_df.columns if column != "customer_id"]
    features_df[numeric_columns] = features_df[numeric_columns].astype(float)
    return features_df


def save_trajectory_features(
    features_df: pd.DataFrame,
    output_path: Path = settings.TRAJECTORY_FEATURES_PATH,
) -> Path:
    """Save trajectory features to the configured processed CSV path."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    features_df.to_csv(output_path, index=False, encoding="utf-8")
    return output_path


def calculate_slope(months: pd.Series, values: pd.Series) -> float:
    """Calculate a linear slope with numpy.polyfit."""

    if len(months) < 2:
        return 0.0
    return float(np.polyfit(months.to_numpy(dtype=float), values.to_numpy(dtype=float), 1)[0])


def calculate_cv(values: pd.Series) -> float:
    """Calculate coefficient of variation with zero-mean protection."""

    mean = float(values.mean())
    if abs(mean) < 1e-9:
        return 0.0
    return float(values.std(ddof=0) / abs(mean))


def max_consecutive_declines(values: pd.Series) -> int:
    """Return the longest run of month-over-month declines."""

    max_run = 0
    current_run = 0
    previous_value: float | None = None
    for value in values.to_numpy(dtype=float):
        if previous_value is not None and value < previous_value:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 0
        previous_value = value
    return max_run


def count_large_expense_months(total_expense: pd.Series) -> int:
    """Count months with total expense above mean + 1.5 standard deviations."""

    threshold = float(total_expense.mean() + 1.5 * total_expense.std(ddof=0))
    return int((total_expense > threshold).sum())


def _build_customer_features(customer_id: str, group: pd.DataFrame) -> dict[str, object]:
    group = group.sort_values("month")
    recent_3 = group.loc[group["month"].between(10, 12)]
    recent_6 = group.loc[group["month"].between(7, 12)]
    early_3 = group.loc[group["month"].between(1, 3)]

    month_1 = group.loc[group["month"] == 1].iloc[0]
    month_12 = group.loc[group["month"] == 12].iloc[0]
    early_expense_mean = float(early_3["total_expense"].mean())
    recent_expense_mean = float(recent_3["total_expense"].mean())
    expense_growth = _change_ratio(recent_expense_mean, early_expense_mean)

    return {
        "customer_id": customer_id,
        "avg_savings_rate_3m": float(recent_3["savings_rate"].mean()),
        "avg_dsr_3m": float(recent_3["dsr"].mean()),
        "avg_fixed_expense_ratio_3m": float(recent_3["fixed_expense_ratio"].mean()),
        "savings_rate_slope_12m": calculate_slope(group["month"], group["savings_rate"]),
        "expense_growth_12m": expense_growth,
        "dsr_change_12m": float(month_12["dsr"] - month_1["dsr"]),
        "balance_change_ratio_12m": _change_ratio(
            float(month_12["cash_balance"]),
            float(month_1["cash_balance"]),
        ),
        "income_cv_12m": calculate_cv(group["income"]),
        "expense_cv_12m": calculate_cv(group["total_expense"]),
        "max_consecutive_balance_decline_12m": float(max_consecutive_declines(group["cash_balance"])),
        "recent_negative_savings_months_6m": float((recent_6["savings_amount"] < 0).sum()),
        "recent_large_expense_count_12m": float(count_large_expense_months(group["total_expense"])),
    }


def _change_ratio(current: float, previous: float) -> float:
    if previous > 0:
        return float((current - previous) / previous)
    return 0.0
