"""Predeclared aggregate metrics for synthetic-versus-approved-real validation.

This module receives aggregate measurement inputs only. It has no dataset
reader, source connector, scorer, policy, triage, Alert, or UI dependency.
It exists to fix comparison definitions before any approved real-data result is
available and must not be interpreted as an actual-data performance report.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from config import settings


VALIDATION_METRICS_REPORT_SCHEMA_VERSION = "synthetic_real_validation_metrics.v1"
VALIDATION_METRICS_TEMPLATE_FILENAME = "synthetic_vs_real_validation_report_template.json"

TRIAGE_DISPOSITION_KEYS = (
    "selected",
    "deferred",
    "monitor",
    "no_actionable_signal",
    "insufficient_evidence",
)
METRIC_SPECIFICATIONS = (
    {
        "metric_id": "data_coverage_missingness",
        "definition": "admitted customer-months / expected customer-months and missing customer-months / expected customer-months",
        "unit": "share",
    },
    {
        "metric_id": "feature_trajectory_distribution_shift",
        "definition": "predeclared per-feature distribution summaries and synthetic-minus-real mean/median deltas when both aggregates exist",
        "unit": "native feature units",
    },
    {
        "metric_id": "match_distance_neighbor_support_distribution",
        "definition": "distribution summaries for reference-match distance and returned neighbor support count",
        "unit": "distance / count",
    },
    {
        "metric_id": "historical_cohort_outcome_share",
        "definition": "descriptive distribution of matched historical-cohort outcome shares; never a target prediction probability",
        "unit": "share",
    },
    {
        "metric_id": "prospective_alert_rate_per_1000_customer_months",
        "definition": "review episodes / declared analysis customer-month denominator * 1000",
        "unit": "episodes per 1,000 customer-months",
    },
    {
        "metric_id": "unique_alerted_selected_rate",
        "definition": "unique alerted customers / declared customers, with selected triage share reported separately",
        "unit": "share",
    },
    {
        "metric_id": "no_event_alert_rate",
        "definition": "no-event review episodes / review episodes when an independently defined outcome/event is available",
        "unit": "share",
    },
    {
        "metric_id": "lead_time_distribution",
        "definition": "median, Q1 and Q3 months from alert to independently defined future event; unavailable if no compatible event definition exists",
        "unit": "months",
    },
    {
        "metric_id": "persistence_flip_rate",
        "definition": "predeclared alert persistence and state-change rates over the declared contiguous analysis months",
        "unit": "share",
    },
    {
        "metric_id": "triage_capacity_distribution",
        "definition": "selected, deferred, monitor, no-actionable-signal and insufficient-evidence shares under one declared capacity scenario",
        "unit": "share",
    },
    {
        "metric_id": "insufficient_evidence_rate",
        "definition": "insufficient-evidence customers / declared customers",
        "unit": "share",
    },
)


class ValidationMetricsContractError(ValueError):
    """Aggregate metrics or report-output request violates the fixed contract."""


@dataclass(frozen=True)
class OutcomeDefinition:
    """Evaluator-only definition metadata; no target label values are accepted."""

    definition_id: str
    comparison_basis_id: str | None
    independently_agreed: bool
    availability: Literal["available", "unavailable"]
    description: str

    def __post_init__(self) -> None:
        if not str(self.definition_id).strip() or not str(self.description).strip():
            raise ValidationMetricsContractError("outcome definition ID and description must be non-empty")
        if self.availability not in {"available", "unavailable"}:
            raise ValidationMetricsContractError("outcome availability must be available or unavailable")
        if self.comparison_basis_id is not None and not str(self.comparison_basis_id).strip():
            raise ValidationMetricsContractError("comparison_basis_id must be non-empty when provided")

    def to_dict(self) -> dict[str, object]:
        return {
            "definition_id": self.definition_id,
            "comparison_basis_id": self.comparison_basis_id,
            "independently_agreed": self.independently_agreed,
            "availability": self.availability,
            "description": self.description,
            "evaluator_only": True,
        }


@dataclass(frozen=True)
class CapacityScenarioDeclaration:
    """A declared comparison input, never a system-selected workload standard."""

    scenario_id: str
    max_reviews_per_cycle: int | None
    status: Literal["draft", "demo", "approved"] = "demo"

    def __post_init__(self) -> None:
        if not str(self.scenario_id).strip():
            raise ValidationMetricsContractError("capacity scenario ID must be non-empty")
        if self.max_reviews_per_cycle is not None and (
            isinstance(self.max_reviews_per_cycle, bool)
            or not isinstance(self.max_reviews_per_cycle, int)
            or self.max_reviews_per_cycle < 0
        ):
            raise ValidationMetricsContractError(
                "max_reviews_per_cycle must be a non-negative integer or None"
            )
        if self.status not in {"draft", "demo", "approved"}:
            raise ValidationMetricsContractError("capacity scenario status is invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "max_reviews_per_cycle": self.max_reviews_per_cycle,
            "status": self.status,
            "automatically_selected": False,
        }


@dataclass(frozen=True)
class AggregateValidationMetricInput:
    """Precomputed aggregate inputs for one dataset section of the report."""

    source: Literal["synthetic", "approved_real"]
    customer_count: int
    expected_customer_month_count: int
    admitted_customer_month_count: int
    missing_customer_month_count: int
    analysis_customer_month_denominator: int
    feature_values: Mapping[str, Sequence[float]]
    match_distances: Sequence[float]
    neighbor_support_counts: Sequence[int]
    historical_cohort_outcome_shares: Sequence[float]
    review_episode_count: int
    unique_alerted_customer_count: int
    no_event_review_episode_count: int
    lead_time_months: Sequence[int]
    persistence_rate: float | None
    flip_rate: float | None
    triage_counts: Mapping[str, int]
    insufficient_evidence_count: int
    capacity_scenario: CapacityScenarioDeclaration
    outcome_definition: OutcomeDefinition

    def __post_init__(self) -> None:
        if self.source not in {"synthetic", "approved_real"}:
            raise ValidationMetricsContractError("source must be synthetic or approved_real")
        if self.source == "approved_real" and (
            self.outcome_definition.availability == "available"
            and not self.outcome_definition.independently_agreed
        ):
            raise ValidationMetricsContractError(
                "an available approved-real outcome definition must be independently agreed"
            )
        _validate_non_negative_int(self.customer_count, "customer_count", allow_zero=False)
        _validate_non_negative_int(
            self.expected_customer_month_count,
            "expected_customer_month_count",
            allow_zero=False,
        )
        _validate_non_negative_int(self.admitted_customer_month_count, "admitted_customer_month_count")
        _validate_non_negative_int(self.missing_customer_month_count, "missing_customer_month_count")
        if self.expected_customer_month_count != (
            self.admitted_customer_month_count + self.missing_customer_month_count
        ):
            raise ValidationMetricsContractError(
                "expected customer-month count must reconcile admitted plus missing counts"
            )
        _validate_non_negative_int(
            self.analysis_customer_month_denominator,
            "analysis_customer_month_denominator",
            allow_zero=False,
        )
        if self.analysis_customer_month_denominator > self.admitted_customer_month_count:
            raise ValidationMetricsContractError(
                "analysis customer-month denominator cannot exceed admitted customer-months"
            )
        if not self.feature_values:
            raise ValidationMetricsContractError("at least one predeclared feature distribution is required")
        for feature_name, values in self.feature_values.items():
            if not str(feature_name).strip():
                raise ValidationMetricsContractError("feature distribution names must be non-empty")
            _validate_numeric_sequence(values, f"feature_values[{feature_name!r}]")
        _validate_numeric_sequence(self.match_distances, "match_distances", minimum=0.0)
        _validate_int_sequence(self.neighbor_support_counts, "neighbor_support_counts", minimum=0)
        _validate_numeric_sequence(
            self.historical_cohort_outcome_shares,
            "historical_cohort_outcome_shares",
            minimum=0.0,
            maximum=1.0,
        )
        _validate_non_negative_int(self.review_episode_count, "review_episode_count")
        _validate_non_negative_int(self.unique_alerted_customer_count, "unique_alerted_customer_count")
        _validate_non_negative_int(
            self.no_event_review_episode_count,
            "no_event_review_episode_count",
        )
        if self.unique_alerted_customer_count > self.customer_count:
            raise ValidationMetricsContractError("unique alerted customers cannot exceed customer_count")
        if self.no_event_review_episode_count > self.review_episode_count:
            raise ValidationMetricsContractError("no-event review episodes cannot exceed review episodes")
        _validate_int_sequence(
            self.lead_time_months,
            "lead_time_months",
            minimum=1,
            allow_empty=True,
        )
        if self.outcome_definition.availability == "unavailable" and self.lead_time_months:
            raise ValidationMetricsContractError(
                "lead-time values require an available independently agreed outcome definition"
            )
        _validate_rate(self.persistence_rate, "persistence_rate")
        _validate_rate(self.flip_rate, "flip_rate")
        if tuple(self.triage_counts) != TRIAGE_DISPOSITION_KEYS:
            raise ValidationMetricsContractError(
                "triage_counts must use the predeclared disposition keys in canonical order"
            )
        for disposition, count in self.triage_counts.items():
            _validate_non_negative_int(count, f"triage_counts[{disposition!r}]")
        if sum(self.triage_counts.values()) != self.customer_count:
            raise ValidationMetricsContractError("triage counts must reconcile to customer_count")
        if self.insufficient_evidence_count != self.triage_counts["insufficient_evidence"]:
            raise ValidationMetricsContractError(
                "insufficient_evidence_count must equal its triage disposition count"
            )


@dataclass(frozen=True)
class DistributionSummary:
    count: int
    mean: float
    q1: float
    median: float
    q3: float

    def to_dict(self) -> dict[str, object]:
        return {
            "count": self.count,
            "mean": self.mean,
            "q1": self.q1,
            "median": self.median,
            "q3": self.q3,
        }


@dataclass(frozen=True)
class ValidationMetricSection:
    """One source's aggregate values under the fixed metric specification."""

    source: str
    coverage: Mapping[str, object]
    feature_trajectory_distributions: Mapping[str, DistributionSummary]
    match_distance_distribution: DistributionSummary
    neighbor_support_distribution: DistributionSummary
    historical_cohort_outcome_share_distribution: DistributionSummary
    prospective_alert_metrics: Mapping[str, object]
    triage_capacity_metrics: Mapping[str, object]
    outcome_definition: OutcomeDefinition

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "coverage": dict(self.coverage),
            "feature_trajectory_distributions": {
                name: summary.to_dict()
                for name, summary in self.feature_trajectory_distributions.items()
            },
            "match_distance_distribution": self.match_distance_distribution.to_dict(),
            "neighbor_support_distribution": self.neighbor_support_distribution.to_dict(),
            "historical_cohort_outcome_share_distribution": {
                "description": "Matched historical-cohort outcome shares; not a target prediction probability.",
                "distribution": self.historical_cohort_outcome_share_distribution.to_dict(),
            },
            "prospective_alert_metrics": dict(self.prospective_alert_metrics),
            "triage_capacity_metrics": dict(self.triage_capacity_metrics),
            "outcome_definition": self.outcome_definition.to_dict(),
        }


