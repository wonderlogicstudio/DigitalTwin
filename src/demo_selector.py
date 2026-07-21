"""Demo customer selection for hackathon presentation scenarios."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from config import settings
from src.breakpoint_analyzer import find_breakpoint
from src.matcher import TrajectoryMatcher
from src.whatif_simulator import build_whatif_results


RISK_OUTCOMES = {"stress", "delinquent"}
AVOIDANCE_OUTCOMES = {"healthy", "recovered"}
OUTCOME_ORDER = ("healthy", "recovered", "stress", "delinquent")


@dataclass(frozen=True)
class RelaxationLevel:
    """Main-candidate thresholds for one relaxation pass."""

    name: str
    risk_ratio_range: tuple[float, float]
    breakpoint_month_range: tuple[int, int]
    dsr_range: tuple[float, float]
    fixed_expense_ratio_range: tuple[float, float]
    reason: str


RELAXATION_LEVELS = (
    RelaxationLevel(
        name="strict",
        risk_ratio_range=(0.25, 0.40),
        breakpoint_month_range=(13, 16),
        dsr_range=(0.30, 0.44),
        fixed_expense_ratio_range=(0.38, 0.49),
        reason="strict criteria",
    ),
    RelaxationLevel(
        name="risk_ratio_20_45",
        risk_ratio_range=(0.20, 0.45),
        breakpoint_month_range=(13, 16),
        dsr_range=(0.30, 0.44),
        fixed_expense_ratio_range=(0.38, 0.49),
        reason="relaxed: risk_group_ratio expanded to 20-45%",
    ),
    RelaxationLevel(
        name="breakpoint_13_18",
        risk_ratio_range=(0.20, 0.45),
        breakpoint_month_range=(13, 18),
        dsr_range=(0.30, 0.44),
        fixed_expense_ratio_range=(0.38, 0.49),
        reason="relaxed: breakpoint range expanded to months 13-18",
    ),
    RelaxationLevel(
        name="dsr_25_45",
        risk_ratio_range=(0.20, 0.45),
        breakpoint_month_range=(13, 18),
        dsr_range=(0.25, 0.45),
        fixed_expense_ratio_range=(0.38, 0.49),
        reason="relaxed: DSR range expanded to 0.25-0.45",
    ),
    RelaxationLevel(
        name="fixed_expense_35_52",
        risk_ratio_range=(0.20, 0.45),
        breakpoint_month_range=(13, 18),
        dsr_range=(0.25, 0.45),
        fixed_expense_ratio_range=(0.35, 0.52),
        reason="relaxed: fixed_expense_ratio range expanded to 0.35-0.52",
    ),
)


def select_demo_customers(
    monthly_df: pd.DataFrame,
    features_df: pd.DataFrame,
    generated_at: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Select main, stable comparison, and high-risk demo customers."""

    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    matcher = TrajectoryMatcher().fit(features_df)
    current_metrics = build_current_metrics(monthly_df)
    outcome_lookup = build_final_outcome_lookup(monthly_df)

    main = select_main_customer(current_metrics, monthly_df, matcher, outcome_lookup)
    stable = select_stable_customer(current_metrics, monthly_df, matcher, outcome_lookup, {main["customer_id"]})
    high_risk = select_high_risk_customer(
        current_metrics,
        monthly_df,
        matcher,
        outcome_lookup,
        {main["customer_id"], stable["customer_id"]},
    )

    selected = [main, stable, high_risk]
    demo_df = pd.DataFrame([candidate["demo_row"] for candidate in selected])
    demo_df = demo_df.loc[:, settings.DEMO_CUSTOMER_COLUMNS]
    main_json = build_main_demo_customer(main, generated_at)
    return demo_df, main_json


