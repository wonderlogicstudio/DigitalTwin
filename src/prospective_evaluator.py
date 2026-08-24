"""Retrospective evaluator for already-completed prospective signal snapshots.

Only this module selects synthetic final labels and post-as-of event/status
rows.  It is intentionally separate from reference-only signal construction.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from config import settings
from src.prospective_scoring import ScoredSignalRecord


HISTORICAL_RISK_OUTCOMES = frozenset({"stress", "delinquent"})
EVALUATOR_REQUIRED_COLUMNS = (
    "customer_id",
    "month",
    "final_outcome",
    "monthly_status",
    "event_type",
)


@dataclass(frozen=True)
class SyntheticEventAnchor:
    """First configured synthetic event for one customer in the future window."""

    customer_id: str
    event_month: int | None
    event_type: str | None
    source: str = "synthetic_event_anchor"

    @property
    def event_observed(self) -> bool:
        return self.event_month is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "customer_id": self.customer_id,
            "event_month": self.event_month,
            "event_type": self.event_type,
            "event_observed": self.event_observed,
            "source": self.source,
        }


@dataclass(frozen=True)
class HistoricalCohortShareProvider:
    """Lookup-only share provider built from a disjoint reference cohort."""

    reference_customer_ids: frozenset[str]
    outcome_by_customer_id: dict[str, str]

    def __call__(self, as_of_month: int, neighbor_ids: tuple[str, ...]) -> float:
        """Return a descriptive historical risk-path share for reference neighbors."""

        if not neighbor_ids:
            raise ValueError("at least one reference neighbor is required")
        unknown_ids = sorted(set(neighbor_ids) - self.reference_customer_ids)
        if unknown_ids:
            raise ValueError("historical share provider received non-reference neighbors")
        outcomes = [self.outcome_by_customer_id[customer_id] for customer_id in neighbor_ids]
        return float(sum(outcome in HISTORICAL_RISK_OUTCOMES for outcome in outcomes) / len(outcomes))


@dataclass(frozen=True)
class EvaluatedSignalRecord:
    """A retrospective label/event record, created only after scoring completes."""

    customer_id: str
    as_of_month: int
    target_final_outcome: str
    future_adverse_event_observed: bool
    first_future_adverse_event_month: int | None
    future_non_none_event_observed: bool
    first_future_non_none_event_month: int | None

    @property
    def key(self) -> tuple[str, int]:
        return (self.customer_id, self.as_of_month)

    def to_dict(self) -> dict[str, object]:
        return {
            "customer_id": self.customer_id,
            "as_of_month": self.as_of_month,
            "target_final_outcome": self.target_final_outcome,
            "future_adverse_event_observed": self.future_adverse_event_observed,
            "first_future_adverse_event_month": self.first_future_adverse_event_month,
            "future_non_none_event_observed": self.future_non_none_event_observed,
            "first_future_non_none_event_month": self.first_future_non_none_event_month,
        }


def build_reference_historical_share_provider(
    monthly_df: pd.DataFrame,
    *,
    reference_customer_ids: Sequence[str],
) -> HistoricalCohortShareProvider:
    """Open labels for reference customers only, never an evaluation target."""

    reference_ids = tuple(sorted(str(customer_id) for customer_id in reference_customer_ids))
    if not reference_ids or len(reference_ids) != len(set(reference_ids)):
        raise ValueError("reference_customer_ids must be non-empty and unique")
    _require_columns(monthly_df, ("customer_id", "final_outcome"))
    reference_rows = monthly_df.loc[
        monthly_df["customer_id"].astype(str).isin(reference_ids),
        ["customer_id", "final_outcome"],
    ].copy()
    reference_rows["customer_id"] = reference_rows["customer_id"].astype(str)
    outcomes_per_customer = reference_rows.groupby("customer_id", sort=True)["final_outcome"].agg(
        lambda outcomes: tuple(sorted(set(outcomes.astype(str))))
    )
    missing_ids = sorted(set(reference_ids) - set(outcomes_per_customer.index))
    inconsistent_ids = [
        customer_id
        for customer_id, outcomes in outcomes_per_customer.items()
        if len(outcomes) != 1
    ]
    if missing_ids or inconsistent_ids:
        raise ValueError(
            "reference final outcomes must contain exactly one label per customer; "
            f"missing={missing_ids[:5]}, inconsistent={inconsistent_ids[:5]}"
        )
    return HistoricalCohortShareProvider(
        reference_customer_ids=frozenset(reference_ids),
        outcome_by_customer_id={
            str(customer_id): outcomes[0] for customer_id, outcomes in outcomes_per_customer.items()
        },
    )


def evaluate_completed_signals(
    monthly_df: pd.DataFrame,
    scored_records: Sequence[ScoredSignalRecord],
) -> tuple[EvaluatedSignalRecord, ...]:
    """Open each target's future rows only after its signal snapshot exists."""

    _require_columns(monthly_df, EVALUATOR_REQUIRED_COLUMNS)
    keys = [record.key for record in scored_records]
    if len(keys) != len(set(keys)):
        raise ValueError("scored records must have unique customer_id and as_of_month keys")
    records = []
    for scored_record in scored_records:
        customer_id, as_of_month = scored_record.key
        future_rows = monthly_df.loc[
            (monthly_df["customer_id"].astype(str) == customer_id)
            & (monthly_df["month"] > as_of_month),
            list(EVALUATOR_REQUIRED_COLUMNS),
        ].copy()
        if future_rows.empty:
            raise ValueError(f"no future evaluator rows are available for {customer_id} month {as_of_month}")
        future_rows = future_rows.sort_values("month")
        final_outcomes = tuple(sorted(set(future_rows["final_outcome"].astype(str))))
        if len(final_outcomes) != 1:
            raise ValueError(
                f"target final outcome must be consistent for {customer_id}: {final_outcomes}"
            )
        adverse_rows = future_rows.loc[
            future_rows["monthly_status"].astype(str).isin(HISTORICAL_RISK_OUTCOMES)
        ]
        non_none_event_rows = future_rows.loc[
            future_rows["event_type"].astype(str).ne("none")
        ]
        records.append(
            EvaluatedSignalRecord(
                customer_id=customer_id,
                as_of_month=as_of_month,
                target_final_outcome=final_outcomes[0],
                future_adverse_event_observed=not adverse_rows.empty,
                first_future_adverse_event_month=(
                    None if adverse_rows.empty else int(adverse_rows.iloc[0]["month"])
                ),
                future_non_none_event_observed=not non_none_event_rows.empty,
                first_future_non_none_event_month=(
                    None if non_none_event_rows.empty else int(non_none_event_rows.iloc[0]["month"])
                ),
            )
        )
    return tuple(records)


