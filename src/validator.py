"""Data validation checks for generated Financial Path Twin CSV files."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

from config import settings


REPORT_COLUMNS = (
    "check_name",
    "status",
    "actual_value",
    "expected_value",
    "message",
)

MASTER_INTEGER_COLUMNS = (
    "initial_income",
    "initial_cash_balance",
    "initial_loan_balance",
    "base_fixed_expense",
    "base_variable_expense",
    "base_debt_payment",
    "primary_event_month",
    "random_seed",
)

MONTHLY_INTEGER_COLUMNS = (
    "month",
    "income",
    "fixed_expense",
    "variable_expense",
    "debt_payment",
    "event_expense",
    "total_expense",
    "savings_amount",
    "cash_balance",
    "loan_balance",
    "delinquency_flag",
)

MONTHLY_FLOAT_COLUMNS = (
    "savings_rate",
    "fixed_expense_ratio",
    "variable_expense_ratio",
    "dsr",
    "debt_to_income_ratio",
    "emergency_months",
    "income_change_rate",
    "expense_change_rate",
    "balance_change_rate",
)

MASTER_TEXT_COLUMNS = (
    "customer_id",
    "persona",
    "age_group",
    "household_type",
    "primary_event_type",
)

MONTHLY_TEXT_COLUMNS = (
    "customer_id",
    "persona",
    "event_type",
    "monthly_status",
    "final_outcome",
)

OUTCOME_TARGET_RANGES = {
    "healthy": (0.45, 0.60),
    "recovered": (0.08, 0.18),
    "stress": (0.20, 0.35),
    "delinquent": (0.05, 0.15),
}

PERSONA_DISTRIBUTION_TOLERANCE = 0.015
RATIO_TOLERANCE = 1e-6


def load_input_data(
    master_path: Path = settings.CUSTOMER_MASTER_PATH,
    monthly_path: Path = settings.CUSTOMER_MONTHLY_PATH,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load customer master and monthly snapshot CSV files."""

    return pd.read_csv(master_path), pd.read_csv(monthly_path)


def validate_schema(master_df: pd.DataFrame, monthly_df: pd.DataFrame) -> list[dict[str, str]]:
    """Validate required columns and column data types."""

    results: list[dict[str, str]] = []
    results.append(
        _check_required_columns(
            "customer_master_required_columns",
            master_df,
            settings.CUSTOMER_MASTER_COLUMNS,
        )
    )
    results.append(
        _check_required_columns(
            "customer_monthly_required_columns",
            monthly_df,
            settings.CUSTOMER_MONTHLY_COLUMNS,
        )
    )
    results.extend(
        _check_integer_columns("customer_master_integer_types", master_df, MASTER_INTEGER_COLUMNS)
    )
    results.extend(
        _check_integer_columns("customer_monthly_integer_types", monthly_df, MONTHLY_INTEGER_COLUMNS)
    )
    results.extend(_check_numeric_columns("customer_monthly_float_types", monthly_df, MONTHLY_FLOAT_COLUMNS))
    results.extend(_check_text_columns("customer_master_text_types", master_df, MASTER_TEXT_COLUMNS))
    results.extend(_check_text_columns("customer_monthly_text_types", monthly_df, MONTHLY_TEXT_COLUMNS))
    return results


def validate_customer_months(master_df: pd.DataFrame, monthly_df: pd.DataFrame) -> list[dict[str, str]]:
    """Validate row counts, monthly coverage, keys, and month range."""

    results = [
        _result(
            "customer_master_row_count",
            "pass" if len(master_df) == settings.CUSTOMER_COUNT else "failure",
            len(master_df),
            settings.CUSTOMER_COUNT,
            "customer_master must contain exactly 5,000 customers.",
        ),
        _result(
            "customer_monthly_row_count",
            "pass"
            if len(monthly_df) == settings.CUSTOMER_COUNT * settings.TOTAL_MONTHS
            else "failure",
            len(monthly_df),
            settings.CUSTOMER_COUNT * settings.TOTAL_MONTHS,
            "monthly data must contain 5,000 customers x 36 months.",
        ),
    ]

    months_per_customer = monthly_df.groupby("customer_id")["month"].nunique()
    invalid_customer_count = int((months_per_customer != settings.TOTAL_MONTHS).sum())
    results.append(
        _result(
            "customer_months_per_customer",
            "pass" if invalid_customer_count == 0 else "failure",
            invalid_customer_count,
            0,
            "Each customer must have exactly 36 distinct months.",
        )
    )

    duplicate_count = int(monthly_df[["customer_id", "month"]].duplicated().sum())
    results.append(
        _result(
            "customer_month_unique_key",
            "pass" if duplicate_count == 0 else "failure",
            duplicate_count,
            0,
            "customer_id + month must be unique.",
        )
    )

    out_of_range_count = int((~monthly_df["month"].between(1, settings.TOTAL_MONTHS)).sum())
    results.append(
        _result(
            "month_range",
            "pass" if out_of_range_count == 0 else "failure",
            out_of_range_count,
            "1..36",
            "month must be between 1 and 36.",
        )
    )
    return results


