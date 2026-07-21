"""Precomputed demo artifacts for resilient hackathon presentations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from config import settings
from src.ui_components import add_balance_ratios, build_breakpoint_comparison
from src.visualizations import (
    create_breakpoint_comparison_chart,
    create_current_trajectory_chart,
    create_outcome_bar_chart,
    create_twin_trajectory_chart,
    create_whatif_balance_chart,
)


MODE_LIVE = "Live calculation"
MODE_CACHED = "Cached calculation"
MODE_FALLBACK = "Demo fallback"

REQUIRED_DEMO_CACHE_FILES = (
    settings.DEMO_MATCHED_CUSTOMERS_PATH,
    settings.DEMO_MATCHED_FUTURE_TRAJECTORY_PATH,
    settings.DEMO_OUTCOME_SUMMARY_PATH,
    settings.DEMO_BREAKPOINT_RESULT_PATH,
    settings.DEMO_WHATIF_RESULTS_PATH,
    settings.MAIN_DEMO_CUSTOMER_PATH,
)


@dataclass(frozen=True)
class DemoCachePayload:
    """Loaded precomputed demo analysis."""

    customer_id: str
    analysis: dict[str, Any]
    main_demo_customer: dict[str, Any]
    missing_files: list[Path]


def required_demo_cache_files() -> tuple[Path, ...]:
    """Return all files needed for the demo fallback analysis."""

    return REQUIRED_DEMO_CACHE_FILES


def missing_demo_cache_files() -> list[Path]:
    """Return precomputed demo files that are currently missing."""

    return [path for path in REQUIRED_DEMO_CACHE_FILES if not path.exists()]


def has_demo_cache() -> bool:
    """Return True when all precomputed demo artifacts are present."""

    return not missing_demo_cache_files()


def save_precomputed_demo_artifacts(
    *,
    customer_id: str,
    matches: pd.DataFrame,
    matched_ids: list[str],
    monthly_df: pd.DataFrame,
    outcome_summary: dict[str, Any],
    breakpoint_result: dict[str, Any],
    whatif_results: dict[str, Any],
    main_demo_customer: dict[str, Any],
    output_dir: Path = settings.DATA_DEMO_DIR,
) -> tuple[Path, ...]:
    """Save fixed demo artifacts for offline/fallback use."""

    output_dir.mkdir(parents=True, exist_ok=True)
    matched_customers_path = output_dir / settings.MATCHED_CUSTOMERS_FILENAME
    matched_future_path = output_dir / settings.MATCHED_FUTURE_TRAJECTORY_FILENAME
    outcome_path = output_dir / settings.OUTCOME_SUMMARY_FILENAME
    breakpoint_path = output_dir / settings.BREAKPOINT_RESULT_FILENAME
    whatif_path = output_dir / settings.WHATIF_RESULTS_FILENAME
    main_demo_path = output_dir / settings.MAIN_DEMO_CUSTOMER_FILENAME

    matches.to_csv(matched_customers_path, index=False, encoding="utf-8")
    future_df = build_matched_future_trajectory(customer_id, matched_ids, monthly_df)
    future_df.to_csv(matched_future_path, index=False, encoding="utf-8")
    _write_json(outcome_path, outcome_summary)
    _write_json(breakpoint_path, breakpoint_result)
    _write_json(whatif_path, whatif_results)
    _write_json(main_demo_path, main_demo_customer)
    return (
        matched_customers_path,
        matched_future_path,
        outcome_path,
        breakpoint_path,
        whatif_path,
        main_demo_path,
    )


def build_matched_future_trajectory(
    target_customer_id: str,
    matched_ids: list[str],
    monthly_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build the fixed matched future trajectory artifact."""

    monthly_with_ratios = add_balance_ratios(monthly_df, matched_ids)
    future_df = monthly_with_ratios[
        monthly_with_ratios["customer_id"].astype(str).isin(set(matched_ids))
        & monthly_with_ratios["month"].between(settings.FUTURE_START_MONTH, settings.FUTURE_END_MONTH)
    ].copy()
    future_df.insert(0, "target_customer_id", str(target_customer_id))
    future_df = future_df.rename(columns={"customer_id": "matched_customer_id"})
    columns = (
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
    missing_columns = [column for column in columns if column not in future_df.columns]
    if missing_columns:
        raise ValueError(f"Missing matched future trajectory columns: {missing_columns}")
    return future_df.loc[:, columns].sort_values(["matched_customer_id", "month"]).reset_index(drop=True)


def load_precomputed_demo_analysis(
    customer_id: str | None = None,
    demo_dir: Path = settings.DATA_DEMO_DIR,
) -> DemoCachePayload:
    """Load precomputed demo analysis from CSV/JSON artifacts."""

    paths = _cache_paths(demo_dir)
    missing_files = [path for path in paths.values() if not path.exists()]
    if missing_files:
        raise FileNotFoundError(f"Missing precomputed demo files: {missing_files}")

    main_demo = _read_json(paths["main_demo_customer"])
    target_id = str(customer_id or main_demo["customer_id"])
    if target_id != str(main_demo["customer_id"]):
        raise ValueError("Precomputed demo cache is available only for the fixed main demo customer.")

    matches = pd.read_csv(paths["matched_customers"])
    _validate_columns(matches, ("target_customer_id", "matched_customer_id", "rank", "distance", "similarity_score"), "matched_customers")
    matches = matches[matches["target_customer_id"].astype(str) == target_id].copy()
    if matches.empty:
        raise ValueError(f"No cached matches for customer_id: {target_id}")
    matched_ids = matches["matched_customer_id"].astype(str).tolist()

    matched_future = pd.read_csv(paths["matched_future_trajectory"])
    _validate_columns(
        matched_future,
        ("target_customer_id", "matched_customer_id", "month", "final_outcome"),
        "matched_future_trajectory",
    )
    matched_future = matched_future[matched_future["target_customer_id"].astype(str) == target_id].copy()

    outcome_summary = _read_json(paths["outcome_summary"])
    breakpoint_result = _read_json(paths["breakpoint_result"])
    whatif_results = _read_json(paths["whatif_results"])
    analysis = {
        "customer_id": target_id,
        "matches": matches.reset_index(drop=True),
        "matched_ids": matched_ids,
        "outcome_summary": outcome_summary,
        "breakpoint_result": breakpoint_result,
        "whatif_results": whatif_results,
        "breakpoint_comparison": pd.DataFrame(),
        "matched_future_trajectory": matched_future.reset_index(drop=True),
        "errors": {},
        "mode": MODE_CACHED,
    }
    return DemoCachePayload(
        customer_id=target_id,
        analysis=analysis,
        main_demo_customer=main_demo,
        missing_files=[],
    )


def build_fallback_customer_summary(main_demo_customer: dict[str, Any]) -> dict[str, Any]:
    """Return current metric cards from the fixed main demo JSON."""

    current = dict(main_demo_customer.get("current_metrics", {}))
    current["customer_id"] = str(main_demo_customer.get("customer_id", ""))
    return current


def save_demo_backup(
    *,
    main_demo_customer: dict[str, Any],
    analysis: dict[str, Any],
    monthly_df: pd.DataFrame | None = None,
    output_dir: Path = settings.DEMO_BACKUP_DIR,
) -> tuple[Path, ...]:
    """Save presenter backup material under reports/demo_backup."""

    output_dir.mkdir(parents=True, exist_ok=True)
    customer_id = str(main_demo_customer["customer_id"])
    summary_path = output_dir / "demo_summary.json"
    metrics_path = output_dir / "main_customer_metrics.csv"
    runbook_path = output_dir / "presentation_runbook.md"
    _write_json(
        summary_path,
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "customer_id": customer_id,
            "current_metrics": main_demo_customer.get("current_metrics", {}),
            "match_summary": main_demo_customer.get("match_summary", {}),
            "outcome_summary": analysis.get("outcome_summary", {}),
            "breakpoint_result": analysis.get("breakpoint_result", {}),
            "best_whatif_scenario": _best_whatif_scenario(analysis.get("whatif_results", {})),
        },
    )
    pd.DataFrame([build_fallback_customer_summary(main_demo_customer)]).to_csv(
        metrics_path,
        index=False,
        encoding="utf-8",
    )
    runbook_path.write_text(_presentation_runbook(customer_id), encoding="utf-8")

    paths = [summary_path, metrics_path, runbook_path]
    paths.extend(_save_backup_charts(output_dir, customer_id, analysis, monthly_df))
    return tuple(paths)


