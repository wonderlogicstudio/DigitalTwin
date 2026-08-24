"""Tests for leakage-safe rolling as-of trajectory features."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from config import settings
from src.as_of_features import (
    AS_OF_REQUIRED_COLUMNS,
    InsufficientHistoryError,
    build_as_of_trajectory_features,
)
from src.data_generator import generate_dataset
from src.feature_engineering import build_trajectory_features
from src.models import GeneratorConfig


@pytest.fixture(scope="module")
def monthly_df() -> pd.DataFrame:
    _, generated_monthly = generate_dataset(GeneratorConfig(customer_count=80, random_seed=42))
    return generated_monthly


def test_as_of_month_12_has_exact_legacy_feature_parity(monthly_df: pd.DataFrame) -> None:
    legacy = build_trajectory_features(monthly_df)
    as_of = build_as_of_trajectory_features(monthly_df, 12)

    pd.testing.assert_frame_equal(as_of, legacy)


def test_future_mutation_and_deletion_do_not_change_month_12_features(
    monthly_df: pd.DataFrame,
) -> None:
    baseline = build_as_of_trajectory_features(monthly_df, 12)
    mutated = monthly_df.copy()
    future_mask = mutated["month"].between(13, settings.TOTAL_MONTHS)
    for column in AS_OF_REQUIRED_COLUMNS:
        if column not in {"customer_id", "month"}:
            mutated.loc[future_mask, column] = -999_999_999
    mutated.loc[future_mask, "persona"] = "overspending"
    mutated.loc[future_mask, "final_outcome"] = "delinquent"

    after_mutation = build_as_of_trajectory_features(mutated, 12)
    after_future_deletion = build_as_of_trajectory_features(
        monthly_df.loc[monthly_df["month"] <= 12].copy(),
        12,
    )

    pd.testing.assert_frame_equal(after_mutation, baseline)
    pd.testing.assert_frame_equal(after_future_deletion, baseline)


def test_as_of_builder_never_requires_persona_or_final_outcome(monthly_df: pd.DataFrame) -> None:
    baseline = build_as_of_trajectory_features(monthly_df, 12)
    no_label_or_persona = monthly_df.drop(columns=["persona", "final_outcome"])

    result = build_as_of_trajectory_features(no_label_or_persona, 12)

    pd.testing.assert_frame_equal(result, baseline)


def test_rolling_windows_at_month_18_are_explicit(monthly_df: pd.DataFrame) -> None:
    features = build_as_of_trajectory_features(monthly_df, 18)
    customer_id = str(features.iloc[0]["customer_id"])
    customer_months = monthly_df.loc[
        (monthly_df["customer_id"] == customer_id) & monthly_df["month"].between(7, 18)
    ].sort_values("month")
    feature_row = features.loc[features["customer_id"] == customer_id].iloc[0]
    baseline_3 = customer_months.loc[customer_months["month"].between(7, 9)]
    recent_3 = customer_months.loc[customer_months["month"].between(16, 18)]
    recent_6 = customer_months.loc[customer_months["month"].between(13, 18)]
    month_7 = customer_months.loc[customer_months["month"] == 7].iloc[0]
    month_18 = customer_months.loc[customer_months["month"] == 18].iloc[0]

    assert feature_row["avg_savings_rate_3m"] == pytest.approx(recent_3["savings_rate"].mean())
    assert feature_row["avg_dsr_3m"] == pytest.approx(recent_3["dsr"].mean())
    assert feature_row["expense_growth_12m"] == pytest.approx(
        (recent_3["total_expense"].mean() - baseline_3["total_expense"].mean())
        / baseline_3["total_expense"].mean()
    )
    assert feature_row["dsr_change_12m"] == pytest.approx(month_18["dsr"] - month_7["dsr"])
    assert feature_row["balance_change_ratio_12m"] == pytest.approx(
        (month_18["cash_balance"] - month_7["cash_balance"]) / month_7["cash_balance"]
        if month_7["cash_balance"] > 0
        else 0.0
    )
    assert feature_row["recent_negative_savings_months_6m"] == float(
        (recent_6["savings_amount"] < 0).sum()
    )
    assert feature_row["savings_rate_slope_12m"] == pytest.approx(
        np.polyfit(customer_months["month"], customer_months["savings_rate"], 1)[0]
    )


def test_data_after_any_as_of_month_does_not_change_features(monthly_df: pd.DataFrame) -> None:
    baseline = build_as_of_trajectory_features(monthly_df, 18)
    mutated = monthly_df.copy()
    after_as_of_mask = mutated["month"] > 18
    for column in AS_OF_REQUIRED_COLUMNS:
        if column not in {"customer_id", "month"}:
            mutated.loc[after_as_of_mask, column] = 777_777_777

    after_mutation = build_as_of_trajectory_features(mutated, 18)
    after_deletion = build_as_of_trajectory_features(
        monthly_df.loc[monthly_df["month"] <= 18].copy(),
        18,
    )

    pd.testing.assert_frame_equal(after_mutation, baseline)
    pd.testing.assert_frame_equal(after_deletion, baseline)


def test_insufficient_history_policy_is_explicit(monthly_df: pd.DataFrame) -> None:
    with pytest.raises(InsufficientHistoryError, match="at least 12 months"):
        build_as_of_trajectory_features(monthly_df, 11)

    missing_month = monthly_df.loc[
        ~((monthly_df["customer_id"] == "C000001") & (monthly_df["month"] == 8))
    ].copy()
    with pytest.raises(InsufficientHistoryError, match="complete trailing 12-month history"):
        build_as_of_trajectory_features(missing_month, 12)


def test_as_of_columns_order_and_dtypes_match_legacy_contract(monthly_df: pd.DataFrame) -> None:
    features = build_as_of_trajectory_features(monthly_df, 12)

    assert list(features.columns) == list(settings.TRAJECTORY_FEATURE_COLUMNS)
    assert features["customer_id"].dtype == object
    assert all(features[column].dtype == float for column in features.columns if column != "customer_id")
    numeric = features.drop(columns=["customer_id"])
    assert np.isfinite(numeric.to_numpy(dtype=float)).all()