def validate_accounting_relationships(
    master_df: pd.DataFrame,
    monthly_df: pd.DataFrame,
) -> list[dict[str, str]]:
    """Validate financial formulas and balance continuity."""

    results: list[dict[str, str]] = []
    expected_total_expense = (
        monthly_df["fixed_expense"]
        + monthly_df["variable_expense"]
        + monthly_df["debt_payment"]
        + monthly_df["event_expense"]
    )
    results.append(
        _count_mismatches(
            "total_expense_formula",
            monthly_df["total_expense"],
            expected_total_expense,
            "total_expense = fixed_expense + variable_expense + debt_payment + event_expense",
        )
    )

    expected_savings = monthly_df["income"] - monthly_df["total_expense"]
    results.append(
        _count_mismatches(
            "savings_amount_formula",
            monthly_df["savings_amount"],
            expected_savings,
            "savings_amount = income - total_expense",
        )
    )

    expected_cash = _expected_cash_balance(master_df, monthly_df)
    results.append(
        _count_mismatches(
            "cash_balance_continuity",
            monthly_df.sort_values(["customer_id", "month"])["cash_balance"].reset_index(drop=True),
            expected_cash,
            "cash_balance(t) = previous cash_balance + savings_amount(t)",
        )
    )

    results.append(
        _result(
            "loan_balance_non_negative",
            "pass" if int((monthly_df["loan_balance"] < 0).sum()) == 0 else "failure",
            int((monthly_df["loan_balance"] < 0).sum()),
            0,
            "loan_balance must never be below zero.",
        )
    )

    results.extend(_validate_ratio_formulas(monthly_df))
    return results


def validate_distribution(master_df: pd.DataFrame, monthly_df: pd.DataFrame) -> list[dict[str, str]]:
    """Validate allowed categorical values and distribution targets."""

    results: list[dict[str, str]] = []
    results.append(_check_allowed_values("master_persona_values", master_df["persona"], settings.PERSONAS))
    results.append(_check_allowed_values("monthly_persona_values", monthly_df["persona"], settings.PERSONAS))
    results.append(_check_allowed_values("event_type_values", monthly_df["event_type"], settings.EVENT_TYPES))
    results.append(
        _check_allowed_values("primary_event_type_values", master_df["primary_event_type"], settings.EVENT_TYPES)
    )
    results.append(
        _check_allowed_values("monthly_status_values", monthly_df["monthly_status"], settings.MONTHLY_STATUSES)
    )
    results.append(
        _check_allowed_values("final_outcome_values", monthly_df["final_outcome"], settings.FINAL_OUTCOMES)
    )

    persona_summary = build_persona_summary(master_df)
    max_persona_delta = float(persona_summary["difference"].abs().max())
    results.append(
        _result(
            "persona_distribution",
            "pass" if max_persona_delta <= PERSONA_DISTRIBUTION_TOLERANCE else "warning",
            round(max_persona_delta, 6),
            f"<= {PERSONA_DISTRIBUTION_TOLERANCE}",
            "Persona ratios should stay close to PERSONA_DISTRIBUTION.",
        )
    )

    outcome_summary = build_outcome_distribution(monthly_df)
    warning_outcomes = outcome_summary.loc[outcome_summary["status"] == "warning", "final_outcome"].tolist()
    results.append(
        _result(
            "final_outcome_distribution",
            "pass" if not warning_outcomes else "warning",
            ",".join(warning_outcomes) if warning_outcomes else "within_target",
            "BUSINESS_RULES target ranges",
            "Final outcome range departures are warnings, not failures.",
        )
    )
    return results


