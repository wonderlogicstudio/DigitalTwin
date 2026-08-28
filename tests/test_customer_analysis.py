"""Parity tests for the UI-neutral customer analysis service."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pandas as pd

import src.customer_analysis as customer_analysis
from src.customer_analysis import run_customer_analysis
from src.data_generator import generate_dataset
from src.feature_engineering import build_trajectory_features
from src.matcher import TrajectoryMatcher
from src.models import GeneratorConfig
from src.ui_components import run_customer_analysis as run_customer_analysis_ui


def _analysis_inputs() -> tuple[str, pd.DataFrame, pd.DataFrame, TrajectoryMatcher]:
    config = GeneratorConfig(customer_count=250, top_k_matches=20)
    _, monthly_df = generate_dataset(config)
    features_df = build_trajectory_features(monthly_df)
    matcher = TrajectoryMatcher().fit(features_df)
    return "C000001", monthly_df, features_df, matcher


def test_service_matches_existing_ui_wrapper_for_customer_analysis() -> None:
    customer_id, monthly_df, features_df, matcher = _analysis_inputs()

    service_result = run_customer_analysis(
        customer_id,
        monthly_df,
        features_df,
        matcher,
        top_k=20,
    )
    compatibility_result = run_customer_analysis_ui(
        customer_id,
        monthly_df,
        features_df,
        matcher,
        top_k=20,
    )

    pd.testing.assert_frame_equal(service_result["matches"], compatibility_result["matches"])
    pd.testing.assert_frame_equal(
        service_result["breakpoint_comparison"],
        compatibility_result["breakpoint_comparison"],
    )
    assert service_result["matched_ids"] == compatibility_result["matched_ids"]
    assert service_result["outcome_summary"] == compatibility_result["outcome_summary"]
    assert service_result["breakpoint_result"] == compatibility_result["breakpoint_result"]
    assert service_result["whatif_results"] == compatibility_result["whatif_results"]
    assert service_result["errors"] == compatibility_result["errors"]

    breakpoint = service_result["breakpoint_result"]
    assert {
        "status",
        "breakpoint_month",
        "months_from_current",
        "primary_factor",
    }.issubset(breakpoint)
    scenarios = service_result["whatif_results"]["scenarios"]
    assert scenarios
    assert {
        "scenario_id",
        "scenario_name",
        "ending_cash_balance",
        "minimum_cash_balance",
        "average_savings_rate",
        "improvement_vs_baseline",
    }.issubset(scenarios[0])


def test_service_has_no_ui_dependency() -> None:
    module_path = Path(customer_analysis.__file__)
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert "src.ui_components" not in imported_modules
    assert "streamlit" not in source.lower()
    assert "ui_components" not in source
    assert "ui_components" not in inspect.getsource(run_customer_analysis)