@dataclass(frozen=True)
class ValidationComparisonReport:
    """Separated synthetic, approved-real and comparison sections."""

    synthetic: ValidationMetricSection
    approved_real: ValidationMetricSection | None
    comparison: Mapping[str, object]
    schema_version: str = VALIDATION_METRICS_REPORT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        real_absent = self.approved_real is None
        return {
            "schema_version": self.schema_version,
            "report_status": "template_real_absent" if real_absent else "aggregate_comparison_ready",
            "metric_specifications": list(METRIC_SPECIFICATIONS),
            "synthetic": self.synthetic.to_dict(),
            "approved_real": (
                {
                    "status": "absent_not_validated",
                    "reason": "No approved real-data aggregate result has been supplied.",
                }
                if real_absent
                else self.approved_real.to_dict()
            ),
            "comparison": dict(self.comparison),
            "prohibitions": {
                "single_actual_accuracy_score": False,
                "automatic_threshold_selection": False,
                "automatic_capacity_selection": False,
                "policy_or_triage_mutated": False,
                "row_level_values_exported": False,
            },
            "limitations": [
                "Synthetic metrics are not actual bank accuracy, customer behavior, RM productivity, intervention effect, or financial-performance claims.",
                "Outcome-dependent comparisons remain unavailable unless the independently agreed definitions are explicitly compatible.",
            ],
        }


