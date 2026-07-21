import numpy as np
import pandas as pd
import pytest

from config import settings
from src.whatif_simulator import (
    build_baseline_profile,
    compare_scenarios,
    save_whatif_results,
    simulate_scenario,
    summarize_scenario,
)


BASELINE_SCENARIO = settings.WHATIF_SCENARIOS[0]
VARIABLE_CUT_SCENARIO = settings.WHATIF_SCENARIOS[1]
FIXED_CUT_SCENARIO = settings.WHATIF_SCENARIOS[2]


def _profile(
    income: float = 1_000.0,
    fixed_expense: float = 100.0,
    variable_expense: float = 200.0,
    debt_payment: float = 300.0,
    cash_balance: float = 500.0,
) -> dict[str, float | str]:
    return {
        "customer_id": "C000001",
        "income": income,
        "fixed_expense": fixed_expense,
        "variable_expense": variable_expense,
        "debt_payment": debt_payment,
        "cash_balance": cash_balance,
    }


def test_baseline_matches_manual_result() -> None:
    result = simulate_scenario(_profile(), BASELINE_SCENARIO, simulation_months=2)

    assert result.iloc[0]["cash_balance"] == pytest.approx(900.0)
    assert result.iloc[0]["savings_rate"] == pytest.approx(0.4)
    assert result.iloc[1]["fixed_expense"] == pytest.approx(100.15)
    assert result.iloc[1]["variable_expense"] == pytest.approx(200.4)
    assert result.iloc[1]["cash_balance"] == pytest.approx(1299.45)

    summary = summarize_scenario(result)
    assert summary["ending_cash_balance"] == pytest.approx(1299.45)
    assert summary["average_savings_rate"] == pytest.approx(0.399725)


def test_variable_expense_cut_balance_not_lower_than_baseline() -> None:
    profile = _profile()
    baseline = simulate_scenario(profile, BASELINE_SCENARIO, simulation_months=6)
    variable_cut = simulate_scenario(profile, VARIABLE_CUT_SCENARIO, simulation_months=6)

    assert (variable_cut["cash_balance"] >= baseline["cash_balance"]).all()


def test_fixed_expense_never_goes_below_zero() -> None:
    result = simulate_scenario(
        _profile(fixed_expense=100.0),
        FIXED_CUT_SCENARIO,
        simulation_months=3,
    )

    assert (result["fixed_expense"] >= 0).all()
    assert result.iloc[0]["fixed_expense"] == 0


def test_cash_depletion_month_is_first_negative_balance() -> None:
    result = simulate_scenario(
        _profile(income=100.0, fixed_expense=100.0, variable_expense=100.0, debt_payment=0.0, cash_balance=50.0),
        BASELINE_SCENARIO,
        simulation_months=3,
    )
    summary = summarize_scenario(result)

    assert summary["cash_depletion_month"] == 1


def test_improvement_calculation_is_baseline_relative() -> None:
    profile = _profile(income=1_000.0, fixed_expense=100.0, variable_expense=100.0, debt_payment=100.0)
    baseline = simulate_scenario(profile, BASELINE_SCENARIO, simulation_months=1)
    variable_cut = simulate_scenario(profile, VARIABLE_CUT_SCENARIO, simulation_months=1)

    summary = summarize_scenario(variable_cut, baseline)

    assert summary["improvement_vs_baseline"] == pytest.approx(15.0)
    assert summary["total_saved_expense"] == pytest.approx(15.0)


def test_negative_savings_month_count_is_exact() -> None:
    result = simulate_scenario(
        _profile(income=100.0, fixed_expense=120.0, variable_expense=50.0, debt_payment=0.0),
        BASELINE_SCENARIO,
        simulation_months=4,
    )
    summary = summarize_scenario(result)

    assert summary["months_with_negative_savings"] == 4


def test_zero_income_does_not_create_inf() -> None:
    result = simulate_scenario(
        _profile(income=0.0, fixed_expense=100.0, variable_expense=50.0, debt_payment=25.0),
        BASELINE_SCENARIO,
        simulation_months=2,
    )

    numeric_values = result.drop(columns=["scenario_name"]).to_numpy(dtype=float)
    assert np.isfinite(numeric_values).all()
    assert result["savings_rate"].tolist() == [-1.0, -1.0]


def test_build_baseline_profile_uses_months_10_to_12() -> None:
    monthly_df = pd.DataFrame(
        [
            {
                "customer_id": "C000001",
                "month": month,
                "income": 1_000 + month,
                "fixed_expense": 100 + month,
                "variable_expense": 200 + month,
                "debt_payment": 50 + month,
                "cash_balance": 10_000 + month,
            }
            for month in range(1, 13)
        ]
    )

    profile = build_baseline_profile("C000001", monthly_df)

    assert profile["income"] == pytest.approx((1010 + 1011 + 1012) / 3)
    assert profile["fixed_expense"] == pytest.approx((110 + 111 + 112) / 3)
    assert profile["cash_balance"] == pytest.approx(10_012)


def test_compare_scenarios_returns_all_configured_scenarios() -> None:
    result = compare_scenarios(_profile(), simulation_months=2)

    assert result["target_customer_id"] == "C000001"
    assert len(result["scenarios"]) == 4
    assert [scenario["scenario_name"] for scenario in result["scenarios"]] == [
        "baseline",
        "variable_expense_cut_15",
        "fixed_expense_cut_300k",
        "debt_payment_cut_20",
    ]


def test_save_whatif_results_writes_json(tmp_path) -> None:
    result = compare_scenarios(_profile(), simulation_months=1)

    output_path = save_whatif_results(result, tmp_path / "whatif_results.json")

    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8")