def build_current_metrics(monthly_df: pd.DataFrame) -> pd.DataFrame:
    """Build current and recent metrics used for demo selection."""

    month_12 = monthly_df.loc[monthly_df["month"] == settings.OBSERVATION_END_MONTH, [
        "customer_id",
        "monthly_status",
        "delinquency_flag",
    ]].rename(columns={"monthly_status": "current_status"})
    recent_3 = (
        monthly_df.loc[monthly_df["month"].between(10, settings.OBSERVATION_END_MONTH)]
        .groupby("customer_id")
        .agg(
            recent_savings_rate=("savings_rate", "mean"),
            recent_dsr=("dsr", "mean"),
            recent_fixed_expense_ratio=("fixed_expense_ratio", "mean"),
        )
        .reset_index()
    )
    recent_6 = monthly_df.loc[monthly_df["month"].between(7, settings.OBSERVATION_END_MONTH)]
    slopes = [
        {
            "customer_id": customer_id,
            "savings_rate_slope_6m": float(
                np.polyfit(group["month"].to_numpy(dtype=float), group["savings_rate"].to_numpy(dtype=float), 1)[0]
            ),
            "balance_decline_run_6m": _tail_decline_run(group.sort_values("month")["cash_balance"]),
        }
        for customer_id, group in recent_6.groupby("customer_id", sort=True)
    ]
    metrics = month_12.merge(recent_3, on="customer_id").merge(pd.DataFrame(slopes), on="customer_id")
    return metrics.sort_values("customer_id").reset_index(drop=True)


def build_final_outcome_lookup(monthly_df: pd.DataFrame) -> pd.Series:
    """Return one final outcome per customer."""

    return monthly_df.drop_duplicates("customer_id").set_index("customer_id")["final_outcome"]


def select_main_customer(
    current_metrics: pd.DataFrame,
    monthly_df: pd.DataFrame,
    matcher: TrajectoryMatcher,
    outcome_lookup: pd.Series,
) -> dict[str, Any]:
    """Select the best main demo customer with documented relaxation levels."""

    fallback_candidates: list[dict[str, Any]] = []
    for level in RELAXATION_LEVELS:
        prefiltered = _main_prefilter(current_metrics, level)
        evaluated: list[dict[str, Any]] = []
        for row in _prioritized_rows(prefiltered, "main"):
            candidate = evaluate_customer(str(row.customer_id), "main", row, monthly_df, matcher, outcome_lookup)
            candidate["selection_reason"] = _main_reason(candidate, level)
            candidate["demo_score"] = score_main_candidate(candidate)
            fallback_candidates.append(candidate)
            if _passes_main_rules(candidate, level):
                evaluated.append(candidate)
        if evaluated:
            return _finalize_candidate(max(evaluated, key=_candidate_sort_key))

    if fallback_candidates:
        best = max(fallback_candidates, key=_candidate_sort_key)
        best["selection_reason"] = (
            "fallback_no_full_match; " + best["selection_reason"]
        )
        return _finalize_candidate(best)
    raise ValueError("No main demo candidates were available, even after relaxation.")


def select_stable_customer(
    current_metrics: pd.DataFrame,
    monthly_df: pd.DataFrame,
    matcher: TrajectoryMatcher,
    outcome_lookup: pd.Series,
    excluded_ids: set[str],
) -> dict[str, Any]:
    """Select a stable comparison demo customer."""

    prefiltered = current_metrics[
        (current_metrics["current_status"] == "healthy")
        & (current_metrics["recent_savings_rate"] >= 0.15)
        & (~current_metrics["customer_id"].isin(excluded_ids))
    ]
    best: dict[str, Any] | None = None
    found = 0
    for row in _prioritized_rows(prefiltered, "stable_comparison"):
        candidate = evaluate_customer(
            str(row.customer_id),
            "stable_comparison",
            row,
            monthly_df,
            matcher,
            outcome_lookup,
        )
        outcome_summary = candidate["outcome_summary"]
        healthy_recovered = (
            outcome_summary["outcomes"]["healthy"]["ratio"]
            + outcome_summary["outcomes"]["recovered"]["ratio"]
        )
        delinquent_ratio = outcome_summary["outcomes"]["delinquent"]["ratio"]
        breakpoint_month = candidate["breakpoint_result"]["breakpoint_month"]
        breakpoint_ok = (
            candidate["breakpoint_result"]["status"] != "found"
            or (breakpoint_month is not None and breakpoint_month > 20)
        )
        if healthy_recovered >= 0.80 and delinquent_ratio < 0.05 and breakpoint_ok:
            candidate["demo_score"] = score_stable_candidate(candidate)
            candidate["selection_reason"] = (
                "healthy month-12 status; healthy+recovered matched ratio >= 80%; "
                "delinquent matched ratio < 5%; no near breakpoint; recent savings rate >= 15%"
            )
            best = candidate if best is None or _candidate_sort_key(candidate) > _candidate_sort_key(best) else best
            found += 1
            if found >= 50:
                break
    if best is None:
        raise ValueError("No stable comparison customer met the selection criteria.")
    return _finalize_candidate(best)