def build_validation_comparison_report(
    synthetic_input: AggregateValidationMetricInput,
    approved_real_input: AggregateValidationMetricInput | None = None,
) -> ValidationComparisonReport:
    """Build the predeclared report without selecting thresholds or policies."""

    if synthetic_input.source != "synthetic":
        raise ValidationMetricsContractError("synthetic_input must have source='synthetic'")
    if approved_real_input is not None and approved_real_input.source != "approved_real":
        raise ValidationMetricsContractError("approved_real_input must have source='approved_real'")
    synthetic_section = _build_section(synthetic_input)
    real_section = None if approved_real_input is None else _build_section(approved_real_input)
    return ValidationComparisonReport(
        synthetic=synthetic_section,
        approved_real=real_section,
        comparison=_build_comparison(synthetic_input, approved_real_input),
    )


def validation_metrics_report_template() -> dict[str, object]:
    """Return the checked-in, source-free report schema template."""

    return {
        "schema_version": VALIDATION_METRICS_REPORT_SCHEMA_VERSION,
        "report_status": "template_real_absent",
        "metric_specifications": list(METRIC_SPECIFICATIONS),
        "synthetic": {"status": "aggregate_input_required"},
        "approved_real": {
            "status": "absent_not_validated",
            "reason": "No approved real-data aggregate result has been supplied.",
        },
        "comparison": {
            "outcome_compatibility_status": "real_absent",
            "direct_outcome_comparison_allowed": False,
            "capacity_scenario_comparison_status": "real_absent",
        },
        "prohibitions": {
            "single_actual_accuracy_score": False,
            "automatic_threshold_selection": False,
            "automatic_capacity_selection": False,
            "policy_or_triage_mutated": False,
            "row_level_values_exported": False,
        },
    }


