"""External legacy contracts that must remain stable before new features."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from config import settings
from src.demo_cache import load_precomputed_demo_analysis
from src.matcher import TrajectoryMatcher
from src.pipeline import PipelineConfig, run_pipeline
from src.ui_components import run_customer_analysis


EXPECTED_MASTER_COLUMNS = (
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
EXPECTED_MONTHLY_COLUMNS = (
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
EXPECTED_FEATURE_COLUMNS = (
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
EXPECTED_MATCH_FEATURES = (
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
EXPECTED_DEMO_COLUMNS = (
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
EXPECTED_MATCH_COLUMNS = (
    "target_customer_id",
    "matched_customer_id",
    "rank",
    "distance",
    "similarity_score",
)
EXPECTED_MATCHED_FUTURE_COLUMNS = (
    "target_customer_id",
    "matched_customer_id",
    "month",
    "savings_rate",
    "fixed_expense_ratio",
    "variable_expense_ratio",
    "dsr",
    "cash_balance",
    "cash_balance_ratio",
    "loan_balance",
    "loan_balance_ratio",
    "monthly_status",
    "final_outcome",
)


def _config(tmp_path: Path) -> PipelineConfig:
    return PipelineConfig(
        customer_count=100,
        random_seed=42,
        top_k=20,
        force=True,
        skip_generation=False,
        skip_validation=False,
        export_charts=False,
        customer_master_path=tmp_path / "data" / "raw" / "customer_master.csv",
        customer_monthly_path=tmp_path / "data" / "raw" / "customer_monthly_5000.csv",
        trajectory_features_path=tmp_path / "data" / "processed" / "trajectory_features.csv",
        reports_dir=tmp_path / "reports",
        data_processed_dir=tmp_path / "data" / "processed",
        data_demo_dir=tmp_path / "data" / "demo",
        charts_dir=tmp_path / "reports" / "charts",
    )


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_fixed_legacy_analytics_contract_values() -> None:
    assert (
        settings.RANDOM_SEED,
        settings.CUSTOMER_COUNT,
        settings.TOTAL_MONTHS,
        settings.OBSERVATION_START_MONTH,
        settings.OBSERVATION_END_MONTH,
        settings.FUTURE_START_MONTH,
        settings.FUTURE_END_MONTH,
        settings.TOP_K_MATCHES,
    ) == (42, 5_000, 36, 1, 12, 13, 36, 200)
    assert settings.TRAJECTORY_FEATURE_COLUMNS == EXPECTED_FEATURE_COLUMNS
    assert settings.MATCH_FEATURES == EXPECTED_MATCH_FEATURES
    assert settings.MATCH_WEIGHTS == {
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
    assert settings.BREAKPOINT_EFFECT_THRESHOLD == 0.5
    assert settings.BREAKPOINT_PERSISTENCE_MONTHS == 2
    assert settings.BREAKPOINT_MIN_GROUP_SIZE == 20
    assert settings.WHATIF_SIMULATION_MONTHS == 24
    assert (
        settings.WHATIF_INCOME_MONTHLY_GROWTH,
        settings.WHATIF_FIXED_EXPENSE_MONTHLY_GROWTH,
        settings.WHATIF_VARIABLE_EXPENSE_MONTHLY_GROWTH,
        settings.WHATIF_DEBT_PAYMENT_MONTHLY_GROWTH,
    ) == (0.0, 0.0015, 0.0020, 0.0)
    assert settings.WHATIF_SCENARIOS == (
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


def test_pipeline_artifacts_preserve_schema_cardinality_and_cached_live_parity(tmp_path: Path) -> None:
    config = _config(tmp_path)
    summary = run_pipeline(config)

    master = pd.read_csv(config.customer_master_path)
    monthly = pd.read_csv(config.customer_monthly_path)
    features = pd.read_csv(config.trajectory_features_path)
    demo = pd.read_csv(config.demo_customers_path)
    matches = pd.read_csv(config.data_demo_dir / settings.MATCHED_CUSTOMERS_FILENAME)
    matched_future = pd.read_csv(config.data_demo_dir / settings.MATCHED_FUTURE_TRAJECTORY_FILENAME)

    assert list(master.columns) == list(EXPECTED_MASTER_COLUMNS)
    assert list(monthly.columns) == list(EXPECTED_MONTHLY_COLUMNS)
    assert list(features.columns) == list(EXPECTED_FEATURE_COLUMNS)
    assert list(demo.columns) == list(EXPECTED_DEMO_COLUMNS)
    assert list(matches.columns) == list(EXPECTED_MATCH_COLUMNS)
    assert list(matched_future.columns) == list(EXPECTED_MATCHED_FUTURE_COLUMNS)

    assert len(master) == config.customer_count
    assert len(monthly) == config.customer_count * settings.TOTAL_MONTHS
    assert len(features) == config.customer_count
    assert monthly.groupby("customer_id")["month"].nunique().eq(settings.TOTAL_MONTHS).all()
    assert monthly["month"].between(settings.OBSERVATION_START_MONTH, settings.FUTURE_END_MONTH).all()
    assert set(master["random_seed"]) == {config.random_seed}
    assert (monthly["total_expense"] == monthly[["fixed_expense", "variable_expense", "debt_payment", "event_expense"]].sum(axis=1)).all()
    assert (monthly["savings_amount"] == monthly["income"] - monthly["total_expense"]).all()

    matcher = TrajectoryMatcher().fit(features)
    assert matcher.feature_names == EXPECTED_MATCH_FEATURES
    assert np.asarray(matcher.scaler.n_samples_seen_).min() == config.customer_count
    assert np.asarray(matcher.scaler.n_samples_seen_).max() == config.customer_count

    main_customer_id = str(summary["main_customer_id"])
    assert len(matches) == config.top_k
    assert matches["target_customer_id"].eq(main_customer_id).all()
    assert main_customer_id not in set(matches["matched_customer_id"].astype(str))
    assert matches["matched_customer_id"].is_unique
    assert matches["rank"].tolist() == list(range(1, config.top_k + 1))
    assert matches["distance"].is_monotonic_increasing
    assert len(matched_future) == config.top_k * (settings.FUTURE_END_MONTH - settings.FUTURE_START_MONTH + 1)
    assert matched_future["target_customer_id"].eq(main_customer_id).all()
    assert matched_future["month"].between(settings.FUTURE_START_MONTH, settings.FUTURE_END_MONTH).all()
    assert matched_future.groupby("matched_customer_id")["month"].nunique().eq(24).all()

    assert demo["demo_role"].tolist() == ["main", "stable_comparison", "high_risk"]
    assert demo["customer_id"].astype(str).is_unique
    assert demo["matched_count"].eq(config.top_k).all()

    main_demo = _read_json(config.main_demo_customer_path)
    outcome = _read_json(config.data_demo_dir / settings.OUTCOME_SUMMARY_FILENAME)
    breakpoint = _read_json(config.data_demo_dir / settings.BREAKPOINT_RESULT_FILENAME)
    whatif = _read_json(config.data_demo_dir / settings.WHATIF_RESULTS_FILENAME)
    assert {
        "customer_id",
        "current_metrics",
        "match_summary",
        "outcome_summary",
        "breakpoint_result",
        "whatif_results",
        "selection_reason",
        "generated_at",
        "random_seed",
    }.issubset(main_demo)
    assert {"target_customer_id", "matched_count", "outcomes", "first_stress_month_median", "first_delinquency_month_median"}.issubset(outcome)
    assert tuple(outcome["outcomes"]) == settings.FINAL_OUTCOMES
    assert sum(values["count"] for values in outcome["outcomes"].values()) == config.top_k
    assert sum(values["ratio"] for values in outcome["outcomes"].values()) == pytest.approx(1.0)
    assert {
        "status",
        "breakpoint_month",
        "months_from_current",
        "primary_factor",
        "risk_group_mean",
        "avoidance_group_mean",
        "standardized_difference",
        "persistence_months",
        "secondary_factors",
        "interpretation",
    }.issubset(breakpoint)
    assert breakpoint["status"] in {"found", "not_found", "insufficient_group_size"}
    assert {"target_customer_id", "simulation_months", "starting_profile", "scenarios"}.issubset(whatif)
    assert whatif["simulation_months"] == settings.WHATIF_SIMULATION_MONTHS
    assert [(scenario["scenario_id"], scenario["scenario_name"]) for scenario in whatif["scenarios"]] == [
        (1, "baseline"),
        (2, "variable_expense_cut_15"),
        (3, "fixed_expense_cut_300k"),
        (4, "debt_payment_cut_20"),
    ]
    assert whatif["scenarios"][0]["improvement_vs_baseline"] == 0.0
    assert all(len(scenario["monthly_data"]) == settings.WHATIF_SIMULATION_MONTHS for scenario in whatif["scenarios"])

    cached = load_precomputed_demo_analysis(demo_dir=config.data_demo_dir)
    live = run_customer_analysis(cached.customer_id, monthly, features, matcher, top_k=config.top_k)
    pd.testing.assert_frame_equal(cached.analysis["matches"], matches)
    pd.testing.assert_frame_equal(cached.analysis["matched_future_trajectory"], matched_future)
    assert cached.analysis["outcome_summary"] == live["outcome_summary"] == outcome
    assert cached.analysis["breakpoint_result"] == live["breakpoint_result"] == breakpoint
    assert cached.analysis["whatif_results"] == live["whatif_results"] == whatif
