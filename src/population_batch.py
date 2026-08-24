"""Deterministic batch execution for population customer analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

import pandas as pd

from config import settings
from src.matcher import TrajectoryMatcher
from src.population_result import (
    PopulationCustomerResult,
    build_population_customer_result,
    failed_population_customer_result,
)


PopulationResultBuilder = Callable[..., PopulationCustomerResult]


@dataclass(frozen=True)
class PopulationBatchResult:
    """Complete, deterministic result set for the supplied feature population."""

    expected_count: int
    processed_count: int
    succeeded_count: int
    partial_failure_count: int
    hard_failure_count: int
    failed_count: int
    results: tuple[PopulationCustomerResult, ...]
    failure_results: tuple[PopulationCustomerResult, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable batch summary and ordered customer results."""

        return {
            "expected_count": self.expected_count,
            "processed_count": self.processed_count,
            "succeeded_count": self.succeeded_count,
            "partial_failure_count": self.partial_failure_count,
            "hard_failure_count": self.hard_failure_count,
            "failed_count": self.failed_count,
            "results": [result.to_dict() for result in self.results],
            "failure_results": [result.to_dict() for result in self.failure_results],
        }


def analyze_population_batch(
    customer_ids: Iterable[str],
    monthly_df: pd.DataFrame,
    features_df: pd.DataFrame,
    matcher: TrajectoryMatcher,
    *,
    top_k: int = settings.TOP_K_MATCHES,
    result_builder: PopulationResultBuilder = build_population_customer_result,
) -> PopulationBatchResult:
    """Analyze exactly the feature-table customer set in stable customer-ID order.

    The supplied matcher is reused as fitted; this service never refits or
    changes matching rules. A result-builder exception is isolated to its
    customer and converted into an explicit failed result.
    """

    ordered_customer_ids = _validate_exact_customer_ids(customer_ids, features_df)
    results: list[PopulationCustomerResult] = []
    for customer_id in ordered_customer_ids:
        try:
            result = result_builder(
                customer_id,
                monthly_df,
                features_df,
                matcher,
                top_k=top_k,
            )
        except Exception as exc:  # noqa: BLE001
            result = failed_population_customer_result(customer_id, "batch_exception", str(exc))
        if result.customer_id != customer_id:
            result = failed_population_customer_result(
                customer_id,
                "result_contract",
                f"result customer_id did not match requested customer_id: {result.customer_id}",
            )
        elif result.analysis_status not in {"success", "partial_failure", "failed"}:
            result = failed_population_customer_result(
                customer_id,
                "result_contract",
                f"unknown analysis_status: {result.analysis_status}",
            )
        results.append(result)

    failure_results = tuple(result for result in results if result.analysis_status != "success")
    partial_failure_count = sum(
        result.analysis_status == "partial_failure" for result in results
    )
    hard_failure_count = sum(result.analysis_status == "failed" for result in results)
    return PopulationBatchResult(
        expected_count=len(ordered_customer_ids),
        processed_count=len(results),
        succeeded_count=sum(result.analysis_status == "success" for result in results),
        partial_failure_count=partial_failure_count,
        hard_failure_count=hard_failure_count,
        failed_count=len(failure_results),
        results=tuple(results),
        failure_results=failure_results,
    )


def _validate_exact_customer_ids(
    customer_ids: Iterable[str],
    features_df: pd.DataFrame,
) -> tuple[str, ...]:
    if "customer_id" not in features_df.columns:
        raise ValueError("features_df must include customer_id")

    requested = [str(customer_id) for customer_id in customer_ids]
    seen: set[str] = set()
    duplicate_id_set: set[str] = set()
    for customer_id in requested:
        if customer_id in seen:
            duplicate_id_set.add(customer_id)
        seen.add(customer_id)
    duplicate_ids = sorted(duplicate_id_set)
    if duplicate_ids:
        raise ValueError(f"duplicate customer_ids are not allowed: {duplicate_ids}")

    expected_ids = features_df["customer_id"].astype(str).tolist()
    if len(expected_ids) != len(set(expected_ids)):
        raise ValueError("features_df customer_id values must be unique")

    expected_set = set(expected_ids)
    requested_set = set(requested)
    missing_ids = sorted(expected_set - requested_set)
    unexpected_ids = sorted(requested_set - expected_set)
    if missing_ids or unexpected_ids:
        raise ValueError(
            "customer_ids must exactly match features_df customer_id values; "
            f"missing={missing_ids}; unexpected={unexpected_ids}"
        )
    return tuple(sorted(requested_set))