def select_high_risk_customer(
    current_metrics: pd.DataFrame,
    monthly_df: pd.DataFrame,
    matcher: TrajectoryMatcher,
    outcome_lookup: pd.Series,
    excluded_ids: set[str],
) -> dict[str, Any]:
    """Select a high-risk demo customer."""

    prefiltered = current_metrics[
        (current_metrics["current_status"].isin(["watch", "stress"]))
        & (current_metrics["balance_decline_run_6m"] >= 3)
        & (~current_metrics["customer_id"].isin(excluded_ids))
    ]
    prefiltered = rank_high_risk_prefilter(prefiltered, matcher, outcome_lookup)
    best: dict[str, Any] | None = None
    found = 0
    for row in _prioritized_rows(prefiltered, "high_risk"):
        candidate = evaluate_customer(str(row.customer_id), "high_risk", row, monthly_df, matcher, outcome_lookup)
        risk_ratio = candidate["demo_row"]["risk_group_ratio"]
        breakpoint_month = candidate["breakpoint_result"]["breakpoint_month"]
        baseline = _baseline_scenario(candidate["whatif_results"])
        cash_problem = baseline["cash_depletion_month"] is not None or baseline["minimum_cash_balance"] < 0
        if (
            risk_ratio >= 0.60
            and candidate["breakpoint_result"]["status"] == "found"
            and breakpoint_month is not None
            and 13 <= breakpoint_month <= 14
            and cash_problem
        ):
            candidate["demo_score"] = score_high_risk_candidate(candidate)
            candidate["selection_reason"] = (
                "watch/stress month-12 status; balance declined for at least 3 recent months; "
                "risk matched ratio >= 60%; breakpoint at month 13-14; baseline cash depletion or negative minimum balance"
            )
            best = candidate if best is None or _candidate_sort_key(candidate) > _candidate_sort_key(best) else best
            found += 1
            if found >= 50:
                break
    if best is None:
        raise ValueError("No high-risk customer met the selection criteria.")
    return _finalize_candidate(best)


def rank_high_risk_prefilter(
    prefiltered: pd.DataFrame,
    matcher: TrajectoryMatcher,
    outcome_lookup: pd.Series,
) -> pd.DataFrame:
    """Reduce high-risk candidates with fast matched outcome ratios before deep checks."""

    if prefiltered.empty:
        return prefiltered
    if matcher._weighted_features is None or matcher._customer_ids is None:
        return prefiltered

    customer_ids = matcher._customer_ids.to_numpy()
    customer_index = {customer_id: index for index, customer_id in enumerate(customer_ids)}
    rows: list[dict[str, Any]] = []
    for row in prefiltered.itertuples(index=False):
        customer_id = str(row.customer_id)
        target_index = customer_index[customer_id]
        distances = np.linalg.norm(
            matcher._weighted_features - matcher._weighted_features[target_index],
            axis=1,
        )
        distances[target_index] = np.inf
        nearest_indices = np.argpartition(distances, settings.TOP_K_MATCHES)[: settings.TOP_K_MATCHES]
        matched_ids = customer_ids[nearest_indices]
        matched_outcomes = outcome_lookup.loc[matched_ids]
        outcome_counts = matched_outcomes.value_counts().to_dict()
        risk_count = int(outcome_counts.get("stress", 0) + outcome_counts.get("delinquent", 0))
        avoidance_count = int(outcome_counts.get("healthy", 0) + outcome_counts.get("recovered", 0))
        if risk_count >= int(settings.TOP_K_MATCHES * 0.60) and avoidance_count >= settings.BREAKPOINT_MIN_GROUP_SIZE:
            values = row._asdict()
            risk_ratio = risk_count / settings.TOP_K_MATCHES
            values["high_risk_prefilter_score"] = (
                -abs(risk_ratio - 0.80)
                + float(values["balance_decline_run_6m"]) * 0.01
            )
            rows.append(values)
    if not rows:
        return prefiltered
    return pd.DataFrame(rows).sort_values(
        ["high_risk_prefilter_score", "customer_id"],
        ascending=[False, True],
    )


