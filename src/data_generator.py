"""Synthetic customer and monthly financial data generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from config import settings
from src.models import GeneratorConfig


@dataclass(frozen=True)
class CustomerState:
    """Internal immutable customer inputs used during monthly simulation."""

    customer_id: str
    persona: str
    initial_income: int
    initial_cash_balance: int
    initial_loan_balance: int
    base_fixed_expense: int
    base_variable_expense: int
    base_debt_payment: int
    primary_event_type: str
    primary_event_month: int


def ensure_output_directories(config: GeneratorConfig) -> None:
    """Create configured output directories when they do not exist."""

    Path(config.customer_master_path).parent.mkdir(parents=True, exist_ok=True)
    Path(config.customer_monthly_path).parent.mkdir(parents=True, exist_ok=True)


def generate_customer_master(config: GeneratorConfig) -> pd.DataFrame:
    """Generate one master row per synthetic customer."""

    rng = np.random.default_rng(config.random_seed)
    personas = _build_persona_assignments(config, rng)
    incomes = _generate_initial_incomes(config.customer_count, rng)

    rows: list[dict[str, object]] = []
    for index, persona in enumerate(personas, start=1):
        income = int(incomes[index - 1])
        has_loan = rng.random() >= _persona_no_loan_probability(persona)
        initial_loan = int(round(income * rng.uniform(3.0, 36.0))) if has_loan else 0
        initial_cash = int(
            np.clip(
                round(income * rng.uniform(*_persona_cash_month_range(persona))),
                settings.CASH_BALANCE_MIN,
                settings.CASH_BALANCE_MAX,
            )
        )

        fixed_range, variable_range, debt_range = _persona_initial_ratio_ranges(persona)
        fixed_ratio = rng.uniform(*fixed_range)
        variable_ratio = rng.uniform(*variable_range)
        debt_ratio = rng.uniform(*debt_range) if has_loan else 0.0
        total_ratio = fixed_ratio + variable_ratio + debt_ratio
        if total_ratio > 1.30:
            scale = 1.30 / total_ratio
            fixed_ratio *= scale
            variable_ratio *= scale
            debt_ratio *= scale

        primary_event_type, primary_event_month = _choose_primary_event(persona, rng)
        rows.append(
            {
                "customer_id": f"C{index:06d}",
                "persona": persona,
                "age_group": str(rng.choice(settings.AGE_GROUPS)),
                "household_type": str(rng.choice(settings.HOUSEHOLD_TYPES)),
                "initial_income": income,
                "initial_cash_balance": initial_cash,
                "initial_loan_balance": initial_loan,
                "base_fixed_expense": int(round(income * fixed_ratio)),
                "base_variable_expense": int(round(income * variable_ratio)),
                "base_debt_payment": int(round(income * debt_ratio)),
                "primary_event_type": primary_event_type,
                "primary_event_month": primary_event_month,
                "random_seed": config.random_seed,
            }
        )

    return pd.DataFrame(rows, columns=settings.CUSTOMER_MASTER_COLUMNS)


def generate_monthly_snapshots(
    customer_master: pd.DataFrame,
    config: GeneratorConfig,
) -> pd.DataFrame:
    """Generate monthly financial snapshots for every customer."""

    rows: list[dict[str, object]] = []
    for row in customer_master.itertuples(index=False):
        state = CustomerState(
            customer_id=row.customer_id,
            persona=row.persona,
            initial_income=int(row.initial_income),
            initial_cash_balance=int(row.initial_cash_balance),
            initial_loan_balance=int(row.initial_loan_balance),
            base_fixed_expense=int(row.base_fixed_expense),
            base_variable_expense=int(row.base_variable_expense),
            base_debt_payment=int(row.base_debt_payment),
            primary_event_type=row.primary_event_type,
            primary_event_month=int(row.primary_event_month),
        )
        rows.extend(_simulate_customer_months(state, config))

    monthly_df = pd.DataFrame(rows, columns=settings.CUSTOMER_MONTHLY_COLUMNS)
    return assign_final_outcomes(monthly_df, config)


def assign_final_outcomes(
    monthly_df: pd.DataFrame,
    config: GeneratorConfig,
) -> pd.DataFrame:
    """Assign final outcomes from months 13 through 36 only."""

    output = monthly_df.copy()
    future_mask = output["month"].between(config.future_start_month, config.future_end_month)
    outcome_by_customer: dict[str, str] = {}
    for customer_id, group in output.loc[future_mask].groupby("customer_id", sort=False):
        outcome_by_customer[customer_id] = classify_final_outcome(group, config)

    output["final_outcome"] = output["customer_id"].map(outcome_by_customer)
    return output[list(settings.CUSTOMER_MONTHLY_COLUMNS)]


def generate_dataset(config: GeneratorConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate customer master and monthly snapshot dataframes."""

    master_df = generate_customer_master(config)
    monthly_df = generate_monthly_snapshots(master_df, config)
    return master_df, monthly_df


