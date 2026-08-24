"""End-to-end pipeline orchestration for Financial Path Twin."""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from config import settings
from src.breakpoint_analyzer import save_breakpoint_result
from src.data_generator import generate_dataset, save_dataset
from src.demo_selector import (
    build_current_metrics,
    build_final_outcome_lookup,
    best_whatif_scenario as selector_best_whatif_scenario,
    save_demo_outputs,
    select_demo_customers,
    summarize_matched_outcomes,
)
from src.demo_cache import save_demo_backup, save_precomputed_demo_artifacts
from src.feature_engineering import build_trajectory_features, save_trajectory_features
from src.matcher import TrajectoryMatcher
from src.models import GeneratorConfig
from src.ui_components import add_balance_ratios, build_breakpoint_comparison
from src.validator import (
    build_outcome_distribution,
    build_persona_summary,
    has_failures,
    run_all_validations,
    save_validation_reports,
)
from src.visualizations import (
    create_breakpoint_comparison_chart,
    create_current_trajectory_chart,
    create_feature_similarity_chart,
    create_outcome_bar_chart,
    create_twin_trajectory_chart,
    create_whatif_balance_chart,
)
from src.whatif_simulator import build_whatif_results, save_whatif_results


PIPELINE_STEPS = (
    "synthetic_data_generation",
    "data_validation",
    "feature_generation",
    "matcher_preparation",
    "demo_candidate_search",
    "main_demo_analysis",
    "result_aggregation",
    "breakpoint_analysis",
    "whatif_simulation",
    "demo_outputs",
    "chart_export",
)


class PipelineError(RuntimeError):
    """Raised when a required pipeline step fails."""

    def __init__(self, step: str, message: str) -> None:
        super().__init__(f"{step}: {message}")
        self.step = step
        self.message = message


@dataclass(frozen=True)
class PipelineConfig:
    """Runtime options and file paths for one pipeline run."""

    customer_count: int = settings.CUSTOMER_COUNT
    random_seed: int = settings.RANDOM_SEED
    top_k: int = settings.TOP_K_MATCHES
    skip_generation: bool = False
    skip_validation: bool = False
    force: bool = False
    export_charts: bool = False
    verbose: bool = False
    customer_master_path: Path = settings.CUSTOMER_MASTER_PATH
    customer_monthly_path: Path = settings.CUSTOMER_MONTHLY_PATH
    trajectory_features_path: Path = settings.TRAJECTORY_FEATURES_PATH
    reports_dir: Path = settings.REPORTS_DIR
    data_processed_dir: Path = settings.DATA_PROCESSED_DIR
    data_demo_dir: Path = settings.DATA_DEMO_DIR
    charts_dir: Path = settings.CHARTS_DIR
    stage_timings: dict[str, float] = field(default_factory=dict, compare=False)

    @property
    def breakpoint_result_path(self) -> Path:
        """Return the configured breakpoint JSON path."""

        return self.data_processed_dir / "breakpoint_result.json"

    @property
    def whatif_results_path(self) -> Path:
        """Return the configured What-if JSON path."""

        return self.data_processed_dir / "whatif_results.json"

    @property
    def demo_customers_path(self) -> Path:
        """Return the configured demo customer CSV path."""

        return self.data_demo_dir / "demo_customers.csv"

    @property
    def main_demo_customer_path(self) -> Path:
        """Return the configured main demo JSON path."""

        return self.data_demo_dir / "main_demo_customer.json"


