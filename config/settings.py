"""Project-wide settings for Financial Path Twin.

This module intentionally contains constants only. Generation, validation,
matching, and UI logic should live in their own modules.
"""

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]

RANDOM_SEED = 42
CUSTOMER_COUNT = 5000
TOTAL_MONTHS = 36
OBSERVATION_START_MONTH = 1
OBSERVATION_END_MONTH = 12
FUTURE_START_MONTH = 13
FUTURE_END_MONTH = 36
TOP_K_MATCHES = 200

DATA_RAW_DIR = BASE_DIR / "data" / "raw"
DATA_PROCESSED_DIR = BASE_DIR / "data" / "processed"
DATA_DEMO_DIR = BASE_DIR / "data" / "demo"
REPORTS_DIR = BASE_DIR / "reports"
CHARTS_DIR = REPORTS_DIR / "charts"
DATA_VALIDATION_REPORT_PATH = REPORTS_DIR / "data_validation_report.csv"
PERSONA_SUMMARY_PATH = REPORTS_DIR / "persona_summary.csv"
OUTCOME_DISTRIBUTION_PATH = REPORTS_DIR / "outcome_distribution.csv"

CUSTOMER_MASTER_FILENAME = "customer_master.csv"
CUSTOMER_MONTHLY_FILENAME = "customer_monthly_5000.csv"
CUSTOMER_MASTER_PATH = DATA_RAW_DIR / CUSTOMER_MASTER_FILENAME
CUSTOMER_MONTHLY_PATH = DATA_RAW_DIR / CUSTOMER_MONTHLY_FILENAME
TRAJECTORY_FEATURES_FILENAME = "trajectory_features.csv"
TRAJECTORY_FEATURES_PATH = DATA_PROCESSED_DIR / TRAJECTORY_FEATURES_FILENAME
WHATIF_RESULTS_FILENAME = "whatif_results.json"
WHATIF_RESULTS_PATH = DATA_PROCESSED_DIR / WHATIF_RESULTS_FILENAME
DEMO_CUSTOMERS_FILENAME = "demo_customers.csv"
MAIN_DEMO_CUSTOMER_FILENAME = "main_demo_customer.json"
MATCHED_CUSTOMERS_FILENAME = "matched_customers.csv"
MATCHED_FUTURE_TRAJECTORY_FILENAME = "matched_future_trajectory.csv"
OUTCOME_SUMMARY_FILENAME = "outcome_summary.json"
BREAKPOINT_RESULT_FILENAME = "breakpoint_result.json"
DEMO_CUSTOMERS_PATH = DATA_DEMO_DIR / DEMO_CUSTOMERS_FILENAME
MAIN_DEMO_CUSTOMER_PATH = DATA_DEMO_DIR / MAIN_DEMO_CUSTOMER_FILENAME
DEMO_MATCHED_CUSTOMERS_PATH = DATA_DEMO_DIR / MATCHED_CUSTOMERS_FILENAME
DEMO_MATCHED_FUTURE_TRAJECTORY_PATH = DATA_DEMO_DIR / MATCHED_FUTURE_TRAJECTORY_FILENAME
DEMO_OUTCOME_SUMMARY_PATH = DATA_DEMO_DIR / OUTCOME_SUMMARY_FILENAME
DEMO_BREAKPOINT_RESULT_PATH = DATA_DEMO_DIR / BREAKPOINT_RESULT_FILENAME
DEMO_WHATIF_RESULTS_PATH = DATA_DEMO_DIR / WHATIF_RESULTS_FILENAME
DEMO_BACKUP_DIR = REPORTS_DIR / "demo_backup"

PERSONAS = (
    "stable",
    "gradual_deterioration",
    "event_shock",
    "recovery",
    "overspending",
    "self_employed",
    "asset_resilient",
    "financially_constrained",
)

PERSONA_DISTRIBUTION = {
    "stable": 0.20,
    "gradual_deterioration": 0.15,
    "event_shock": 0.15,
    "recovery": 0.12,
    "overspending": 0.13,
    "self_employed": 0.12,
    "asset_resilient": 0.08,
    "financially_constrained": 0.05,
}

EVENT_TYPES = (
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
)

MONTHLY_STATUSES = ("healthy", "watch", "stress", "delinquent")
FINAL_OUTCOMES = ("healthy", "recovered", "stress", "delinquent")

AGE_GROUPS = ("20s", "30s", "40s", "50s", "60s")
HOUSEHOLD_TYPES = (
    "single",
    "couple",
    "family_with_children",
    "single_parent",
    "senior_household",
)

CUSTOMER_MASTER_COLUMNS = (
    "customer_id",
    "persona",
    "age_group",
    "household_type",
    "initial_income",
    "initial_cash_balance",
    "initial_loan_balance",
    "base_fixed_expense",
    "base_variable_expense",
    "base_debt_payment",
    "primary_event_type",
    "primary_event_month",
    "random_seed",
)

