"""Deterministic cross-fit orchestration for prospective-signal backtests."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd

from config import settings
from src.prospective_evaluator import (
    EvaluatedSignalRecord,
    build_reference_historical_share_provider,
    evaluate_completed_signals,
)
from src.prospective_scoring import (
    FoldScoringResult,
    ScoredSignalRecord,
    ScoringFailure,
    normalize_as_of_months,
    prepare_observed_scoring_data,
    score_reference_only_fold,
)


CROSSFIT_BACKTEST_SCHEMA_VERSION = "prospective_crossfit_backtest.v1"


@dataclass(frozen=True)
class DeterministicFold:
    """One disjoint reference/evaluation split."""

    fold_id: int
    reference_customer_ids: tuple[str, ...]
    evaluation_customer_ids: tuple[str, ...]


@dataclass(frozen=True)
class CustomerMonthReconciliation:
    """Exact expected-versus-processed accounting for signal rows."""

    expected_keys: tuple[tuple[str, int], ...]
    processed_keys: tuple[tuple[str, int], ...]
    missing_keys: tuple[tuple[str, int], ...]
    unexpected_keys: tuple[tuple[str, int], ...]
    duplicate_processed_keys: tuple[tuple[str, int], ...]

    @property
    def is_exact(self) -> bool:
        return not (
            self.missing_keys or self.unexpected_keys or self.duplicate_processed_keys
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "expected_count": len(self.expected_keys),
            "processed_count": len(self.processed_keys),
            "missing_count": len(self.missing_keys),
            "unexpected_count": len(self.unexpected_keys),
            "duplicate_processed_count": len(self.duplicate_processed_keys),
            "is_exact": self.is_exact,
            "missing_keys": [list(key) for key in self.missing_keys],
            "unexpected_keys": [list(key) for key in self.unexpected_keys],
            "duplicate_processed_keys": [list(key) for key in self.duplicate_processed_keys],
        }


@dataclass(frozen=True)
class FoldManifest:
    """A fold's deterministic membership, disjointness, and row counts."""

    fold_id: int
    reference_customer_ids: tuple[str, ...]
    evaluation_customer_ids: tuple[str, ...]
    reference_count: int
    evaluation_count: int
    id_sets_disjoint: bool
    expected_customer_month_count: int
    processed_customer_month_count: int
    failure_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "fold_id": self.fold_id,
            "reference_customer_ids": list(self.reference_customer_ids),
            "evaluation_customer_ids": list(self.evaluation_customer_ids),
            "reference_count": self.reference_count,
            "evaluation_count": self.evaluation_count,
            "id_sets_disjoint": self.id_sets_disjoint,
            "expected_customer_month_count": self.expected_customer_month_count,
            "processed_customer_month_count": self.processed_customer_month_count,
            "failure_count": self.failure_count,
        }


@dataclass(frozen=True)
class CrossFitBacktestManifest:
    """Serializable manifest for one deterministic cross-fit execution."""

    schema_version: str
    as_of_months: tuple[int, ...]
    fold_count: int
    customer_count: int
    folds: tuple[FoldManifest, ...]
    reconciliation: CustomerMonthReconciliation

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "as_of_months": list(self.as_of_months),
            "fold_count": self.fold_count,
            "customer_count": self.customer_count,
            "folds": [fold.to_dict() for fold in self.folds],
            "reconciliation": self.reconciliation.to_dict(),
        }


@dataclass(frozen=True)
class CrossFitBacktestResult:
    """Completed score snapshots plus evaluator-only retrospective records."""

    manifest: CrossFitBacktestManifest
    scored_records: tuple[ScoredSignalRecord, ...]
    evaluation_records: tuple[EvaluatedSignalRecord, ...]
    failures: tuple[ScoringFailure, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest": self.manifest.to_dict(),
            "scored_records": [record.to_dict() for record in self.scored_records],
            "evaluation_records": [record.to_dict() for record in self.evaluation_records],
            "failures": [failure.to_dict() for failure in self.failures],
        }


class CrossFitReconciliationError(RuntimeError):
    """Raised before evaluation if a target customer-month was not scored exactly once."""


def build_deterministic_folds(
    customer_ids: Sequence[str],
    *,
    fold_count: int = 5,
) -> tuple[DeterministicFold, ...]:
    """Round-robin sorted IDs into deterministic, complete evaluation folds."""

    normalized_ids = _normalize_customer_ids(customer_ids)
    if isinstance(fold_count, bool) or not isinstance(fold_count, int):
        raise TypeError("fold_count must be an integer")
    if fold_count < 2 or fold_count > len(normalized_ids):
        raise ValueError("fold_count must be at least 2 and no greater than customer count")
    evaluations = [tuple(normalized_ids[index::fold_count]) for index in range(fold_count)]
    folds = []
    for fold_id, evaluation_ids in enumerate(evaluations):
        evaluation_set = set(evaluation_ids)
        reference_ids = tuple(customer_id for customer_id in normalized_ids if customer_id not in evaluation_set)
        folds.append(
            DeterministicFold(
                fold_id=fold_id,
                reference_customer_ids=reference_ids,
                evaluation_customer_ids=evaluation_ids,
            )
        )
    return tuple(folds)


