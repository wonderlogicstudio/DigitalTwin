"""Tests for separate, reconciling population artifacts."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pandas as pd
import pytest

from config import settings
from src.data_generator import generate_dataset
from src.feature_engineering import build_trajectory_features
from src.matcher import TrajectoryMatcher
from src.models import GeneratorConfig
from src.population_artifacts import (
    DETAIL_SCHEMA_VERSION,
    POPULATION_DETAIL_COLUMNS,
    build_population_summary,
    export_population_artifacts,
    load_population_artifacts,
)
from src.population_batch import PopulationBatchResult, analyze_population_batch


@pytest.fixture(scope="module")
def small_batch() -> tuple[list[str], PopulationBatchResult]:
    _, monthly_df = generate_dataset(GeneratorConfig(customer_count=12, random_seed=42))
    features_df = build_trajectory_features(monthly_df)
    matcher = TrajectoryMatcher().fit(features_df)
    customer_ids = features_df["customer_id"].astype(str).tolist()
    return customer_ids, analyze_population_batch(
        customer_ids, monthly_df, features_df, matcher, top_k=5
    )


def test_population_artifacts_roundtrip_and_reconcile_summary(
    tmp_path: Path,
    small_batch: tuple[list[str], PopulationBatchResult],
) -> None:
    customer_ids, batch = small_batch
    paths = export_population_artifacts(
        batch,
        customer_ids,
        run_id="population-test-001",
        output_dir=tmp_path / "population",
        created_at="2026-08-23T00:00:00+00:00",
        code_ref="test-head",
    )

    loaded = load_population_artifacts(paths.detail_csv.parent)
    assert list(loaded["detail_csv"].columns) == list(POPULATION_DETAIL_COLUMNS)
    assert len(loaded["detail_csv"]) == len(batch.results)
    assert loaded["detail_json"]["schema_version"] == DETAIL_SCHEMA_VERSION
    assert [row["customer_id"] for row in loaded["detail_json"]["results"]] == [
        result.customer_id for result in batch.results
    ]
    assert loaded["summary"] == build_population_summary(batch, run_id="population-test-001")
    assert loaded["summary"]["total_count"] == loaded["summary"]["processed_count"] == 12
    assert loaded["summary"]["succeeded_count"] + loaded["summary"]["failed_count"] == 12
    assert loaded["manifest"]["counters"]["processed"] == 12
    assert loaded["manifest"]["reconciliation"] == {
        "expected_id_count": 12,
        "output_id_count": 12,
        "missing_ids": [],
        "unexpected_ids": [],
        "duplicate_output_ids": [],
        "expected_ids_sha256": loaded["manifest"]["reconciliation"]["expected_ids_sha256"],
        "output_ids_sha256": loaded["manifest"]["reconciliation"]["output_ids_sha256"],
    }
    assert not list(paths.detail_csv.parent.glob("*.tmp"))


def test_manifest_is_equal_after_excluding_dynamic_fields(
    tmp_path: Path,
    small_batch: tuple[list[str], PopulationBatchResult],
) -> None:
    customer_ids, batch = small_batch
    first = export_population_artifacts(
        batch,
        customer_ids,
        run_id="deterministic-run",
        output_dir=tmp_path / "first",
        created_at="2026-08-23T00:00:00+00:00",
        code_ref="test-head",
    )
    second = export_population_artifacts(
        batch,
        customer_ids,
        run_id="deterministic-run",
        output_dir=tmp_path / "second",
        created_at="2026-08-24T00:00:00+00:00",
        code_ref="test-head",
    )
    first_manifest = deepcopy(load_population_artifacts(first.detail_csv.parent)["manifest"])
    second_manifest = deepcopy(load_population_artifacts(second.detail_csv.parent)["manifest"])
    for manifest in (first_manifest, second_manifest):
        manifest.pop("created_at")
        manifest.pop("output_paths")

    assert first_manifest == second_manifest


def test_export_rejects_reconciliation_mismatch_and_canonical_output_dir(
    tmp_path: Path,
    small_batch: tuple[list[str], PopulationBatchResult],
) -> None:
    customer_ids, batch = small_batch

    with pytest.raises(ValueError, match="reconciliation failed"):
        export_population_artifacts(
            batch,
            customer_ids[:-1],
            run_id="bad-reconciliation",
            output_dir=tmp_path / "rejected",
        )
    assert not (tmp_path / "rejected").exists()
    with pytest.raises(ValueError, match="outside canonical analytics"):
        export_population_artifacts(
            batch,
            customer_ids,
            run_id="canonical-path",
            output_dir=settings.DATA_DEMO_DIR,
        )


def test_loader_rejects_partial_or_corrupt_artifacts(
    tmp_path: Path,
    small_batch: tuple[list[str], PopulationBatchResult],
) -> None:
    customer_ids, batch = small_batch
    partial_dir = tmp_path / "partial"
    partial_dir.mkdir()
    (partial_dir / "population_detail.csv").write_text("customer_id\nC000001\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="Incomplete population artifact set"):
        load_population_artifacts(partial_dir)

    paths = export_population_artifacts(
        batch,
        customer_ids,
        run_id="corrupt-json",
        output_dir=tmp_path / "corrupt",
        created_at="2026-08-23T00:00:00+00:00",
        code_ref="test-head",
    )
    paths.detail_json.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON artifact"):
        load_population_artifacts(paths.detail_csv.parent)


def test_loader_rejects_summary_detail_counter_mismatch(
    tmp_path: Path,
    small_batch: tuple[list[str], PopulationBatchResult],
) -> None:
    customer_ids, batch = small_batch
    paths = export_population_artifacts(
        batch,
        customer_ids,
        run_id="counter-mismatch",
        output_dir=tmp_path / "counter-mismatch",
        created_at="2026-08-23T00:00:00+00:00",
        code_ref="test-head",
    )
    summary = json.loads(paths.summary_json.read_text(encoding="utf-8"))
    summary["failed_count"] += 1
    paths.summary_json.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(ValueError, match="summary counters do not reconcile"):
        load_population_artifacts(paths.detail_csv.parent)
