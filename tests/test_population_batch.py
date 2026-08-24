"""Tests for deterministic, complete population batch analysis."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from src.data_generator import generate_dataset
from src.feature_engineering import build_trajectory_features
from src.matcher import TrajectoryMatcher
from src.models import GeneratorConfig
from src.population_batch import analyze_population_batch
from src.population_result import build_population_customer_result


@pytest.fixture(scope="module")
def batch_inputs() -> tuple[list[str], pd.DataFrame, pd.DataFrame, TrajectoryMatcher]:
    _, monthly_df = generate_dataset(GeneratorConfig(customer_count=12, random_seed=42))
    features_df = build_trajectory_features(monthly_df)
    matcher = TrajectoryMatcher().fit(features_df)
    customer_ids = features_df["customer_id"].astype(str).tolist()
    return customer_ids, monthly_df, features_df, matcher


def test_small_batch_processes_the_exact_customer_set_in_deterministic_order(
    batch_inputs: tuple[list[str], pd.DataFrame, pd.DataFrame, TrajectoryMatcher],
) -> None:
    customer_ids, monthly_df, features_df, matcher = batch_inputs

    first = analyze_population_batch(
        list(reversed(customer_ids)), monthly_df, features_df, matcher, top_k=5
    )
    second = analyze_population_batch(customer_ids, monthly_df, features_df, matcher, top_k=5)

    expected_ids = sorted(customer_ids)
    assert [result.customer_id for result in first.results] == expected_ids
    assert [result.customer_id for result in second.results] == expected_ids
    assert first == second
    assert first.expected_count == first.processed_count == len(expected_ids)
    assert first.succeeded_count + first.failed_count == first.processed_count
    assert first.failed_count == len(first.failure_results)


def test_batch_rejects_duplicate_or_nonexact_customer_input(
    batch_inputs: tuple[list[str], pd.DataFrame, pd.DataFrame, TrajectoryMatcher],
) -> None:
    customer_ids, monthly_df, features_df, matcher = batch_inputs

    with pytest.raises(ValueError, match="duplicate customer_ids"):
        analyze_population_batch(
            [*customer_ids, customer_ids[0]], monthly_df, features_df, matcher, top_k=5
        )
    with pytest.raises(ValueError, match="must exactly match"):
        analyze_population_batch(customer_ids[:-1], monthly_df, features_df, matcher, top_k=5)
    with pytest.raises(ValueError, match="must exactly match"):
        analyze_population_batch(
            [*customer_ids[:-1], "C999999"], monthly_df, features_df, matcher, top_k=5
        )


def test_batch_isolates_hard_and_partial_customer_failures(
    batch_inputs: tuple[list[str], pd.DataFrame, pd.DataFrame, TrajectoryMatcher],
) -> None:
    customer_ids, monthly_df, features_df, matcher = batch_inputs
    hard_failure_id = customer_ids[2]
    partial_failure_id = customer_ids[5]

    def controlled_builder(customer_id: str, *args: object, **kwargs: object):
        if customer_id == hard_failure_id:
            raise RuntimeError("simulated batch failure")
        result = build_population_customer_result(customer_id, *args, **kwargs)
        if customer_id == partial_failure_id:
            return replace(
                result,
                analysis_status="partial_failure",
                error_category="whatif",
                error_message="whatif: simulated failure",
            )
        return result

    batch = analyze_population_batch(
        customer_ids,
        monthly_df,
        features_df,
        matcher,
        top_k=5,
        result_builder=controlled_builder,
    )

    assert batch.expected_count == batch.processed_count == len(customer_ids)
    assert batch.succeeded_count == len(customer_ids) - 2
    assert batch.partial_failure_count == 1
    assert batch.hard_failure_count == 1
    assert batch.failed_count == 2
    assert [result.customer_id for result in batch.failure_results] == sorted(
        [hard_failure_id, partial_failure_id]
    )
    failures_by_id = {result.customer_id: result for result in batch.failure_results}
    assert failures_by_id[hard_failure_id].analysis_status == "failed"
    assert failures_by_id[hard_failure_id].error_category == "batch_exception"
    assert failures_by_id[partial_failure_id].analysis_status == "partial_failure"
