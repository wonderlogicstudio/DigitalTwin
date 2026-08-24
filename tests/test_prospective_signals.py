"""Tests for prospective, current-and-prior-only signal snapshots."""

from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path

import pandas as pd
import pytest

import src.prospective_signals as prospective_signals
from src.as_of_features import AS_OF_REQUIRED_COLUMNS, build_as_of_trajectory_features
from src.data_generator import generate_dataset
from src.models import GeneratorConfig
from src.prospective_signals import (
    SIGNAL_DEFINITIONS,
    SignalSnapshot,
    SignalSnapshotHistory,
    build_signal_snapshot,
)
from src.reference_matcher import ReferenceTrajectoryMatcher


@pytest.fixture(scope="module")
def monthly_df() -> pd.DataFrame:
    _, generated_monthly = generate_dataset(GeneratorConfig(customer_count=60, random_seed=42))
    return generated_monthly


def _matches_for_as_of_month(monthly_df: pd.DataFrame, as_of_month: int) -> tuple[str, pd.DataFrame]:
    features = build_as_of_trajectory_features(monthly_df, as_of_month)
    target = features.iloc[[0]].copy()
    reference = features.iloc[1:].copy()
    matches = ReferenceTrajectoryMatcher().fit(reference).match(target, top_k=5)
    return str(target.iloc[0]["customer_id"]), matches


def _snapshot_for_as_of_month(
    monthly_df: pd.DataFrame,
    as_of_month: int,
    historical_cohort_risk_share: float,
    previous_snapshot: SignalSnapshot | None = None,
) -> SignalSnapshot:
    customer_id, matches = _matches_for_as_of_month(monthly_df, as_of_month)
    return build_signal_snapshot(
        monthly_df,
        customer_id=customer_id,
        as_of_month=as_of_month,
        matches=matches,
        historical_cohort_risk_share=historical_cohort_risk_share,
        previous_snapshot=previous_snapshot,
    )


def test_signal_snapshot_schema_is_serializable_and_has_no_composite_score(
    monthly_df: pd.DataFrame,
) -> None:
    snapshot = _snapshot_for_as_of_month(monthly_df, 12, historical_cohort_risk_share=0.30)

    serialized = snapshot.to_dict()

    assert isinstance(snapshot, SignalSnapshot)
    assert list(serialized) == [field.name for field in fields(SignalSnapshot)]
    assert serialized["matched_count"] == 5
    assert serialized["historical_cohort_risk_share"] == pytest.approx(0.30)
    assert serialized["historical_cohort_risk_share_delta"] is None
    assert serialized["neighbor_jaccard_similarity"] is None
    assert serialized["current_status_transition"] == "initial"
    assert not any("score" in name.lower() for name in serialized)
    assert set(SIGNAL_DEFINITIONS) == {
        "historical_cohort_risk_share",
        "historical_cohort_risk_share_delta",
        "match_distance_mean",
        "match_distance_mean_delta",
        "neighbor_jaccard_similarity",
        "current_status_transition",
        "financial_stress_factors",
        "persistent_financial_stress_factors",
    }
    assert all({"direction", "unit", "description"} <= set(item) for item in SIGNAL_DEFINITIONS.values())
    assert "probability" not in " ".join(str(item) for item in SIGNAL_DEFINITIONS.values()).lower()


