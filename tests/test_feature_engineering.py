import numpy as np
import pandas as pd
import pytest

from config import settings
from src.data_generator import generate_dataset
from src.feature_engineering import (
    build_trajectory_features,
    calculate_cv,
    calculate_slope,
    max_consecutive_declines,
    save_trajectory_features,
)
from src.models import GeneratorConfig


@pytest.fixture(scope="module")
def monthly_df() -> pd.DataFrame:
    _, generated_monthly = generate_dataset(GeneratorConfig())
    return generated_monthly


@pytest.fixture(scope="module")
def features_df(monthly_df: pd.DataFrame) -> pd.DataFrame:
    return build_trajectory_features(monthly_df)


def test_trajectory_features_shape_and_columns(features_df: pd.DataFrame) -> None:
    assert len(features_df) == settings.CUSTOMER_COUNT
    assert list(features_df.columns) == list(settings.TRAJECTORY_FEATURE_COLUMNS)
    assert features_df.shape[1] == len(settings.TRAJECTORY_FEATURE_COLUMNS)


def test_customer_id_is_unique(features_df: pd.DataFrame) -> None:
    assert features_df["customer_id"].is_unique


def test_numeric_features_have_no_nan_or_inf(features_df: pd.DataFrame) -> None:
    numeric = features_df.drop(columns=["customer_id"])
    assert not numeric.isna().any().any()
    assert np.isfinite(numeric.to_numpy(dtype=float)).all()


def test_feature_generation_uses_only_observation_months(monthly_df: pd.DataFrame) -> None:
    baseline = build_trajectory_features(monthly_df)
    mutated = monthly_df.copy()
    future_mask = mutated["month"].between(settings.FUTURE_START_MONTH, settings.FUTURE_END_MONTH)
    future_numeric_columns = [
        "income",
        "fixed_expense",
        "variable_expense",
        "debt_payment",
        "event_expense",
        "total_expense",
        "savings_amount",
        "savings_rate",
        "fixed_expense_ratio",
        "variable_expense_ratio",
        "dsr",
        "cash_balance",
        "loan_balance",
        "debt_to_income_ratio",
        "emergency_months",
        "income_change_rate",
        "expense_change_rate",
        "balance_change_rate",
        "delinquency_flag",
    ]
    mutated.loc[future_mask, future_numeric_columns] = 999_999_999
    mutated.loc[future_mask, "event_type"] = "new_loan"
    mutated.loc[future_mask, "monthly_status"] = "delinquent"
    mutated.loc[future_mask, "final_outcome"] = "delinquent"

    after_mutation = build_trajectory_features(mutated)
    pd.testing.assert_frame_equal(baseline, after_mutation)


def test_core_feature_calculations_on_small_sample() -> None:
    months = pd.Series([1, 2, 3, 4])
    values = pd.Series([1.0, 2.0, 3.0, 4.0])

    assert calculate_slope(months, values) == pytest.approx(1.0)
    assert calculate_cv(pd.Series([5.0, 5.0, 5.0])) == 0.0
    assert max_consecutive_declines(pd.Series([5, 4, 3, 5, 4])) == 2


def test_documented_feature_values_for_one_customer(monthly_df: pd.DataFrame) -> None:
    features = build_trajectory_features(monthly_df)
    customer_id = features.iloc[0]["customer_id"]
    customer_months = monthly_df[
        (monthly_df["customer_id"] == customer_id)
        & (monthly_df["month"] <= settings.OBSERVATION_END_MONTH)
    ].sort_values("month")
    feature_row = features.loc[features["customer_id"] == customer_id].iloc[0]

    recent_3 = customer_months[customer_months["month"].between(10, 12)]
    early_3 = customer_months[customer_months["month"].between(1, 3)]
    month_1 = customer_months.loc[customer_months["month"] == 1].iloc[0]
    month_12 = customer_months.loc[customer_months["month"] == 12].iloc[0]

    assert feature_row["avg_savings_rate_3m"] == pytest.approx(recent_3["savings_rate"].mean())
    assert feature_row["avg_dsr_3m"] == pytest.approx(recent_3["dsr"].mean())
    assert feature_row["avg_fixed_expense_ratio_3m"] == pytest.approx(
        recent_3["fixed_expense_ratio"].mean()
    )
    assert feature_row["savings_rate_slope_12m"] == pytest.approx(
        np.polyfit(customer_months["month"], customer_months["savings_rate"], 1)[0]
    )
    assert feature_row["expense_growth_12m"] == pytest.approx(
        (recent_3["total_expense"].mean() - early_3["total_expense"].mean())
        / early_3["total_expense"].mean()
    )
    assert feature_row["dsr_change_12m"] == pytest.approx(month_12["dsr"] - month_1["dsr"])
    assert feature_row["balance_change_ratio_12m"] == pytest.approx(
        (month_12["cash_balance"] - month_1["cash_balance"]) / month_1["cash_balance"]
        if month_1["cash_balance"] > 0
        else 0
    )


def test_save_trajectory_features_writes_csv(tmp_path, features_df: pd.DataFrame) -> None:
    output_path = save_trajectory_features(features_df, tmp_path / "trajectory_features.csv")

    assert output_path.exists()
    saved = pd.read_csv(output_path)
    assert saved.shape == features_df.shape