def run_pipeline(config: PipelineConfig) -> dict[str, Any]:
    """Run the full Financial Path Twin pipeline and return a summary."""

    _validate_config(config)
    start_time = time.perf_counter()
    timings: dict[str, float] = {}
    generated_files: list[Path] = []

    with _patched_settings(config):
        master_df: pd.DataFrame | None = None
        monthly_df: pd.DataFrame | None = None
        features_df: pd.DataFrame | None = None
        matcher: TrajectoryMatcher | None = None
        demo_df: pd.DataFrame | None = None
        main_demo: dict[str, Any] | None = None
        fallback_used = False

        with _stage("synthetic_data_generation", timings, config.verbose):
            if config.skip_generation:
                master_df, monthly_df = _load_required_raw_data(config)
            elif _raw_outputs_exist(config) and not config.force:
                master_df, monthly_df = _load_required_raw_data(config)
            else:
                master_df, monthly_df = _generate_raw_data(config)
                generated_files.extend([config.customer_master_path, config.customer_monthly_path])
            _assert_raw_data_matches_config(config, master_df, monthly_df)

        with _stage("data_validation", timings, config.verbose):
            if config.skip_validation:
                _assert_raw_data_matches_config(config, master_df, monthly_df)
            else:
                validation_files = _validate_and_save(config, master_df, monthly_df)
                generated_files.extend(validation_files)

        with _stage("feature_generation", timings, config.verbose):
            if config.trajectory_features_path.exists() and not config.force:
                features_df = pd.read_csv(config.trajectory_features_path)
            else:
                features_df = build_trajectory_features(monthly_df)
                save_trajectory_features(features_df, config.trajectory_features_path)
                generated_files.append(config.trajectory_features_path)
            _assert_features_match_raw(config, features_df, master_df)

        with _stage("matcher_preparation", timings, config.verbose):
            matcher = TrajectoryMatcher().fit(features_df)

        with _stage("demo_candidate_search", timings, config.verbose):
            if _demo_outputs_exist(config) and not config.force:
                demo_df = pd.read_csv(config.demo_customers_path)
                main_demo = json.loads(config.main_demo_customer_path.read_text(encoding="utf-8"))
            else:
                try:
                    demo_df, main_demo = select_demo_customers(
                        monthly_df,
                        features_df,
                        generated_at=datetime.now(timezone.utc).isoformat(),
                    )
                except ValueError as exc:
                    if not _is_demo_candidate_exhaustion_error(exc):
                        raise
                    fallback_used = True
                    demo_df, main_demo = _select_fallback_demo_customers(
                        config,
                        monthly_df,
                        features_df,
                        matcher,
                    )
            _assert_demo_outputs_match_config(config, demo_df, main_demo, features_df)

        with _stage("main_demo_analysis", timings, config.verbose):
            main_customer_id = str(main_demo["customer_id"])
            matches = matcher.match(main_customer_id, top_k=config.top_k)
            matched_ids = matches["matched_customer_id"].astype(str).tolist()

        with _stage("result_aggregation", timings, config.verbose):
            outcome_lookup = build_final_outcome_lookup(monthly_df)
            outcome_summary = summarize_matched_outcomes(
                main_customer_id,
                matched_ids,
                monthly_df,
                outcome_lookup,
            )
            main_demo["match_summary"] = {
                "matched_count": int(len(matches)),
                "top_10": matches.head(10).to_dict(orient="records"),
            }
            main_demo["outcome_summary"] = outcome_summary

        with _stage("breakpoint_analysis", timings, config.verbose):
            from src.breakpoint_analyzer import find_breakpoint

            breakpoint_result = find_breakpoint(matched_ids, monthly_df)
            main_demo["breakpoint_result"] = breakpoint_result
            save_breakpoint_result(breakpoint_result, config.breakpoint_result_path)
            generated_files.append(config.breakpoint_result_path)

        with _stage("whatif_simulation", timings, config.verbose):
            whatif_results = build_whatif_results(main_customer_id, monthly_df)
            main_demo["whatif_results"] = whatif_results
            save_whatif_results(whatif_results, config.whatif_results_path)
            generated_files.append(config.whatif_results_path)

        with _stage("demo_outputs", timings, config.verbose):
            main_demo["random_seed"] = config.random_seed
            main_demo["generated_at"] = main_demo.get("generated_at") or datetime.now(timezone.utc).isoformat()
            demo_paths = save_demo_outputs(
                demo_df,
                main_demo,
                demo_customers_path=config.demo_customers_path,
                main_demo_customer_path=config.main_demo_customer_path,
            )
            generated_files.extend(demo_paths)
            analysis_payload = {
                "customer_id": main_customer_id,
                "matches": matches,
                "matched_ids": matched_ids,
                "outcome_summary": outcome_summary,
                "breakpoint_result": breakpoint_result,
                "whatif_results": whatif_results,
                "breakpoint_comparison": build_breakpoint_comparison(matched_ids, monthly_df),
                "errors": {},
            }
            generated_files.extend(
                save_precomputed_demo_artifacts(
                    customer_id=main_customer_id,
                    matches=matches,
                    matched_ids=matched_ids,
                    monthly_df=monthly_df,
                    outcome_summary=outcome_summary,
                    breakpoint_result=breakpoint_result,
                    whatif_results=whatif_results,
                    main_demo_customer=main_demo,
                    output_dir=config.data_demo_dir,
                )
            )
            generated_files.extend(
                save_demo_backup(
                    main_demo_customer=main_demo,
                    analysis=analysis_payload,
                    monthly_df=monthly_df,
                    output_dir=config.reports_dir / "demo_backup",
                )
            )

        with _stage("chart_export", timings, config.verbose):
            if config.export_charts:
                chart_files = _export_charts(config, main_customer_id, matched_ids, monthly_df, features_df, main_demo)
                generated_files.extend(chart_files)

    elapsed = time.perf_counter() - start_time
    summary = _build_summary(
        config,
        master_df,
        monthly_df,
        features_df,
        main_demo,
        elapsed,
        timings,
        generated_files,
        fallback_used,
    )
    config.stage_timings.update(timings)
    return summary