def export_validation_comparison_report(
    report: ValidationComparisonReport,
    output_path: Path,
    *,
    allowed_root: Path,
) -> Path:
    """Atomically export aggregate report metadata to an injected noncanonical root."""

    destination = Path(output_path)
    root = Path(allowed_root)
    _assert_injected_output_path(destination, root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, destination)
    except OSError:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
        raise
    return destination


def _build_section(metric_input: AggregateValidationMetricInput) -> ValidationMetricSection:
    coverage_rate = metric_input.admitted_customer_month_count / metric_input.expected_customer_month_count
    missingness_rate = metric_input.missing_customer_month_count / metric_input.expected_customer_month_count
    triage_shares = {
        disposition: count / metric_input.customer_count
        for disposition, count in metric_input.triage_counts.items()
    }
    lead_time_distribution = (
        None
        if not metric_input.lead_time_months
        else _summarize(metric_input.lead_time_months).to_dict()
    )
    return ValidationMetricSection(
        source=metric_input.source,
        coverage={
            "customer_count": metric_input.customer_count,
            "expected_customer_month_count": metric_input.expected_customer_month_count,
            "admitted_customer_month_count": metric_input.admitted_customer_month_count,
            "missing_customer_month_count": metric_input.missing_customer_month_count,
            "coverage_rate": coverage_rate,
            "missingness_rate": missingness_rate,
        },
        feature_trajectory_distributions={
            name: _summarize(values)
            for name, values in sorted(metric_input.feature_values.items())
        },
        match_distance_distribution=_summarize(metric_input.match_distances),
        neighbor_support_distribution=_summarize(metric_input.neighbor_support_counts),
        historical_cohort_outcome_share_distribution=_summarize(
            metric_input.historical_cohort_outcome_shares
        ),
        prospective_alert_metrics={
            "analysis_customer_month_denominator": metric_input.analysis_customer_month_denominator,
            "review_episode_count": metric_input.review_episode_count,
            "alerts_per_1000_customer_months": (
                metric_input.review_episode_count
                / metric_input.analysis_customer_month_denominator
                * 1000.0
            ),
            "unique_alerted_customer_count": metric_input.unique_alerted_customer_count,
            "unique_alerted_rate": metric_input.unique_alerted_customer_count / metric_input.customer_count,
            "no_event_review_episode_count": metric_input.no_event_review_episode_count,
            "no_event_alert_rate": (
                None
                if metric_input.review_episode_count == 0
                else metric_input.no_event_review_episode_count / metric_input.review_episode_count
            ),
            "lead_time_distribution_months": lead_time_distribution,
            "lead_time_status": (
                "unavailable_without_independent_outcome"
                if metric_input.outcome_definition.availability == "unavailable"
                else "available"
            ),
            "persistence_rate": metric_input.persistence_rate,
            "flip_rate": metric_input.flip_rate,
        },
        triage_capacity_metrics={
            "capacity_scenario": metric_input.capacity_scenario.to_dict(),
            "counts": dict(metric_input.triage_counts),
            "shares": triage_shares,
            "insufficient_evidence_rate": (
                metric_input.insufficient_evidence_count / metric_input.customer_count
            ),
        },
        outcome_definition=metric_input.outcome_definition,
    )


