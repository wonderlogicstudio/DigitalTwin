"""Export the main demo customer's Plotly charts as standalone HTML files."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings  # noqa: E402
from src.breakpoint_analyzer import (  # noqa: E402
    AVOIDANCE_OUTCOMES,
    RISK_OUTCOMES,
    calculate_monthly_smd,
    prepare_breakpoint_data,
)
from src.matcher import TrajectoryMatcher  # noqa: E402
from src.visualizations import (  # noqa: E402
    create_breakpoint_comparison_chart,
    create_current_trajectory_chart,
    create_income_expense_chart,
    create_outcome_bar_chart,
    create_twin_trajectory_chart,
    create_whatif_balance_chart,
    create_whatif_improvement_chart,
)


def main() -> None:
    """Build and export the main demo chart set."""

    started_at = time.perf_counter()
    settings.CHARTS_DIR.mkdir(parents=True, exist_ok=True)

    main_demo = json.loads(settings.MAIN_DEMO_CUSTOMER_PATH.read_text(encoding="utf-8"))
    target_customer_id = str(main_demo["customer_id"])
    monthly_df = pd.read_csv(settings.CUSTOMER_MONTHLY_PATH)
    features_df = pd.read_csv(settings.TRAJECTORY_FEATURES_PATH)

    matcher = TrajectoryMatcher().fit(features_df)
    matches = matcher.match(target_customer_id, top_k=settings.TOP_K_MATCHES)
    matched_ids = matches["matched_customer_id"].astype(str).tolist()
    monthly_with_ratios = _add_balance_ratios(monthly_df, [target_customer_id, *matched_ids])

    target_history = monthly_with_ratios[
        (monthly_with_ratios["customer_id"] == target_customer_id)
        & (monthly_with_ratios["month"] <= settings.OBSERVATION_END_MONTH)
    ]
    twin_trajectory = monthly_with_ratios[monthly_with_ratios["customer_id"].isin(matched_ids)]
    breakpoint_comparison = _build_breakpoint_comparison(matched_ids, monthly_df)

    breakpoint_metric = main_demo["breakpoint_result"].get("primary_factor") or "savings_rate"

    figures = _build_chart_figures(
        target_history=target_history,
        twin_trajectory=twin_trajectory,
        breakpoint_metric=breakpoint_metric,
        breakpoint_result=main_demo["breakpoint_result"],
        breakpoint_comparison=breakpoint_comparison,
        outcome_summary=main_demo["outcome_summary"],
        whatif_results=main_demo["whatif_results"],
        language="ko",
    )
    chart_paths = {name: settings.CHARTS_DIR / f"{name}.html" for name in figures}
    for language in ("ko", "en"):
        localized_figures = _build_chart_figures(
            target_history=target_history,
            twin_trajectory=twin_trajectory,
            breakpoint_metric=breakpoint_metric,
            breakpoint_result=main_demo["breakpoint_result"],
            breakpoint_comparison=breakpoint_comparison,
            outcome_summary=main_demo["outcome_summary"],
            whatif_results=main_demo["whatif_results"],
            language=language,
        )
        for name, figure in localized_figures.items():
            localized_name = f"{language}_{name}"
            figures[localized_name] = figure
            chart_paths[localized_name] = settings.CHARTS_DIR / f"{localized_name}.html"

    for name, figure in figures.items():
        figure.write_html(chart_paths[name], include_plotlyjs="cdn", full_html=True)

    elapsed = time.perf_counter() - started_at
    print(f"target_customer_id: {target_customer_id}")
    for name, path in chart_paths.items():
        print(f"{name}: {path}")
    print("twin_sampling: default quantile band and medians; raw sample lines are opt-in")
    print(f"elapsed_seconds: {elapsed:.2f}")


def _build_chart_figures(
    *,
    target_history: pd.DataFrame,
    twin_trajectory: pd.DataFrame,
    breakpoint_metric: str,
    breakpoint_result: dict,
    breakpoint_comparison: pd.DataFrame,
    outcome_summary: dict,
    whatif_results: dict,
    language: str = "ko",
) -> dict[str, object]:
    return {
        "current_income_expense": create_income_expense_chart(target_history, language=language),
        "current_savings_rate": create_current_trajectory_chart(target_history, "savings_rate", language=language),
        "current_dsr": create_current_trajectory_chart(target_history, "dsr", language=language),
        "twin_trajectory": create_twin_trajectory_chart(
            target_history,
            twin_trajectory,
            metric=breakpoint_metric,
            breakpoint_result=breakpoint_result,
            language=language,
        ),
        "outcome_distribution": create_outcome_bar_chart(outcome_summary, language=language),
        "breakpoint": create_breakpoint_comparison_chart(
            breakpoint_result,
            breakpoint_comparison,
            language=language,
        ),
        "whatif_balance": create_whatif_balance_chart(whatif_results, language=language),
        "whatif_improvement": create_whatif_improvement_chart(whatif_results, language=language),
    }


def _add_balance_ratios(monthly_df: pd.DataFrame, customer_ids: list[str]) -> pd.DataFrame:
    filtered_df = monthly_df[monthly_df["customer_id"].isin(customer_ids)].copy()
    baseline_income = (
        filtered_df[filtered_df["month"].between(10, settings.OBSERVATION_END_MONTH)]
        .groupby("customer_id")["income"]
        .mean()
    )
    denominator = filtered_df["customer_id"].map(baseline_income).fillna(1).clip(lower=1)
    filtered_df["cash_balance_ratio"] = filtered_df["cash_balance"] / denominator
    filtered_df["loan_balance_ratio"] = filtered_df["loan_balance"] / denominator
    return filtered_df


def _build_breakpoint_comparison(matched_ids: list[str], monthly_df: pd.DataFrame) -> pd.DataFrame:
    enriched_df = prepare_breakpoint_data(matched_ids, monthly_df)
    customer_outcomes = (
        enriched_df[["customer_id", "final_outcome"]]
        .drop_duplicates("customer_id")
        .set_index("customer_id")["final_outcome"]
    )
    risk_ids = customer_outcomes[customer_outcomes.isin(RISK_OUTCOMES)].index.tolist()
    avoidance_ids = customer_outcomes[customer_outcomes.isin(AVOIDANCE_OUTCOMES)].index.tolist()
    future_df = enriched_df[
        enriched_df["month"].between(settings.FUTURE_START_MONTH, settings.FUTURE_END_MONTH)
    ]
    return calculate_monthly_smd(future_df, risk_ids, avoidance_ids)


if __name__ == "__main__":
    main()
