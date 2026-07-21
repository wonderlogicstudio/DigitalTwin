"""Breakpoint analysis between risk and avoidance matched-customer groups."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from config import settings


RISK_OUTCOMES = {"stress", "delinquent"}
AVOIDANCE_OUTCOMES = {"healthy", "recovered"}
BREAKPOINT_METRICS = (
    "savings_rate",
    "fixed_expense_ratio",
    "variable_expense_ratio",
    "dsr",
    "cash_balance_ratio",
    "loan_balance_ratio",
)
BREAKPOINT_RESULT_PATH = settings.DATA_PROCESSED_DIR / "breakpoint_result.json"


def find_breakpoint(
    matched_ids: list[str],
    monthly_df: pd.DataFrame,
    min_group_size: int = settings.BREAKPOINT_MIN_GROUP_SIZE,
    effect_threshold: float = settings.BREAKPOINT_EFFECT_THRESHOLD,
    persistence_months: int = settings.BREAKPOINT_PERSISTENCE_MONTHS,
) -> dict[str, Any]:
    """Find the earliest sustained SMD separation in months 13..36."""

    enriched_df = prepare_breakpoint_data(matched_ids, monthly_df)
    customer_outcomes = (
        enriched_df[["customer_id", "final_outcome"]]
        .drop_duplicates("customer_id")
        .set_index("customer_id")["final_outcome"]
    )
    risk_ids = customer_outcomes[customer_outcomes.isin(RISK_OUTCOMES)].index.tolist()
    avoidance_ids = customer_outcomes[customer_outcomes.isin(AVOIDANCE_OUTCOMES)].index.tolist()

    if len(risk_ids) < min_group_size or len(avoidance_ids) < min_group_size:
        return _empty_result(
            "insufficient_group_size",
            (
                f"Risk group size is {len(risk_ids)} and avoidance group size is "
                f"{len(avoidance_ids)}; both groups need at least {min_group_size} customers."
            ),
        )

    future_df = enriched_df[
        enriched_df["month"].between(settings.FUTURE_START_MONTH, settings.FUTURE_END_MONTH)
    ].copy()
    smd_df = calculate_monthly_smd(future_df, risk_ids, avoidance_ids, min_group_size)
    if smd_df.empty:
        return _empty_result("not_found", "No valid monthly comparison rows were available.")

    candidates = _find_persistent_candidates(smd_df, effect_threshold, persistence_months)
    if not candidates:
        return _empty_result(
            "not_found",
            "No metric showed a sustained standardized difference at the configured threshold.",
        )

    candidates_df = pd.DataFrame(candidates)
    earliest_month = int(candidates_df["month"].min())
    earliest_candidates = candidates_df[candidates_df["month"] == earliest_month].copy()
    selected = earliest_candidates.loc[
        earliest_candidates["standardized_difference"].abs().idxmax()
    ]
    secondary_factors = _build_secondary_factors(earliest_candidates, str(selected["metric"]))

    return {
        "status": "found",
        "breakpoint_month": earliest_month,
        "months_from_current": earliest_month - settings.OBSERVATION_END_MONTH,
        "primary_factor": str(selected["metric"]),
        "risk_group_mean": float(selected["risk_group_mean"]),
        "avoidance_group_mean": float(selected["avoidance_group_mean"]),
        "standardized_difference": float(selected["standardized_difference"]),
        "persistence_months": int(selected["persistence_months"]),
        "secondary_factors": secondary_factors,
        "interpretation": (
            "Risk and avoidance groups first show a sustained standardized difference "
            f"in {selected['metric']} at month {earliest_month}. This describes an "
            "association within the matched synthetic customers and is not a causal estimate."
        ),
    }


def prepare_breakpoint_data(matched_ids: list[str], monthly_df: pd.DataFrame) -> pd.DataFrame:
    """Filter matched customers and add balance-to-income ratio metrics."""

    required_columns = {
        "customer_id",
        "month",
        "income",
        "savings_rate",
        "fixed_expense_ratio",
        "variable_expense_ratio",
        "dsr",
        "cash_balance",
        "loan_balance",
        "final_outcome",
    }
    missing_columns = sorted(required_columns - set(monthly_df.columns))
    if missing_columns:
        raise ValueError(f"Missing required monthly columns: {missing_columns}")

    matched_set = set(matched_ids)
    filtered_df = monthly_df[monthly_df["customer_id"].isin(matched_set)].copy()
    baseline_income = (
        filtered_df[filtered_df["month"].between(10, settings.OBSERVATION_END_MONTH)]
        .groupby("customer_id")["income"]
        .mean()
    )
    filtered_df["baseline_income"] = filtered_df["customer_id"].map(baseline_income)
    denominator = filtered_df["baseline_income"].clip(lower=1)
    filtered_df["cash_balance_ratio"] = filtered_df["cash_balance"] / denominator
    filtered_df["loan_balance_ratio"] = filtered_df["loan_balance"] / denominator
    return filtered_df


def calculate_monthly_smd(
    future_df: pd.DataFrame,
    risk_ids: list[str],
    avoidance_ids: list[str],
    min_group_size: int = settings.BREAKPOINT_MIN_GROUP_SIZE,
) -> pd.DataFrame:
    """Calculate SMD rows for each month and breakpoint metric."""

    rows: list[dict[str, Any]] = []
    risk_set = set(risk_ids)
    avoidance_set = set(avoidance_ids)
    for month in range(settings.FUTURE_START_MONTH, settings.FUTURE_END_MONTH + 1):
        month_df = future_df[future_df["month"] == month]
        for metric in BREAKPOINT_METRICS:
            risk_values = _valid_metric_values(month_df, risk_set, metric)
            avoidance_values = _valid_metric_values(month_df, avoidance_set, metric)
            if len(risk_values) < min_group_size or len(avoidance_values) < min_group_size:
                continue
            pooled_std = calculate_pooled_std(risk_values, avoidance_values)
            if pooled_std <= 1e-12 or not np.isfinite(pooled_std):
                continue
            risk_mean = float(risk_values.mean())
            avoidance_mean = float(avoidance_values.mean())
            rows.append(
                {
                    "month": month,
                    "metric": metric,
                    "risk_group_mean": risk_mean,
                    "avoidance_group_mean": avoidance_mean,
                    "standardized_difference": (risk_mean - avoidance_mean) / pooled_std,
                    "risk_count": int(len(risk_values)),
                    "avoidance_count": int(len(avoidance_values)),
                }
            )
    return pd.DataFrame(rows)


def calculate_pooled_std(risk_values: pd.Series, avoidance_values: pd.Series) -> float:
    """Calculate pooled sample standard deviation for two groups."""

    risk_count = len(risk_values)
    avoidance_count = len(avoidance_values)
    if risk_count < 2 or avoidance_count < 2:
        return 0.0
    numerator = (
        (risk_count - 1) * float(risk_values.var(ddof=1))
        + (avoidance_count - 1) * float(avoidance_values.var(ddof=1))
    )
    denominator = risk_count + avoidance_count - 2
    if denominator <= 0:
        return 0.0
    return float(np.sqrt(numerator / denominator))


def save_breakpoint_result(
    result: dict[str, Any],
    output_path: Path = BREAKPOINT_RESULT_PATH,
) -> Path:
    """Save a breakpoint result dictionary as UTF-8 JSON."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def _valid_metric_values(month_df: pd.DataFrame, customer_ids: set[str], metric: str) -> pd.Series:
    values = month_df.loc[month_df["customer_id"].isin(customer_ids), metric]
    values = pd.to_numeric(values, errors="coerce")
    return values[np.isfinite(values)]