def _generate_raw_data(config: PipelineConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    generator_config = GeneratorConfig(
        random_seed=config.random_seed,
        customer_count=config.customer_count,
        top_k_matches=config.top_k,
        customer_master_path=str(config.customer_master_path),
        customer_monthly_path=str(config.customer_monthly_path),
    )
    master_df, monthly_df = generate_dataset(generator_config)
    save_dataset(master_df, monthly_df, generator_config)
    return master_df, monthly_df


def _validate_and_save(
    config: PipelineConfig,
    master_df: pd.DataFrame,
    monthly_df: pd.DataFrame,
) -> list[Path]:
    validation_report = run_all_validations(master_df, monthly_df)
    persona_summary = build_persona_summary(master_df)
    outcome_distribution = build_outcome_distribution(monthly_df)
    paths = list(save_validation_reports(validation_report, persona_summary, outcome_distribution, config.reports_dir))
    if has_failures(validation_report):
        failed = validation_report.loc[validation_report["status"] == "failure", "check_name"].tolist()
        raise PipelineError("data_validation", f"required validation failed: {failed}")
    return paths


def _select_fallback_demo_customers(
    config: PipelineConfig,
    monthly_df: pd.DataFrame,
    features_df: pd.DataFrame,
    matcher: TrajectoryMatcher,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    current_metrics = build_current_metrics(monthly_df)
    candidates = _select_observation_only_fallback_candidates(current_metrics, features_df)
    outcome_lookup = build_final_outcome_lookup(monthly_df)

    roles = ("main", "stable_comparison", "high_risk")
    rows: list[dict[str, Any]] = []
    main_demo: dict[str, Any] | None = None
    for role, customer_id in zip(roles, candidates[:3], strict=True):
        matches = matcher.match(customer_id, top_k=config.top_k)
        matched_ids = matches["matched_customer_id"].astype(str).tolist()
        outcome_summary = summarize_matched_outcomes(customer_id, matched_ids, monthly_df, outcome_lookup)
        from src.breakpoint_analyzer import find_breakpoint

        breakpoint_result = find_breakpoint(matched_ids, monthly_df)
        whatif_results = build_whatif_results(customer_id, monthly_df)
        best = selector_best_whatif_scenario(whatif_results)
        metric_row = current_metrics[current_metrics["customer_id"] == customer_id].iloc[0]
        row = {
            "demo_role": role,
            "customer_id": customer_id,
            "demo_score": 0.0,
            "current_status": str(metric_row["current_status"]),
            "recent_savings_rate": round(float(metric_row["recent_savings_rate"]), 6),
            "recent_dsr": round(float(metric_row["recent_dsr"]), 6),
            "recent_fixed_expense_ratio": round(float(metric_row["recent_fixed_expense_ratio"]), 6),
            "matched_count": int(outcome_summary["matched_count"]),
            "healthy_ratio": outcome_summary["outcomes"]["healthy"]["ratio"],
            "recovered_ratio": outcome_summary["outcomes"]["recovered"]["ratio"],
            "stress_ratio": outcome_summary["outcomes"]["stress"]["ratio"],
            "delinquent_ratio": outcome_summary["outcomes"]["delinquent"]["ratio"],
            "risk_group_ratio": round(
                outcome_summary["outcomes"]["stress"]["ratio"]
                + outcome_summary["outcomes"]["delinquent"]["ratio"],
                6,
            ),
            "breakpoint_status": breakpoint_result["status"],
            "breakpoint_month": breakpoint_result["breakpoint_month"],
            "months_from_current": breakpoint_result["months_from_current"],
            "primary_factor": breakpoint_result["primary_factor"],
            "best_scenario_id": best["scenario_id"],
            "best_scenario_improvement": best["improvement_vs_baseline"],
            "selection_reason": "pipeline fallback selection for small or strict-test datasets",
        }
        rows.append(row)
        if role == "main":
            main_demo = {
                "customer_id": customer_id,
                "current_metrics": {
                    "current_status": row["current_status"],
                    "recent_savings_rate": row["recent_savings_rate"],
                    "recent_dsr": row["recent_dsr"],
                    "recent_fixed_expense_ratio": row["recent_fixed_expense_ratio"],
                    "savings_rate_slope_6m": round(float(metric_row["savings_rate_slope_6m"]), 6),
                    "balance_decline_run_6m": int(metric_row["balance_decline_run_6m"]),
                },
                "match_summary": {
                    "matched_count": row["matched_count"],
                    "top_10": matches.head(10).to_dict(orient="records"),
                },
                "outcome_summary": outcome_summary,
                "breakpoint_result": breakpoint_result,
                "whatif_results": whatif_results,
                "selection_reason": row["selection_reason"],
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "random_seed": config.random_seed,
            }

    return pd.DataFrame(rows).loc[:, settings.DEMO_CUSTOMER_COLUMNS], main_demo or {}


def _select_observation_only_fallback_candidates(
    current_metrics: pd.DataFrame,
    features_df: pd.DataFrame,
) -> list[str]:
    """Choose deterministic fallback demos from month-12 and prior metrics only.

    This path is used only when the stricter representative-demo rules have no
    candidates (typically small test datasets).  It must not use a target
    customer's future outcomes, persona, or months 13--36.
    """

    feature_ids = set(features_df["customer_id"].astype(str))
    metrics = current_metrics.copy()
    metrics["customer_id"] = metrics["customer_id"].astype(str)
    metrics = metrics[metrics["customer_id"].isin(feature_ids)].copy()

    status_risk = {"healthy": 0, "watch": 1, "stress": 2, "delinquent": 3}
    metrics["_status_risk"] = metrics["current_status"].map(status_risk).fillna(-1)

    ranked_customer_ids = [
        metrics.sort_values(
            [
                "_status_risk",
                "balance_decline_run_6m",
                "recent_savings_rate",
                "recent_dsr",
                "customer_id",
            ],
            ascending=[False, False, True, False, True],
        )["customer_id"].tolist(),
        metrics.sort_values(
            ["_status_risk", "recent_savings_rate", "recent_dsr", "customer_id"],
            ascending=[True, False, True, True],
        )["customer_id"].tolist(),
        metrics.sort_values(
            [
                "_status_risk",
                "balance_decline_run_6m",
                "recent_savings_rate",
                "recent_dsr",
                "customer_id",
            ],
            ascending=[False, False, True, False, True],
        )["customer_id"].tolist(),
        sorted(feature_ids),
    ]

    candidates: list[str] = []
    for customer_ids in ranked_customer_ids:
        for customer_id in customer_ids:
            if customer_id not in candidates:
                candidates.append(customer_id)
            if len(candidates) >= 3:
                return candidates

    raise PipelineError("demo_candidate_search", "at least three fallback demo customers are required")


def _export_charts(
    config: PipelineConfig,
    main_customer_id: str,
    matched_ids: list[str],
    monthly_df: pd.DataFrame,
    features_df: pd.DataFrame,
    main_demo: dict[str, Any],
) -> list[Path]:
    config.charts_dir.mkdir(parents=True, exist_ok=True)
    monthly_with_ratios = add_balance_ratios(monthly_df, [main_customer_id, *matched_ids])
    target_history = monthly_with_ratios[
        (monthly_with_ratios["customer_id"].astype(str) == main_customer_id)
        & (monthly_with_ratios["month"] <= settings.OBSERVATION_END_MONTH)
    ]
    twin_trajectory = monthly_with_ratios[monthly_with_ratios["customer_id"].astype(str).isin(matched_ids)]
    comparison_df = build_breakpoint_comparison(matched_ids, monthly_df)
    target_features = features_df[features_df["customer_id"].astype(str) == main_customer_id]
    matched_features = features_df[features_df["customer_id"].astype(str).isin(matched_ids)]
    breakpoint_metric = main_demo["breakpoint_result"].get("primary_factor") or "savings_rate"
    outputs = {
        "current_trajectory.html": create_current_trajectory_chart(target_history, "savings_rate"),
        "twin_trajectory.html": create_twin_trajectory_chart(
            target_history,
            twin_trajectory,
            metric=breakpoint_metric,
            breakpoint_result=main_demo["breakpoint_result"],
        ),
        "outcome_distribution.html": create_outcome_bar_chart(main_demo["outcome_summary"]),
        "breakpoint.html": create_breakpoint_comparison_chart(main_demo["breakpoint_result"], comparison_df),
        "whatif.html": create_whatif_balance_chart(main_demo["whatif_results"]),
        "feature_similarity.html": create_feature_similarity_chart(target_features, matched_features),
    }
    paths: list[Path] = []
    for filename, figure in outputs.items():
        path = config.charts_dir / filename
        figure.write_html(path, include_plotlyjs="cdn", full_html=True)
        paths.append(path)
    return paths


def _build_summary(
    config: PipelineConfig,
    master_df: pd.DataFrame,
    monthly_df: pd.DataFrame,
    features_df: pd.DataFrame,
    main_demo: dict[str, Any],
    elapsed: float,
    timings: dict[str, float],
    generated_files: list[Path],
    fallback_used: bool,
) -> dict[str, Any]:
    outcomes = main_demo["outcome_summary"]["outcomes"]
    risk_ratio = outcomes["stress"]["ratio"] + outcomes["delinquent"]["ratio"]
    best = selector_best_whatif_scenario(main_demo["whatif_results"])
    unique_files = sorted({str(path) for path in generated_files})
    return {
        "customer_count": int(len(master_df)),
        "monthly_row_count": int(len(monthly_df)),
        "feature_row_count": int(len(features_df)),
        "main_customer_id": str(main_demo["customer_id"]),
        "matched_count": int(main_demo["match_summary"]["matched_count"]),
        "risk_group_ratio": round(float(risk_ratio), 6),
        "breakpoint": main_demo["breakpoint_result"],
        "best_whatif_scenario": {
            "scenario_id": int(best["scenario_id"]),
            "scenario_name": str(best["scenario_name"]),
            "improvement_vs_baseline": float(best["improvement_vs_baseline"]),
        },
        "elapsed_seconds": round(float(elapsed), 2),
        "stage_timings": {key: round(value, 3) for key, value in timings.items()},
        "generated_files": unique_files,
        "fallback_used": fallback_used,
        "paths": {
            "customer_master": str(config.customer_master_path),
            "customer_monthly": str(config.customer_monthly_path),
            "trajectory_features": str(config.trajectory_features_path),
            "demo_customers": str(config.demo_customers_path),
            "main_demo_customer": str(config.main_demo_customer_path),
            "breakpoint_result": str(config.breakpoint_result_path),
            "whatif_results": str(config.whatif_results_path),
        },
    }


def _assert_raw_data_matches_config(
    config: PipelineConfig,
    master_df: pd.DataFrame | None,
    monthly_df: pd.DataFrame | None,
) -> None:
    _ensure_dataframes(master_df, monthly_df)
    missing_master = [column for column in settings.CUSTOMER_MASTER_COLUMNS if column not in master_df.columns]
    missing_monthly = [column for column in settings.CUSTOMER_MONTHLY_COLUMNS if column not in monthly_df.columns]
    if missing_master or missing_monthly:
        raise PipelineError(
            "synthetic_data_generation",
            f"raw data schema mismatch; missing_master={missing_master}, missing_monthly={missing_monthly}",
        )

    if len(master_df) != config.customer_count:
        raise PipelineError(
            "synthetic_data_generation",
            (
                f"raw customer count {len(master_df)} does not match requested "
                f"customer_count {config.customer_count}; rerun with --force"
            ),
        )

    expected_monthly_rows = config.customer_count * settings.TOTAL_MONTHS
    if len(monthly_df) != expected_monthly_rows:
        raise PipelineError(
            "synthetic_data_generation",
            (
                f"monthly row count {len(monthly_df)} does not match expected "
                f"{expected_monthly_rows}; rerun with --force"
            ),
        )

    seeds = set(pd.to_numeric(master_df["random_seed"], errors="coerce").dropna().astype(int).unique())
    if seeds != {config.random_seed}:
        raise PipelineError(
            "synthetic_data_generation",
            (
                f"raw random_seed values {sorted(seeds)} do not match requested "
                f"random_seed {config.random_seed}; rerun with --force"
            ),
        )

    month_counts = monthly_df.groupby("customer_id")["month"].nunique()
    if not month_counts.eq(settings.TOTAL_MONTHS).all():
        raise PipelineError(
            "synthetic_data_generation",
            "raw monthly data must contain exactly 36 months per customer; rerun with --force",
        )
    if monthly_df[["customer_id", "month"]].duplicated().any():
        raise PipelineError(
            "synthetic_data_generation",
            "raw monthly data contains duplicated customer_id + month rows; rerun with --force",
        )


def _assert_features_match_raw(
    config: PipelineConfig,
    features_df: pd.DataFrame,
    master_df: pd.DataFrame,
) -> None:
    missing_features = [column for column in settings.TRAJECTORY_FEATURE_COLUMNS if column not in features_df.columns]
    if missing_features:
        raise PipelineError(
            "feature_generation",
            f"trajectory feature schema mismatch; missing columns: {missing_features}",
        )
    if len(features_df) != config.customer_count:
        raise PipelineError(
            "feature_generation",
            (
                f"feature row count {len(features_df)} does not match requested "
                f"customer_count {config.customer_count}; rerun with --force"
            ),
        )
    raw_ids = set(master_df["customer_id"].astype(str))
    feature_ids = set(features_df["customer_id"].astype(str))
    if feature_ids != raw_ids:
        raise PipelineError(
            "feature_generation",
            "trajectory feature customer_ids do not match raw customer ids; rerun with --force",
        )


def _assert_demo_outputs_match_config(
    config: PipelineConfig,
    demo_df: pd.DataFrame,
    main_demo: dict[str, Any],
    features_df: pd.DataFrame,
) -> None:
    missing_demo = [column for column in settings.DEMO_CUSTOMER_COLUMNS if column not in demo_df.columns]
    if missing_demo:
        raise PipelineError(
            "demo_candidate_search",
            f"demo customer schema mismatch; missing columns: {missing_demo}",
        )
    roles = set(demo_df["demo_role"].astype(str))
    if roles != set(settings.DEMO_ROLES):
        raise PipelineError(
            "demo_candidate_search",
            f"demo roles {sorted(roles)} do not match required roles {list(settings.DEMO_ROLES)}",
        )
    main_customer_id = str(main_demo.get("customer_id", ""))
    if main_customer_id not in set(features_df["customer_id"].astype(str)):
        raise PipelineError(
            "demo_candidate_search",
            f"main demo customer_id {main_customer_id!r} is not present in trajectory features",
        )
    stored_seed = main_demo.get("random_seed")
    if stored_seed is not None and int(stored_seed) != config.random_seed:
        raise PipelineError(
            "demo_candidate_search",
            (
                f"main demo random_seed {stored_seed} does not match requested "
                f"random_seed {config.random_seed}; rerun with --force"
            ),
        )


def _is_demo_candidate_exhaustion_error(exc: ValueError) -> bool:
    message = str(exc)
    return message.startswith("No ") and ("candidate" in message or "customer" in message)


def _load_required_raw_data(config: PipelineConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not _raw_outputs_exist(config):
        raise PipelineError(
            "synthetic_data_generation",
            "raw data files are missing; rerun without --skip-generation",
        )
    return pd.read_csv(config.customer_master_path), pd.read_csv(config.customer_monthly_path)


def _raw_outputs_exist(config: PipelineConfig) -> bool:
    return config.customer_master_path.exists() and config.customer_monthly_path.exists()


def _demo_outputs_exist(config: PipelineConfig) -> bool:
    return config.demo_customers_path.exists() and config.main_demo_customer_path.exists()


def _ensure_dataframes(master_df: pd.DataFrame | None, monthly_df: pd.DataFrame | None) -> None:
    if master_df is None or monthly_df is None:
        raise PipelineError("data_validation", "raw dataframes are unavailable")


def _validate_config(config: PipelineConfig) -> None:
    if config.customer_count <= 0:
        raise ValueError("customer_count must be positive.")
    if config.customer_count < len(settings.DEMO_ROLES):
        raise ValueError("customer_count must be at least 3 for demo role selection.")
    if config.top_k <= 0:
        raise ValueError("top_k must be positive.")
    if config.top_k >= config.customer_count:
        raise ValueError("top_k must be smaller than customer_count.")


@contextmanager
def _stage(name: str, timings: dict[str, float], verbose: bool) -> Iterator[None]:
    if verbose:
        print(f"[start] {name}")
    started_at = time.perf_counter()
    try:
        yield
    except Exception as exc:
        if verbose:
            print(f"[failed] {name}: {exc}")
        if isinstance(exc, PipelineError):
            raise
        raise PipelineError(name, str(exc)) from exc
    finally:
        timings[name] = time.perf_counter() - started_at
    if verbose:
        print(f"[done] {name} ({timings[name]:.2f}s)")


@contextmanager
def _patched_settings(config: PipelineConfig) -> Iterator[None]:
    original_values = {
        "CUSTOMER_COUNT": settings.CUSTOMER_COUNT,
        "RANDOM_SEED": settings.RANDOM_SEED,
        "TOP_K_MATCHES": settings.TOP_K_MATCHES,
        "CUSTOMER_MASTER_PATH": settings.CUSTOMER_MASTER_PATH,
        "CUSTOMER_MONTHLY_PATH": settings.CUSTOMER_MONTHLY_PATH,
        "TRAJECTORY_FEATURES_PATH": settings.TRAJECTORY_FEATURES_PATH,
        "REPORTS_DIR": settings.REPORTS_DIR,
        "DATA_PROCESSED_DIR": settings.DATA_PROCESSED_DIR,
        "DATA_DEMO_DIR": settings.DATA_DEMO_DIR,
        "CHARTS_DIR": settings.CHARTS_DIR,
        "DEMO_CUSTOMERS_PATH": settings.DEMO_CUSTOMERS_PATH,
        "MAIN_DEMO_CUSTOMER_PATH": settings.MAIN_DEMO_CUSTOMER_PATH,
    }
    settings.CUSTOMER_COUNT = config.customer_count
    settings.RANDOM_SEED = config.random_seed
    settings.TOP_K_MATCHES = config.top_k
    settings.CUSTOMER_MASTER_PATH = config.customer_master_path
    settings.CUSTOMER_MONTHLY_PATH = config.customer_monthly_path
    settings.TRAJECTORY_FEATURES_PATH = config.trajectory_features_path
    settings.REPORTS_DIR = config.reports_dir
    settings.DATA_PROCESSED_DIR = config.data_processed_dir
    settings.DATA_DEMO_DIR = config.data_demo_dir
    settings.CHARTS_DIR = config.charts_dir
    settings.DEMO_CUSTOMERS_PATH = config.demo_customers_path
    settings.MAIN_DEMO_CUSTOMER_PATH = config.main_demo_customer_path
    try:
        yield
    finally:
        for key, value in original_values.items():
            setattr(settings, key, value)
