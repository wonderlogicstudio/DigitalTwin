"""Synthetic retrospective workload and timing trade-off comparisons.

This module compares caller-supplied candidate-policy timing evidence.  It
does not create policies, choose a threshold, select customers for an RM
queue, or send notifications.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from math import ceil
from typing import Any

from config import settings
from src.timing_evidence import (
    LEAD_TIME_STATUS,
    NO_EVENT_ALERT_STATUS,
    TOO_LATE_STATUS,
    ProspectiveTimingRecord,
    TimingEvidenceResult,
)


TRADEOFF_REPORT_SCHEMA_VERSION = "synthetic_alert_tradeoff_report.v1"
SYNTHETIC_EVENT_DEFINITION = (
    "Evaluator-only first non-none generated event_type in the configured synthetic future window."
)


@dataclass(frozen=True)
class TradeoffMeasurementContext:
    """Shared denominator and period definition for comparable policy rows."""

    customer_ids: tuple[str, ...]
    analysis_months: tuple[int, ...]
    period_days: int
    event_definition: str = SYNTHETIC_EVENT_DEFINITION

    def __post_init__(self) -> None:
        normalized_ids = tuple(sorted(str(customer_id) for customer_id in self.customer_ids))
        if not normalized_ids or len(normalized_ids) != len(set(normalized_ids)):
            raise ValueError("customer_ids must be non-empty and unique")
        normalized_months = tuple(self.analysis_months)
        if not normalized_months or any(
            isinstance(month, bool) or not isinstance(month, int) for month in normalized_months
        ):
            raise ValueError("analysis_months must be non-empty integer months")
        if normalized_months != tuple(sorted(set(normalized_months))):
            raise ValueError("analysis_months must be sorted and unique")
        if any(month < 1 or month > settings.TOTAL_MONTHS for month in normalized_months):
            raise ValueError(
                f"analysis_months must be between 1 and {settings.TOTAL_MONTHS}"
            )
        if any(current != previous + 1 for previous, current in zip(normalized_months, normalized_months[1:])):
            raise ValueError("analysis_months must be contiguous for persistence and flip metrics")
        if isinstance(self.period_days, bool) or not isinstance(self.period_days, int) or self.period_days <= 0:
            raise ValueError("period_days must be a positive integer")
        if not str(self.event_definition).strip():
            raise ValueError("event_definition must be non-empty")
        object.__setattr__(self, "customer_ids", normalized_ids)

    @property
    def customer_month_denominator(self) -> int:
        return len(self.customer_ids) * len(self.analysis_months)

    def to_dict(self) -> dict[str, object]:
        return {
            "population_customer_count": len(self.customer_ids),
            "analysis_months": list(self.analysis_months),
            "customer_month_denominator": self.customer_month_denominator,
            "period_days": self.period_days,
            "event_definition": self.event_definition,
        }


@dataclass(frozen=True)
class CandidatePolicyTimingEvidence:
    """One externally supplied candidate policy and its timing evidence."""

    policy_id: str
    policy_name: str
    timing_evidence: TimingEvidenceResult
    description: str = ""

    def __post_init__(self) -> None:
        if not str(self.policy_id).strip() or not str(self.policy_name).strip():
            raise ValueError("policy_id and policy_name must be non-empty")


@dataclass(frozen=True)
class ReviewCapacityScenario:
    """Optional comparison-only review capacity, not an approved bank standard."""

    scenario_id: str
    max_reviews_per_cycle: int
    cycle_days: int

    def __post_init__(self) -> None:
        if not str(self.scenario_id).strip():
            raise ValueError("scenario_id must be non-empty")
        if (
            isinstance(self.max_reviews_per_cycle, bool)
            or not isinstance(self.max_reviews_per_cycle, int)
            or self.max_reviews_per_cycle <= 0
        ):
            raise ValueError("max_reviews_per_cycle must be a positive integer")
        if isinstance(self.cycle_days, bool) or not isinstance(self.cycle_days, int) or self.cycle_days <= 0:
            raise ValueError("cycle_days must be a positive integer")


@dataclass(frozen=True)
class CapacityWorkloadComparison:
    """Episode workload compared with one hypothetical capacity scenario."""

    scenario_id: str
    max_reviews_per_cycle: int
    cycle_days: int
    review_episode_count: int
    cycles_required: int
    episodes_beyond_one_cycle: int
    comparison_only: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "max_reviews_per_cycle": self.max_reviews_per_cycle,
            "cycle_days": self.cycle_days,
            "review_episode_count": self.review_episode_count,
            "cycles_required": self.cycles_required,
            "episodes_beyond_one_cycle": self.episodes_beyond_one_cycle,
            "comparison_only": self.comparison_only,
        }


@dataclass(frozen=True)
class PolicyTradeoffMetrics:
    """One candidate policy's workload and synthetic retrospective proxies."""

    policy_id: str
    policy_name: str
    description: str
    alert_moment_count: int
    review_episode_count: int
    alerts_per_1000_customer_months: float
    unique_alerted_customer_count: int
    synthetic_precision_proxy: float | None
    synthetic_recall_proxy: float | None
    no_event_alert_rate: float | None
    lead_time_median_months: float | None
    lead_time_q1_months: float | None
    lead_time_q3_months: float | None
    persistence_rate: float | None
    mean_episode_length_months: float | None
    flip_rate: float | None
    estimated_reviews_per_period: int
    estimated_reviews_per_day: float
    capacity_comparisons: tuple[CapacityWorkloadComparison, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "policy_name": self.policy_name,
            "description": self.description,
            "alert_moment_count": self.alert_moment_count,
            "review_episode_count": self.review_episode_count,
            "alerts_per_1000_customer_months": self.alerts_per_1000_customer_months,
            "unique_alerted_customer_count": self.unique_alerted_customer_count,
            "synthetic_precision_proxy": self.synthetic_precision_proxy,
            "synthetic_recall_proxy": self.synthetic_recall_proxy,
            "no_event_alert_rate": self.no_event_alert_rate,
            "lead_time_median_months": self.lead_time_median_months,
            "lead_time_q1_months": self.lead_time_q1_months,
            "lead_time_q3_months": self.lead_time_q3_months,
            "persistence_rate": self.persistence_rate,
            "mean_episode_length_months": self.mean_episode_length_months,
            "flip_rate": self.flip_rate,
            "estimated_reviews_per_period": self.estimated_reviews_per_period,
            "estimated_reviews_per_day": self.estimated_reviews_per_day,
            "capacity_comparisons": [item.to_dict() for item in self.capacity_comparisons],
            "metric_scope": "synthetic retrospective comparison only",
        }