def save_dataset(
    master_df: pd.DataFrame,
    monthly_df: pd.DataFrame,
    config: GeneratorConfig,
) -> tuple[Path, Path]:
    """Save generated dataframes to configured CSV paths."""

    ensure_output_directories(config)
    master_path = Path(config.customer_master_path)
    monthly_path = Path(config.customer_monthly_path)
    master_df.to_csv(master_path, index=False, encoding="utf-8")
    monthly_df.to_csv(monthly_path, index=False, encoding="utf-8")
    return master_path, monthly_path


def classify_monthly_status(history: list[dict[str, object]]) -> str:
    """Classify the latest monthly row using BUSINESS_RULES priority order."""

    current = history[-1]
    recent_2 = history[-2:]
    recent_3 = history[-3:]
    recent_6 = history[-6:]

    if current["delinquency_flag"] == 1 or (
        len(recent_2) == 2
        and all(float(row["cash_balance"]) < -2_000_000 for row in recent_2)
        and float(current["debt_payment"]) > 0
    ):
        return "delinquent"

    if (
        float(current["cash_balance"]) < 0
        or (len(recent_3) == 3 and all(float(row["savings_amount"]) < 0 for row in recent_3))
        or float(current["dsr"]) >= 0.45
        or float(current["emergency_months"]) < 1
        or float(current["fixed_expense_ratio"]) >= 0.55
        or (
            len(recent_3) == 3
            and sum(float(row["balance_change_rate"]) for row in recent_3) <= -0.30
        )
    ):
        return "stress"

    if (
        float(current["savings_rate"]) < 0.05
        or float(current["dsr"]) >= 0.35
        or float(current["emergency_months"]) < 3
        or (
            len(recent_3) == 3
            and all(float(row["balance_change_rate"]) < 0 for row in recent_3)
        )
        or float(current["fixed_expense_ratio"]) >= 0.45
        or sum(1 for row in recent_6 if float(row["savings_amount"]) < 0) >= 2
    ):
        return "watch"

    return "healthy"


def classify_final_outcome(future_df: pd.DataFrame, config: GeneratorConfig) -> str:
    """Classify a customer's final outcome from future monthly rows."""

    future_df = future_df.sort_values("month")
    statuses = future_df["monthly_status"].tolist()
    last_3 = future_df.tail(3)
    stress_count = statuses.count("stress")

    if "delinquent" in statuses:
        return "delinquent"

    if (
        stress_count >= 2
        and (last_3["monthly_status"] == "healthy").all()
        and float(last_3["savings_rate"].mean()) >= 0.05
        and int(last_3.iloc[-1]["cash_balance"]) >= 0
    ):
        return "recovered"

    last_3_stress_or_watch = last_3["monthly_status"].isin(["stress", "watch"]).sum()
    if (
        stress_count >= 6
        or last_3_stress_or_watch >= 2
        or int(last_3.iloc[-1]["cash_balance"]) < 0
        or float(last_3["dsr"].mean()) >= 0.45
    ):
        return "stress"

    return "healthy"


