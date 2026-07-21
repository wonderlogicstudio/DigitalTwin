"""Rule-based cash-flow what-if simulation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from config import settings


REQUIRED_PROFILE_COLUMNS = (
    "customer_id",
    "month",
    "income",
    "fixed_expense",
    "variable_expense",
    "debt_payment",
    "cash_balance",
)


def build_baseline_profile(customer_id: str, monthly_df: pd.DataFrame) -> dict[str, Any]:
    """Build a starting profile from months 10..12 for one customer."""

    missing_columns = [column for column in REQUIRED_PROFILE_COLUMNS if column not in monthly_df.columns]
    if missing_columns:
        raise ValueError(f"Missing required monthly columns: {missing_columns}")

    customer_df = monthly_df.loc[monthly_df["customer_id"] == customer_id].copy()
    if customer_df.empty:
        raise ValueError(f"Unknown customer_id: {customer_id}")

    recent_df = customer_df.loc[customer_df["month"].between(10, settings.OBSERVATION_END_MONTH)]
    month_12_df = customer_df.loc[customer_df["month"] == settings.OBSERVATION_END_MONTH]
    if len(recent_df) != 3 or month_12_df.empty:
        raise ValueError("Customer must have months 10, 11, and 12 to build a profile.")

    return {
        "customer_id": customer_id,
        "income": float(recent_df["income"].mean()),
        "fixed_expense": float(recent_df["fixed_expense"].mean()),
        "variable_expense": float(recent_df["variable_expense"].mean()),
        "debt_payment": float(recent_df["debt_payment"].mean()),
        "cash_balance": float(month_12_df.iloc[0]["cash_balance"]),
    }


def simulate_scenario(
    profile: dict[str, Any],
    scenario: dict[str, Any],
    simulation_months: int = settings.WHATIF_SIMULATION_MONTHS,
) -> pd.DataFrame:
    """Simulate monthly cash balances for a single what-if scenario."""

    current_cash_balance = float(profile["cash_balance"])
    rows: list[dict[str, Any]] = []
    for month in range(1, simulation_months + 1):
        trend_index = month - 1
        income = _round_money(
            float(profile["income"]) * (1 + settings.WHATIF_INCOME_MONTHLY_GROWTH) ** trend_index
        )
        fixed_expense = _round_money(
            float(profile["fixed_expense"])
            * (1 + settings.WHATIF_FIXED_EXPENSE_MONTHLY_GROWTH) ** trend_index
            + float(scenario.get("fixed_expense_delta", 0))
        )
        fixed_expense = max(0.0, fixed_expense)
        variable_expense = _round_money(
            float(profile["variable_expense"])
            * (1 + settings.WHATIF_VARIABLE_EXPENSE_MONTHLY_GROWTH) ** trend_index
            * float(scenario.get("variable_expense_multiplier", 1.0))
        )
        debt_payment = _round_money(
            float(profile["debt_payment"])
            * (1 + settings.WHATIF_DEBT_PAYMENT_MONTHLY_GROWTH) ** trend_index
            * float(scenario.get("debt_payment_multiplier", 1.0))
        )
        total_expense = fixed_expense + variable_expense + debt_payment
        savings_amount = income - total_expense
        current_cash_balance += savings_amount
        savings_rate = _calculate_savings_rate(income, savings_amount)

        rows.append(
            {
                "scenario_id": int(scenario["scenario_id"]),
                "scenario_name": str(scenario["scenario_name"]),
                "month": month,
                "income": income,
                "fixed_expense": fixed_expense,
                "variable_expense": variable_expense,
                "debt_payment": debt_payment,
                "total_expense": total_expense,
                "savings_amount": savings_amount,
                "savings_rate": savings_rate,
                "cash_balance": current_cash_balance,
            }
        )
    return pd.DataFrame(rows)


def summarize_scenario(
    monthly_simulation: pd.DataFrame,
    baseline_simulation: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Summarize one scenario and compare it to baseline when provided."""

    ending_cash_balance = float(monthly_simulation.iloc[-1]["cash_balance"])
    baseline_ending = (
        ending_cash_balance
        if baseline_simulation is None
        else float(baseline_simulation.iloc[-1]["cash_balance"])
    )
    baseline_total_expense = (
        float(monthly_simulation["total_expense"].sum())
        if baseline_simulation is None
        else float(baseline_simulation["total_expense"].sum())
    )
    cash_depletion = monthly_simulation.loc[monthly_simulation["cash_balance"] < 0, "month"]

    return {
        "scenario_id": int(monthly_simulation.iloc[0]["scenario_id"]),
        "scenario_name": str(monthly_simulation.iloc[0]["scenario_name"]),
        "ending_cash_balance": _round_money(ending_cash_balance),
        "minimum_cash_balance": _round_money(float(monthly_simulation["cash_balance"].min())),
        "average_savings_rate": round(float(monthly_simulation["savings_rate"].mean()), 6),
        "cash_depletion_month": None if cash_depletion.empty else int(cash_depletion.iloc[0]),
        "improvement_vs_baseline": _round_money(ending_cash_balance - baseline_ending),
        "total_saved_expense": _round_money(
            baseline_total_expense - float(monthly_simulation["total_expense"].sum())
        ),
        "months_with_negative_savings": int((monthly_simulation["savings_amount"] < 0).sum()),
        "monthly_data": _records_for_json(monthly_simulation),
    }


def compare_scenarios(
    profile: dict[str, Any],
    scenarios: tuple[dict[str, Any], ...] = settings.WHATIF_SCENARIOS,
    simulation_months: int = settings.WHATIF_SIMULATION_MONTHS,
) -> dict[str, Any]:
    """Run all scenarios and return baseline-relative cash-flow results."""

    simulations = {
        str(scenario["scenario_name"]): simulate_scenario(profile, scenario, simulation_months)
        for scenario in scenarios
    }
    baseline = simulations["baseline"]
    scenario_results = [
        summarize_scenario(simulations[str(scenario["scenario_name"])], baseline)
        for scenario in scenarios
    ]
    return {
        "target_customer_id": str(profile.get("customer_id", "")),
        "simulation_months": simulation_months,
        "starting_profile": _json_ready_profile(profile),
        "scenarios": scenario_results,
    }


def build_whatif_results(
    customer_id: str,
    monthly_df: pd.DataFrame,
    scenarios: tuple[dict[str, Any], ...] = settings.WHATIF_SCENARIOS,
    simulation_months: int = settings.WHATIF_SIMULATION_MONTHS,
) -> dict[str, Any]:
    """Build baseline profile and run all configured what-if scenarios."""

    profile = build_baseline_profile(customer_id, monthly_df)
    return compare_scenarios(profile, scenarios, simulation_months)


def save_whatif_results(
    results: dict[str, Any],
    output_path: Path = settings.WHATIF_RESULTS_PATH,
) -> Path:
    """Save what-if results as UTF-8 JSON."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def _calculate_savings_rate(income: float, savings_amount: float) -> float:
    if income > 0:
        return round(float(savings_amount / income), 6)
    return -1.0


def _round_money(value: float) -> float:
    return float(round(value, 2))


def _records_for_json(df: pd.DataFrame) -> list[dict[str, Any]]:
    records = df.replace({np.nan: None}).to_dict(orient="records")
    for record in records:
        for key, value in list(record.items()):
            if isinstance(value, np.generic):
                record[key] = value.item()
    return records


def _json_ready_profile(profile: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in profile.items():
        if isinstance(value, (int, float)):
            output[key] = _round_money(float(value))
        else:
            output[key] = value
    return output
