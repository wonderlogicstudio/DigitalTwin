import numpy as np
import pandas as pd
import pytest

from config import settings
from src.data_generator import generate_dataset
from src.feature_engineering import build_trajectory_features
from src.matcher import MATCH_RESULT_COLUMNS, TrajectoryMatcher
from src.models import GeneratorConfig


@pytest.fixture(scope="module")
def features_df() -> pd.DataFrame:
    if settings.TRAJECTORY_FEATURES_PATH.exists():
        return pd.read_csv(settings.TRAJECTORY_FEATURES_PATH)

    _, monthly_df = generate_dataset(GeneratorConfig())
    return build_trajectory_features(monthly_df)


@pytest.fixture(scope="module")
def decorated_features_df(features_df: pd.DataFrame) -> pd.DataFrame:
    decorated = features_df.copy()
    decorated["persona"] = [
        settings.PERSONAS[index % len(settings.PERSONAS)] for index in range(len(decorated))
    ]
    decorated["final_outcome"] = [
        settings.FINAL_OUTCOMES[index % len(settings.FINAL_OUTCOMES)]
        for index in range(len(decorated))
    ]
    return decorated


@pytest.fixture(scope="module")
def matcher(decorated_features_df: pd.DataFrame) -> TrajectoryMatcher:
    return TrajectoryMatcher().fit(decorated_features_df)


@pytest.fixture(scope="module")
def target_customer_id(decorated_features_df: pd.DataFrame) -> str:
    return str(decorated_features_df.iloc[0]["customer_id"])


def test_match_excludes_target_customer(
    matcher: TrajectoryMatcher,
    target_customer_id: str,
) -> None:
    matches = matcher.match(target_customer_id)

    assert target_customer_id not in set(matches["matched_customer_id"])


def test_match_returns_exactly_200_rows(
    matcher: TrajectoryMatcher,
    target_customer_id: str,
) -> None:
    matches = matcher.match(target_customer_id)

    assert len(matches) == settings.TOP_K_MATCHES


def test_rank_starts_at_one_and_is_contiguous(
    matcher: TrajectoryMatcher,
    target_customer_id: str,
) -> None:
    matches = matcher.match(target_customer_id)

    assert matches["rank"].tolist() == list(range(1, settings.TOP_K_MATCHES + 1))


def test_distances_are_sorted_ascending(
    matcher: TrajectoryMatcher,
    target_customer_id: str,
) -> None:
    matches = matcher.match(target_customer_id)

    assert matches["distance"].is_monotonic_increasing


def test_similarity_score_range(
    matcher: TrajectoryMatcher,
    target_customer_id: str,
) -> None:
    matches = matcher.match(target_customer_id)

    assert (matches["similarity_score"] > 0).all()
    assert (matches["similarity_score"] <= 1).all()


def test_same_input_produces_same_result(
    decorated_features_df: pd.DataFrame,
    target_customer_id: str,
) -> None:
    first = TrajectoryMatcher().fit(decorated_features_df).match(target_customer_id)
    second = TrajectoryMatcher().fit(decorated_features_df).match(target_customer_id)

    pd.testing.assert_frame_equal(first, second)


def test_final_outcome_does_not_affect_matching(
    decorated_features_df: pd.DataFrame,
    target_customer_id: str,
) -> None:
    baseline = TrajectoryMatcher().fit(decorated_features_df).match(target_customer_id)
    mutated = decorated_features_df.copy()
    mutated["final_outcome"] = list(reversed(mutated["final_outcome"].tolist()))
    after_mutation = TrajectoryMatcher().fit(mutated).match(target_customer_id)

    pd.testing.assert_frame_equal(
        baseline.loc[:, MATCH_RESULT_COLUMNS],
        after_mutation.loc[:, MATCH_RESULT_COLUMNS],
    )


def test_persona_does_not_affect_matching(
    decorated_features_df: pd.DataFrame,
    target_customer_id: str,
) -> None:
    baseline = TrajectoryMatcher().fit(decorated_features_df).match(target_customer_id)
    mutated = decorated_features_df.copy()
    mutated["persona"] = list(reversed(mutated["persona"].tolist()))
    after_mutation = TrajectoryMatcher().fit(mutated).match(target_customer_id)

    pd.testing.assert_frame_equal(
        baseline.loc[:, MATCH_RESULT_COLUMNS],
        after_mutation.loc[:, MATCH_RESULT_COLUMNS],
    )


def test_known_nearest_customer_is_rank_one() -> None:
    rows = []
    customer_values = {
        "C000001": 0.0,
        "C000002": 0.1,
        "C000003": 4.0,
        "C000004": -5.0,
        "C000005": 10.0,
    }
    for customer_id, value in customer_values.items():
        row = {"customer_id": customer_id}
        row.update({feature: value for feature in settings.MATCH_FEATURES})
        rows.append(row)
    features_df = pd.DataFrame(rows)

    matches = TrajectoryMatcher().fit(features_df).match("C000001", top_k=1)

    assert matches.iloc[0]["matched_customer_id"] == "C000002"
    assert matches.iloc[0]["rank"] == 1


def test_unknown_customer_id_raises_error(matcher: TrajectoryMatcher) -> None:
    with pytest.raises(ValueError, match="Unknown customer_id"):
        matcher.match("C999999")


def test_match_before_fit_raises_runtime_error(target_customer_id: str) -> None:
    with pytest.raises(RuntimeError, match="fit"):
        TrajectoryMatcher().match(target_customer_id)


def test_top_k_larger_than_available_customers_raises_error(
    matcher: TrajectoryMatcher,
    target_customer_id: str,
) -> None:
    with pytest.raises(ValueError, match="top_k"):
        matcher.match(target_customer_id, top_k=settings.CUSTOMER_COUNT)


def test_missing_required_feature_column_raises_error(features_df: pd.DataFrame) -> None:
    broken = features_df.drop(columns=[settings.MATCH_FEATURES[0]])

    with pytest.raises(ValueError, match="Missing required feature columns"):
        TrajectoryMatcher().fit(broken)


def test_nan_or_inf_feature_raises_error(features_df: pd.DataFrame) -> None:
    broken = features_df.copy()
    broken.loc[0, settings.MATCH_FEATURES[0]] = np.inf

    with pytest.raises(ValueError, match="NaN or inf"):
        TrajectoryMatcher().fit(broken)
