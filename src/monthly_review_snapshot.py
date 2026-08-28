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


SNAPSHOT_SCHEMA_VERSION = 1
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
    evidence = _evidence(current_summary, breakpoint, errors)
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
    return MonthlyReviewSnapshotRecord(
        customer_id=customer_id,
        snapshot_id=snapshot_id,
        analysis_as_of_month=analysis_as_of_month,
        current_summary=current_summary,
        matched_count=0,
        breakpoint={
            "status": "error",
            "breakpoint_month": None,
            "months_from_current": None,
            "primary_factor": None,
        },
        evidence={
            "available": False,
            "status": evidence_status,
            "errors": {"analysis": error_message},
        },
        relationship_metadata=relationship_metadata,
        outcome_summary=None,
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
