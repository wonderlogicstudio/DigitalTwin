"""Read-only monthly analysis Snapshot builder for the RM Portfolio."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from config import settings
from src.customer_analysis import run_customer_analysis
from src.demo_selector import build_current_metrics
from src.matcher import TrajectoryMatcher
from src.rm_portfolio import METADATA_SOURCE, RmPortfolio, RmPortfolioCustomer


SNAPSHOT_SCHEMA_VERSION = 2
EVIDENCE_AVAILABLE = "available"
EVIDENCE_AVAILABLE_WITH_OPTIONAL_ERRORS = "available_with_optional_errors"
EVIDENCE_ANALYSIS_ERROR = "analysis_error"
EVIDENCE_CURRENT_SUMMARY_UNAVAILABLE = "current_summary_unavailable"

CURRENT_SUMMARY_FIELDS = (
    "current_status",
    "delinquency_flag",
    "recent_savings_rate",
    "recent_dsr",
    "recent_fixed_expense_ratio",
    "savings_rate_slope_6m",
    "balance_decline_run_6m",
)
BREAKPOINT_FIELDS = (
    "status",
    "breakpoint_month",
    "months_from_current",
    "primary_factor",
)
OUTCOME_SUMMARY_FIELDS = (
    "matched_count",
    "outcomes",
    "first_stress_month_median",
    "first_delinquency_month_median",
)


@dataclass(frozen=True)
class MonthlyReviewSnapshotRecord:
    """One read-only monthly analysis record joined with operational metadata."""

    customer_id: str
    snapshot_id: str
    analysis_as_of_month: int
    current_summary: dict[str, object]
    matched_count: int
    breakpoint: dict[str, object]
    evidence: dict[str, object]
    relationship_metadata: dict[str, str]
    outcome_summary: dict[str, object] | None
    matched_customer_ids: tuple[str, ...] = ()
    supporting_evidence: dict[str, object] | None = None

    def as_dict(self) -> dict[str, object]:
        """Return the JSON-safe Snapshot record."""

        return {
            "customer_id": self.customer_id,
            "snapshot_id": self.snapshot_id,
            "analysis_as_of_month": self.analysis_as_of_month,
            "current_summary": self.current_summary,
            "matched_count": self.matched_count,
            "breakpoint": self.breakpoint,
            "evidence": self.evidence,
            "relationship_metadata": self.relationship_metadata,
            "outcome_summary": self.outcome_summary,
            "matched_customer_ids": list(self.matched_customer_ids),
            "supporting_evidence": self.supporting_evidence,
        }


@dataclass(frozen=True)
class MonthlyReviewSnapshot:
    """An immutable Portfolio-scoped monthly analysis Snapshot."""

    snapshot_id: str
    analysis_as_of_month: int
    rm_portfolio_id: str
    universe_customer_count: int
    records: tuple[MonthlyReviewSnapshotRecord, ...]

    def as_artifact(self) -> dict[str, object]:
        """Return a standalone artifact without Financial Path Twin raw data."""

        return {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "snapshot_id": self.snapshot_id,
            "analysis_as_of_month": self.analysis_as_of_month,
            "rm_portfolio_id": self.rm_portfolio_id,
            "universe_customer_count": self.universe_customer_count,
            "portfolio_size": len(self.records),
            "records": [record.as_dict() for record in self.records],
        }


def build_monthly_review_snapshot(
    portfolio: RmPortfolio,
    monthly_df: pd.DataFrame,
    features_df: pd.DataFrame,
    matcher: TrajectoryMatcher,
    *,
    snapshot_id: str,
    analysis_as_of_month: int = settings.OBSERVATION_END_MONTH,
    top_k: int = settings.TOP_K_MATCHES,
    analysis_runner: Callable[..., dict[str, Any]] = run_customer_analysis,
) -> MonthlyReviewSnapshot:
    """Build Portfolio records by reusing the existing customer analysis service.

    The supplied matcher remains responsible for the caller's full reference
    universe. Portfolio metadata is joined only after customer analysis returns.
    """

    _validate_snapshot_inputs(snapshot_id, analysis_as_of_month)
    _validate_reference_universe(portfolio, features_df, matcher)
    current_metrics = build_current_metrics(monthly_df)
    current_metrics_by_customer = {
        str(row["customer_id"]): row
        for _, row in current_metrics.set_index("customer_id", drop=False).iterrows()
    }

    records = tuple(
        _build_record(
            portfolio_customer,
            snapshot_id=snapshot_id,
            analysis_as_of_month=analysis_as_of_month,
            current_metrics_row=current_metrics_by_customer.get(portfolio_customer.customer_id),
            monthly_df=monthly_df,
            features_df=features_df,
            matcher=matcher,
            top_k=top_k,
            analysis_runner=analysis_runner,
        )
        for portfolio_customer in sorted(portfolio.customers, key=lambda customer: customer.customer_id)
    )
    return MonthlyReviewSnapshot(
        snapshot_id=snapshot_id,
        analysis_as_of_month=analysis_as_of_month,
        rm_portfolio_id=portfolio.rm_portfolio_id,
        universe_customer_count=portfolio.universe_customer_count,
        records=records,
    )


def write_monthly_review_snapshot(
    snapshot: MonthlyReviewSnapshot,
    output_path: Path | str,
) -> Path:
    """Write a separate Snapshot artifact and reject all core data directories."""

    path = Path(output_path)
    _ensure_separate_artifact_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(snapshot.as_artifact(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def _build_record(
    portfolio_customer: RmPortfolioCustomer,
    *,
    snapshot_id: str,
    analysis_as_of_month: int,
    current_metrics_row: pd.Series | None,
    monthly_df: pd.DataFrame,
    features_df: pd.DataFrame,
    matcher: TrajectoryMatcher,
    top_k: int,
    analysis_runner: Callable[..., dict[str, Any]],
) -> MonthlyReviewSnapshotRecord:
    current_summary = _current_summary(current_metrics_row)
    relationship_metadata = {
        "source": METADATA_SOURCE,
        "rm_portfolio_id": portfolio_customer.rm_portfolio_id,
        "relationship_priority": portfolio_customer.relationship_priority,
        "relationship_label": portfolio_customer.relationship_label,
    }
    if current_metrics_row is None:
        return _error_record(
            portfolio_customer.customer_id,
            snapshot_id=snapshot_id,
            analysis_as_of_month=analysis_as_of_month,
            current_summary=current_summary,
            relationship_metadata=relationship_metadata,
            evidence_status=EVIDENCE_CURRENT_SUMMARY_UNAVAILABLE,
            error_message="Current summary was unavailable for this Portfolio customer.",
        )

    try:
        analysis = analysis_runner(
            portfolio_customer.customer_id,
            monthly_df,
            features_df,
            matcher,
            top_k=top_k,
        )
    except Exception as exc:  # noqa: BLE001
        return _error_record(
            portfolio_customer.customer_id,
            snapshot_id=snapshot_id,
            analysis_as_of_month=analysis_as_of_month,
            current_summary=current_summary,
            relationship_metadata=relationship_metadata,
            evidence_status=EVIDENCE_ANALYSIS_ERROR,
            error_message=str(exc),
        )

    return _record_from_analysis(
        portfolio_customer.customer_id,
        snapshot_id=snapshot_id,
        analysis_as_of_month=analysis_as_of_month,
        current_summary=current_summary,
        relationship_metadata=relationship_metadata,
        analysis=analysis,
    )


def _record_from_analysis(
    customer_id: str,
    *,
    snapshot_id: str,
    analysis_as_of_month: int,
    current_summary: dict[str, object],
    relationship_metadata: dict[str, str],
    analysis: dict[str, Any],
) -> MonthlyReviewSnapshotRecord:
    errors = {
        str(key): str(value)
        for key, value in dict(analysis.get("errors", {})).items()
    }
    breakpoint = _minimal_breakpoint(analysis.get("breakpoint_result", {}))
    outcome_source = analysis.get("outcome_summary")
    outcome_summary = _minimal_outcome_summary(outcome_source)
    matched_count = int(
        outcome_source.get("matched_count", 0)
        if isinstance(outcome_source, dict)
        else 0
    )
    matched_customer_ids = _matched_customer_ids(analysis.get("matched_ids"))
    evidence = _evidence(current_summary, breakpoint, errors)
    supporting_evidence = _supporting_evidence(
        snapshot_id=snapshot_id,
        analysis_as_of_month=analysis_as_of_month,
        evidence=evidence,
        current_summary=current_summary,
        breakpoint=breakpoint,
        outcome_summary=outcome_summary,
        analysis=analysis,
    )
    return MonthlyReviewSnapshotRecord(
        customer_id=customer_id,
        snapshot_id=snapshot_id,
        analysis_as_of_month=analysis_as_of_month,
        current_summary=current_summary,
        matched_count=matched_count,
        breakpoint=breakpoint,
        evidence=evidence,
        relationship_metadata=relationship_metadata,
        outcome_summary=outcome_summary,
        matched_customer_ids=matched_customer_ids,
        supporting_evidence=supporting_evidence,
    )


def _current_summary(current_metrics_row: pd.Series | None) -> dict[str, object]:
    if current_metrics_row is None:
        return {}
    return {
        field: _json_value(current_metrics_row.get(field))
        for field in CURRENT_SUMMARY_FIELDS
    }


def _minimal_breakpoint(source: object) -> dict[str, object]:
    result = source if isinstance(source, dict) else {}
    return {
        field: _json_value(result.get(field))
        for field in BREAKPOINT_FIELDS
    }


def _minimal_outcome_summary(source: object) -> dict[str, object] | None:
    if not isinstance(source, dict):
        return None
    return {
        field: _json_value(source.get(field))
        for field in OUTCOME_SUMMARY_FIELDS
    }


def _matched_customer_ids(source: object) -> tuple[str, ...]:
    if not isinstance(source, (list, tuple)):
        return ()
    return tuple(str(customer_id) for customer_id in source)


def _supporting_evidence(
    *,
    snapshot_id: str,
    analysis_as_of_month: int,
    evidence: dict[str, object],
    current_summary: dict[str, object],
    breakpoint: dict[str, object],
    outcome_summary: dict[str, object] | None,
    analysis: dict[str, Any],
) -> dict[str, object]:
    """Create display evidence only from an already-completed analysis result."""

    evidence_available = evidence.get("available") is True
    evidence_status = str(evidence.get("status") or "unavailable")
    errors = {
        str(key): str(value)
        for key, value in dict(evidence.get("errors", {})).items()
    }
    provenance = {
        "snapshot_id": snapshot_id,
        "analysis_as_of_month": analysis_as_of_month,
        "generated_from": "existing_customer_analysis",
        "source_service": "src.customer_analysis.run_customer_analysis",
    }
    if not evidence_available:
        return {
            "evidence_status": evidence_status,
            "available": False,
            "errors": errors,
            "provenance": provenance,
            "why_now": dict(breakpoint),
            "current_change_cards": [],
            "cohort_path_chart": _unavailable_component(
                "analysis_evidence_unavailable",
                "Customer analysis evidence was unavailable for this Snapshot record.",
            ),
            "outcome_summary": outcome_summary,
            "whatif_summary": _unavailable_component(
                "analysis_evidence_unavailable",
                "What-if summary was unavailable because customer analysis evidence failed.",
            ),
        }
    return {
        "evidence_status": evidence_status,
        "available": True,
        "errors": errors,
        "provenance": provenance,
        "why_now": dict(breakpoint),
        "current_change_cards": _current_change_cards(current_summary),
        "cohort_path_chart": _cohort_path_chart(
            analysis.get("breakpoint_comparison"), breakpoint, errors
        ),
        "outcome_summary": outcome_summary,
        "whatif_summary": _whatif_summary(analysis.get("whatif_results"), errors),
    }


def _current_change_cards(current_summary: dict[str, object]) -> list[dict[str, object]]:
    card_specs = (
        ("cash_availability", "현금 여력", "balance_decline_run_6m", "consecutive_months"),
        ("debt_service_burden", "대출 상환 부담", "recent_dsr", "ratio"),
        ("fixed_expense", "고정지출", "recent_fixed_expense_ratio", "ratio"),
        ("savings_capacity", "저축 여력", "recent_savings_rate", "ratio"),
    )
    cards: list[dict[str, object]] = []
    for key, label, source_field, value_type in card_specs:
        value = current_summary.get(source_field)
        if value is not None:
            cards.append(
                {
                    "key": key,
                    "label": label,
                    "source_field": source_field,
                    "value": _json_value(value),
                    "value_type": value_type,
                }
            )
    return cards


def _cohort_path_chart(
    comparison_source: object,
    breakpoint: dict[str, object],
    errors: dict[str, str],
) -> dict[str, object]:
    status = str(breakpoint.get("status") or "")
    if status != "found":
        return _unavailable_component(
            f"breakpoint_{status or 'unavailable'}",
            "Historical cohort comparison is unavailable because a breakpoint was not found.",
        )
    if "breakpoint_comparison" in errors:
        return _unavailable_component("breakpoint_comparison_error", errors["breakpoint_comparison"])
    if not isinstance(comparison_source, pd.DataFrame) or comparison_source.empty:
        return _unavailable_component(
            "breakpoint_comparison_unavailable",
            "No saved historical cohort comparison was available from customer analysis.",
        )
    metric = breakpoint.get("primary_factor")
    required_columns = {
        "month", "metric", "risk_group_mean", "avoidance_group_mean", "risk_count", "avoidance_count"
    }
    if not isinstance(metric, str) or not metric:
        return _unavailable_component("primary_factor_unavailable", "A primary breakpoint factor was unavailable.")
    if not required_columns.issubset(comparison_source.columns):
        return _unavailable_component(
            "breakpoint_comparison_schema_unavailable",
            "The saved comparison did not contain the required historical cohort fields.",
        )
    metric_rows = comparison_source.loc[
        comparison_source["metric"].astype(str) == metric
    ].sort_values("month")
    if metric_rows.empty:
        return _unavailable_component(
            "primary_factor_comparison_unavailable",
            "The saved comparison did not contain the primary breakpoint factor.",
        )
    risk_path = [
        {
            "month": _json_value(row["month"]),
            "mean": _json_value(row["risk_group_mean"]),
            "group_size": _json_value(row["risk_count"]),
        }
        for _, row in metric_rows.iterrows()
    ]
    avoidance_path = [
        {
            "month": _json_value(row["month"]),
            "mean": _json_value(row["avoidance_group_mean"]),
            "group_size": _json_value(row["avoidance_count"]),
        }
        for _, row in metric_rows.iterrows()
    ]
    breakpoint_month = breakpoint.get("breakpoint_month")
    marker_rows = metric_rows.loc[metric_rows["month"] == breakpoint_month]
    marker_row = marker_rows.iloc[0] if not marker_rows.empty else metric_rows.iloc[0]
    return {
        "available": True,
        "comparison_type": "historical_matched_cohort_comparison",
        "label": "유사 고객의 과거 경로 비교",
        "metric": metric,
        "risk_path_label": "위험 경로",
        "avoidance_path_label": "회피 경로",
        "group_sizes": {
            "risk_path": _json_value(marker_row["risk_count"]),
            "avoidance_path": _json_value(marker_row["avoidance_count"]),
        },
        "breakpoint_marker": {"month": _json_value(breakpoint_month)},
        "risk_path": risk_path,
        "avoidance_path": avoidance_path,
    }


def _whatif_summary(source: object, errors: dict[str, str]) -> dict[str, object]:
    if "whatif" in errors:
        return _unavailable_component("whatif_error", errors["whatif"])
    if not isinstance(source, dict):
        return _unavailable_component(
            "whatif_unavailable",
            "No saved What-if summary was available from customer analysis.",
        )
    scenario_fields = (
        "scenario_id", "scenario_name", "ending_cash_balance", "minimum_cash_balance",
        "average_savings_rate", "cash_depletion_month", "improvement_vs_baseline",
        "total_saved_expense", "months_with_negative_savings",
    )
    scenarios = source.get("scenarios")
    if not isinstance(scenarios, list):
        return _unavailable_component(
            "whatif_scenarios_unavailable",
            "The saved What-if result did not contain scenario summaries.",
        )
    return {
        "available": True,
        "simulation_months": _json_value(source.get("simulation_months")),
        "scenarios": [
            {field: _json_value(scenario.get(field)) for field in scenario_fields}
            for scenario in scenarios
            if isinstance(scenario, dict)
        ],
    }


def _unavailable_component(reason_code: str, reason: str) -> dict[str, object]:
    return {
        "available": False,
        "status": "unavailable",
        "reason_code": reason_code,
        "reason": reason,
        "scenarios": [],
        "risk_path": [],
        "avoidance_path": [],
    }


def _evidence(
    current_summary: dict[str, object],
    breakpoint: dict[str, object],
    errors: dict[str, str],
) -> dict[str, object]:
    if breakpoint.get("status") == "error" or "breakpoint" in errors:
        return {
            "available": False,
            "status": EVIDENCE_ANALYSIS_ERROR,
            "errors": errors,
        }
    if not current_summary.get("current_status"):
        return {
            "available": False,
            "status": EVIDENCE_CURRENT_SUMMARY_UNAVAILABLE,
            "errors": errors,
        }
    if errors:
        return {
            "available": True,
            "status": EVIDENCE_AVAILABLE_WITH_OPTIONAL_ERRORS,
            "errors": errors,
        }
    return {
        "available": True,
        "status": EVIDENCE_AVAILABLE,
        "errors": {},
    }


def _error_record(
    customer_id: str,
    *,
    snapshot_id: str,
    analysis_as_of_month: int,
    current_summary: dict[str, object],
    relationship_metadata: dict[str, str],
    evidence_status: str,
    error_message: str,
) -> MonthlyReviewSnapshotRecord:
    breakpoint = {
        "status": "error",
        "breakpoint_month": None,
        "months_from_current": None,
        "primary_factor": None,
    }
    evidence = {
        "available": False,
        "status": evidence_status,
        "errors": {"analysis": error_message},
    }
    return MonthlyReviewSnapshotRecord(
        customer_id=customer_id,
        snapshot_id=snapshot_id,
        analysis_as_of_month=analysis_as_of_month,
        current_summary=current_summary,
        matched_count=0,
        breakpoint=breakpoint,
        evidence=evidence,
        relationship_metadata=relationship_metadata,
        outcome_summary=None,
        matched_customer_ids=(),
        supporting_evidence=_supporting_evidence(
            snapshot_id=snapshot_id,
            analysis_as_of_month=analysis_as_of_month,
            evidence=evidence,
            current_summary=current_summary,
            breakpoint=breakpoint,
            outcome_summary=None,
            analysis={},
        ),
    )


def _validate_snapshot_inputs(snapshot_id: str, analysis_as_of_month: int) -> None:
    if not str(snapshot_id).strip():
        raise ValueError("snapshot_id must not be blank.")
    if analysis_as_of_month != settings.OBSERVATION_END_MONTH:
        raise ValueError(
            "analysis_as_of_month must match the existing observation end month."
        )


def _validate_reference_universe(
    portfolio: RmPortfolio,
    features_df: pd.DataFrame,
    matcher: TrajectoryMatcher,
) -> None:
    """Require Portfolio targets to retain the full declared matching universe."""

    if "customer_id" not in features_df.columns:
        raise ValueError("features_df must include customer_id for the matching universe.")

    feature_customer_ids = features_df["customer_id"].astype(str)
    if feature_customer_ids.duplicated().any():
        raise ValueError("features_df customer_id values must be unique.")
    if len(feature_customer_ids) != portfolio.universe_customer_count:
        raise ValueError(
            "features_df must retain the RM Portfolio's full matching reference universe."
        )
    feature_customer_id_set = set(feature_customer_ids)
    missing_portfolio_ids = sorted(
        customer.customer_id
        for customer in portfolio.customers
        if customer.customer_id not in feature_customer_id_set
    )
    if missing_portfolio_ids:
        raise ValueError(
            "RM Portfolio customers must exist in the matching reference universe: "
            f"{missing_portfolio_ids[:3]}"
        )

    matcher_customer_ids = matcher._customer_ids  # noqa: SLF001 - validates the fitted universe boundary
    if matcher_customer_ids is None:
        raise ValueError("matcher must be fitted to the full matching reference universe.")
    if list(matcher_customer_ids.astype(str)) != list(feature_customer_ids):
        raise ValueError("matcher must be fitted to the supplied full matching reference universe.")


def _ensure_separate_artifact_path(path: Path) -> None:
    resolved_path = path.resolve()
    core_directories = (
        settings.DATA_RAW_DIR,
        settings.DATA_PROCESSED_DIR,
        settings.DATA_DEMO_DIR,
    )
    for directory in core_directories:
        if resolved_path.is_relative_to(directory.resolve()):
            raise ValueError("Monthly Review Snapshot must not overwrite core data artifacts.")


def _json_value(value: object) -> object:
    if value is None:
        return None
    if value is pd.NA:
        return None
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "item"):
        return _json_value(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (str, int, bool)):
        return value
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)