def evaluate_customer(
    customer_id: str,
    demo_role: str,
    metric_row: Any,
    monthly_df: pd.DataFrame,
    matcher: TrajectoryMatcher,
    outcome_lookup: pd.Series,
) -> dict[str, Any]:
    """Calculate all selector outputs for one customer."""

    matches = matcher.match(customer_id, top_k=settings.TOP_K_MATCHES)
    matched_ids = matches["matched_customer_id"].astype(str).tolist()
    outcome_summary = summarize_matched_outcomes(customer_id, matched_ids, monthly_df, outcome_lookup)
    breakpoint_result = find_breakpoint(matched_ids, monthly_df)
    whatif_results = build_whatif_results(customer_id, monthly_df)
    best_scenario = best_whatif_scenario(whatif_results)

    demo_row = {
        "demo_role": demo_role,
        "customer_id": customer_id,
        "demo_score": 0.0,
        "current_status": str(metric_row.current_status),
        "recent_savings_rate": round(float(metric_row.recent_savings_rate), 6),
        "recent_dsr": round(float(metric_row.recent_dsr), 6),
        "recent_fixed_expense_ratio": round(float(metric_row.recent_fixed_expense_ratio), 6),
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
        "best_scenario_id": best_scenario["scenario_id"],
        "best_scenario_improvement": best_scenario["improvement_vs_baseline"],
        "selection_reason": "",
    }
    return {
        "customer_id": customer_id,
        "demo_role": demo_role,
        "metric_row": metric_row._asdict() if hasattr(metric_row, "_asdict") else dict(metric_row),
        "matches": matches,
        "outcome_summary": outcome_summary,
        "breakpoint_result": breakpoint_result,
        "whatif_results": whatif_results,
        "demo_row": demo_row,
        "demo_score": 0.0,
        "selection_reason": "",
    }


def summarize_matched_outcomes(
    target_customer_id: str,
    matched_ids: list[str],
    monthly_df: pd.DataFrame,
    outcome_lookup: pd.Series,
) -> dict[str, Any]:
    """Summarize final outcomes and first future status months for matched customers."""

    matched_outcomes = outcome_lookup.loc[matched_ids]
    counts = matched_outcomes.value_counts().to_dict()
    matched_count = len(matched_ids)
    outcomes = {
        outcome: {
            "count": int(counts.get(outcome, 0)),
            "ratio": round(float(counts.get(outcome, 0) / matched_count), 6),
        }
        for outcome in OUTCOME_ORDER
    }
    future_df = monthly_df[
        monthly_df["customer_id"].isin(matched_ids)
        & monthly_df["month"].between(settings.FUTURE_START_MONTH, settings.FUTURE_END_MONTH)
    ]
    return {
        "target_customer_id": target_customer_id,
        "matched_count": matched_count,
        "outcomes": outcomes,
        "first_stress_month_median": _first_status_month_median(future_df, "stress"),
        "first_delinquency_month_median": _first_status_month_median(future_df, "delinquent"),
    }