def reconcile_customer_month_keys(
    expected_keys: Sequence[tuple[str, int]],
    processed_keys: Sequence[tuple[str, int]],
) -> CustomerMonthReconciliation:
    """Expose missing, unexpected, and duplicate customer-month results."""

    expected = tuple(sorted((str(customer_id), int(month)) for customer_id, month in expected_keys))
    processed = tuple(sorted((str(customer_id), int(month)) for customer_id, month in processed_keys))
    if len(expected) != len(set(expected)):
        raise ValueError("expected customer-month keys must be unique")
    processed_set = set(processed)
    duplicates = tuple(sorted({key for key in processed if processed.count(key) > 1}))
    return CustomerMonthReconciliation(
        expected_keys=expected,
        processed_keys=processed,
        missing_keys=tuple(sorted(set(expected) - processed_set)),
        unexpected_keys=tuple(sorted(processed_set - set(expected))),
        duplicate_processed_keys=duplicates,
    )


def run_deterministic_crossfit_backtest(
    monthly_df: pd.DataFrame,
    *,
    customer_ids: Sequence[str] | None = None,
    as_of_months: Sequence[int] = (12,),
    fold_count: int = 5,
    top_k: int = settings.TOP_K_MATCHES,
) -> CrossFitBacktestResult:
    """Score each customer only against its fold's reference cohort, then evaluate.

    Reference historical shares are prepared from reference customers only.
    Target labels and future events are opened only after all score snapshots
    reconcile exactly with their expected customer-month key set.
    """

    normalized_months = normalize_as_of_months(as_of_months)
    observed_scoring_data = prepare_observed_scoring_data(
        monthly_df,
        as_of_months=normalized_months,
    )
    available_customer_ids = tuple(sorted(observed_scoring_data["customer_id"].astype(str).unique()))
    selected_customer_ids = (
        available_customer_ids if customer_ids is None else _normalize_customer_ids(customer_ids)
    )
    missing_ids = sorted(set(selected_customer_ids) - set(available_customer_ids))
    if missing_ids:
        raise ValueError(f"selected customer IDs are not present in observed data: {missing_ids[:5]}")
    folds = build_deterministic_folds(selected_customer_ids, fold_count=fold_count)

    fold_results: list[FoldScoringResult] = []
    for fold in folds:
        historical_share_provider = build_reference_historical_share_provider(
            monthly_df,
            reference_customer_ids=fold.reference_customer_ids,
        )
        fold_results.append(
            score_reference_only_fold(
                observed_scoring_data,
                fold_id=fold.fold_id,
                reference_customer_ids=fold.reference_customer_ids,
                evaluation_customer_ids=fold.evaluation_customer_ids,
                as_of_months=normalized_months,
                historical_share_provider=historical_share_provider,
                top_k=top_k,
            )
        )

    scored_records = tuple(record for result in fold_results for record in result.records)
    failures = tuple(failure for result in fold_results for failure in result.failures)
    expected_keys = tuple(
        (customer_id, as_of_month)
        for customer_id in selected_customer_ids
        for as_of_month in normalized_months
    )
    reconciliation = reconcile_customer_month_keys(
        expected_keys,
        tuple(record.key for record in scored_records),
    )
    manifest = CrossFitBacktestManifest(
        schema_version=CROSSFIT_BACKTEST_SCHEMA_VERSION,
        as_of_months=normalized_months,
        fold_count=len(folds),
        customer_count=len(selected_customer_ids),
        folds=tuple(
            FoldManifest(
                fold_id=fold.fold_id,
                reference_customer_ids=fold.reference_customer_ids,
                evaluation_customer_ids=fold.evaluation_customer_ids,
                reference_count=len(fold.reference_customer_ids),
                evaluation_count=len(fold.evaluation_customer_ids),
                id_sets_disjoint=not (
                    set(fold.reference_customer_ids) & set(fold.evaluation_customer_ids)
                ),
                expected_customer_month_count=len(fold_result.expected_keys),
                processed_customer_month_count=len(fold_result.processed_keys),
                failure_count=len(fold_result.failures),
            )
            for fold, fold_result in zip(folds, fold_results, strict=True)
        ),
        reconciliation=reconciliation,
    )
    if failures or not reconciliation.is_exact:
        raise CrossFitReconciliationError(
            "cross-fit scoring reconciliation failed; "
            f"missing={len(reconciliation.missing_keys)}, "
            f"unexpected={len(reconciliation.unexpected_keys)}, "
            f"duplicates={len(reconciliation.duplicate_processed_keys)}, "
            f"failures={len(failures)}"
        )

    evaluation_records = evaluate_completed_signals(monthly_df, scored_records)
    evaluation_reconciliation = reconcile_customer_month_keys(
        expected_keys,
        tuple(record.key for record in evaluation_records),
    )
    if not evaluation_reconciliation.is_exact:
        raise CrossFitReconciliationError("evaluator customer-month reconciliation failed")
    return CrossFitBacktestResult(
        manifest=manifest,
        scored_records=scored_records,
        evaluation_records=evaluation_records,
        failures=failures,
    )


def _normalize_customer_ids(customer_ids: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(str(customer_id) for customer_id in customer_ids)
    if not normalized:
        raise ValueError("customer_ids must not be empty")
    if len(normalized) != len(set(normalized)):
        raise ValueError("customer_ids must not contain duplicates")
    return tuple(sorted(normalized))