def _find_persistent_candidates(
    smd_df: pd.DataFrame,
    effect_threshold: float,
    persistence_months: int,
) -> list[dict[str, Any]]:
    passing = smd_df[smd_df["standardized_difference"].abs() >= effect_threshold].copy()
    candidates: list[dict[str, Any]] = []
    for metric, metric_df in passing.groupby("metric"):
        available_months = set(metric_df["month"].astype(int))
        for _, row in metric_df.sort_values("month").iterrows():
            month = int(row["month"])
            run_length = 0
            while month + run_length in available_months:
                run_length += 1
            if run_length >= persistence_months:
                candidate = row.to_dict()
                candidate["metric"] = metric
                candidate["persistence_months"] = run_length
                candidates.append(candidate)
    return candidates


def _build_secondary_factors(candidates_df: pd.DataFrame, primary_metric: str) -> list[dict[str, Any]]:
    secondary_df = candidates_df[candidates_df["metric"] != primary_metric].copy()
    if secondary_df.empty:
        return []
    secondary_df["abs_smd"] = secondary_df["standardized_difference"].abs()
    secondary_df = secondary_df.sort_values("abs_smd", ascending=False)
    return [
        {
            "factor": str(row["metric"]),
            "risk_group_mean": float(row["risk_group_mean"]),
            "avoidance_group_mean": float(row["avoidance_group_mean"]),
            "standardized_difference": float(row["standardized_difference"]),
            "persistence_months": int(row["persistence_months"]),
        }
        for _, row in secondary_df.iterrows()
    ]


def _empty_result(status: str, interpretation: str) -> dict[str, Any]:
    return {
        "status": status,
        "breakpoint_month": None,
        "months_from_current": None,
        "primary_factor": None,
        "risk_group_mean": None,
        "avoidance_group_mean": None,
        "standardized_difference": None,
        "persistence_months": 0,
        "secondary_factors": [],
        "interpretation": interpretation,
    }