def _save_backup_charts(
    output_dir: Path,
    customer_id: str,
    analysis: dict[str, Any],
    monthly_df: pd.DataFrame | None,
) -> list[Path]:
    paths: list[Path] = []
    chart_specs = {
        "outcome_distribution.html": lambda: create_outcome_bar_chart(analysis["outcome_summary"]),
        "breakpoint.html": lambda: create_breakpoint_comparison_chart(analysis["breakpoint_result"], analysis.get("breakpoint_comparison")),
        "whatif.html": lambda: create_whatif_balance_chart(analysis["whatif_results"]),
    }
    if monthly_df is not None and not monthly_df.empty:
        matched_ids = list(analysis.get("matched_ids", []))
        with_ratios = add_balance_ratios(monthly_df, [customer_id, *matched_ids])
        target_history = with_ratios[
            (with_ratios["customer_id"].astype(str) == customer_id)
            & (with_ratios["month"] <= settings.OBSERVATION_END_MONTH)
        ]
        twin_df = with_ratios[with_ratios["customer_id"].astype(str).isin(set(matched_ids))]
        metric = analysis["breakpoint_result"].get("primary_factor") or "savings_rate"
        chart_specs["current_trajectory.html"] = lambda: create_current_trajectory_chart(target_history, "savings_rate")
        chart_specs["twin_trajectory.html"] = lambda: create_twin_trajectory_chart(
            target_history,
            twin_df,
            metric=metric,
            breakpoint_result=analysis["breakpoint_result"],
        )

    for filename, factory in chart_specs.items():
        path = output_dir / filename
        try:
            factory().write_html(path, include_plotlyjs="cdn", full_html=True)
        except Exception as exc:  # noqa: BLE001
            path = output_dir / filename.replace(".html", ".txt")
            path.write_text(f"Chart generation skipped: {exc}", encoding="utf-8")
        paths.append(path)
    return paths


