"""Prospective signal snapshots built from current and prior information only.

This module deliberately does not calculate outcomes or import an evaluator.
The historical matched-cohort risk share is a scalar supplied by the caller;
it is a descriptive cohort statistic, not a target likelihood.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd


CURRENT_SNAPSHOT_COLUMNS = (
    "customer_id",
    "month",
    "savings_amount",
    "savings_rate",
    "fixed_expense_ratio",
    "dsr",
    "cash_balance",
    "emergency_months",
    "monthly_status",
)
MATCH_REQUIRED_COLUMNS = (
    "target_customer_id",
    "matched_customer_id",
    "distance",
)
SIGNAL_DEFINITIONS = {
    "historical_cohort_risk_share": {
        "direction": "higher_is_more_concerning",
        "unit": "share_0_to_1",
        "description": "Historical risk-path share in the matched reference cohort.",
    },
    "historical_cohort_risk_share_delta": {
        "direction": "higher_is_more_concerning",
        "unit": "share_change",
        "description": "Current historical cohort risk share minus the prior-month snapshot share.",
    },
    "match_distance_mean": {
        "direction": "higher_is_less_similar_to_reference",
        "unit": "weighted_standardized_distance",
        "description": "Mean weighted standardized distance across returned reference neighbors.",
    },
    "match_distance_mean_delta": {
        "direction": "higher_is_less_similar_to_reference",
        "unit": "distance_change",
        "description": "Current mean match distance minus the prior-month snapshot distance.",
    },
    "neighbor_jaccard_similarity": {
        "direction": "higher_is_more_stable",
        "unit": "share_0_to_1",
        "description": "Jaccard similarity of current and prior reference-neighbor ID sets.",
    },
    "current_status_transition": {
        "direction": "categorical",
        "unit": "status_transition",
        "description": "Current monthly status relative to the immediately prior snapshot.",
    },
    "financial_stress_factors": {
        "direction": "factor_specific",
        "unit": "categorical_factor_set",
        "description": "Current threshold-based financial stress factors; no composite score is created.",
    },
    "persistent_financial_stress_factors": {
        "direction": "persistent_is_more_concerning",
        "unit": "categorical_factor_set",
        "description": "Current factors also present in the immediately prior snapshot.",
    },
}


@dataclass(frozen=True)
class SignalSnapshot:
    """One customer's prospective signal state at one explicit as-of month."""

    customer_id: str
    as_of_month: int
    matched_count: int
    neighbor_ids: tuple[str, ...]
    historical_cohort_risk_share: float
    historical_cohort_risk_share_delta: float | None
    match_distance_mean: float
    match_distance_mean_delta: float | None
    neighbor_jaccard_similarity: float | None
    current_status: str
    current_status_transition: str
    financial_stress_factors: tuple[str, ...]
    persistent_financial_stress_factors: tuple[str, ...]
    previous_as_of_month: int | None

    def to_dict(self) -> dict[str, Any]:
        """Return primitive, JSON-serializable snapshot fields."""

        return {
            "customer_id": self.customer_id,
            "as_of_month": self.as_of_month,
            "matched_count": self.matched_count,
            "neighbor_ids": list(self.neighbor_ids),
            "historical_cohort_risk_share": self.historical_cohort_risk_share,
            "historical_cohort_risk_share_delta": self.historical_cohort_risk_share_delta,
            "match_distance_mean": self.match_distance_mean,
            "match_distance_mean_delta": self.match_distance_mean_delta,
            "neighbor_jaccard_similarity": self.neighbor_jaccard_similarity,
            "current_status": self.current_status,
            "current_status_transition": self.current_status_transition,
            "financial_stress_factors": list(self.financial_stress_factors),
            "persistent_financial_stress_factors": list(self.persistent_financial_stress_factors),
            "previous_as_of_month": self.previous_as_of_month,
        }


