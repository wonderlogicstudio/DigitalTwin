from pathlib import Path

from config import settings
from src.models import (
    BreakpointResult,
    CustomerProfile,
    GeneratorConfig,
    MatchResult,
    MonthlySnapshot,
    OutcomeBucket,
    OutcomeSummary,
    WhatIfResult,
    WhatIfScenario,
)


def test_required_project_directories_exist() -> None:
    for directory in settings.REQUIRED_DIRECTORIES:
        assert directory.exists()
        assert directory.is_dir()


def test_requirements_match_documented_bootstrap_dependencies() -> None:
    requirements = (settings.BASE_DIR / "requirements.txt").read_text().splitlines()

    assert requirements == [
        "pandas>=2.2,<3.0",
        "numpy>=1.26,<3.0",
        "scikit-learn>=1.5,<2.0",
        "streamlit>=1.36,<2.0",
        "plotly>=5.22,<7.0",
        "pytest>=8.2,<9.0",
        "pydantic>=2.7,<3.0",
    ]


def test_settings_follow_documented_business_constants() -> None:
    assert settings.RANDOM_SEED == 42
    assert settings.CUSTOMER_COUNT == 5000
    assert settings.TOTAL_MONTHS == 36
    assert settings.OBSERVATION_END_MONTH == 12
    assert settings.FUTURE_START_MONTH == 13
    assert settings.FUTURE_END_MONTH == 36
    assert settings.TOP_K_MATCHES == 200
    assert sum(settings.PERSONA_DISTRIBUTION.values()) == 1.0


def test_basic_pydantic_models_validate_documented_shapes() -> None:
    config = GeneratorConfig()
    assert config.customer_count == settings.CUSTOMER_COUNT

    customer = CustomerProfile(
        customer_id="C000001",
        persona="stable",
        age_group="40s",
        household_type="single",
        initial_income=4_500_000,
        initial_cash_balance=12_000_000,
        initial_loan_balance=20_000_000,
        base_fixed_expense=1_500_000,
        base_variable_expense=1_000_000,
        base_debt_payment=500_000,
        random_seed=42,
    )
    assert customer.primary_event_type == "none"

    snapshot = MonthlySnapshot(
        customer_id="C000001",
        month=12,
        persona="stable",
        income=4_500_000,
        fixed_expense=1_500_000,
        variable_expense=1_000_000,
        debt_payment=500_000,
        event_expense=0,
        total_expense=3_000_000,
        savings_amount=1_500_000,
        savings_rate=0.3333,
        fixed_expense_ratio=0.3333,
        variable_expense_ratio=0.2222,
        dsr=0.1111,
        cash_balance=13_500_000,
        loan_balance=19_650_000,
        debt_to_income_ratio=4.3667,
        emergency_months=5.4,
        income_change_rate=0.0,
        expense_change_rate=0.0,
        balance_change_rate=0.0,
        delinquency_flag=0,
        monthly_status="healthy",
        final_outcome="healthy",
    )
    assert snapshot.month == settings.OBSERVATION_END_MONTH

    match = MatchResult(
        target_customer_id="C000001",
        matched_customer_id="C000002",
        rank=1,
        distance=0.1,
        similarity_score=0.909,
        matched_final_outcome="stress",
        matched_persona="event_shock",
    )
    assert match.rank == 1

    summary = OutcomeSummary(
        target_customer_id="C000001",
        matched_count=200,
        outcomes={
            "healthy": OutcomeBucket(count=100, ratio=0.5),
            "recovered": OutcomeBucket(count=20, ratio=0.1),
            "stress": OutcomeBucket(count=60, ratio=0.3),
            "delinquent": OutcomeBucket(count=20, ratio=0.1),
        },
        first_stress_month_median=18,
    )
    assert summary.outcomes["healthy"].ratio == 0.5

    breakpoint = BreakpointResult(
        status="found",
        breakpoint_month=14,
        months_from_current=2,
        primary_factor="fixed_expense_ratio",
        risk_group_mean=0.47,
        avoidance_group_mean=0.36,
        standardized_difference=0.72,
    )
    assert breakpoint.persistence_months == settings.BREAKPOINT_PERSISTENCE_MONTHS

    scenario = WhatIfScenario(name="variable_expense_cut_15", variable_expense_multiplier=0.85)
    result = WhatIfResult(
        scenario_name=scenario.name,
        ending_cash_balance=10_000_000,
        minimum_cash_balance=7_500_000,
        average_savings_rate=0.12,
        improvement_vs_baseline=800_000,
        months_with_negative_savings=0,
    )
    assert result.scenario_name == "variable_expense_cut_15"


def test_app_contains_streamlit_mvp_entrypoint() -> None:
    app_source = (settings.BASE_DIR / "app.py").read_text(encoding="utf-8")
    copy_source = (settings.BASE_DIR / "src" / "copy.py").read_text(encoding="utf-8")

    assert "Financial Path Twin" in app_source
    assert "당신의 미래를 예측하지 않습니다" in app_source
    assert "BUTTON_LABELS" in app_source
    assert "유사 재무 흐름 찾기" in copy_source
    assert "generate_dataset" not in app_source
    assert "generate_customer_master" not in app_source