def score_main_candidate(candidate: dict[str, Any]) -> float:
    """Score a main demo candidate using configured weighted components."""

    weights = settings.DEMO_MAIN_SCORE_WEIGHTS
    row = candidate["demo_row"]
    bp = candidate["breakpoint_result"]
    risk_ratio = row["risk_group_ratio"]
    outcomes = candidate["outcome_summary"]["outcomes"]
    max_outcome_ratio = max(outcome["ratio"] for outcome in outcomes.values())
    score = 0.0
    score += weights["breakpoint_found"] if bp["status"] == "found" else 0.0
    score += weights["breakpoint_month_13_16"] if bp["breakpoint_month"] and 13 <= bp["breakpoint_month"] <= 16 else 0.0
    score += weights["risk_ratio_target"] * max(0.0, 1.0 - abs(risk_ratio - 0.325) / 0.325)
    score += weights["current_status_watch"] if row["current_status"] == "watch" else 0.0
    score += weights["savings_rate_decline"] if candidate["metric_row"]["savings_rate_slope_6m"] < 0 else 0.0
    score += weights["dsr_risk_approach"] * _range_closeness(row["recent_dsr"], 0.30, 0.44)
    score += weights["fixed_expense_risk_approach"] * _range_closeness(
        row["recent_fixed_expense_ratio"], 0.38, 0.49
    )
    score += weights["whatif_improvement"] * min(
        1.0, max(0.0, row["best_scenario_improvement"]) / 10_000_000
    )
    score += weights["outcome_balance"] * max(0.0, 1.0 - max_outcome_ratio)
    return round(float(score), 6)


def score_stable_candidate(candidate: dict[str, Any]) -> float:
    """Score a stable comparison candidate."""

    row = candidate["demo_row"]
    healthy_recovered = row["healthy_ratio"] + row["recovered_ratio"]
    return round(float(healthy_recovered * 70 + row["recent_savings_rate"] * 30 - row["delinquent_ratio"] * 50), 6)


def score_high_risk_candidate(candidate: dict[str, Any]) -> float:
    """Score a high-risk comparison candidate."""

    row = candidate["demo_row"]
    baseline = _baseline_scenario(candidate["whatif_results"])
    cash_penalty = abs(min(0.0, baseline["minimum_cash_balance"])) / 1_000_000
    return round(float(row["risk_group_ratio"] * 70 + cash_penalty + candidate["metric_row"]["balance_decline_run_6m"] * 3), 6)


def best_whatif_scenario(whatif_results: dict[str, Any]) -> dict[str, Any]:
    """Return the non-baseline scenario with the largest baseline-relative improvement."""

    options = [
        scenario
        for scenario in whatif_results["scenarios"]
        if scenario["scenario_name"] != "baseline"
    ]
    return max(options, key=lambda scenario: (scenario["improvement_vs_baseline"], -scenario["scenario_id"]))