def validate_missing_and_numeric_values(
    master_df: pd.DataFrame,
    monthly_df: pd.DataFrame,
) -> list[dict[str, str]]:
    """Validate required missing values, NaN, inf, and numeric ranges."""

    results: list[dict[str, str]] = []
    results.append(_check_missing("customer_master_missing_required_values", master_df, settings.CUSTOMER_MASTER_COLUMNS))
    results.append(_check_missing("customer_monthly_missing_required_values", monthly_df, settings.CUSTOMER_MONTHLY_COLUMNS))

    master_numeric = [column for column in MASTER_INTEGER_COLUMNS if column in master_df.columns]
    monthly_numeric = list(MONTHLY_INTEGER_COLUMNS) + list(MONTHLY_FLOAT_COLUMNS)
    results.append(_check_finite("customer_master_numeric_finite", master_df, master_numeric))
    results.append(_check_finite("customer_monthly_numeric_finite", monthly_df, monthly_numeric))

    results.extend(_validate_numeric_ranges(master_df, monthly_df))
    return results


def run_all_validations(master_df: pd.DataFrame, monthly_df: pd.DataFrame) -> pd.DataFrame:
    """Run every validation and return the report dataframe."""

    results: list[dict[str, str]] = []
    results.extend(validate_schema(master_df, monthly_df))
    results.extend(validate_customer_months(master_df, monthly_df))
    results.extend(validate_missing_and_numeric_values(master_df, monthly_df))
    results.extend(validate_accounting_relationships(master_df, monthly_df))
    results.extend(validate_distribution(master_df, monthly_df))
    return pd.DataFrame(results, columns=REPORT_COLUMNS)


def build_persona_summary(master_df: pd.DataFrame) -> pd.DataFrame:
    """Build persona count and ratio summary report."""

    counts = master_df["persona"].value_counts().reindex(settings.PERSONAS, fill_value=0)
    rows = []
    total = max(len(master_df), 1)
    for persona, count in counts.items():
        actual_ratio = count / total
        expected_ratio = settings.PERSONA_DISTRIBUTION[persona]
        rows.append(
            {
                "persona": persona,
                "count": int(count),
                "ratio": actual_ratio,
                "expected_ratio": expected_ratio,
                "difference": actual_ratio - expected_ratio,
            }
        )
    return pd.DataFrame(rows)


def build_outcome_distribution(monthly_df: pd.DataFrame) -> pd.DataFrame:
    """Build final outcome distribution summary report."""

    customer_outcomes = monthly_df.drop_duplicates("customer_id")["final_outcome"]
    counts = customer_outcomes.value_counts().reindex(settings.FINAL_OUTCOMES, fill_value=0)
    total = max(int(counts.sum()), 1)
    rows = []
    for outcome, count in counts.items():
        ratio = count / total
        min_ratio, max_ratio = OUTCOME_TARGET_RANGES[outcome]
        rows.append(
            {
                "final_outcome": outcome,
                "count": int(count),
                "ratio": ratio,
                "min_ratio": min_ratio,
                "max_ratio": max_ratio,
                "status": "pass" if min_ratio <= ratio <= max_ratio else "warning",
            }
        )
    return pd.DataFrame(rows)


def save_validation_reports(
    validation_report: pd.DataFrame,
    persona_summary: pd.DataFrame,
    outcome_distribution: pd.DataFrame,
    reports_dir: Path = settings.REPORTS_DIR,
) -> tuple[Path, Path, Path]:
    """Write validation, persona, and outcome reports to CSV files."""

    reports_dir.mkdir(parents=True, exist_ok=True)
    validation_path = reports_dir / "data_validation_report.csv"
    persona_path = reports_dir / "persona_summary.csv"
    outcome_path = reports_dir / "outcome_distribution.csv"
    validation_report.to_csv(validation_path, index=False, encoding="utf-8")
    persona_summary.to_csv(persona_path, index=False, encoding="utf-8")
    outcome_distribution.to_csv(outcome_path, index=False, encoding="utf-8")
    return validation_path, persona_path, outcome_path


def has_failures(validation_report: pd.DataFrame) -> bool:
    """Return whether any validation check failed."""

    return bool((validation_report["status"] == "failure").any())


def _result(
    check_name: str,
    status: str,
    actual_value: object,
    expected_value: object,
    message: str,
) -> dict[str, str]:
    return {
        "check_name": check_name,
        "status": status,
        "actual_value": str(actual_value),
        "expected_value": str(expected_value),
        "message": message,
    }