def _build_comparison(
    synthetic_input: AggregateValidationMetricInput,
    real_input: AggregateValidationMetricInput | None,
) -> dict[str, object]:
    if real_input is None:
        return {
            "outcome_compatibility_status": "real_absent",
            "direct_outcome_comparison_allowed": False,
            "capacity_scenario_comparison_status": "real_absent",
            "feature_distribution_shift": {"status": "real_absent"},
            "match_distance_neighbor_support_shift": {"status": "real_absent"},
        }

    outcome_status = _outcome_compatibility_status(
        synthetic_input.outcome_definition,
        real_input.outcome_definition,
    )
    same_capacity = synthetic_input.capacity_scenario == real_input.capacity_scenario
    return {
        "outcome_compatibility_status": outcome_status,
        "direct_outcome_comparison_allowed": outcome_status == "compatible_predeclared",
        "capacity_scenario_comparison_status": (
            "same_declared_scenario" if same_capacity else "different_declared_scenarios"
        ),
        "feature_distribution_shift": _distribution_shift(
            synthetic_input.feature_values,
            real_input.feature_values,
        ),
        "match_distance_neighbor_support_shift": {
            "status": "available",
            "match_distance": _summary_delta(
                _summarize(synthetic_input.match_distances),
                _summarize(real_input.match_distances),
            ),
            "neighbor_support": _summary_delta(
                _summarize(synthetic_input.neighbor_support_counts),
                _summarize(real_input.neighbor_support_counts),
            ),
        },
    }