def _build_persona_assignments(config: GeneratorConfig, rng: np.random.Generator) -> np.ndarray:
    counts = {
        persona: int(config.customer_count * ratio)
        for persona, ratio in config.persona_distribution.items()
    }
    assigned = sum(counts.values())
    remainder = config.customer_count - assigned
    if remainder:
        personas = list(config.persona_distribution)
        for persona in personas[:remainder]:
            counts[persona] += 1

    values: list[str] = []
    for persona in settings.PERSONAS:
        values.extend([persona] * counts[persona])
    assignments = np.array(values, dtype=object)
    rng.shuffle(assignments)
    return assignments


def _generate_initial_incomes(count: int, rng: np.random.Generator) -> np.ndarray:
    raw = rng.lognormal(mean=np.log(4_500_000), sigma=0.35, size=count)
    return np.clip(np.round(raw), settings.INCOME_MIN, settings.INCOME_MAX).astype(int)


def _persona_no_loan_probability(persona: str) -> float:
    if persona in {"stable", "recovery"}:
        return 0.30
    return 0.15


def _persona_cash_month_range(persona: str) -> tuple[float, float]:
    if persona == "stable":
        return 4.0, 12.0
    if persona == "recovery":
        return 2.0, 8.0
    if persona == "overspending":
        return 1.0, 4.0
    if persona == "event_shock":
        return 1.0, 5.0
    return 1.0, 6.0


