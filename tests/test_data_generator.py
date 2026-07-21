import numpy as np
import pandas as pd
import pytest

from config import settings
from src.data_generator import classify_final_outcome, generate_dataset
from src.models import GeneratorConfig


NUMERIC_COLUMNS = [
    "initial_income",
    "initial_cash_balance",
    "initial_loan_balance",
    "base_fixed_expense",
    "base_variable_expense",
    "base_debt_payment",
    "primary_event_month",
    "random_seed",
    "month",
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


@pytest.fixture(scope="module")
def generated_dataset() -> tuple[pd.DataFrame, pd.DataFrame]:
    return generate_dataset(GeneratorConfig())


def test_generated_dataset_has_required_size_and_customer_months(
    generated_dataset: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    master_df, monthly_df = generated_dataset

    assert len(master_df) == settings.CUSTOMER_COUNT
    assert len(monthly_df) == settings.CUSTOMER_COUNT * settings.TOTAL_MONTHS
    assert monthly_df.groupby("customer_id")["month"].nunique().eq(settings.TOTAL_MONTHS).all()


def test_customer_month_key_is_unique(
    generated_dataset: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    _, monthly_df = generated_dataset

    assert monthly_df[["customer_id", "month"]].duplicated().sum() == 0


def test_same_seed_reproduces_identical_results() -> None:
    first_master, first_monthly = generate_dataset(GeneratorConfig(random_seed=42))
    second_master, second_monthly = generate_dataset(GeneratorConfig(random_seed=42))

    pd.testing.assert_frame_equal(first_master, second_master)
    pd.testing.assert_frame_equal(first_monthly, second_monthly)


def test_different_seed_changes_results() -> None:
    first_master, first_monthly = generate_dataset(GeneratorConfig(random_seed=42))
    second_master, second_monthly = generate_dataset(GeneratorConfig(random_seed=43))

    assert not first_master.equals(second_master)
    assert not first_monthly.equals(second_monthly)


def test_required_columns_exist(generated_dataset: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    master_df, monthly_df = generated_dataset

    assert list(master_df.columns) == list(settings.CUSTOMER_MASTER_COLUMNS)
    assert list(monthly_df.columns) == list(settings.CUSTOMER_MONTHLY_COLUMNS)


def test_accounting_relationships_are_consistent(
    generated_dataset: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    _, monthly_df = generated_dataset

    expected_total = (
        monthly_df["fixed_expense"]
        + monthly_df["variable_expense"]
        + monthly_df["debt_payment"]
        + monthly_df["event_expense"]
    )
    expected_savings = monthly_df["income"] - monthly_df["total_expense"]

    assert (monthly_df["total_expense"] == expected_total).all()
    assert (monthly_df["savings_amount"] == expected_savings).all()


def test_loan_balance_is_never_negative(
    generated_dataset: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    _, monthly_df = generated_dataset

    assert monthly_df["loan_balance"].ge(0).all()


def test_required_numeric_columns_have_no_nan_or_inf(
    generated_dataset: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    master_df, monthly_df = generated_dataset
    master_numeric = master_df[[column for column in NUMERIC_COLUMNS if column in master_df.columns]]
    monthly_numeric = monthly_df[
        [column for column in NUMERIC_COLUMNS if column in monthly_df.columns]
    ]

    assert not master_numeric.isna().any().any()
    assert not monthly_numeric.isna().any().any()
    assert np.isfinite(master_numeric.to_numpy(dtype=float)).all()
    assert np.isfinite(monthly_numeric.to_numpy(dtype=float)).all()


def test_persona_values_are_allowed(
    generated_dataset: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    master_df, monthly_df = generated_dataset

    allowed_personas = set(settings.PERSONAS)
    assert set(master_df["persona"].unique()) <= allowed_personas
    assert set(monthly_df["persona"].unique()) <= allowed_personas


def test_months_are_in_documented_range(
    generated_dataset: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    _, monthly_df = generated_dataset

    assert monthly_df["month"].between(1, settings.TOTAL_MONTHS).all()


def test_final_outcome_uses_future_statuses(
    generated_dataset: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    _, monthly_df = generated_dataset
    future_df = monthly_df[monthly_df["month"].between(13, 36)]
    delinquent_customers = set(
        future_df.loc[future_df["monthly_status"] == "delinquent", "customer_id"].unique()
    )
    final_delinquent_customers = set(
        monthly_df.loc[monthly_df["final_outcome"] == "delinquent", "customer_id"].unique()
    )

    assert delinquent_customers <= final_delinquent_customers


def _future_outcome_rows(
    statuses: list[str],
    *,
    savings_rate: float = 0.10,
    cash_balance: int = 1_000_000,
    dsr: float = 0.20,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "customer_id": ["C999999"] * len(statuses),
            "month": list(range(13, 13 + len(statuses))),
            "monthly_status": statuses,
            "savings_rate": [savings_rate] * len(statuses),
            "cash_balance": [cash_balance] * len(statuses),
            "dsr": [dsr] * len(statuses),
        }
    )


def test_final_outcome_priority_delinquent_over_recovered() -> None:
    statuses = ["stress", "stress"] + ["healthy"] * 21 + ["delinquent"]
    future_df = _future_outcome_rows(statuses)

    assert classify_final_outcome(future_df, GeneratorConfig()) == "delinquent"


def test_final_outcome_priority_recovered_over_stress() -> None:
    statuses = ["stress"] * 6 + ["watch"] * 15 + ["healthy", "healthy", "healthy"]
    future_df = _future_outcome_rows(statuses)

    assert classify_final_outcome(future_df, GeneratorConfig()) == "recovered"


def test_final_outcome_stress_when_recovered_conditions_not_met() -> None:
    statuses = ["stress"] * 6 + ["healthy"] * 18
    future_df = _future_outcome_rows(statuses, savings_rate=0.01)

    assert classify_final_outcome(future_df, GeneratorConfig()) == "stress"


def test_final_outcome_healthy_when_no_future_rule_matches() -> None:
    statuses = ["watch"] + ["healthy"] * 23
    future_df = _future_outcome_rows(statuses)

    assert classify_final_outcome(future_df, GeneratorConfig()) == "healthy"