@dataclass(frozen=True)
class SignalSnapshotHistory:
    """Deterministic, customer-month unique sequence of signal snapshots."""

    snapshots: tuple[SignalSnapshot, ...] = ()

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.snapshots, key=lambda item: (item.customer_id, item.as_of_month)))
        keys = [(snapshot.customer_id, snapshot.as_of_month) for snapshot in ordered]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate customer_id and as_of_month snapshot key")
        for customer_id, customer_snapshots in _group_snapshots_by_customer(ordered).items():
            first = customer_snapshots[0]
            if first.previous_as_of_month is not None:
                raise ValueError(
                    f"signal history for {customer_id} starts with a missing previous snapshot"
                )
            for previous, current in zip(customer_snapshots, customer_snapshots[1:], strict=False):
                if current.as_of_month != previous.as_of_month + 1:
                    raise ValueError(
                        f"signal history for {customer_id} must advance one month at a time"
                    )
                if current.previous_as_of_month != previous.as_of_month:
                    raise ValueError(
                        f"signal history for {customer_id} has an inconsistent previous snapshot link"
                    )
        object.__setattr__(self, "snapshots", ordered)

    def previous_snapshot(self, customer_id: str, as_of_month: int) -> SignalSnapshot | None:
        """Return only the immediately preceding snapshot for this customer."""

        expected_month = int(as_of_month) - 1
        for snapshot in self.snapshots:
            if snapshot.customer_id == str(customer_id) and snapshot.as_of_month == expected_month:
                return snapshot
        return None

    def append(self, snapshot: SignalSnapshot) -> "SignalSnapshotHistory":
        """Append a next-month snapshot, rejecting duplicate or gapped customer history."""

        previous = self.previous_snapshot(snapshot.customer_id, snapshot.as_of_month)
        existing_customer_months = [
            item.as_of_month for item in self.snapshots if item.customer_id == snapshot.customer_id
        ]
        if snapshot.as_of_month in existing_customer_months:
            raise ValueError("duplicate customer_id and as_of_month snapshot key")
        if existing_customer_months and previous is None:
            raise ValueError("signal history must append the next month for an existing customer")
        if previous is None and snapshot.previous_as_of_month is not None:
            raise ValueError("initial snapshot must not link to an absent previous snapshot")
        if previous is not None and snapshot.previous_as_of_month != previous.as_of_month:
            raise ValueError("snapshot previous_as_of_month must reference the immediately prior month")
        return SignalSnapshotHistory((*self.snapshots, snapshot))


def build_signal_snapshot(
    monthly_df: pd.DataFrame,
    *,
    customer_id: str,
    as_of_month: int,
    matches: pd.DataFrame,
    historical_cohort_risk_share: float,
    previous_snapshot: SignalSnapshot | None = None,
) -> SignalSnapshot:
    """Build one current-or-prior-only prospective snapshot.

    ``monthly_df`` is restricted to the target's rows at or before
    ``as_of_month`` before current status and financial factors are selected.
    The caller supplies a historical matched-cohort share instead of this
    module reading any outcome or evaluation data.
    """

    target_id = str(customer_id)
    current_row = _current_target_row(monthly_df, target_id, as_of_month)
    matched_count, neighbor_ids, match_distance_mean = _match_signals(matches, target_id)
    risk_share = _validate_share(historical_cohort_risk_share)
    _validate_previous_snapshot(previous_snapshot, target_id, as_of_month)

    factors = _financial_stress_factors(current_row)
    if previous_snapshot is None:
        return SignalSnapshot(
            customer_id=target_id,
            as_of_month=int(as_of_month),
            matched_count=matched_count,
            neighbor_ids=neighbor_ids,
            historical_cohort_risk_share=risk_share,
            historical_cohort_risk_share_delta=None,
            match_distance_mean=match_distance_mean,
            match_distance_mean_delta=None,
            neighbor_jaccard_similarity=None,
            current_status=str(current_row["monthly_status"]),
            current_status_transition="initial",
            financial_stress_factors=factors,
            persistent_financial_stress_factors=(),
            previous_as_of_month=None,
        )

    return SignalSnapshot(
        customer_id=target_id,
        as_of_month=int(as_of_month),
        matched_count=matched_count,
        neighbor_ids=neighbor_ids,
        historical_cohort_risk_share=risk_share,
        historical_cohort_risk_share_delta=risk_share - previous_snapshot.historical_cohort_risk_share,
        match_distance_mean=match_distance_mean,
        match_distance_mean_delta=match_distance_mean - previous_snapshot.match_distance_mean,
        neighbor_jaccard_similarity=_jaccard_similarity(neighbor_ids, previous_snapshot.neighbor_ids),
        current_status=str(current_row["monthly_status"]),
        current_status_transition=(
            f"{previous_snapshot.current_status}_to_{str(current_row['monthly_status'])}"
        ),
        financial_stress_factors=factors,
        persistent_financial_stress_factors=tuple(
            factor for factor in factors if factor in previous_snapshot.financial_stress_factors
        ),
        previous_as_of_month=previous_snapshot.as_of_month,
    )


