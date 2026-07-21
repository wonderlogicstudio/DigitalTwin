"""Pydantic models for Financial Path Twin data contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from config import settings


Persona = Literal[
    "stable",
    "gradual_deterioration",
    "event_shock",
    "recovery",
    "overspending",
]
EventType = Literal[
    "none",
    "job_loss",
    "job_change",
    "childbirth",
    "medical_cost",
    "housing_cost_increase",
    "interest_rate_shock",
    "income_recovery",
    "expense_reduction",
    "new_loan",
]
MonthlyStatus = Literal["healthy", "watch", "stress", "delinquent"]
FinalOutcome = Literal["healthy", "recovered", "stress", "delinquent"]
BreakpointStatus = Literal["found", "not_found", "insufficient_group_size"]
ScenarioName = Literal[
    "baseline",
    "variable_expense_cut_15",
    "fixed_expense_cut_300k",
    "debt_payment_cut_20",
]


class ProjectModel(BaseModel):
    """Base model with strict assignment validation."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")


class GeneratorConfig(ProjectModel):
    """Configuration values used by synthetic data generation."""

    random_seed: int = settings.RANDOM_SEED
    customer_count: int = Field(default=settings.CUSTOMER_COUNT, gt=0)
    total_months: int = Field(default=settings.TOTAL_MONTHS, gt=0)
    observation_end_month: int = Field(default=settings.OBSERVATION_END_MONTH, gt=0)
    future_start_month: int = Field(default=settings.FUTURE_START_MONTH, gt=0)
    future_end_month: int = Field(default=settings.FUTURE_END_MONTH, gt=0)
    top_k_matches: int = Field(default=settings.TOP_K_MATCHES, gt=0)
    persona_distribution: dict[str, float] = Field(
        default_factory=lambda: dict(settings.PERSONA_DISTRIBUTION)
    )
    customer_master_path: str = str(settings.CUSTOMER_MASTER_PATH)
    customer_monthly_path: str = str(settings.CUSTOMER_MONTHLY_PATH)

    @field_validator("persona_distribution")
    @classmethod
    def validate_persona_distribution(cls, value: dict[str, float]) -> dict[str, float]:
        if set(value) != set(settings.PERSONAS):
            raise ValueError("persona_distribution must include all configured personas")
        if any(ratio < 0 for ratio in value.values()):
            raise ValueError("persona ratios must be non-negative")
        if abs(sum(value.values()) - 1.0) > 1e-9:
            raise ValueError("persona ratios must sum to 1.0")
        return value


class CustomerProfile(ProjectModel):
    """One row of customer master data."""

    customer_id: str = Field(pattern=r"^C\d{6}$")
    persona: Persona
    age_group: str
    household_type: str
    initial_income: int = Field(ge=0)
    initial_cash_balance: int = Field(ge=0)
    initial_loan_balance: int = Field(ge=0)
    base_fixed_expense: int = Field(ge=0)
    base_variable_expense: int = Field(ge=0)
    base_debt_payment: int = Field(ge=0)
    primary_event_type: EventType = "none"
    primary_event_month: int = Field(default=0, ge=0, le=settings.TOTAL_MONTHS)
    random_seed: int


class MonthlySnapshot(ProjectModel):
    """One customer-month financial snapshot."""

    customer_id: str = Field(pattern=r"^C\d{6}$")
    month: int = Field(ge=1, le=settings.TOTAL_MONTHS)
    persona: Persona
    income: int = Field(ge=0)
    fixed_expense: int = Field(ge=0)
    variable_expense: int = Field(ge=0)
    debt_payment: int = Field(ge=0)
    event_expense: int = Field(ge=0)
    total_expense: int = Field(ge=0)
    savings_amount: int
    savings_rate: float
    fixed_expense_ratio: float = Field(ge=0)
    variable_expense_ratio: float = Field(ge=0)
    dsr: float = Field(ge=0)
    cash_balance: int
    loan_balance: int = Field(ge=0)
    debt_to_income_ratio: float = Field(ge=0)
    emergency_months: float = Field(ge=0)
    income_change_rate: float
    expense_change_rate: float
    balance_change_rate: float
    event_type: EventType = "none"
    delinquency_flag: int = Field(ge=0, le=1)
    monthly_status: MonthlyStatus
    final_outcome: FinalOutcome


class MatchResult(ProjectModel):
    """A matched customer returned by the trajectory matcher."""

    target_customer_id: str = Field(pattern=r"^C\d{6}$")
    matched_customer_id: str = Field(pattern=r"^C\d{6}$")
    rank: int = Field(ge=1)
    distance: float = Field(ge=0)
    similarity_score: float = Field(ge=0, le=1)
    matched_final_outcome: FinalOutcome
    matched_persona: Persona


class OutcomeBucket(ProjectModel):
    """Count and ratio for a single final outcome."""

    count: int = Field(ge=0)
    ratio: float = Field(ge=0, le=1)


class OutcomeSummary(ProjectModel):
    """Future outcome aggregation for a target customer."""

    target_customer_id: str = Field(pattern=r"^C\d{6}$")
    matched_count: int = Field(ge=0)
    outcomes: dict[FinalOutcome, OutcomeBucket]
    first_stress_month_median: int | None = Field(default=None, ge=1, le=settings.TOTAL_MONTHS)
    first_delinquency_month_median: int | None = Field(
        default=None, ge=1, le=settings.TOTAL_MONTHS
    )


class BreakpointResult(ProjectModel):
    """Detected separation point between risk and avoidance groups."""

    status: BreakpointStatus
    breakpoint_month: int | None = Field(default=None, ge=1, le=settings.TOTAL_MONTHS)
    months_from_current: int | None = None
    primary_factor: str | None = None
    risk_group_mean: float | None = None
    avoidance_group_mean: float | None = None
    standardized_difference: float | None = None
    persistence_months: int = Field(default=settings.BREAKPOINT_PERSISTENCE_MONTHS, ge=0)
    secondary_factors: list[dict[str, str | int | float]] = Field(default_factory=list)
    interpretation: str = ""


class WhatIfScenario(ProjectModel):
    """A supported what-if scenario definition."""

    scenario_id: int = Field(default=1, ge=1)
    name: ScenarioName
    fixed_expense_delta: int = 0
    variable_expense_multiplier: float = Field(default=1.0, ge=0)
    debt_payment_multiplier: float = Field(default=1.0, ge=0)


class WhatIfResult(ProjectModel):
    """Summary metrics for a simulated what-if scenario."""

    scenario_id: int = Field(default=1, ge=1)
    scenario_name: ScenarioName
    ending_cash_balance: float
    minimum_cash_balance: float
    average_savings_rate: float
    cash_depletion_month: int | None = Field(default=None, ge=1, le=24)
    improvement_vs_baseline: float
    total_saved_expense: float = 0.0
    months_with_negative_savings: int = Field(ge=0, le=24)
    monthly_data: list[dict[str, int | float | str | None]] = Field(default_factory=list)