@dataclass(frozen=True)
class AlertTradeoffReport:
    """A policy comparison table with no selected threshold or RM queue."""

    context: TradeoffMeasurementContext
    policies: tuple[PolicyTradeoffMetrics, ...]
    schema_version: str = TRADEOFF_REPORT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "context": self.context.to_dict(),
            "policies": [policy.to_dict() for policy in self.policies],
            "selection": {
                "automatic_threshold_selection": False,
                "rm_queue_selection": False,
                "alert_creation": False,
            },
            "methodology": {
                "alert_unit": "Contiguous candidate alert months for one customer are one review episode.",
                "alerts_per_1000_denominator": "review episodes / shared customer-month denominator * 1000",
                "synthetic_precision_proxy": "lead-time episodes / review episodes",
                "synthetic_recall_proxy": "customers with at least one lead-time episode / customers with a synthetic event anchor",
                "no_event_alert_rate": "no-event review episodes / review episodes",
                "persistence_rate": "alert-to-alert adjacent month pairs / adjacent pairs with an alert in the prior month",
                "flip_rate": "alert-state changes / all adjacent customer-month state pairs",
            },
            "limitations": [
                "Synthetic retrospective proxies are not bank precision, recall, productivity, or intervention-effect KPIs.",
                "Capacity scenarios are comparison inputs only and do not approve a bank standard or choose a policy.",
                "The report contains aggregate counts only; it does not create an RM queue or alert work items.",
            ],
        }