def _current_target_row(monthly_df: pd.DataFrame, customer_id: str, as_of_month: int) -> pd.Series:
    missing_columns = sorted(set(CURRENT_SNAPSHOT_COLUMNS) - set(monthly_df.columns))
    if missing_columns:
        raise ValueError(f"monthly_df is missing required snapshot columns: {missing_columns}")
    if not isinstance(as_of_month, int) or isinstance(as_of_month, bool):
        raise TypeError("as_of_month must be an integer")

    observed_df = monthly_df.loc[
        (monthly_df["customer_id"].astype(str) == customer_id)
        & (monthly_df["month"] <= as_of_month),
        list(CURRENT_SNAPSHOT_COLUMNS),
    ].copy()
    if observed_df.duplicated(["customer_id", "month"]).any():
        raise ValueError("duplicate target customer_id and month rows are not allowed")
    current_rows = observed_df.loc[observed_df["month"] == as_of_month]
    if len(current_rows) != 1:
        raise ValueError("exactly one target row is required at as_of_month")
    return current_rows.iloc[0]


def _match_signals(matches: pd.DataFrame, target_customer_id: str) -> tuple[int, tuple[str, ...], float]:
    missing_columns = sorted(set(MATCH_REQUIRED_COLUMNS) - set(matches.columns))
    if missing_columns:
        raise ValueError(f"matches is missing required columns: {missing_columns}")
    target_ids = matches["target_customer_id"].astype(str)
    if matches.empty or not target_ids.eq(target_customer_id).all():
        raise ValueError("matches must contain at least one row for the requested target customer")
    neighbor_ids = tuple(matches["matched_customer_id"].astype(str))
    if target_customer_id in neighbor_ids:
        raise ValueError("matches must not include the target customer as a neighbor")
    if len(set(neighbor_ids)) != len(neighbor_ids):
        raise ValueError("matches must not contain duplicate neighbor customer IDs")
    distances = pd.to_numeric(matches["distance"], errors="raise").to_numpy(dtype=float)
    if not np.isfinite(distances).all() or (distances < 0).any():
        raise ValueError("match distances must be finite non-negative values")
    return len(neighbor_ids), tuple(sorted(neighbor_ids)), float(np.mean(distances))


def _validate_share(value: float) -> float:
    share = float(value)
    if not np.isfinite(share) or not 0.0 <= share <= 1.0:
        raise ValueError("historical_cohort_risk_share must be a finite value between 0 and 1")
    return share


def _validate_previous_snapshot(
    previous_snapshot: SignalSnapshot | None,
    customer_id: str,
    as_of_month: int,
) -> None:
    if previous_snapshot is None:
        return
    if previous_snapshot.customer_id != customer_id:
        raise ValueError("previous snapshot customer_id must match the current target")
    if previous_snapshot.as_of_month != as_of_month - 1:
        raise ValueError("previous snapshot must be from the immediately prior month")


def _financial_stress_factors(current_row: pd.Series) -> tuple[str, ...]:
    factors = []
    if float(current_row["savings_rate"]) < 0.05:
        factors.append("low_savings_rate")
    if float(current_row["dsr"]) >= 0.35:
        factors.append("elevated_dsr")
    if float(current_row["fixed_expense_ratio"]) >= 0.45:
        factors.append("high_fixed_expense_ratio")
    if float(current_row["cash_balance"]) < 0:
        factors.append("negative_cash_balance")
    if float(current_row["emergency_months"]) < 3:
        factors.append("low_emergency_months")
    if float(current_row["savings_amount"]) < 0:
        factors.append("negative_savings_amount")
    return tuple(factors)


def _jaccard_similarity(current_ids: Iterable[str], previous_ids: Iterable[str]) -> float | None:
    current_set = set(current_ids)
    previous_set = set(previous_ids)
    union = current_set | previous_set
    return None if not union else float(len(current_set & previous_set) / len(union))


def _group_snapshots_by_customer(
    snapshots: Iterable[SignalSnapshot],
) -> dict[str, list[SignalSnapshot]]:
    grouped: dict[str, list[SignalSnapshot]] = {}
    for snapshot in snapshots:
        grouped.setdefault(snapshot.customer_id, []).append(snapshot)
    return grouped