def _check_required_columns(
    check_name: str,
    df: pd.DataFrame,
    required_columns: Iterable[str],
) -> dict[str, str]:
    missing = [column for column in required_columns if column not in df.columns]
    return _result(
        check_name,
        "pass" if not missing else "failure",
        ",".join(missing) if missing else "none",
        ",".join(required_columns),
        "Required columns must be present.",
    )


def _check_integer_columns(
    check_prefix: str,
    df: pd.DataFrame,
    columns: Iterable[str],
) -> list[dict[str, str]]:
    results = []
    for column in columns:
        if column not in df.columns:
            continue
        is_valid = is_numeric_dtype(df[column]) and bool((df[column].dropna() % 1 == 0).all())
        results.append(
            _result(
                f"{check_prefix}_{column}",
                "pass" if is_valid else "failure",
                str(df[column].dtype),
                "integer-like numeric",
                f"{column} must contain integer-like numeric values.",
            )
        )
    return results


def _check_numeric_columns(
    check_prefix: str,
    df: pd.DataFrame,
    columns: Iterable[str],
) -> list[dict[str, str]]:
    results = []
    for column in columns:
        if column not in df.columns:
            continue
        results.append(
            _result(
                f"{check_prefix}_{column}",
                "pass" if is_numeric_dtype(df[column]) else "failure",
                str(df[column].dtype),
                "numeric",
                f"{column} must contain numeric values.",
            )
        )
    return results


def _check_text_columns(
    check_prefix: str,
    df: pd.DataFrame,
    columns: Iterable[str],
) -> list[dict[str, str]]:
    results = []
    for column in columns:
        if column not in df.columns:
            continue
        is_valid = df[column].dtype == object or str(df[column].dtype).startswith("string")
        results.append(
            _result(
                f"{check_prefix}_{column}",
                "pass" if is_valid else "failure",
                str(df[column].dtype),
                "string/category",
                f"{column} must contain string/category values.",
            )
        )
    return results


def _check_missing(
    check_name: str,
    df: pd.DataFrame,
    required_columns: Iterable[str],
) -> dict[str, str]:
    columns = [column for column in required_columns if column in df.columns]
    missing_count = int(df[columns].isna().sum().sum())
    return _result(
        check_name,
        "pass" if missing_count == 0 else "failure",
        missing_count,
        0,
        "Required columns must not contain missing values.",
    )


def _check_finite(check_name: str, df: pd.DataFrame, columns: Iterable[str]) -> dict[str, str]:
    present_columns = [column for column in columns if column in df.columns]
    numeric_values = df[present_columns].to_numpy(dtype=float)
    non_finite_count = int((~np.isfinite(numeric_values)).sum())
    return _result(
        check_name,
        "pass" if non_finite_count == 0 else "failure",
        non_finite_count,
        0,
        "Numeric columns must not contain NaN or infinite values.",
    )


def _validate_numeric_ranges(
    master_df: pd.DataFrame,
    monthly_df: pd.DataFrame,
) -> list[dict[str, str]]:
    expense_columns = [
        "fixed_expense",
        "variable_expense",
        "debt_payment",
        "event_expense",
        "total_expense",
    ]
    master_amount_columns = [
        "initial_income",
        "initial_cash_balance",
        "initial_loan_balance",
        "base_fixed_expense",
        "base_variable_expense",
        "base_debt_payment",
    ]
    results = [
        _range_check("master_amount_non_negative", master_df, master_amount_columns, lower=0),
        _range_check("monthly_income_non_negative", monthly_df, ["income"], lower=0),
        _range_check("monthly_expense_non_negative", monthly_df, expense_columns, lower=0),
        _range_check("monthly_loan_balance_non_negative", monthly_df, ["loan_balance"], lower=0),
        _range_check(
            "monthly_ratio_reasonable_range",
            monthly_df,
            ["fixed_expense_ratio", "variable_expense_ratio", "dsr"],
            lower=0,
            upper=1,
        ),
    ]
    return results