CUSTOMER_MONTHLY_COLUMNS = (
    "customer_id",
    "month",
    "persona",
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
    "event_type",
    "delinquency_flag",
    "monthly_status",
    "final_outcome",
)

TRAJECTORY_FEATURE_COLUMNS = (
    "customer_id",
    "avg_savings_rate_3m",
    "avg_dsr_3m",
    "avg_fixed_expense_ratio_3m",
    "savings_rate_slope_12m",
    "expense_growth_12m",
    "dsr_change_12m",
    "balance_change_ratio_12m",
    "income_cv_12m",
    "expense_cv_12m",
    "max_consecutive_balance_decline_12m",
    "recent_negative_savings_months_6m",
    "recent_large_expense_count_12m",
)

INCOME_MIN = 1_500_000
INCOME_MAX = 20_000_000
CASH_BALANCE_MIN = 500_000
CASH_BALANCE_MAX = 250_000_000
NO_LOAN_PROBABILITY = 0.25

MATCH_FEATURES = (
    "avg_savings_rate_3m",
    "avg_dsr_3m",
    "avg_fixed_expense_ratio_3m",
    "savings_rate_slope_12m",
    "expense_growth_12m",
    "dsr_change_12m",
    "balance_change_ratio_12m",
    "income_cv_12m",
    "expense_cv_12m",
    "max_consecutive_balance_decline_12m",
)

MATCH_WEIGHTS = {
    "avg_savings_rate_3m": 1.4,
    "avg_dsr_3m": 1.4,
    "avg_fixed_expense_ratio_3m": 1.2,
    "savings_rate_slope_12m": 1.4,
    "expense_growth_12m": 1.1,
    "dsr_change_12m": 1.2,
    "balance_change_ratio_12m": 1.3,
    "income_cv_12m": 0.8,
    "expense_cv_12m": 0.8,
    "max_consecutive_balance_decline_12m": 1.0,
}

BREAKPOINT_EFFECT_THRESHOLD = 0.5
BREAKPOINT_PERSISTENCE_MONTHS = 2
BREAKPOINT_MIN_GROUP_SIZE = 20

WHATIF_SIMULATION_MONTHS = 24
WHATIF_INCOME_MONTHLY_GROWTH = 0.0
WHATIF_FIXED_EXPENSE_MONTHLY_GROWTH = 0.0015
WHATIF_VARIABLE_EXPENSE_MONTHLY_GROWTH = 0.0020
WHATIF_DEBT_PAYMENT_MONTHLY_GROWTH = 0.0

WHATIF_SCENARIOS = (
    {
        "scenario_id": 1,
        "scenario_name": "baseline",
        "fixed_expense_delta": 0,
        "variable_expense_multiplier": 1.0,
        "debt_payment_multiplier": 1.0,
    },
    {
        "scenario_id": 2,
        "scenario_name": "variable_expense_cut_15",
        "fixed_expense_delta": 0,
        "variable_expense_multiplier": 0.85,
        "debt_payment_multiplier": 1.0,
    },
    {
        "scenario_id": 3,
        "scenario_name": "fixed_expense_cut_300k",
        "fixed_expense_delta": -300_000,
        "variable_expense_multiplier": 1.0,
        "debt_payment_multiplier": 1.0,
    },
    {
        "scenario_id": 4,
        "scenario_name": "debt_payment_cut_20",
        "fixed_expense_delta": 0,
        "variable_expense_multiplier": 1.0,
        "debt_payment_multiplier": 0.80,
    },
)

DEMO_ROLES = ("main", "stable_comparison", "high_risk")
DEMO_CUSTOMER_COLUMNS = (
    "demo_role",
    "customer_id",
    "demo_score",
    "current_status",
    "recent_savings_rate",
    "recent_dsr",
    "recent_fixed_expense_ratio",
    "matched_count",
    "healthy_ratio",
    "recovered_ratio",
    "stress_ratio",
    "delinquent_ratio",
    "risk_group_ratio",
    "breakpoint_status",
    "breakpoint_month",
    "months_from_current",
    "primary_factor",
    "best_scenario_id",
    "best_scenario_improvement",
    "selection_reason",
)

DEMO_MAIN_SCORE_WEIGHTS = {
    "breakpoint_found": 25.0,
    "breakpoint_month_13_16": 15.0,
    "risk_ratio_target": 15.0,
    "current_status_watch": 10.0,
    "savings_rate_decline": 10.0,
    "dsr_risk_approach": 8.0,
    "fixed_expense_risk_approach": 8.0,
    "whatif_improvement": 6.0,
    "outcome_balance": 3.0,
}

REQUIRED_DIRECTORIES = (
    DATA_RAW_DIR,
    DATA_PROCESSED_DIR,
    DATA_DEMO_DIR,
    REPORTS_DIR,
    CHARTS_DIR,
    BASE_DIR / "scripts",
    BASE_DIR / "src",
    BASE_DIR / "tests",
)
