"""Tests for deterministic, reference-only prospective cross-fit backtests."""

from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd
import pytest

import src.prospective_scoring as prospective_scoring
from src.crossfit_backtest import (
    CrossFitReconciliationError,
    build_deterministic_folds,
    reconcile_customer_month_keys,
    run_deterministic_crossfit_backtest,
)
from src.data_generator import generate_dataset
from src.models import GeneratorConfig
from src.prospective_evaluator import (
    build_reference_historical_share_provider,
    evaluate_completed_signals,
)
from src.prospective_scoring import (
    prepare_observed_scoring_data,
    score_reference_only_fold,
)


@pytest.fixture(scope="module")
def monthly_df() -> pd.DataFrame:
    _, generated_monthly = generate_dataset(GeneratorConfig(customer_count=30, random_seed=42))
    return generated_monthly


@pytest.fixture(scope="module")
def backtest_result(monthly_df: pd.DataFrame):
    return run_deterministic_crossfit_backtest(
        monthly_df,
        as_of_months=(12, 13),
        fold_count=3,
        top_k=5,
    )


class _ColumnTrackingLoc:
    def __init__(self, indexer, seen_columns: set[str]) -> None:
        self._indexer = indexer
        self._seen_columns = seen_columns

    def __getitem__(self, key):  # type: ignore[no-untyped-def]
        if isinstance(key, tuple) and len(key) > 1:
            selected_columns = key[1]
            if isinstance(selected_columns, str):
                self._seen_columns.add(selected_columns)
            elif isinstance(selected_columns, (list, tuple, pd.Index)):
                self._seen_columns.update(str(column) for column in selected_columns)
        return self._indexer[key]

    def __getattr__(self, name: str):
        return getattr(self._indexer, name)


class _LabelAccessSpyFrame(pd.DataFrame):
    _metadata = ["seen_columns"]

    @property
    def _constructor(self):  # type: ignore[override]
        return pd.DataFrame

    @property
    def loc(self):  # type: ignore[override]
        return _ColumnTrackingLoc(pd.DataFrame.loc.__get__(self, pd.DataFrame), self.seen_columns)


def test_deterministic_folds_are_disjoint_complete_and_excluded_from_scaler_fit(
    monkeypatch: pytest.MonkeyPatch,
    monthly_df: pd.DataFrame,
) -> None:
    customer_ids = tuple(sorted(monthly_df["customer_id"].astype(str).unique()))
    folds = build_deterministic_folds(customer_ids, fold_count=3)
    observed = prepare_observed_scoring_data(monthly_df, as_of_months=(12, 13))
    captured_reference_ids: list[set[str]] = []
    original_fit = prospective_scoring.ReferenceTrajectoryMatcher.fit

    def tracking_fit(self, reference_features_df: pd.DataFrame):  # type: ignore[no-untyped-def]
        captured_reference_ids.append(set(reference_features_df["customer_id"].astype(str)))
        return original_fit(self, reference_features_df)

    monkeypatch.setattr(prospective_scoring.ReferenceTrajectoryMatcher, "fit", tracking_fit)
    fold = folds[0]
    score_result = score_reference_only_fold(
        observed,
        fold_id=fold.fold_id,
        reference_customer_ids=fold.reference_customer_ids,
        evaluation_customer_ids=fold.evaluation_customer_ids,
        as_of_months=(12, 13),
        historical_share_provider=build_reference_historical_share_provider(
            monthly_df,
            reference_customer_ids=fold.reference_customer_ids,
        ),
        top_k=5,
    )

    evaluation_coverage = set().union(*(set(fold.evaluation_customer_ids) for fold in folds))
    assert evaluation_coverage == set(customer_ids)
    assert sum(len(fold.evaluation_customer_ids) for fold in folds) == len(customer_ids)
    assert all(
        not (set(fold.reference_customer_ids) & set(fold.evaluation_customer_ids))
        for fold in folds
    )
    assert len(captured_reference_ids) == 2
    assert all(reference_ids == set(fold.reference_customer_ids) for reference_ids in captured_reference_ids)
    assert all(not (reference_ids & set(fold.evaluation_customer_ids)) for reference_ids in captured_reference_ids)
    assert len(score_result.records) == len(fold.evaluation_customer_ids) * 2
    assert not score_result.failures


