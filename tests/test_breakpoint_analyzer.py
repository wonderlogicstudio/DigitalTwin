import pandas as pd
import pytest

from config import settings
from src.breakpoint_analyzer import (
    calculate_pooled_std,
    find_breakpoint,
    save_breakpoint_result,
)


def _build_monthly_data(
    risk_count: int = 20,
    avoidance_count: int = 20,
    metric_differences: dict[str, dict[int, tuple[float, float]]] | None = None,
    add_variation: bool = True,
) -> pd.DataFrame:
    metric_differences = metric_differences or {}
    rows = []
    customers = [
        *[(f"R{index:06d}", "stress") for index in range(1, risk_count + 1)],
        *[(f"A{index:06d}", "healthy") for index in range(1, avoidance_count + 1)],
    ]

    for customer_index, (customer_id, final_outcome) in enumerate(customers):
        is_risk = final_outcome == "stress"
        variation = ((customer_index % 5) - 2) * 0.01 if add_variation else 0.0
        for month in range(10, settings.FUTURE_END_MONTH + 1):
            income = 1_000_000
            savings_rate = 0.10 + variation
            fixed_expense_ratio = 0.30 + variation
            variable_expense_ratio = 0.20 + variation
            dsr = 0.20 + variation

            metric_values = {
                "savings_rate": savings_rate,
                "fixed_expense_ratio": fixed_expense_ratio,
                "variable_expense_ratio": variable_expense_ratio,
                "dsr": dsr,
            }
            for metric, month_values in metric_differences.items():
                if month in month_values:
                    risk_value, avoidance_value = month_values[month]
                    metric_values[metric] = (risk_value if is_risk else avoidance_value) + variation

            rows.append(
                {
                    "customer_id": customer_id,
                    "month": month,
                    "income": income,
                    "savings_rate": metric_values["savings_rate"],
                    "fixed_expense_ratio": metric_values["fixed_expense_ratio"],
                    "variable_expense_ratio": metric_values["variable_expense_ratio"],
                    "dsr": metric_values["dsr"],
                    "cash_balance": income * 2,
                    "loan_balance": income,
                    "final_outcome": final_outcome,
                }
            )
    return pd.DataFrame(rows)


def _matched_ids(monthly_df: pd.DataFrame) -> list[str]:
    return sorted(monthly_df["customer_id"].unique())


def test_detects_artificial_month_14_breakpoint() -> None:
    monthly_df = _build_monthly_data(
        metric_differences={
            "fixed_expense_ratio": {
                14: (0.62, 0.30),
                15: (0.63, 0.31),
            }
        }
    )

    result = find_breakpoint(_matched_ids(monthly_df), monthly_df)

    assert result["status"] == "found"
    assert result["breakpoint_month"] == 14
    assert result["primary_factor"] == "fixed_expense_ratio"
    assert result["months_from_current"] == 2
    assert result["risk_group_mean"] > result["avoidance_group_mean"]
    assert "causal" in result["interpretation"]


def test_one_month_difference_is_excluded() -> None:
    monthly_df = _build_monthly_data(
        metric_differences={"fixed_expense_ratio": {14: (0.70, 0.25)}}
    )

    result = find_breakpoint(_matched_ids(monthly_df), monthly_df)

    assert result["status"] == "not_found"


def test_group_size_19_returns_insufficient_group_size() -> None:
    monthly_df = _build_monthly_data(
        risk_count=19,
        avoidance_count=20,
        metric_differences={
            "fixed_expense_ratio": {
                14: (0.70, 0.25),
                15: (0.70, 0.25),
            }
        },
    )

    result = find_breakpoint(_matched_ids(monthly_df), monthly_df)

    assert result["status"] == "insufficient_group_size"


def test_smd_below_threshold_returns_not_found() -> None:
    monthly_df = _build_monthly_data(
        metric_differences={
            "fixed_expense_ratio": {
                14: (0.305, 0.300),
                15: (0.305, 0.300),
            }
        }
    )

    result = find_breakpoint(_matched_ids(monthly_df), monthly_df)

    assert result["status"] == "not_found"


def test_largest_smd_metric_selected_when_same_month_has_multiple_metrics() -> None:
    monthly_df = _build_monthly_data(
        metric_differences={
            "fixed_expense_ratio": {
                14: (0.50, 0.30),
                15: (0.50, 0.30),
            },
            "dsr": {
                14: (0.75, 0.20),
                15: (0.75, 0.20),
            },
        }
    )

    result = find_breakpoint(_matched_ids(monthly_df), monthly_df)

    assert result["breakpoint_month"] == 14
    assert result["primary_factor"] == "dsr"
    assert result["secondary_factors"][0]["factor"] == "fixed_expense_ratio"


def test_zero_pooled_std_is_excluded_without_error() -> None:
    monthly_df = _build_monthly_data(
        metric_differences={
            "fixed_expense_ratio": {
                14: (0.70, 0.25),
                15: (0.70, 0.25),
            }
        },
        add_variation=False,
    )

    result = find_breakpoint(_matched_ids(monthly_df), monthly_df)

    assert calculate_pooled_std(pd.Series([1.0, 1.0]), pd.Series([2.0, 2.0])) == 0.0
    assert result["status"] == "not_found"


def test_months_from_current_calculation() -> None:
    monthly_df = _build_monthly_data(
        metric_differences={
            "fixed_expense_ratio": {
                14: (0.62, 0.30),
                15: (0.63, 0.31),
            }
        }
    )

    result = find_breakpoint(_matched_ids(monthly_df), monthly_df)

    assert result["months_from_current"] == result["breakpoint_month"] - settings.OBSERVATION_END_MONTH


def test_save_breakpoint_result_writes_json(tmp_path) -> None:
    result = {
        "status": "not_found",
        "breakpoint_month": None,
        "months_from_current": None,
        "primary_factor": None,
        "risk_group_mean": None,
        "avoidance_group_mean": None,
        "standardized_difference": None,
        "persistence_months": 0,
        "secondary_factors": [],
        "interpretation": "No sustained standardized difference was found.",
    }

    output_path = save_breakpoint_result(result, tmp_path / "breakpoint_result.json")

    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8")
