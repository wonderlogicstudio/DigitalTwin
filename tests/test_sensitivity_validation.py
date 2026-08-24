"""Tests for validation-only multi-seed and TOP_K sensitivity reports."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from config import settings
from src.sensitivity_validation import (
    SENSITIVITY_SCHEMA_VERSION,
    export_multi_seed_top_k_sensitivity_report,
    run_multi_seed_top_k_sensitivity_validation,
)


def _temporary_canonical_paths(tmp_path: Path) -> dict[str, Path]:
    paths = {
        "customer_master": tmp_path / "canonical" / "customer_master.csv",
        "customer_monthly": tmp_path / "canonical" / "customer_monthly_5000.csv",
        "trajectory_features": tmp_path / "canonical" / "trajectory_features.csv",
    }
    for index, path in enumerate(paths.values(), start=1):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"canonical-input-{index}\n", encoding="utf-8")
    return paths


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_multi_seed_runs_are_isolated_and_reproducible(tmp_path: Path) -> None:
    canonical_paths = _temporary_canonical_paths(tmp_path)
    kwargs = {
        "seeds": (11, 29),
        "top_k_grid": (20, 30),
        "target_sample_size": 6,
        "target_selection_seed": 77,
        "customer_count": 80,
        "canonical_input_paths": canonical_paths,
    }

    first = run_multi_seed_top_k_sensitivity_validation(**kwargs)
    second = run_multi_seed_top_k_sensitivity_validation(**kwargs)

    assert first == second
    assert first["schema_version"] == SENSITIVITY_SCHEMA_VERSION
    assert first["canonical_input_integrity"]["unchanged"] is True
    assert len(first["run_records"]) == 4
    assert {(record["seed"], record["top_k"]) for record in first["run_records"]} == {
        (11, 20),
        (11, 30),
        (29, 20),
        (29, 30),
    }
    fingerprints = {
        record["seed"]: record["generated_data_fingerprint"]
        for record in first["run_records"]
        if record["top_k"] == 20
    }
    assert fingerprints[11] != fingerprints[29]


def test_canonical_input_checksum_and_settings_are_unchanged(tmp_path: Path) -> None:
    canonical_paths = _temporary_canonical_paths(tmp_path)
    before = {key: _sha256(path) for key, path in canonical_paths.items()}
    production_seed = settings.RANDOM_SEED
    production_top_k = settings.TOP_K_MATCHES

    report = run_multi_seed_top_k_sensitivity_validation(
        seeds=(42,),
        top_k_grid=(20, 30),
        target_sample_size=5,
        customer_count=80,
        canonical_input_paths=canonical_paths,
    )

    after = {key: _sha256(path) for key, path in canonical_paths.items()}
    assert after == before
    assert report["canonical_input_integrity"]["unchanged"] is True
    assert settings.RANDOM_SEED == production_seed == 42
    assert settings.TOP_K_MATCHES == production_top_k == 200
    assert report["settings_guard"]["production_settings_mutated"] is False
    assert report["settings_guard"]["validation_top_k_grid"] == [20, 30]


def test_export_is_atomic_and_rejects_canonical_output_paths(tmp_path: Path) -> None:
    report = run_multi_seed_top_k_sensitivity_validation(
        seeds=(42,),
        top_k_grid=(20,),
        target_sample_size=4,
        customer_count=80,
        canonical_input_paths=_temporary_canonical_paths(tmp_path),
    )

    output_path = export_multi_seed_top_k_sensitivity_report(
        report,
        output_dir=tmp_path / "validation" / "sensitivity",
    )
    assert output_path.exists()
    assert not list(output_path.parent.glob("*.tmp"))
    with pytest.raises(ValueError, match="outside canonical analytics"):
        export_multi_seed_top_k_sensitivity_report(report, output_dir=settings.DATA_PROCESSED_DIR)


def test_production_modules_do_not_import_sensitivity_validation() -> None:
    source_dir = Path(__file__).resolve().parents[1] / "src"
    for source_path in source_dir.glob("*.py"):
        if source_path.name == "sensitivity_validation.py":
            continue
        assert "sensitivity_validation" not in source_path.read_text(encoding="utf-8")
