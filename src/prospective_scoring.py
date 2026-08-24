"""Reference-only construction of prospective signal snapshots.

This module accepts a prepared, observed-month input table and a historical
reference-cohort share provider.  It neither imports an evaluation component
nor selects target labels or future rows.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import pandas as pd

from config import settings
from src.as_of_features import AS_OF_REQUIRED_COLUMNS, build_as_of_trajectory_features
from src.prospective_signals import (
    CURRENT_SNAPSHOT_COLUMNS,
    SignalSnapshot,
    SignalSnapshotHistory,
    build_signal_snapshot,
)
from src.reference_matcher import ReferenceTrajectoryMatcher


OBSERVED_SCORING_COLUMNS = tuple(
    dict.fromkeys((*AS_OF_REQUIRED_COLUMNS, *CURRENT_SNAPSHOT_COLUMNS))
)
HistoricalShareProvider = Callable[[int, tuple[str, ...]], float]


@dataclass(frozen=True)
class ScoredSignalRecord:
    """One completed signal snapshot, tagged with its deterministic fold."""

    fold_id: int
    snapshot: SignalSnapshot

    @property
    def key(self) -> tuple[str, int]:
        return (self.snapshot.customer_id, self.snapshot.as_of_month)

    def to_dict(self) -> dict[str, object]:
        return {"fold_id": self.fold_id, **self.snapshot.to_dict()}


@dataclass(frozen=True)
class ScoringFailure:
    """A non-silent failure for one expected customer-month signal."""

    customer_id: str
    as_of_month: int
    error_category: str
    message: str

    @property
    def key(self) -> tuple[str, int]:
        return (self.customer_id, self.as_of_month)

    def to_dict(self) -> dict[str, object]:
        return {
            "customer_id": self.customer_id,
            "as_of_month": self.as_of_month,
            "error_category": self.error_category,
            "message": self.message,
        }


@dataclass(frozen=True)
class FoldScoringResult:
    """Completed and failed signal rows for one evaluation fold."""

    fold_id: int
    expected_keys: tuple[tuple[str, int], ...]
    records: tuple[ScoredSignalRecord, ...]
    failures: tuple[ScoringFailure, ...]

    @property
    def processed_keys(self) -> tuple[tuple[str, int], ...]:
        return tuple(record.key for record in self.records)


def prepare_observed_scoring_data(
    monthly_df: pd.DataFrame,
    *,
    as_of_months: Sequence[int],
) -> pd.DataFrame:
    """Copy only the observed columns and rows needed by signal construction."""

    normalized_months = normalize_as_of_months(as_of_months)
    missing_columns = sorted(set(OBSERVED_SCORING_COLUMNS) - set(monthly_df.columns))
    if missing_columns:
        raise ValueError(f"monthly_df is missing observed scoring columns: {missing_columns}")
    return monthly_df.loc[
        monthly_df["month"] <= max(normalized_months),
        list(OBSERVED_SCORING_COLUMNS),
    ].copy()


def normalize_as_of_months(as_of_months: Sequence[int]) -> tuple[int, ...]:
    """Require a non-empty, contiguous scoring timeline with available history."""

    supplied_months = tuple(as_of_months)
    if not supplied_months:
        raise ValueError("at least one as_of_month is required")
    if any(isinstance(month, bool) or not isinstance(month, int) for month in supplied_months):
        raise TypeError("as_of_months must contain integers")
    normalized = tuple(sorted(set(supplied_months)))
    if normalized[0] < 12 or normalized[-1] >= settings.TOTAL_MONTHS:
        raise ValueError(
            f"as_of_months must be between 12 and {settings.TOTAL_MONTHS - 1} for backtesting"
        )
    if any(current != previous + 1 for previous, current in zip(normalized, normalized[1:])):
        raise ValueError("as_of_months must be contiguous for sequential signal history")
    return normalized


def score_reference_only_fold(
    observed_monthly_df: pd.DataFrame,
    *,
    fold_id: int,
    reference_customer_ids: Sequence[str],
    evaluation_customer_ids: Sequence[str],
    as_of_months: Sequence[int],
    historical_share_provider: HistoricalShareProvider,
    top_k: int = settings.TOP_K_MATCHES,
) -> FoldScoringResult:
    """Build snapshots for evaluation customers against one disjoint reference set.

    The scaler is fitted once per as-of month using reference customers only.
    A caller-provided historical-share provider receives reference neighbor IDs
    only, while this function reads no target labels.
    """

    reference_ids = _normalize_customer_ids(reference_customer_ids, label="reference_customer_ids")
    evaluation_ids = _normalize_customer_ids(
        evaluation_customer_ids,
        label="evaluation_customer_ids",
    )
    if set(reference_ids) & set(evaluation_ids):
        raise ValueError("reference and evaluation customer IDs must be disjoint")
    if top_k <= 0 or top_k > len(reference_ids):
        raise ValueError("top_k must be between 1 and the reference customer count")
    normalized_months = normalize_as_of_months(as_of_months)
    observed_data = prepare_observed_scoring_data(
        observed_monthly_df,
        as_of_months=normalized_months,
    )
    expected_keys = tuple(
        (customer_id, as_of_month)
        for customer_id in evaluation_ids
        for as_of_month in normalized_months
    )
    histories = {customer_id: SignalSnapshotHistory() for customer_id in evaluation_ids}
    records: list[ScoredSignalRecord] = []
    failures: list[ScoringFailure] = []

    for month_index, as_of_month in enumerate(normalized_months):
        try:
            features_df = build_as_of_trajectory_features(observed_data, as_of_month)
            reference_features = _select_feature_rows(
                features_df,
                reference_ids,
                label="reference",
            )
            evaluation_features = _select_feature_rows(
                features_df,
                evaluation_ids,
                label="evaluation",
            )
            matcher = ReferenceTrajectoryMatcher().fit(reference_features)
        except Exception as error:  # collect every expected row rather than silently aborting
            failures.extend(
                _failure(customer_id, as_of_month, error) for customer_id in evaluation_ids
            )
            continue

        evaluation_by_id = evaluation_features.set_index("customer_id", drop=False)
        for customer_id in evaluation_ids:
            try:
                previous_snapshot = histories[customer_id].previous_snapshot(customer_id, as_of_month)
                if month_index and previous_snapshot is None:
                    raise RuntimeError("the immediately prior signal snapshot is unavailable")
                matches = matcher.match(evaluation_by_id.loc[[customer_id]], top_k=top_k)
                neighbor_ids = tuple(matches["matched_customer_id"].astype(str))
                historical_share = historical_share_provider(as_of_month, neighbor_ids)
                snapshot = build_signal_snapshot(
                    observed_data,
                    customer_id=customer_id,
                    as_of_month=as_of_month,
                    matches=matches,
                    historical_cohort_risk_share=historical_share,
                    previous_snapshot=previous_snapshot,
                )
                histories[customer_id] = histories[customer_id].append(snapshot)
                records.append(ScoredSignalRecord(fold_id=int(fold_id), snapshot=snapshot))
            except Exception as error:  # preserve the expected customer-month in failures
                failures.append(_failure(customer_id, as_of_month, error))

    return FoldScoringResult(
        fold_id=int(fold_id),
        expected_keys=expected_keys,
        records=tuple(records),
        failures=tuple(failures),
    )


def _normalize_customer_ids(customer_ids: Sequence[str], *, label: str) -> tuple[str, ...]:
    normalized = tuple(str(customer_id) for customer_id in customer_ids)
    if not normalized:
        raise ValueError(f"{label} must not be empty")
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{label} must not contain duplicates")
    return tuple(sorted(normalized))


def _select_feature_rows(
    features_df: pd.DataFrame,
    customer_ids: Sequence[str],
    *,
    label: str,
) -> pd.DataFrame:
    expected_ids = tuple(customer_ids)
    selected = features_df.loc[features_df["customer_id"].astype(str).isin(expected_ids)].copy()
    selected["customer_id"] = selected["customer_id"].astype(str)
    selected = selected.sort_values("customer_id").reset_index(drop=True)
    missing_ids = sorted(set(expected_ids) - set(selected["customer_id"]))
    if missing_ids:
        raise ValueError(f"{label} customers are missing complete as-of features: {missing_ids[:5]}")
    return selected


def _failure(customer_id: str, as_of_month: int, error: Exception) -> ScoringFailure:
    return ScoringFailure(
        customer_id=str(customer_id),
        as_of_month=int(as_of_month),
        error_category=type(error).__name__,
        message=str(error),
    )