def build_alert_tradeoff_report(
    *,
    context: TradeoffMeasurementContext,
    policy_evidence: Iterable[CandidatePolicyTimingEvidence],
    review_capacity_scenarios: Iterable[ReviewCapacityScenario] = (),
) -> AlertTradeoffReport:
    """Compare multiple candidate policies without selecting one as correct."""

    policies = tuple(policy_evidence)
    if len(policies) < 2:
        raise ValueError("at least two candidate policies are required for a trade-off comparison")
    policy_ids = [policy.policy_id for policy in policies]
    if len(policy_ids) != len(set(policy_ids)):
        raise ValueError("policy_id values must be unique")
    scenarios = _normalize_capacity_scenarios(review_capacity_scenarios)
    metrics = tuple(
        _build_policy_metrics(context, policy, scenarios)
        for policy in sorted(policies, key=lambda policy: policy.policy_id)
    )
    return AlertTradeoffReport(context=context, policies=metrics)


def _build_policy_metrics(
    context: TradeoffMeasurementContext,
    policy: CandidatePolicyTimingEvidence,
    scenarios: Sequence[ReviewCapacityScenario],
) -> PolicyTradeoffMetrics:
    records = _validate_and_normalize_timing_records(context, policy.timing_evidence)
    candidate_records = tuple(record for record in records if record.alert_month is not None)
    episodes = _build_review_episodes(candidate_records)
    episode_count = len(episodes)
    lead_time_episodes = [episode for episode in episodes if any(
        record.status == LEAD_TIME_STATUS for record in episode
    )]
    no_event_episodes = [episode for episode in episodes if all(
        record.status == NO_EVENT_ALERT_STATUS for record in episode
    )]
    event_customer_ids = {record.customer_id for record in records if record.event_observed}
    lead_time_customer_ids = {episode[0].customer_id for episode in lead_time_episodes}
    persistence_numerator, persistence_denominator = _persistence_pairs(context, candidate_records)
    flip_numerator, flip_denominator = _flip_pairs(context, candidate_records)
    episode_lengths = [len(episode) for episode in episodes]
    return PolicyTradeoffMetrics(
        policy_id=policy.policy_id,
        policy_name=policy.policy_name,
        description=policy.description,
        alert_moment_count=len(candidate_records),
        review_episode_count=episode_count,
        alerts_per_1000_customer_months=(
            episode_count / context.customer_month_denominator * 1000.0
        ),
        unique_alerted_customer_count=len({record.customer_id for record in candidate_records}),
        synthetic_precision_proxy=(
            None if not episodes else len(lead_time_episodes) / episode_count
        ),
        synthetic_recall_proxy=(
            None if not event_customer_ids else len(lead_time_customer_ids) / len(event_customer_ids)
        ),
        no_event_alert_rate=(None if not episodes else len(no_event_episodes) / episode_count),
        lead_time_median_months=policy.timing_evidence.summary.lead_time_median_months,
        lead_time_q1_months=policy.timing_evidence.summary.lead_time_q1_months,
        lead_time_q3_months=policy.timing_evidence.summary.lead_time_q3_months,
        persistence_rate=(
            None if persistence_denominator == 0 else persistence_numerator / persistence_denominator
        ),
        mean_episode_length_months=(
            None if not episode_lengths else sum(episode_lengths) / len(episode_lengths)
        ),
        flip_rate=None if flip_denominator == 0 else flip_numerator / flip_denominator,
        estimated_reviews_per_period=episode_count,
        estimated_reviews_per_day=episode_count / context.period_days,
        capacity_comparisons=tuple(
            _capacity_comparison(episode_count, scenario) for scenario in scenarios
        ),
    )


