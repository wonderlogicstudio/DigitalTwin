"""Tests for fixed demo cache artifacts and fallback loading."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from config import settings
from src.demo_cache import load_precomputed_demo_analysis
from src.matcher import TrajectoryMatcher
from src.pipeline import PipelineConfig, run_pipeline
from src.ui_components import run_customer_analysis


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


def test_fallback_loads_without_raw_data(tmp_path: Path) -> None:
    run_pipeline(_config(tmp_path))
    raw_dir = tmp_path / "data" / "raw"
    for path in raw_dir.glob("*.csv"):
        path.unlink()

    payload = load_precomputed_demo_analysis(demo_dir=tmp_path / "data" / "demo")

    assert payload.customer_id
    assert len(payload.analysis["matches"]) == 20
    assert payload.analysis["outcome_summary"]["matched_count"] == 20


def test_bad_json_is_reported(tmp_path: Path) -> None:
    run_pipeline(_config(tmp_path))
    outcome_path = tmp_path / "data" / "demo" / settings.OUTCOME_SUMMARY_FILENAME
    outcome_path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid JSON"):
        load_precomputed_demo_analysis(demo_dir=tmp_path / "data" / "demo")


def test_live_analysis_matches_cached_core_numbers(tmp_path: Path) -> None:
    run_pipeline(_config(tmp_path))
    monthly_df = pd.read_csv(tmp_path / "data" / "raw" / "customer_monthly_5000.csv")
    features_df = pd.read_csv(tmp_path / "data" / "processed" / "trajectory_features.csv")
    matcher = TrajectoryMatcher().fit(features_df)
    cached = load_precomputed_demo_analysis(demo_dir=tmp_path / "data" / "demo")

    live = run_customer_analysis(cached.customer_id, monthly_df, features_df, matcher, top_k=20)

    assert live["outcome_summary"]["matched_count"] == cached.analysis["outcome_summary"]["matched_count"]
    assert live["outcome_summary"]["outcomes"] == cached.analysis["outcome_summary"]["outcomes"]
    assert live["breakpoint_result"]["status"] == cached.analysis["breakpoint_result"]["status"]
    assert live["whatif_results"]["scenarios"][0]["ending_cash_balance"] == pytest.approx(
        cached.analysis["whatif_results"]["scenarios"][0]["ending_cash_balance"]
    )


def test_precomputed_artifact_files_exist_after_pipeline(tmp_path: Path) -> None:
    run_pipeline(_config(tmp_path))
    demo_dir = tmp_path / "data" / "demo"

    for filename in (
        settings.MATCHED_CUSTOMERS_FILENAME,
        settings.MATCHED_FUTURE_TRAJECTORY_FILENAME,
        settings.OUTCOME_SUMMARY_FILENAME,
        settings.BREAKPOINT_RESULT_FILENAME,
        settings.WHATIF_RESULTS_FILENAME,
        settings.MAIN_DEMO_CUSTOMER_FILENAME,
    ):
        assert (demo_dir / filename).exists()

    backup_dir = tmp_path / "reports" / "demo_backup"
    assert (backup_dir / "demo_summary.json").exists()
    assert json.loads((backup_dir / "demo_summary.json").read_text(encoding="utf-8"))["customer_id"]
