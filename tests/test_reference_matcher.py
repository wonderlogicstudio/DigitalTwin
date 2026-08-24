"""Tests for reference-only prospective trajectory matching."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.preprocessing import StandardScaler

import src.reference_matcher as reference_matcher
from config import settings
from src.as_of_features import AS_OF_REQUIRED_COLUMNS, build_as_of_trajectory_features
from src.data_generator import generate_dataset
from src.matcher import MATCH_RESULT_COLUMNS, TrajectoryMatcher
from src.models import GeneratorConfig
from src.reference_matcher import ReferenceTrajectoryMatcher


@pytest.fixture(scope="module")
def monthly_df() -> pd.DataFrame:
    _, generated_monthly = generate_dataset(GeneratorConfig(customer_count=60, random_seed=42))
    return generated_monthly


@pytest.fixture(scope="module")
def as_of_features(monthly_df: pd.DataFrame) -> pd.DataFrame:
    return build_as_of_trajectory_features(monthly_df, 12)


@pytest.fixture
def reference_and_target(as_of_features: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    return as_of_features.iloc[1:].copy(), as_of_features.iloc[[0]].copy()


def test_scaler_fit_receives_reference_features_only(
    monkeypatch: pytest.MonkeyPatch,
    reference_and_target: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    reference_df, target_df = reference_and_target

    class TrackingScaler(StandardScaler):
        fit_inputs: list[np.ndarray] = []

        def fit(self, X, y=None, sample_weight=None):  # noqa: N803
            type(self).fit_inputs.append(np.asarray(X, dtype=float).copy())
            return super().fit(X, y=y, sample_weight=sample_weight)

    monkeypatch.setattr(reference_matcher, "StandardScaler", TrackingScaler)
    matcher = reference_matcher.ReferenceTrajectoryMatcher().fit(reference_df)
    expected_reference_matrix = reference_df.loc[:, settings.MATCH_FEATURES].to_numpy(dtype=float)

    assert len(TrackingScaler.fit_inputs) == 1
    np.testing.assert_array_equal(TrackingScaler.fit_inputs[0], expected_reference_matrix)
    matcher.match(target_df, top_k=5)
    assert len(TrackingScaler.fit_inputs) == 1


def test_target_id_in_reference_is_rejected(as_of_features: pd.DataFrame) -> None:
    matcher = ReferenceTrajectoryMatcher().fit(as_of_features)

    with pytest.raises(ValueError, match="must not be present"):
        matcher.match(as_of_features.iloc[[0]], top_k=5)


def test_returned_neighbors_use_existing_consumer_contract(
    reference_and_target: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    reference_df, target_df = reference_and_target
    matcher = ReferenceTrajectoryMatcher().fit(reference_df)

    matches = matcher.match(target_df, top_k=5)

    assert list(matches.columns) == list(MATCH_RESULT_COLUMNS)
    assert len(matches) == 5
    assert matches["target_customer_id"].eq(target_df.iloc[0]["customer_id"]).all()
    assert set(matches["matched_customer_id"]) <= set(reference_df["customer_id"])
    assert target_df.iloc[0]["customer_id"] not in set(matches["matched_customer_id"])
    assert matches["rank"].tolist() == [1, 2, 3, 4, 5]
    assert matches["distance"].is_monotonic_increasing


def test_neighbors_are_deterministic(
    reference_and_target: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    reference_df, target_df = reference_and_target

    first = ReferenceTrajectoryMatcher().fit(reference_df).match(target_df, top_k=8)
    second = ReferenceTrajectoryMatcher().fit(reference_df).match(target_df, top_k=8)

    pd.testing.assert_frame_equal(first, second)


def test_future_mutation_does_not_affect_as_of_reference_or_target_matching(
    monthly_df: pd.DataFrame,
) -> None:
    baseline_features = build_as_of_trajectory_features(monthly_df, 12)
    mutated_monthly = monthly_df.copy()
    future_mask = mutated_monthly["month"] > 12
    for column in AS_OF_REQUIRED_COLUMNS:
        if column not in {"customer_id", "month"}:
            mutated_monthly.loc[future_mask, column] = 999_999_999
    mutated_monthly.loc[future_mask, "persona"] = "overspending"
    mutated_monthly.loc[future_mask, "final_outcome"] = "delinquent"
    mutated_features = build_as_of_trajectory_features(mutated_monthly, 12)

    baseline = ReferenceTrajectoryMatcher().fit(baseline_features.iloc[1:]).match(
        baseline_features.iloc[[0]], top_k=5
    )
    after_mutation = ReferenceTrajectoryMatcher().fit(mutated_features.iloc[1:]).match(
        mutated_features.iloc[[0]], top_k=5
    )

    pd.testing.assert_frame_equal(after_mutation, baseline)


def test_persona_and_final_outcome_columns_do_not_affect_matching(
    reference_and_target: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    reference_df, target_df = reference_and_target
    decorated_reference = reference_df.assign(persona="stable", final_outcome="healthy")
    decorated_target = target_df.assign(persona="overspending", final_outcome="delinquent")
    baseline = ReferenceTrajectoryMatcher().fit(decorated_reference).match(
        decorated_target,
        top_k=5,
    )
    mutated_reference = decorated_reference.copy()
    mutated_target = decorated_target.copy()
    mutated_reference["persona"] = "event_shock"
    mutated_reference["final_outcome"] = "stress"
    mutated_target["persona"] = "recovery"
    mutated_target["final_outcome"] = "healthy"

    after_mutation = ReferenceTrajectoryMatcher().fit(mutated_reference).match(
        mutated_target,
        top_k=5,
    )

    pd.testing.assert_frame_equal(after_mutation, baseline)


def test_legacy_matcher_remains_available_for_legacy_self_exclusion(
    as_of_features: pd.DataFrame,
) -> None:
    legacy_matches = TrajectoryMatcher().fit(as_of_features).match(
        str(as_of_features.iloc[0]["customer_id"]),
        top_k=5,
    )

    assert len(legacy_matches) == 5
    assert as_of_features.iloc[0]["customer_id"] not in set(legacy_matches["matched_customer_id"])