def _range_check(
    check_name: str,
    df: pd.DataFrame,
    columns: Iterable[str],
    lower: float | None = None,
    upper: float | None = None,
) -> dict[str, str]:
    present_columns = [column for column in columns if column in df.columns]
    invalid_mask = pd.Series(False, index=df.index)
    for column in present_columns:
        if lower is not None:
            invalid_mask |= df[column] < lower
        if upper is not None:
            invalid_mask |= df[column] > upper
    invalid_count = int(invalid_mask.sum())
    expected = []
    if lower is not None:
        expected.append(f">= {lower:g}")
    if upper is not None:
        expected.append(f"<= {upper:g}")
    return _result(
        check_name,
        "pass" if invalid_count == 0 else "failure",
        invalid_count,
        " and ".join(expected),
        f"Columns {','.join(present_columns)} must stay within allowed range.",
    )


def _count_mismatches(
    check_name: str,
    actual: pd.Series,
    expected: pd.Series,
    message: str,
    tolerance: float = 0,
) -> dict[str, str]:
    if tolerance:
        mismatch_count = int((~np.isclose(actual.to_numpy(float), expected.to_numpy(float), atol=tolerance)).sum())
    else:
        mismatch_count = int((actual.reset_index(drop=True) != expected.reset_index(drop=True)).sum())
    return _result(check_name, "pass" if mismatch_count == 0 else "failure", mismatch_count, 0, message)


def _expected_cash_balance(master_df: pd.DataFrame, monthly_df: pd.DataFrame) -> pd.Series:
    monthly_sorted = monthly_df.sort_values(["customer_id", "month"]).reset_index(drop=True)
    initial_cash = master_df.set_index("customer_id")["initial_cash_balance"]
    expected = []
    previous_customer_id = None
    running_cash = 0
    for row in monthly_sorted.itertuples(index=False):
        if row.customer_id != previous_customer_id:
            running_cash = int(initial_cash.loc[row.customer_id])
            previous_customer_id = row.customer_id
        running_cash += int(row.savings_amount)
        expected.append(running_cash)
    return pd.Series(expected)


def _validate_ratio_formulas(monthly_df: pd.DataFrame) -> list[dict[str, str]]:
    income = monthly_df["income"]
    income_positive = income > 0
    expected_savings_rate = pd.Series(-1.0, index=monthly_df.index, dtype=float)
    expected_fixed_ratio = pd.Series(1.0, index=monthly_df.index, dtype=float)
    expected_variable_ratio = pd.Series(1.0, index=monthly_df.index, dtype=float)
    expected_dsr = pd.Series(1.0, index=monthly_df.index, dtype=float)
    expected_savings_rate.loc[income_positive] = (
        monthly_df.loc[income_positive, "savings_amount"] / income.loc[income_positive]
    ).round(6)
    expected_fixed_ratio.loc[income_positive] = (
        monthly_df.loc[income_positive, "fixed_expense"] / income.loc[income_positive]
    ).round(6)
    expected_variable_ratio.loc[income_positive] = (
        monthly_df.loc[income_positive, "variable_expense"] / income.loc[income_positive]
    ).round(6)
    expected_dsr.loc[income_positive] = (
        monthly_df.loc[income_positive, "debt_payment"] / income.loc[income_positive]
    ).round(6)

    return [
        _count_mismatches(
            "savings_rate_formula",
            monthly_df["savings_rate"],
            expected_savings_rate,
            "savings_rate follows income > 0 and income = 0 rules.",
            tolerance=RATIO_TOLERANCE,
        ),
        _count_mismatches(
            "fixed_expense_ratio_formula",
            monthly_df["fixed_expense_ratio"],
            expected_fixed_ratio,
            "fixed_expense_ratio follows income > 0 and income = 0 rules.",
            tolerance=RATIO_TOLERANCE,
        ),
        _count_mismatches(
            "variable_expense_ratio_formula",
            monthly_df["variable_expense_ratio"],
            expected_variable_ratio,
            "variable_expense_ratio follows income > 0 and income = 0 rules.",
            tolerance=RATIO_TOLERANCE,
        ),
        _count_mismatches(
            "dsr_formula",
            monthly_df["dsr"],
            expected_dsr,
            "dsr follows income > 0 and income = 0 rules.",
            tolerance=RATIO_TOLERANCE,
        ),
    ]


def _check_allowed_values(
    check_name: str,
    series: pd.Series,
    allowed_values: Iterable[str],
) -> dict[str, str]:
    allowed = set(allowed_values)
    unexpected = sorted(set(series.dropna().unique()) - allowed)
    return _result(
        check_name,
        "pass" if not unexpected else "failure",
        ",".join(map(str, unexpected)) if unexpected else "none",
        ",".join(allowed_values),
        f"{series.name} must only contain documented values.",
    )