def _cache_paths(demo_dir: Path) -> dict[str, Path]:
    return {
        "matched_customers": demo_dir / settings.MATCHED_CUSTOMERS_FILENAME,
        "matched_future_trajectory": demo_dir / settings.MATCHED_FUTURE_TRAJECTORY_FILENAME,
        "outcome_summary": demo_dir / settings.OUTCOME_SUMMARY_FILENAME,
        "breakpoint_result": demo_dir / settings.BREAKPOINT_RESULT_FILENAME,
        "whatif_results": demo_dir / settings.WHATIF_RESULTS_FILENAME,
        "main_demo_customer": demo_dir / settings.MAIN_DEMO_CUSTOMER_FILENAME,
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON file: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _validate_columns(df: pd.DataFrame, required_columns: tuple[str, ...], context: str) -> None:
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in {context}: {missing}")


def _best_whatif_scenario(whatif_results: dict[str, Any]) -> dict[str, Any] | None:
    scenarios = [
        scenario
        for scenario in whatif_results.get("scenarios", [])
        if scenario.get("scenario_name") != "baseline"
    ]
    if not scenarios:
        return None
    return max(scenarios, key=lambda scenario: float(scenario.get("improvement_vs_baseline", 0.0)))


def _presentation_runbook(customer_id: str) -> str:
    return (
        "# Financial Path Twin Demo Runbook\n\n"
        "1. Open the app and confirm the mode badge at the top.\n"
        f"2. Select the main demo customer `{customer_id}`.\n"
        "3. Show current 12-month trajectory and current status.\n"
        "4. Show similar-customer outcomes as observed peer results, not prediction probability.\n"
        "5. Show breakpoint month and primary separating factor without causal wording.\n"
        "6. Show What-if scenarios as cash-flow improvement only.\n"
        "7. If live calculation fails, use the cached/demo fallback mode and backup HTML files in this folder.\n"
    )
