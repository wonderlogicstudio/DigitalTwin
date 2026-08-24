"""Tests for the end-to-end pipeline runner."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.run_pipeline import main as pipeline_cli_main
from src.data_generator import generate_dataset
from src.demo_selector import build_current_metrics
from src.feature_engineering import build_trajectory_features
from src.models import GeneratorConfig
from src.pipeline import (
    PipelineConfig,
    PipelineError,
    _select_observation_only_fallback_candidates,
    run_pipeline,
)


def _config(
    tmp_path: Path,
    *,
    customer_count: int = 100,
    random_seed: int = 42,
    top_k: int = 20,
    force: bool = True,
    skip_generation: bool = False,
    skip_validation: bool = False,
    export_charts: bool = False,
) -> PipelineConfig:
    return PipelineConfig(
        customer_count=customer_count,
        random_seed=random_seed,
        top_k=top_k,
        force=force,
        skip_generation=skip_generation,
        skip_validation=skip_validation,
        export_charts=export_charts,
        customer_master_path=tmp_path / "data" / "raw" / "customer_master.csv",
        customer_monthly_path=tmp_path / "data" / "raw" / "customer_monthly_5000.csv",
        trajectory_features_path=tmp_path / "data" / "processed" / "trajectory_features.csv",
        reports_dir=tmp_path / "reports",
        data_processed_dir=tmp_path / "data" / "processed",
        data_demo_dir=tmp_path / "data" / "demo",
        charts_dir=tmp_path / "reports" / "charts",
    )


def test_small_pipeline_runs_end_to_end(tmp_path: Path) -> None:
    summary = run_pipeline(_config(tmp_path, export_charts=True))

    assert summary["customer_count"] == 100
    assert summary["monthly_row_count"] == 3_600
    assert summary["feature_row_count"] == 100
    assert summary["matched_count"] == 20
    assert summary["main_customer_id"].startswith("C")
    assert summary["breakpoint"]["status"] in {"found", "not_found", "insufficient_group_size"}
    assert (tmp_path / "reports" / "charts" / "whatif.html").exists()


def test_pipeline_stops_on_validation_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_validation_report(master_df: pd.DataFrame, monthly_df: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "check_name": "forced_failure",
                    "status": "failure",
                    "actual_value": "bad",
                    "expected_value": "good",
                    "message": "forced test failure",
                }
            ]
        )

    monkeypatch.setattr("src.pipeline.run_all_validations", fake_validation_report)

    with pytest.raises(PipelineError) as exc_info:
        run_pipeline(_config(tmp_path))

    assert exc_info.value.step == "data_validation"
    assert not (tmp_path / "data" / "processed" / "trajectory_features.csv").exists()


def test_skip_options_reuse_existing_outputs(tmp_path: Path) -> None:
    first = run_pipeline(_config(tmp_path, force=True))
    second = run_pipeline(
        _config(
            tmp_path,
            force=False,
            skip_generation=True,
            skip_validation=True,
        )
    )

    assert first["customer_count"] == second["customer_count"]
    assert second["matched_count"] == 20
    assert (tmp_path / "data" / "demo" / "main_demo_customer.json").exists()


def test_reused_raw_outputs_must_match_requested_seed(tmp_path: Path) -> None:
    run_pipeline(_config(tmp_path, random_seed=42, force=True))

    with pytest.raises(PipelineError) as exc_info:
        run_pipeline(
            _config(
                tmp_path,
                random_seed=43,
                force=False,
                skip_generation=True,
                skip_validation=True,
            )
        )

    assert exc_info.value.step == "synthetic_data_generation"


def test_unexpected_demo_selection_error_is_not_silently_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_selector(*args: object, **kwargs: object) -> tuple[pd.DataFrame, dict]:
        raise KeyError("schema bug")

    monkeypatch.setattr("src.pipeline.select_demo_customers", broken_selector)

    with pytest.raises(PipelineError) as exc_info:
        run_pipeline(_config(tmp_path))

    assert exc_info.value.step == "demo_candidate_search"
    assert "schema bug" in exc_info.value.message


def test_fallback_demo_selection_ignores_target_future_outcomes() -> None:
    _, monthly_df = generate_dataset(GeneratorConfig(customer_count=100, random_seed=42))
    features_df = build_trajectory_features(monthly_df)
    baseline_ids = _select_observation_only_fallback_candidates(
        build_current_metrics(monthly_df),
        features_df,
    )

    mutated = monthly_df.copy()
    mutated.loc[mutated["month"] >= 13, "final_outcome"] = "delinquent"
    mutated_ids = _select_observation_only_fallback_candidates(
        build_current_metrics(mutated),
        build_trajectory_features(mutated),
    )

    assert baseline_ids == mutated_ids
    assert len(baseline_ids) == 3
    assert len(set(baseline_ids)) == 3


def test_reused_demo_outputs_refresh_breakpoint_for_current_matches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_pipeline(_config(tmp_path, force=True))
    main_json_path = tmp_path / "data" / "demo" / "main_demo_customer.json"
    main_json = json.loads(main_json_path.read_text(encoding="utf-8"))
    main_json["breakpoint_result"] = {
        "status": "not_found",
        "breakpoint_month": None,
        "months_from_current": None,
        "primary_factor": None,
        "risk_group_mean": None,
        "avoidance_group_mean": None,
        "standardized_difference": None,
        "persistence_months": 0,
        "secondary_factors": [],
        "interpretation": "stale breakpoint",
    }
    main_json_path.write_text(json.dumps(main_json), encoding="utf-8")

    def fake_breakpoint(matched_ids: list[str], monthly_df: pd.DataFrame) -> dict:
        return {
            "status": "found",
            "breakpoint_month": 13,
            "months_from_current": 1,
            "primary_factor": "dsr",
            "risk_group_mean": float(len(matched_ids)),
            "avoidance_group_mean": 0.0,
            "standardized_difference": 1.0,
            "persistence_months": 2,
            "secondary_factors": [],
            "interpretation": "fresh breakpoint",
        }

    monkeypatch.setattr("src.breakpoint_analyzer.find_breakpoint", fake_breakpoint)

    summary = run_pipeline(
        _config(
            tmp_path,
            force=False,
            skip_generation=True,
            skip_validation=True,
        )
    )

    assert summary["breakpoint"]["status"] == "found"
    assert summary["breakpoint"]["risk_group_mean"] == 20.0


def test_force_regenerates_with_new_seed(tmp_path: Path) -> None:
    run_pipeline(_config(tmp_path, random_seed=42, force=True))
    first_master = pd.read_csv(tmp_path / "data" / "raw" / "customer_master.csv")

    run_pipeline(_config(tmp_path, random_seed=43, force=True))
    second_master = pd.read_csv(tmp_path / "data" / "raw" / "customer_master.csv")

    assert not first_master.equals(second_master)


def test_same_seed_is_reproducible(tmp_path: Path) -> None:
    first_dir = tmp_path / "run1"
    second_dir = tmp_path / "run2"
    first_summary = run_pipeline(_config(first_dir, random_seed=77))
    second_summary = run_pipeline(_config(second_dir, random_seed=77))

    first_master = pd.read_csv(first_dir / "data" / "raw" / "customer_master.csv")
    second_master = pd.read_csv(second_dir / "data" / "raw" / "customer_master.csv")

    pd.testing.assert_frame_equal(first_master, second_master)
    assert first_summary["main_customer_id"] == second_summary["main_customer_id"]


def test_output_files_and_main_json_keys(tmp_path: Path) -> None:
    summary = run_pipeline(_config(tmp_path))

    required_paths = [
        "customer_master",
        "customer_monthly",
        "trajectory_features",
        "demo_customers",
        "main_demo_customer",
        "breakpoint_result",
        "whatif_results",
    ]
    for key in required_paths:
        assert Path(summary["paths"][key]).exists()

    main_json = json.loads((tmp_path / "data" / "demo" / "main_demo_customer.json").read_text(encoding="utf-8"))
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
    }.issubset(main_json)


def test_invalid_cli_arguments_return_failure() -> None:
    assert pipeline_cli_main(["--customer-count", "10", "--top-k", "10"]) == 1