def test_snapshot_does_not_access_final_outcome_or_persona(
    monthly_df: pd.DataFrame,
) -> None:
    class LabelAccessSpyFrame(pd.DataFrame):
        @property
        def _constructor(self):  # type: ignore[override]
            return LabelAccessSpyFrame

        def __getitem__(self, key):  # type: ignore[no-untyped-def]
            requested = {key} if isinstance(key, str) else set(key)
            forbidden = {"final_outcome", "persona"}
            if requested & forbidden:
                raise AssertionError("prospective snapshot attempted to access a label field")
            return super().__getitem__(key)

    customer_id, matches = _matches_for_as_of_month(monthly_df, 12)
    label_spy = LabelAccessSpyFrame(monthly_df.copy())

    snapshot = build_signal_snapshot(
        label_spy,
        customer_id=customer_id,
        as_of_month=12,
        matches=matches,
        historical_cohort_risk_share=0.30,
    )
    source_tree = ast.parse(Path(prospective_signals.__file__).read_text(encoding="utf-8"))
    imported_modules = [
        alias.name
        for node in ast.walk(source_tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    ]

    assert snapshot.customer_id == customer_id
    assert not any("evaluator" in module for module in imported_modules)


def test_sequential_history_calculates_deltas_stability_and_persistence(
    monthly_df: pd.DataFrame,
) -> None:
    month_12 = _snapshot_for_as_of_month(monthly_df, 12, historical_cohort_risk_share=0.30)
    month_13 = _snapshot_for_as_of_month(
        monthly_df,
        13,
        historical_cohort_risk_share=0.35,
        previous_snapshot=month_12,
    )
    history = SignalSnapshotHistory().append(month_12).append(month_13)

    expected_jaccard = len(set(month_12.neighbor_ids) & set(month_13.neighbor_ids)) / len(
        set(month_12.neighbor_ids) | set(month_13.neighbor_ids)
    )

    assert [snapshot.as_of_month for snapshot in history.snapshots] == [12, 13]
    assert history.previous_snapshot(month_13.customer_id, 13) == month_12
    assert month_13.previous_as_of_month == 12
    assert month_13.historical_cohort_risk_share_delta == pytest.approx(0.05)
    assert month_13.match_distance_mean_delta == pytest.approx(
        month_13.match_distance_mean - month_12.match_distance_mean
    )
    assert month_13.neighbor_jaccard_similarity == pytest.approx(expected_jaccard)
    assert month_13.current_status_transition == (
        f"{month_12.current_status}_to_{month_13.current_status}"
    )
    assert set(month_13.persistent_financial_stress_factors) <= set(
        month_12.financial_stress_factors
    )
    assert set(month_13.persistent_financial_stress_factors) <= set(
        month_13.financial_stress_factors
    )


def test_history_rejects_duplicate_customer_month_and_month_gaps(
    monthly_df: pd.DataFrame,
) -> None:
    month_12 = _snapshot_for_as_of_month(monthly_df, 12, historical_cohort_risk_share=0.30)
    month_13 = _snapshot_for_as_of_month(
        monthly_df,
        13,
        historical_cohort_risk_share=0.35,
        previous_snapshot=month_12,
    )
    history = SignalSnapshotHistory().append(month_12)

    with pytest.raises(ValueError, match="duplicate customer_id"):
        history.append(month_12)
    with pytest.raises(ValueError, match="next month"):
        SignalSnapshotHistory().append(month_12).append(
            SignalSnapshot(
                **{
                    **month_13.to_dict(),
                    "as_of_month": 14,
                    "previous_as_of_month": 13,
                }
            )
        )
    with pytest.raises(ValueError, match="missing previous snapshot"):
        SignalSnapshotHistory((month_13,))

    duplicated_current_row = monthly_df.loc[
        (monthly_df["customer_id"].astype(str) == month_12.customer_id)
        & (monthly_df["month"] == 12)
    ]
    malformed_monthly = pd.concat([monthly_df, duplicated_current_row], ignore_index=True)
    _, matches = _matches_for_as_of_month(monthly_df, 12)
    with pytest.raises(ValueError, match="duplicate target customer_id"):
        build_signal_snapshot(
            malformed_monthly,
            customer_id=month_12.customer_id,
            as_of_month=12,
            matches=matches,
            historical_cohort_risk_share=0.30,
        )


def test_future_mutation_does_not_change_current_or_prior_snapshot(
    monthly_df: pd.DataFrame,
) -> None:
    baseline = _snapshot_for_as_of_month(monthly_df, 12, historical_cohort_risk_share=0.30)
    mutated = monthly_df.copy()
    future_mask = mutated["month"] > 12
    for column in AS_OF_REQUIRED_COLUMNS:
        if column not in {"customer_id", "month"}:
            mutated.loc[future_mask, column] = 999_999_999
    mutated.loc[future_mask, "monthly_status"] = "mutated_future_status"
    mutated.loc[future_mask, "persona"] = "mutated_future_persona"
    mutated.loc[future_mask, "final_outcome"] = "mutated_future_outcome"

    after_future_mutation = _snapshot_for_as_of_month(
        mutated,
        12,
        historical_cohort_risk_share=0.30,
    )

    assert after_future_mutation == baseline


def test_snapshot_and_history_are_deterministic(monthly_df: pd.DataFrame) -> None:
    first_12 = _snapshot_for_as_of_month(monthly_df, 12, historical_cohort_risk_share=0.30)
    first_13 = _snapshot_for_as_of_month(
        monthly_df,
        13,
        historical_cohort_risk_share=0.35,
        previous_snapshot=first_12,
    )
    second_12 = _snapshot_for_as_of_month(monthly_df, 12, historical_cohort_risk_share=0.30)
    second_13 = _snapshot_for_as_of_month(
        monthly_df,
        13,
        historical_cohort_risk_share=0.35,
        previous_snapshot=second_12,
    )

    assert first_12 == second_12
    assert first_13 == second_13
    assert SignalSnapshotHistory((first_13, first_12)) == SignalSnapshotHistory((second_12, second_13))