def _persona_initial_ratio_ranges(
    persona: str,
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    if persona == "stable":
        return (0.20, 0.35), (0.15, 0.30), (0.05, 0.25)
    if persona == "gradual_deterioration":
        return (0.28, 0.45), (0.25, 0.40), (0.10, 0.35)
    if persona == "event_shock":
        return (0.25, 0.42), (0.20, 0.35), (0.10, 0.32)
    if persona == "recovery":
        return (0.25, 0.42), (0.20, 0.35), (0.08, 0.30)
    return (0.25, 0.43), (0.30, 0.40), (0.12, 0.35)


def _choose_primary_event(persona: str, rng: np.random.Generator) -> tuple[str, int]:
    if persona == "event_shock":
        event_type = str(
            rng.choice(
                [
                    "job_loss",
                    "childbirth",
                    "medical_cost",
                    "housing_cost_increase",
                    "interest_rate_shock",
                ]
            )
        )
        return event_type, int(rng.integers(8, 29))
    if persona == "recovery":
        return str(rng.choice(["income_recovery", "expense_reduction"])), int(rng.integers(14, 27))
    if persona == "overspending" and rng.random() < 0.45:
        return "new_loan", int(rng.integers(13, 31))
    return "none", 0


def _simulate_customer_months(
    state: CustomerState,
    config: GeneratorConfig,
) -> list[dict[str, object]]:
    customer_seed = config.random_seed + int(state.customer_id[1:])
    rng = np.random.default_rng(customer_seed)
    loan_balance = state.initial_loan_balance
    cash_balance = state.initial_cash_balance
    previous_income = state.initial_income
    previous_total_expense = (
        state.base_fixed_expense + state.base_variable_expense + state.base_debt_payment
    )
    previous_cash_balance = state.initial_cash_balance
    history: list[dict[str, object]] = []

    trend = _persona_trend_parameters(state.persona, rng)
    shock_duration = int(rng.integers(3, 9))
    recovery_start = int(rng.integers(12, 19)) if state.persona == "recovery" else 0
    recovery_duration = int(rng.integers(3, 9)) if state.persona == "recovery" else 0

    for month in range(1, config.total_months + 1):
        month_index = month - 1
        income = state.initial_income * (1 + trend["income_growth"]) ** month_index
        fixed_expense = state.base_fixed_expense * (1 + trend["fixed_growth"]) ** month_index
        variable_expense = state.base_variable_expense * (1 + trend["variable_growth"]) ** month_index
        debt_payment = state.base_debt_payment * (1 + trend["debt_growth"]) ** month_index
        event_expense = 0.0
        event_type = "none"
        new_loan_amount = 0.0

        income *= rng.uniform(0.97, 1.03)
        fixed_expense *= rng.uniform(0.99, 1.02)
        variable_expense *= rng.uniform(0.92, 1.12)

        if state.persona == "event_shock" and state.primary_event_month:
            event_type, event_expense, new_loan_amount, income, fixed_expense, debt_payment = (
                _apply_event_shock(
                    state,
                    month,
                    shock_duration,
                    income,
                    fixed_expense,
                    debt_payment,
                    event_expense,
                )
            )
        elif state.persona == "recovery":
            income, fixed_expense, variable_expense = _apply_recovery_pattern(
                month,
                recovery_start,
                recovery_duration,
                income,
                fixed_expense,
                variable_expense,
            )
            if month == state.primary_event_month:
                event_type = state.primary_event_type
        elif state.persona == "overspending":
            if state.primary_event_type == "new_loan" and month == state.primary_event_month:
                event_type = "new_loan"
                new_loan_amount = state.initial_income * rng.uniform(3.0, 8.0)
            if month >= config.future_start_month:
                variable_expense *= 1.15

        income = max(0, int(round(income)))
        fixed_expense = max(0, int(round(fixed_expense)))
        variable_expense = max(0, int(round(variable_expense)))
        debt_payment = max(0, int(round(min(debt_payment, loan_balance * 0.20 if loan_balance else 0))))
        event_expense = max(0, int(round(event_expense)))
        new_loan_amount = max(0, int(round(new_loan_amount)))
        if income > 0:
            fixed_expense = min(fixed_expense, income)
            variable_expense = min(variable_expense, income)
            debt_payment = min(debt_payment, income)

        total_expense = fixed_expense + variable_expense + debt_payment + event_expense
        savings_amount = income - total_expense
        cash_balance = int(round(cash_balance + savings_amount))
        principal_repayment = min(int(round(debt_payment * 0.70)), loan_balance)
        loan_balance = int(max(0, loan_balance - principal_repayment + new_loan_amount))

        ratios = _calculate_ratios(
            income,
            savings_amount,
            fixed_expense,
            variable_expense,
            debt_payment,
            loan_balance,
            cash_balance,
        )
        income_change_rate = _change_rate(income, previous_income)
        expense_change_rate = _change_rate(total_expense, previous_total_expense)
        balance_change_rate = _change_rate(cash_balance, previous_cash_balance)
        delinquency_flag = int(
            month >= config.future_start_month
            and loan_balance > 0
            and cash_balance < -2_000_000
            and debt_payment > 0
            and (ratios["dsr"] >= 0.30 or cash_balance < -6_000_000)
        )

        row: dict[str, object] = {
            "customer_id": state.customer_id,
            "month": month,
            "persona": state.persona,
            "income": income,
            "fixed_expense": fixed_expense,
            "variable_expense": variable_expense,
            "debt_payment": debt_payment,
            "event_expense": event_expense,
            "total_expense": total_expense,
            "savings_amount": savings_amount,
            "savings_rate": ratios["savings_rate"],
            "fixed_expense_ratio": ratios["fixed_expense_ratio"],
            "variable_expense_ratio": ratios["variable_expense_ratio"],
            "dsr": ratios["dsr"],
            "cash_balance": cash_balance,
            "loan_balance": loan_balance,
            "debt_to_income_ratio": ratios["debt_to_income_ratio"],
            "emergency_months": ratios["emergency_months"],
            "income_change_rate": income_change_rate,
            "expense_change_rate": expense_change_rate,
            "balance_change_rate": balance_change_rate,
            "event_type": event_type,
            "delinquency_flag": delinquency_flag,
            "monthly_status": "healthy",
            "final_outcome": "healthy",
        }
        history.append(row)
        row["monthly_status"] = classify_monthly_status(history)

        previous_income = income
        previous_total_expense = total_expense
        previous_cash_balance = cash_balance

    return history


def _persona_trend_parameters(persona: str, rng: np.random.Generator) -> dict[str, float]:
    if persona == "stable":
        return {
            "income_growth": rng.uniform(0.0008, 0.0040),
            "fixed_growth": rng.uniform(0.0, 0.0025),
            "variable_growth": rng.uniform(-0.0010, 0.0025),
            "debt_growth": rng.uniform(-0.0020, 0.0),
        }
    if persona == "gradual_deterioration":
        return {
            "income_growth": rng.uniform(-0.0005, 0.0005),
            "fixed_growth": rng.uniform(0.0010, 0.0035),
            "variable_growth": rng.uniform(0.0100, 0.0200),
            "debt_growth": rng.uniform(0.0, 0.0010),
        }
    if persona == "overspending":
        return {
            "income_growth": rng.uniform(-0.0002, 0.0010),
            "fixed_growth": rng.uniform(0.0010, 0.0030),
            "variable_growth": rng.uniform(0.0120, 0.0240),
            "debt_growth": rng.uniform(0.0, 0.0010),
        }
    if persona == "recovery":
        return {
            "income_growth": rng.uniform(0.0003, 0.0020),
            "fixed_growth": rng.uniform(0.0005, 0.0020),
            "variable_growth": rng.uniform(0.0010, 0.0040),
            "debt_growth": rng.uniform(-0.0010, 0.0),
        }
    return {
        "income_growth": rng.uniform(-0.0005, 0.0010),
        "fixed_growth": rng.uniform(0.0010, 0.0035),
        "variable_growth": rng.uniform(0.0010, 0.0050),
        "debt_growth": rng.uniform(0.0, 0.0020),
    }


def _apply_event_shock(
    state: CustomerState,
    month: int,
    shock_duration: int,
    income: float,
    fixed_expense: float,
    debt_payment: float,
    event_expense: float,
) -> tuple[str, float, float, float, float, float]:
    event_type = "none"
    new_loan_amount = 0.0
    event_month = state.primary_event_month
    if event_month <= month < event_month + shock_duration:
        event_type = state.primary_event_type
        if event_type == "job_loss":
            income *= 0.10
        elif event_type == "interest_rate_shock":
            debt_payment *= 1.50
        elif event_type == "housing_cost_increase":
            fixed_expense += 800_000
        elif event_type == "childbirth" and month == event_month:
            event_expense += 8_000_000
            fixed_expense += 500_000
        elif event_type == "medical_cost" and month == event_month:
            event_expense += 15_000_000
        if event_type in {"medical_cost", "childbirth"} and month == event_month:
            new_loan_amount = state.initial_income * 2.0
    return event_type, event_expense, new_loan_amount, income, fixed_expense, debt_payment


def _apply_recovery_pattern(
    month: int,
    recovery_start: int,
    recovery_duration: int,
    income: float,
    fixed_expense: float,
    variable_expense: float,
) -> tuple[float, float, float]:
    if 8 <= month < recovery_start:
        income *= 0.75
        variable_expense *= 1.25
    elif recovery_start <= month < recovery_start + recovery_duration:
        income *= 0.96
        variable_expense *= 0.96
    elif month >= recovery_start + recovery_duration:
        income *= 1.05
        fixed_expense *= 0.90
        variable_expense *= 0.85
    return income, fixed_expense, variable_expense


def _calculate_ratios(
    income: int,
    savings_amount: int,
    fixed_expense: int,
    variable_expense: int,
    debt_payment: int,
    loan_balance: int,
    cash_balance: int,
) -> dict[str, float]:
    if income > 0:
        savings_rate = savings_amount / income
        fixed_expense_ratio = fixed_expense / income
        variable_expense_ratio = variable_expense / income
        dsr = debt_payment / income
        debt_to_income_ratio = loan_balance / income
    else:
        savings_rate = -1.0
        fixed_expense_ratio = 1.0
        variable_expense_ratio = 1.0
        dsr = 1.0
        debt_to_income_ratio = 0.0

    living_expense = fixed_expense + variable_expense
    emergency_months = max(cash_balance, 0) / max(living_expense, 1)
    return {
        "savings_rate": round(float(savings_rate), 6),
        "fixed_expense_ratio": round(float(fixed_expense_ratio), 6),
        "variable_expense_ratio": round(float(variable_expense_ratio), 6),
        "dsr": round(float(dsr), 6),
        "debt_to_income_ratio": round(float(debt_to_income_ratio), 6),
        "emergency_months": round(float(emergency_months), 6),
    }


def _change_rate(current: int, previous: int) -> float:
    if previous > 0:
        return round(float((current - previous) / previous), 6)
    return 0.0