def _validate_and_normalize_timing_records(
    context: TradeoffMeasurementContext,
    evidence: TimingEvidenceResult,
) -> tuple[ProspectiveTimingRecord, ...]:
    records = tuple(evidence.prospective_records)
    customer_ids = {record.customer_id for record in records}
    if customer_ids != set(context.customer_ids):
        raise ValueError("each policy timing evidence must exactly cover the shared customer population")
    candidate_keys = [
        (record.customer_id, record.alert_month)
        for record in records
        if record.alert_month is not None
    ]
    if len(candidate_keys) != len(set(candidate_keys)):
        raise ValueError("policy timing evidence contains duplicate candidate alert moments")
    invalid_months = sorted(
        {
            int(record.alert_month)
            for record in records
            if record.alert_month is not None and record.alert_month not in context.analysis_months
        }
    )
    if invalid_months:
        raise ValueError(f"candidate alert months fall outside the shared analysis period: {invalid_months}")
    return tuple(
        sorted(
            records,
            key=lambda record: (
                record.customer_id,
                -1 if record.alert_month is None else record.alert_month,
            ),
        )
    )


def _build_review_episodes(
    candidate_records: Sequence[ProspectiveTimingRecord],
) -> tuple[tuple[ProspectiveTimingRecord, ...], ...]:
    grouped: dict[str, list[ProspectiveTimingRecord]] = {}
    for record in candidate_records:
        grouped.setdefault(record.customer_id, []).append(record)
    episodes: list[tuple[ProspectiveTimingRecord, ...]] = []
    for customer_id in sorted(grouped):
        current_episode: list[ProspectiveTimingRecord] = []
        previous_month: int | None = None
        for record in sorted(grouped[customer_id], key=lambda item: int(item.alert_month or 0)):
            assert record.alert_month is not None
            if previous_month is None or record.alert_month == previous_month + 1:
                current_episode.append(record)
            else:
                episodes.append(tuple(current_episode))
                current_episode = [record]
            previous_month = record.alert_month
        if current_episode:
            episodes.append(tuple(current_episode))
    return tuple(episodes)


def _persistence_pairs(
    context: TradeoffMeasurementContext,
    candidate_records: Sequence[ProspectiveTimingRecord],
) -> tuple[int, int]:
    alerted_keys = {(record.customer_id, record.alert_month) for record in candidate_records}
    numerator = 0
    denominator = 0
    for customer_id in context.customer_ids:
        for previous_month, current_month in zip(context.analysis_months, context.analysis_months[1:]):
            if (customer_id, previous_month) in alerted_keys:
                denominator += 1
                if (customer_id, current_month) in alerted_keys:
                    numerator += 1
    return numerator, denominator


def _flip_pairs(
    context: TradeoffMeasurementContext,
    candidate_records: Sequence[ProspectiveTimingRecord],
) -> tuple[int, int]:
    alerted_keys = {(record.customer_id, record.alert_month) for record in candidate_records}
    numerator = 0
    denominator = 0
    for customer_id in context.customer_ids:
        for previous_month, current_month in zip(context.analysis_months, context.analysis_months[1:]):
            denominator += 1
            if ((customer_id, previous_month) in alerted_keys) != (
                (customer_id, current_month) in alerted_keys
            ):
                numerator += 1
    return numerator, denominator


def _normalize_capacity_scenarios(
    scenarios: Iterable[ReviewCapacityScenario],
) -> tuple[ReviewCapacityScenario, ...]:
    normalized = tuple(scenarios)
    scenario_ids = [scenario.scenario_id for scenario in normalized]
    if len(scenario_ids) != len(set(scenario_ids)):
        raise ValueError("review capacity scenario IDs must be unique")
    return tuple(sorted(normalized, key=lambda scenario: scenario.scenario_id))


def _capacity_comparison(
    review_episode_count: int,
    scenario: ReviewCapacityScenario,
) -> CapacityWorkloadComparison:
    return CapacityWorkloadComparison(
        scenario_id=scenario.scenario_id,
        max_reviews_per_cycle=scenario.max_reviews_per_cycle,
        cycle_days=scenario.cycle_days,
        review_episode_count=review_episode_count,
        cycles_required=ceil(review_episode_count / scenario.max_reviews_per_cycle),
        episodes_beyond_one_cycle=max(0, review_episode_count - scenario.max_reviews_per_cycle),
    )
