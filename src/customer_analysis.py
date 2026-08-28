"""Customer-level Financial Path Twin analysis service boundary."""

from __future__ import annotations

from typing import Any, Callable

import pandas as pd

from config import settings
from src.breakpoint_analyzer import (
    AVOIDANCE_OUTCOMES,
    RISK_OUTCOMES,
    calculate_monthly_smd,
    find_breakpoint,
    prepare_breakpoint_data,
)
from src.demo_selector import build_final_outcome_lookup, summarize_matched_outcomes
from src.matcher import TrajectoryMatcher
from src.whatif_simulator import build_whatif_results


def add_balance_ratios(monthly_df: pd.DataFrame, customer_ids: list[str]) -> pd.DataFrame:
    """Filter rows and add balance-to-recent-income ratios for consumers."""

    required_columns = ("customer_id", "month", "income", "cash_balance", "loan_balance")
    missing_columns = [column for column in required_columns if column not in monthly_df.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns in monthly_df: {missing_columns}")

    filtered_df = monthly_df[monthly_df["customer_id"].astype(str).isin(set(customer_ids))].copy()
    baseline_income = (
        filtered_df[filtered_df["month"].between(10, settings.OBSERVATION_END_MONTH)]
        .groupby("customer_id")["income"]
        .mean()
    )
    denominator = filtered_df["customer_id"].map(baseline_income).fillna(1).clip(lower=1)
    filtered_df["cash_balance_ratio"] = filtered_df["cash_balance"] / denominator
    filtered_df["loan_balance_ratio"] = filtered_df["loan_balance"] / denominator
    return filtered_df


def build_breakpoint_comparison(matched_ids: list[str], monthly_df: pd.DataFrame) -> pd.DataFrame:
    """Build existing monthly SMD comparison rows for matched groups."""

    enriched_df = prepare_breakpoint_data(matched_ids, monthly_df)
    customer_outcomes = (
        enriched_df[["customer_id", "final_outcome"]]
        .drop_duplicates("customer_id")
        .set_index("customer_id")["final_outcome"]
    )
    risk_ids = customer_outcomes[customer_outcomes.isin(RISK_OUTCOMES)].index.tolist()
    avoidance_ids = customer_outcomes[customer_outcomes.isin(AVOIDANCE_OUTCOMES)].index.tolist()
    future_df = enriched_df[
        enriched_df["month"].between(settings.FUTURE_START_MONTH, settings.FUTURE_END_MONTH)
    ]
    return calculate_monthly_smd(future_df, risk_ids, avoidance_ids)


def run_customer_analysis(
    customer_id: str,
    monthly_df: pd.DataFrame,
    features_df: pd.DataFrame,
    matcher: TrajectoryMatcher,
    top_k: int = settings.TOP_K_MATCHES,
) -> dict[str, Any]:
    """Run the existing customer analysis composition outside any UI module."""

    return run_customer_analysis_with_dependencies(
        customer_id,
        monthly_df,
        features_df,
        matcher,
        top_k=top_k,
        outcome_lookup_builder=build_final_outcome_lookup,
        outcome_summary_builder=summarize_matched_outcomes,
        breakpoint_finder=find_breakpoint,
        breakpoint_comparison_builder=build_breakpoint_comparison,
        whatif_builder=build_whatif_results,
    )


def run_customer_analysis_with_dependencies(
    customer_id: str,
    monthly_df: pd.DataFrame,
    features_df: pd.DataFrame,
    matcher: TrajectoryMatcher,
    *,
    top_k: int,
    outcome_lookup_builder: Callable[[pd.DataFrame], Any],
    outcome_summary_builder: Callable[[str, list[str], pd.DataFrame, Any], dict[str, Any]],
    breakpoint_finder: Callable[[list[str], pd.DataFrame], dict[str, Any]],
    breakpoint_comparison_builder: Callable[[list[str], pd.DataFrame], pd.DataFrame],
    whatif_builder: Callable[[str, pd.DataFrame], dict[str, Any]],
) -> dict[str, Any]:
    """Execute the fixed composition with injectable operations for compatibility."""

    normalized_customer_id = str(customer_id)
    if normalized_customer_id not in set(features_df["customer_id"].astype(str)):
        raise ValueError(f"Unknown customer_id: {customer_id}")

    matches = matcher.match(normalized_customer_id, top_k=top_k)
    matched_ids = matches["matched_customer_id"].astype(str).tolist()
    outcome_lookup = outcome_lookup_builder(monthly_df)
    outcome_summary = outcome_summary_builder(
        normalized_customer_id,
        matched_ids,
        monthly_df,
        outcome_lookup,
    )
    errors: dict[str, str] = {}
    try:
        breakpoint_result = breakpoint_finder(matched_ids, monthly_df)
    except Exception as exc:  # noqa: BLE001
        errors["breakpoint"] = str(exc)
        breakpoint_result = _error_breakpoint_result(str(exc))
    try:
        comparison_df = breakpoint_comparison_builder(matched_ids, monthly_df)
    except Exception as exc:  # noqa: BLE001
        errors["breakpoint_comparison"] = str(exc)
        comparison_df = pd.DataFrame()
    try:
        whatif_results = whatif_builder(normalized_customer_id, monthly_df)
    except Exception as exc:  # noqa: BLE001
        errors["whatif"] = str(exc)
        whatif_results = {
            "target_customer_id": normalized_customer_id,
            "simulation_months": 0,
            "scenarios": [],
        }

    return {
        "customer_id": normalized_customer_id,
        "matches": matches,
        "matched_ids": matched_ids,
        "outcome_summary": outcome_summary,
        "breakpoint_result": breakpoint_result,
        "whatif_results": whatif_results,
        "breakpoint_comparison": comparison_df,
        "errors": errors,
    }


def _error_breakpoint_result(message: str) -> dict[str, Any]:
    return {
        "status": "error",
        "breakpoint_month": None,
        "months_from_current": None,
        "primary_factor": None,
        "risk_group_mean": None,
        "avoidance_group_mean": None,
        "standardized_difference": None,
        "persistence_months": 0,
        "secondary_factors": [],
        "interpretation": message,
    }