def save_demo_outputs(
    demo_df: pd.DataFrame,
    main_demo_customer: dict[str, Any],
    demo_customers_path: Path = settings.DEMO_CUSTOMERS_PATH,
    main_demo_customer_path: Path = settings.MAIN_DEMO_CUSTOMER_PATH,
) -> tuple[Path, Path]:
    """Save selected demo customers to CSV and JSON."""

    demo_customers_path.parent.mkdir(parents=True, exist_ok=True)
    main_demo_customer_path.parent.mkdir(parents=True, exist_ok=True)
    demo_df.to_csv(demo_customers_path, index=False, encoding="utf-8")
    main_demo_customer_path.write_text(
        json.dumps(main_demo_customer, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return demo_customers_path, main_demo_customer_path


def build_main_demo_customer(candidate: dict[str, Any], generated_at: str) -> dict[str, Any]:
    """Build the fixed main customer JSON payload."""

    row = candidate["demo_row"]
    return {
        "customer_id": candidate["customer_id"],
        "current_metrics": {
            "current_status": row["current_status"],
            "recent_savings_rate": row["recent_savings_rate"],
            "recent_dsr": row["recent_dsr"],
            "recent_fixed_expense_ratio": row["recent_fixed_expense_ratio"],
            "savings_rate_slope_6m": round(float(candidate["metric_row"]["savings_rate_slope_6m"]), 6),
            "balance_decline_run_6m": int(candidate["metric_row"]["balance_decline_run_6m"]),
        },
        "match_summary": {
            "matched_count": row["matched_count"],
            "top_10": candidate["matches"].head(10).to_dict(orient="records"),
        },
        "outcome_summary": candidate["outcome_summary"],
        "breakpoint_result": candidate["breakpoint_result"],
        "whatif_results": candidate["whatif_results"],
        "selection_reason": candidate["selection_reason"],
        "generated_at": generated_at,
        "random_seed": settings.RANDOM_SEED,
    }


def _main_prefilter(current_metrics: pd.DataFrame, level: RelaxationLevel) -> pd.DataFrame:
    return current_metrics[
        (current_metrics["current_status"].isin(["healthy", "watch"]))
        & (current_metrics["delinquency_flag"] == 0)
        & (current_metrics["savings_rate_slope_6m"] < 0)
        & (current_metrics["recent_dsr"].between(*level.dsr_range))
        & (current_metrics["recent_fixed_expense_ratio"].between(*level.fixed_expense_ratio_range))
    ]


def _passes_main_rules(candidate: dict[str, Any], level: RelaxationLevel) -> bool:
    row = candidate["demo_row"]
    bp = candidate["breakpoint_result"]
    return (
        level.risk_ratio_range[0] <= row["risk_group_ratio"] <= level.risk_ratio_range[1]
        and bp["status"] == "found"
        and bp["breakpoint_month"] is not None
        and level.breakpoint_month_range[0] <= bp["breakpoint_month"] <= level.breakpoint_month_range[1]
        and bp["months_from_current"] is not None
        and 1 <= bp["months_from_current"] <= 4
        and bp["primary_factor"] is not None
        and row["best_scenario_improvement"] > 0
    )


def _main_reason(candidate: dict[str, Any], level: RelaxationLevel) -> str:
    row = candidate["demo_row"]
    return (
        f"{level.reason}; status={row['current_status']}; savings_rate_declining; "
        f"risk_group_ratio={row['risk_group_ratio']:.3f}; "
        f"breakpoint={row['breakpoint_status']} month={row['breakpoint_month']}; "
        f"primary_factor={row['primary_factor']}; "
        f"best_scenario_id={row['best_scenario_id']} improvement={row['best_scenario_improvement']:.2f}"
    )


def _finalize_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    candidate["demo_row"]["demo_score"] = candidate["demo_score"]
    candidate["demo_row"]["selection_reason"] = candidate["selection_reason"]
    return candidate


def _prioritized_rows(df: pd.DataFrame, role: str) -> list[Any]:
    if df.empty:
        return []
    ordered = df.copy()
    if role == "main":
        ordered["priority"] = (
            -ordered["recent_dsr"].sub(0.34).abs()
            - ordered["recent_fixed_expense_ratio"].sub(0.40).abs()
            - ordered["savings_rate_slope_6m"]
        )
    elif role == "stable_comparison":
        ordered["priority"] = ordered["recent_savings_rate"]
    else:
        if "high_risk_prefilter_score" in ordered.columns:
            ordered["priority"] = ordered["high_risk_prefilter_score"]
        else:
            ordered["priority"] = (
                ordered["balance_decline_run_6m"] * 10
                - ordered["recent_savings_rate"]
            )
    ordered = ordered.sort_values(["priority", "customer_id"], ascending=[False, True])
    return list(ordered.itertuples(index=False))


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[float, str]:
    return float(candidate["demo_score"]), str(candidate["customer_id"])


def _range_closeness(value: float, lower: float, upper: float) -> float:
    midpoint = (lower + upper) / 2
    half_width = (upper - lower) / 2
    if half_width <= 0:
        return 0.0
    return max(0.0, 1.0 - abs(value - midpoint) / half_width)


def _tail_decline_run(values: pd.Series) -> int:
    ordered = values.to_list()
    run = 0
    for index in range(len(ordered) - 1, 0, -1):
        if ordered[index] < ordered[index - 1]:
            run += 1
        else:
            break
    return run


def _first_status_month_median(future_df: pd.DataFrame, status: str) -> int | None:
    first_months = (
        future_df.loc[future_df["monthly_status"] == status]
        .groupby("customer_id")["month"]
        .min()
    )
    if first_months.empty:
        return None
    return int(round(float(first_months.median())))


def _baseline_scenario(whatif_results: dict[str, Any]) -> dict[str, Any]:
    return next(
        scenario
        for scenario in whatif_results["scenarios"]
        if scenario["scenario_name"] == "baseline"
    )