def _outcome_compatibility_status(
    synthetic: OutcomeDefinition,
    approved_real: OutcomeDefinition,
) -> str:
    if synthetic.availability != "available" or approved_real.availability != "available":
        return "outcome_unavailable"
    if not approved_real.independently_agreed:
        return "approved_real_outcome_not_independently_agreed"
    if synthetic.comparison_basis_id != approved_real.comparison_basis_id:
        return "incompatible_outcome_definitions"
    return "compatible_predeclared"


def _distribution_shift(
    synthetic_values: Mapping[str, Sequence[float]],
    real_values: Mapping[str, Sequence[float]],
) -> dict[str, object]:
    common_features = sorted(set(synthetic_values) & set(real_values))
    unavailable_features = sorted(set(synthetic_values) ^ set(real_values))
    return {
        "status": "available" if common_features else "no_common_feature_summary",
        "common_features": {
            feature_name: _summary_delta(
                _summarize(synthetic_values[feature_name]),
                _summarize(real_values[feature_name]),
            )
            for feature_name in common_features
        },
        "unavailable_features": unavailable_features,
        "threshold_declared": False,
    }


def _summary_delta(
    synthetic: DistributionSummary,
    approved_real: DistributionSummary,
) -> dict[str, float]:
    return {
        "synthetic_minus_approved_real_mean": synthetic.mean - approved_real.mean,
        "synthetic_minus_approved_real_median": synthetic.median - approved_real.median,
    }


def _summarize(values: Sequence[float] | Sequence[int]) -> DistributionSummary:
    normalized = sorted(float(value) for value in values)
    return DistributionSummary(
        count=len(normalized),
        mean=sum(normalized) / len(normalized),
        q1=_quantile(normalized, 0.25),
        median=_quantile(normalized, 0.5),
        q3=_quantile(normalized, 0.75),
    )


def _quantile(values: Sequence[float], quantile: float) -> float:
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def _validate_non_negative_int(value: int, label: str, *, allow_zero: bool = True) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or (not allow_zero and value == 0):
        qualifier = "positive" if not allow_zero else "non-negative"
        raise ValidationMetricsContractError(f"{label} must be a {qualifier} integer")


def _validate_int_sequence(
    values: Sequence[int],
    label: str,
    *,
    minimum: int,
    allow_empty: bool = False,
) -> None:
    if not values and not allow_empty:
        raise ValidationMetricsContractError(f"{label} must be non-empty")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < minimum for value in values):
        raise ValidationMetricsContractError(f"{label} values must be integers >= {minimum}")


def _validate_numeric_sequence(
    values: Sequence[float],
    label: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> None:
    if not values:
        raise ValidationMetricsContractError(f"{label} must be non-empty")
    normalized = [float(value) for value in values]
    if not all(math.isfinite(value) for value in normalized):
        raise ValidationMetricsContractError(f"{label} values must be finite")
    if minimum is not None and any(value < minimum for value in normalized):
        raise ValidationMetricsContractError(f"{label} values must be >= {minimum}")
    if maximum is not None and any(value > maximum for value in normalized):
        raise ValidationMetricsContractError(f"{label} values must be <= {maximum}")


def _validate_rate(value: float | None, label: str) -> None:
    if value is None:
        return
    numeric = float(value)
    if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
        raise ValidationMetricsContractError(f"{label} must be None or a finite rate in [0, 1]")


def _assert_injected_output_path(destination: Path, allowed_root: Path) -> None:
    resolved_destination = destination.resolve()
    resolved_root = allowed_root.resolve()
    try:
        resolved_destination.relative_to(resolved_root)
    except ValueError as error:
        raise ValidationMetricsContractError(
            "aggregate comparison reports must be written under an injected output root"
        ) from error
    for canonical_root in (
        settings.DATA_RAW_DIR,
        settings.DATA_PROCESSED_DIR,
        settings.DATA_DEMO_DIR,
    ):
        try:
            resolved_destination.relative_to(canonical_root.resolve())
        except ValueError:
            continue
        raise ValidationMetricsContractError(
            "aggregate comparison reports must not overwrite canonical data paths"
        )
