"""Provider- and UI-independent result contract for one population customer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

import pandas as pd

from config import settings
from src.matcher import TrajectoryMatcher
from src.ui_components import run_customer_analysis


AnalysisStatus = Literal["success", "partial_failure", "failed"]


@dataclass(frozen=True)
class PopulationCustomerResult:
    """Serializable population-analysis result for exactly one customer.

    Historical outcome shares and breakpoint evidence describe only the matched
    synthetic cohort. They are not prediction probabilities or future facts
    about the target customer.
    """

    customer_id: str
    matched_count: int
    distance_summary: Mapping[str, float | None]
    historical_outcome_shares: Mapping[str, float]
    breakpoint_status: str
    breakpoint_month: int | None
    breakpoint_factor: str | None
    breakpoint_support: Mapping[str, int]
    analysis_status: AnalysisStatus
    error_category: str | None
    error_message: str | None

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable primitive values with stable field names."""

        return {
            "customer_id": self.customer_id,
            "matched_count": self.matched_count,
            "distance_summary": dict(self.distance_summary),
            "historical_outcome_shares": dict(self.historical_outcome_shares),
            "breakpoint_status": self.breakpoint_status,
            "breakpoint_month": self.breakpoint_month,
            "breakpoint_factor": self.breakpoint_factor,
            "breakpoint_support": dict(self.breakpoint_support),
            "analysis_status": self.analysis_status,
            "error_category": self.error_category,
            "error_message": self.error_message,
        }


def build_population_customer_result(
    customer_id: str,
    monthly_df: pd.DataFrame,
    features_df: pd.DataFrame,
    matcher: TrajectoryMatcher,
    *,
    top_k: int = settings.TOP_K_MATCHES,
) -> PopulationCustomerResult:
    """Adapt legacy single-customer analysis into the population result contract.

    A customer-level exception is returned as a failed result so a future batch
    engine can retain an explicit disposition instead of silently omitting it.
    """

    target_id = str(customer_id)
    try:
        analysis = run_customer_analysis(target_id, monthly_df, features_df, matcher, top_k=top_k)
        return population_result_from_analysis(target_id, analysis)
    except Exception as exc:  # noqa: BLE001
        return failed_population_customer_result(target_id, _error_category(exc), str(exc))


def population_result_from_analysis(
    customer_id: str,
    analysis: Mapping[str, Any],
) -> PopulationCustomerResult:
    """Build a result from an existing legacy analysis payload."""

    try:
        matches = analysis["matches"]
        if not isinstance(matches, pd.DataFrame):
            raise TypeError("analysis matches must be a pandas DataFrame")
        if "distance" not in matches.columns:
            raise ValueError("analysis matches are missing distance")

        outcome_summary = analysis["outcome_summary"]
        outcomes = outcome_summary["outcomes"]
        breakpoint = analysis["breakpoint_result"]

        outcome_counts = {
            outcome: int(outcomes.get(outcome, {}).get("count", 0))
            for outcome in settings.FINAL_OUTCOMES
        }
        outcome_shares = {
            outcome: float(outcomes.get(outcome, {}).get("ratio", 0.0))
            for outcome in settings.FINAL_OUTCOMES
        }
        distances = pd.to_numeric(matches["distance"], errors="coerce").dropna()
        distance_summary = {
            "min": None if distances.empty else float(distances.min()),
            "mean": None if distances.empty else float(distances.mean()),
            "median": None if distances.empty else float(distances.median()),
            "max": None if distances.empty else float(distances.max()),
        }
        errors = analysis.get("errors", {})
        if not isinstance(errors, Mapping):
            raise TypeError("analysis errors must be a mapping")
        error_items = [(str(key), str(value)) for key, value in sorted(errors.items())]

        breakpoint_month = breakpoint.get("breakpoint_month")
        return PopulationCustomerResult(
            customer_id=str(customer_id),
            matched_count=int(len(matches)),
            distance_summary=distance_summary,
            historical_outcome_shares=outcome_shares,
            breakpoint_status=str(breakpoint.get("status", "not_available")),
            breakpoint_month=None if breakpoint_month is None else int(breakpoint_month),
            breakpoint_factor=(
                None if breakpoint.get("primary_factor") is None else str(breakpoint["primary_factor"])
            ),
            breakpoint_support={
                "risk_group_count": outcome_counts["stress"] + outcome_counts["delinquent"],
                "avoidance_group_count": outcome_counts["healthy"] + outcome_counts["recovered"],
                "persistence_months": int(breakpoint.get("persistence_months", 0)),
            },
            analysis_status="success" if not error_items else "partial_failure",
            error_category=None if not error_items else ",".join(key for key, _ in error_items),
            error_message=None if not error_items else "; ".join(
                f"{key}: {value}" for key, value in error_items
            ),
        )
    except Exception as exc:  # noqa: BLE001
        return failed_population_customer_result(str(customer_id), "analysis_schema", str(exc))


def failed_population_customer_result(
    customer_id: str,
    error_category: str,
    error_message: str,
) -> PopulationCustomerResult:
    """Return an explicit failed result for one customer without masking it."""

    return PopulationCustomerResult(
        customer_id=customer_id,
        matched_count=0,
        distance_summary={"min": None, "mean": None, "median": None, "max": None},
        historical_outcome_shares={outcome: 0.0 for outcome in settings.FINAL_OUTCOMES},
        breakpoint_status="not_available",
        breakpoint_month=None,
        breakpoint_factor=None,
        breakpoint_support={
            "risk_group_count": 0,
            "avoidance_group_count": 0,
            "persistence_months": 0,
        },
        analysis_status="failed",
        error_category=error_category,
        error_message=error_message,
    )


def _error_category(exc: Exception) -> str:
    if isinstance(exc, ValueError):
        return "input_validation"
    if isinstance(exc, RuntimeError):
        return "analysis_runtime"
    return "analysis_exception"