def extract_synthetic_future_event_anchors(
    monthly_df: pd.DataFrame,
    *,
    customer_ids: Sequence[str],
) -> tuple[SyntheticEventAnchor, ...]:
    """Extract each customer's first non-``none`` event in months 13 through 36.

    This is an evaluator-only synthetic anchor.  A missing anchor means that
    no generated event occurred in the configured future window; it is not a
    statement about a real customer's future.
    """

    normalized_ids = tuple(sorted(str(customer_id) for customer_id in customer_ids))
    if not normalized_ids or len(normalized_ids) != len(set(normalized_ids)):
        raise ValueError("customer_ids must be non-empty and unique")
    _require_columns(monthly_df, ("customer_id", "month", "event_type"))
    future_rows = monthly_df.loc[
        monthly_df["customer_id"].astype(str).isin(normalized_ids)
        & monthly_df["month"].between(settings.FUTURE_START_MONTH, settings.FUTURE_END_MONTH),
        ["customer_id", "month", "event_type"],
    ].copy()
    future_rows["customer_id"] = future_rows["customer_id"].astype(str)
    missing_ids = sorted(set(normalized_ids) - set(future_rows["customer_id"]))
    if missing_ids:
        raise ValueError(f"customers are missing configured future event rows: {missing_ids[:5]}")

    anchors = []
    for customer_id in normalized_ids:
        events = future_rows.loc[
            future_rows["customer_id"].eq(customer_id)
            & future_rows["event_type"].astype(str).ne("none")
        ].sort_values("month")
        if events.empty:
            anchors.append(SyntheticEventAnchor(customer_id=customer_id, event_month=None, event_type=None))
        else:
            first_event = events.iloc[0]
            anchors.append(
                SyntheticEventAnchor(
                    customer_id=customer_id,
                    event_month=int(first_event["month"]),
                    event_type=str(first_event["event_type"]),
                )
            )
    return tuple(anchors)


def _require_columns(monthly_df: pd.DataFrame, required_columns: Sequence[str]) -> None:
    missing_columns = sorted(set(required_columns) - set(monthly_df.columns))
    if missing_columns:
        raise ValueError(f"monthly_df is missing evaluator columns: {missing_columns}")
