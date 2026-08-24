"""Tests for the population single-customer result contract."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from config import settings
from src.data_generator import generate_dataset
from src.feature_engineering import build_trajectory_features
from src.matcher import TrajectoryMatcher
from src.models import GeneratorConfig
from src.population_result import build_population_customer_result, population_result_from_analysis
from src.ui_components import run_customer_analysis


@pytest.fixture(scope="module")
def analysis_inputs() -> tuple[pd.DataFrame, pd.DataFrame, TrajectoryMatcher, str]:
    _, monthly_df = generate_dataset(GeneratorConfig(customer_count=100, random_seed=42))
    features_df = build_trajectory_features(monthly_df)
    matcher = TrajectoryMatcher().fit(features_df)
    customer_id = str(features_df.iloc[0]["customer_id"])
    return monthly_df, features_df, matcher, customer_id


def test_population_result_schema_is_json_serializable(
    analysis_inputs: tuple[pd.DataFrame, pd.DataFrame, TrajectoryMatcher, str],
) -> None:
    monthly_df, features_df, matcher, customer_id = analysis_inputs

    result = build_population_customer_result(
        customer_id,
        monthly_df,
        features_df,
        matcher,
        top_k=20,
    )

    payload = result.to_dict()
    assert set(payload) == {
        "customer_id",
        "matched_count",
        "distance_summary",
        "historical_outcome_shares",
        "breakpoint_status",
        "breakpoint_month",
        "breakpoint_factor",
        "breakpoint_support",
        "analysis_status",
        "error_category",
        "error_message",
    }
    assert result.analysis_status == "success"
    assert payload["matched_count"] == 20
    assert set(payload["distance_summary"]) == {"min", "mean", "median", "max"}
    assert tuple(payload["historical_outcome_shares"]) == settings.FINAL_OUTCOMES
    assert set(payload["breakpoint_support"]) == {
        "risk_group_count",
        "avoidance_group_count",
        "persistence_months",
    }
    assert json.loads(json.dumps(payload)) == payload


def test_population_result_matches_legacy_single_customer_analysis(
    analysis_inputs: tuple[pd.DataFrame, pd.DataFrame, TrajectoryMatcher, str],
) -> None:
    monthly_df, features_df, matcher, customer_id = analysis_inputs

    legacy = run_customer_analysis(customer_id, monthly_df, features_df, matcher, top_k=20)
    result = build_population_customer_result(
        customer_id,
        monthly_df,
        features_df,
        matcher,
        top_k=20,
    )

    assert result.analysis_status == "success"
    assert result.matched_count == len(legacy["matches"]) == legacy["outcome_summary"]["matched_count"]
    assert customer_id not in set(legacy["matches"]["matched_customer_id"].astype(str))
    assert result.distance_summary == {
        "min": pytest.approx(float(legacy["matches"]["distance"].min())),
        "mean": pytest.approx(float(legacy["matches"]["distance"].mean())),
        "median": pytest.approx(float(legacy["matches"]["distance"].median())),
        "max": pytest.approx(float(legacy["matches"]["distance"].max())),
    }
    assert result.historical_outcome_shares == {
        outcome: legacy["outcome_summary"]["outcomes"][outcome]["ratio"]
        for outcome in settings.FINAL_OUTCOMES
    }
    assert result.breakpoint_status == legacy["breakpoint_result"]["status"]
    assert result.breakpoint_month == legacy["breakpoint_result"]["breakpoint_month"]
    assert result.breakpoint_factor == legacy["breakpoint_result"]["primary_factor"]
    assert result.breakpoint_support == {
        "risk_group_count": (
            legacy["outcome_summary"]["outcomes"]["stress"]["count"]
            + legacy["outcome_summary"]["outcomes"]["delinquent"]["count"]
        ),
        "avoidance_group_count": (
            legacy["outcome_summary"]["outcomes"]["healthy"]["count"]
            + legacy["outcome_summary"]["outcomes"]["recovered"]["count"]
        ),
        "persistence_months": legacy["breakpoint_result"]["persistence_months"],
    }


def test_population_result_is_deterministic_and_ignores_target_future_rows(
    analysis_inputs: tuple[pd.DataFrame, pd.DataFrame, TrajectoryMatcher, str],
) -> None:
    monthly_df, features_df, matcher, customer_id = analysis_inputs
    first = build_population_customer_result(customer_id, monthly_df, features_df, matcher, top_k=20)
    second = build_population_customer_result(customer_id, monthly_df, features_df, matcher, top_k=20)

    mutated = monthly_df.copy()
    target_future = (mutated["customer_id"].astype(str) == customer_id) & (
        mutated["month"] >= settings.FUTURE_START_MONTH
    )
    mutated.loc[target_future, "final_outcome"] = "delinquent"
    mutated.loc[target_future, "monthly_status"] = "delinquent"
    mutated.loc[target_future, "cash_balance"] = -999_999_999
    after_target_future_mutation = build_population_customer_result(
        customer_id,
        mutated,
        features_df,
        matcher,
        top_k=20,
    )

    assert first == second == after_target_future_mutation


def test_population_result_exposes_failed_customer_as_structured_result(
    analysis_inputs: tuple[pd.DataFrame, pd.DataFrame, TrajectoryMatcher, str],
) -> None:
    monthly_df, features_df, matcher, _ = analysis_inputs

    result = build_population_customer_result(
        "C999999",
        monthly_df,
        features_df,
        matcher,
        top_k=20,
    )

    assert result.analysis_status == "failed"
    assert result.error_category == "input_validation"
    assert result.error_message
    assert result.matched_count == 0
    assert result.breakpoint_status == "not_available"
    assert result.historical_outcome_shares == {
        outcome: 0.0 for outcome in settings.FINAL_OUTCOMES
    }


def test_population_result_marks_legacy_subanalysis_errors_as_partial_failure(
    analysis_inputs: tuple[pd.DataFrame, pd.DataFrame, TrajectoryMatcher, str],
) -> None:
    monthly_df, features_df, matcher, customer_id = analysis_inputs
    legacy = run_customer_analysis(customer_id, monthly_df, features_df, matcher, top_k=20)
    partial_analysis = {**legacy, "errors": {"whatif": "simulated failure"}}

    result = population_result_from_analysis(customer_id, partial_analysis)

    assert result.analysis_status == "partial_failure"
    assert result.error_category == "whatif"
    assert result.error_message == "whatif: simulated failure"