def test_scorer_has_no_label_access_while_evaluator_opens_labels(
    monthly_df: pd.DataFrame,
) -> None:
    spy = _LabelAccessSpyFrame(monthly_df.copy())
    spy.seen_columns = set()
    folds = build_deterministic_folds(tuple(spy["customer_id"].astype(str).unique()), fold_count=3)
    fold = folds[0]

    observed = prepare_observed_scoring_data(spy, as_of_months=(12,))
    score_result = score_reference_only_fold(
        observed,
        fold_id=fold.fold_id,
        reference_customer_ids=fold.reference_customer_ids,
        evaluation_customer_ids=fold.evaluation_customer_ids,
        as_of_months=(12,),
        historical_share_provider=lambda _month, _neighbors: 0.25,
        top_k=5,
    )
    scorer_source = Path(prospective_scoring.__file__).read_text(encoding="utf-8")
    scorer_imports = [
        alias.name
        for node in ast.walk(ast.parse(scorer_source))
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    ]

    assert {"final_outcome", "event_type", "persona"}.isdisjoint(observed.columns)
    assert {"final_outcome", "event_type", "persona"}.isdisjoint(spy.seen_columns)
    assert "final_outcome" not in scorer_source
    assert "persona" not in scorer_source
    assert not any("evaluator" in imported_module for imported_module in scorer_imports)

    spy.seen_columns.clear()
    evaluated = evaluate_completed_signals(spy, score_result.records)

    assert len(evaluated) == len(score_result.records)
    assert {"final_outcome", "event_type"} <= spy.seen_columns


def test_target_future_mutation_before_evaluator_does_not_change_its_snapshot(
    monthly_df: pd.DataFrame,
) -> None:
    customer_ids = tuple(sorted(monthly_df["customer_id"].astype(str).unique()))
    fold = build_deterministic_folds(customer_ids, fold_count=3)[0]
    target_customer_id = fold.evaluation_customer_ids[0]
    baseline = score_reference_only_fold(
        prepare_observed_scoring_data(monthly_df, as_of_months=(12,)),
        fold_id=fold.fold_id,
        reference_customer_ids=fold.reference_customer_ids,
        evaluation_customer_ids=fold.evaluation_customer_ids,
        as_of_months=(12,),
        historical_share_provider=build_reference_historical_share_provider(
            monthly_df,
            reference_customer_ids=fold.reference_customer_ids,
        ),
        top_k=5,
    )
    mutated = monthly_df.copy()
    future_target_mask = (
        mutated["customer_id"].astype(str).eq(target_customer_id) & mutated["month"].gt(12)
    )
    mutated.loc[future_target_mask, "final_outcome"] = "delinquent"
    mutated.loc[future_target_mask, "event_type"] = "medical_cost"
    mutated.loc[future_target_mask, "monthly_status"] = "delinquent"
    mutated.loc[future_target_mask, "persona"] = "overspending"
    after_mutation = score_reference_only_fold(
        prepare_observed_scoring_data(mutated, as_of_months=(12,)),
        fold_id=fold.fold_id,
        reference_customer_ids=fold.reference_customer_ids,
        evaluation_customer_ids=fold.evaluation_customer_ids,
        as_of_months=(12,),
        historical_share_provider=build_reference_historical_share_provider(
            mutated,
            reference_customer_ids=fold.reference_customer_ids,
        ),
        top_k=5,
    )

    baseline_snapshot = next(
        record.snapshot for record in baseline.records if record.snapshot.customer_id == target_customer_id
    )
    mutated_snapshot = next(
        record.snapshot
        for record in after_mutation.records
        if record.snapshot.customer_id == target_customer_id
    )
    assert mutated_snapshot == baseline_snapshot


def test_crossfit_manifest_reconciles_all_expected_customer_months(
    backtest_result,
) -> None:
    manifest = backtest_result.manifest

    assert manifest.schema_version == "prospective_crossfit_backtest.v1"
    assert manifest.customer_count == 30
    assert manifest.as_of_months == (12, 13)
    assert manifest.reconciliation.is_exact
    assert len(backtest_result.scored_records) == 60
    assert len(backtest_result.evaluation_records) == 60
    assert not backtest_result.failures
    assert all(fold.id_sets_disjoint for fold in manifest.folds)
    assert sum(fold.expected_customer_month_count for fold in manifest.folds) == 60
    assert sum(fold.processed_customer_month_count for fold in manifest.folds) == 60
    assert all(fold.failure_count == 0 for fold in manifest.folds)


def test_reconciliation_exposes_missing_and_duplicate_customer_months() -> None:
    reconciliation = reconcile_customer_month_keys(
        (("C000001", 12), ("C000002", 12)),
        (("C000001", 12), ("C000001", 12)),
    )

    assert not reconciliation.is_exact
    assert reconciliation.missing_keys == (("C000002", 12),)
    assert reconciliation.duplicate_processed_keys == (("C000001", 12),)


def test_rerun_is_deterministic_and_missing_signal_rows_are_not_silent(
    monthly_df: pd.DataFrame,
    backtest_result,
) -> None:
    rerun = run_deterministic_crossfit_backtest(
        monthly_df,
        as_of_months=(12, 13),
        fold_count=3,
        top_k=5,
    )
    missing_observation = monthly_df.loc[
        ~(
            monthly_df["customer_id"].astype(str).eq("C000001")
            & monthly_df["month"].eq(12)
        )
    ].copy()

    assert rerun.to_dict() == backtest_result.to_dict()
    with pytest.raises(CrossFitReconciliationError, match="reconciliation failed"):
        run_deterministic_crossfit_backtest(
            missing_observation,
            as_of_months=(12,),
            fold_count=3,
            top_k=5,
        )
