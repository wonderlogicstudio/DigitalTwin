"""Validation-only multi-seed and TOP_K sensitivity measurements.

The production generator, canonical seed-42 CSV/JSON artifacts, matcher
settings, and breakpoint logic remain unchanged.  Alternative seeds are built
in memory only; the supplied K values are passed only to validation matcher
calls and never written back to ``config.settings``.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from config import settings
from src.breakpoint_analyzer import find_breakpoint
from src.data_generator import generate_dataset
from src.demo_selector import build_final_outcome_lookup, summarize_matched_outcomes
from src.feature_engineering import build_trajectory_features
from src.matcher import TrajectoryMatcher
from src.models import GeneratorConfig


SENSITIVITY_SCHEMA_VERSION = "synthetic_sensitivity_validation.v1"
SENSITIVITY_VALIDATION_DIR = settings.BASE_DIR / "artifacts" / "validation" / "sensitivity"
SENSITIVITY_REPORT_FILENAME = "multi_seed_top_k_sensitivity_report.json"
DEFAULT_VALIDATION_SEEDS = (7, settings.RANDOM_SEED, 99)
DEFAULT_VALIDATION_TOP_K_GRID = (100, settings.TOP_K_MATCHES, 300)
DEFAULT_TARGET_SAMPLE_SIZE = 50
DEFAULT_TARGET_SELECTION_SEED = 1701


def run_multi_seed_top_k_sensitivity_validation(
    *,
    seeds: Sequence[int] = DEFAULT_VALIDATION_SEEDS,
    top_k_grid: Sequence[int] = DEFAULT_VALIDATION_TOP_K_GRID,
    target_sample_size: int = DEFAULT_TARGET_SAMPLE_SIZE,
    target_selection_seed: int = DEFAULT_TARGET_SELECTION_SEED,
    customer_count: int = settings.CUSTOMER_COUNT,
    canonical_input_paths: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    """Measure seed and neighborhood sensitivity without changing production.

    The target sample is selected from the common synthetic customer-ID domain
    with a fixed RNG. It does not use a target's future months, final outcome,
    persona, or any evaluator label. Historical final outcomes are used only
    after matching to summarize matched synthetic cohorts and form the
    retrospective breakpoint groups.
    """

    normalized_seeds = _normalize_seeds(seeds)
    normalized_top_k = _normalize_top_k_grid(top_k_grid, customer_count)
    _validate_target_sample_size(target_sample_size, customer_count)
    paths = _canonical_paths(canonical_input_paths)
    canonical_before = _capture_file_integrity(paths)
    target_ids = _select_target_ids(
        customer_count,
        target_sample_size,
        target_selection_seed,
    )

    run_records: list[dict[str, Any]] = []
    for seed in normalized_seeds:
        master_df, monthly_df = generate_dataset(
            GeneratorConfig(random_seed=seed, customer_count=customer_count)
        )
        features_df = build_trajectory_features(monthly_df)
        _validate_generated_seed_data(master_df, monthly_df, features_df, customer_count, seed)
        matcher = TrajectoryMatcher().fit(features_df)
        indexed_monthly_df = monthly_df.set_index("customer_id", drop=False)
        outcome_lookup = build_final_outcome_lookup(monthly_df)
        generated_data_fingerprint = _dataframe_fingerprint(monthly_df)
        population_outcome_counts = _sorted_counter(
            outcome_lookup.astype(str).tolist()
        )
        for top_k in normalized_top_k:
            target_records = _evaluate_seed_top_k_run(
                target_ids,
                top_k,
                matcher,
                indexed_monthly_df,
                outcome_lookup,
            )
            run_records.append(
                _build_run_record(
                    seed,
                    top_k,
                    customer_count,
                    generated_data_fingerprint,
                    population_outcome_counts,
                    target_records,
                )
            )

    canonical_after = _capture_file_integrity(paths)
    integrity_unchanged = canonical_before == canonical_after
    if not integrity_unchanged:
        raise RuntimeError("canonical input files changed during sensitivity validation")
    comparisons = _build_comparisons_to_canonical(run_records)
    return {
        "schema_version": SENSITIVITY_SCHEMA_VERSION,
        "validation_scope": "synthetic, retrospective, validation-only",
        "method": {
            "seed_execution": (
                "Each seed is generated in memory with the unchanged synthetic generator; "
                "no alternative-seed data is saved to canonical paths."
            ),
            "target_selection": (
                "A seeded sample from the common customer-ID domain only; no target future "
                "months, final_outcome, persona, or evaluator label is used."
            ),
            "matching": (
                "The unchanged observation-only feature builder, scaler, feature order, "
                "weights, and self-exclusion are reused. top_k is a validation argument only."
            ),
            "outcome_and_breakpoint": (
                "Historical matched synthetic cohort outcome shares and the unchanged "
                "retrospective breakpoint function are summarized. They are not prediction "
                "probabilities or future facts about target customers."
            ),
        },
        "settings_guard": {
            "production_random_seed": settings.RANDOM_SEED,
            "production_top_k_matches": settings.TOP_K_MATCHES,
            "production_settings_mutated": False,
            "validation_seeds": list(normalized_seeds),
            "validation_top_k_grid": list(normalized_top_k),
            "target_sample_size": len(target_ids),
            "target_selection_seed": int(target_selection_seed),
        },
        "canonical_input_integrity": {
            "before": canonical_before,
            "after": canonical_after,
            "unchanged": integrity_unchanged,
        },
        "run_records": run_records,
        "direction_and_variance": _build_direction_and_variance(run_records),
        "comparisons_to_seed42_k200": comparisons,
        "synthetic_limitations": [
            "All measured populations are synthetic outputs of the same generator family, not observed bank data.",
            "Cross-seed and K variation describes sensitivity within this PoC; it is not accuracy, calibration, causal, or intervention-efficacy evidence.",
            "Breakpoint factor and month comparisons are retrospective matched-cohort landmarks, not forecasts that target customers will reach those outcomes or months.",
            "The report does not select a favorable seed or K for production. Production seed=42 and TOP_K=200 remain unchanged.",
        ],
    }


def export_multi_seed_top_k_sensitivity_report(
    report: Mapping[str, Any],
    *,
    output_dir: Path = SENSITIVITY_VALIDATION_DIR,
    filename: str = SENSITIVITY_REPORT_FILENAME,
) -> Path:
    """Atomically write the validation report outside canonical artifact roots."""

    destination = Path(output_dir)
    _assert_separate_validation_output_dir(destination)
    if not str(filename).strip() or Path(filename).name != filename:
        raise ValueError("filename must be a non-empty file name")
    if report.get("schema_version") != SENSITIVITY_SCHEMA_VERSION:
        raise ValueError("unexpected sensitivity validation report schema version")
    destination.mkdir(parents=True, exist_ok=True)
    output_path = destination / filename
    _atomic_write_json(output_path, dict(report))
    return output_path


def _evaluate_seed_top_k_run(
    target_ids: tuple[str, ...],
    top_k: int,
    matcher: TrajectoryMatcher,
    indexed_monthly_df: pd.DataFrame,
    outcome_lookup: pd.Series,
) -> list[dict[str, Any]]:
    records = []
    for target_id in target_ids:
        matches = matcher.match(target_id, top_k=top_k)
        matched_ids = matches["matched_customer_id"].astype(str).tolist()
        matched_monthly_df = indexed_monthly_df.loc[matched_ids].reset_index(drop=True)
        outcome_summary = summarize_matched_outcomes(
            target_id,
            matched_ids,
            matched_monthly_df,
            outcome_lookup,
        )
        breakpoint = find_breakpoint(matched_ids, matched_monthly_df)
        records.append(
            {
                "target_customer_id": target_id,
                "matched_count": len(matched_ids),
                "distance_mean": float(matches["distance"].mean()),
                "distance_median": float(matches["distance"].median()),
                "historical_outcome_shares": {
                    outcome: float(outcome_summary["outcomes"][outcome]["ratio"])
                    for outcome in settings.FINAL_OUTCOMES
                },
                "breakpoint_status": str(breakpoint["status"]),
                "breakpoint_month": breakpoint["breakpoint_month"],
                "breakpoint_factor": breakpoint["primary_factor"],
            }
        )
    return records


def _build_run_record(
    seed: int,
    top_k: int,
    customer_count: int,
    generated_data_fingerprint: str,
    population_outcome_counts: Mapping[str, int],
    target_records: list[dict[str, Any]],
) -> dict[str, Any]:
    found_records = [record for record in target_records if record["breakpoint_status"] == "found"]
    return {
        "seed": int(seed),
        "top_k": int(top_k),
        "customer_count": int(customer_count),
        "target_count": len(target_records),
        "generated_data_fingerprint": generated_data_fingerprint,
        "population_historical_outcome_counts": dict(population_outcome_counts),
        "matched_distance": {
            "mean_of_target_means": _mean_or_none(
                [float(record["distance_mean"]) for record in target_records]
            ),
            "median_of_target_medians": _median_or_none(
                [float(record["distance_median"]) for record in target_records]
            ),
            "target_mean_distribution": _numeric_summary(
                [float(record["distance_mean"]) for record in target_records]
            ),
        },
        "historical_outcome_share_distribution": {
            outcome: _numeric_summary(
                [float(record["historical_outcome_shares"][outcome]) for record in target_records]
            )
            for outcome in settings.FINAL_OUTCOMES
        },
        "breakpoint": {
            "found_count": len(found_records),
            "found_rate": _rate_or_none(len(found_records), len(target_records)),
            "status_counts": _sorted_counter(
                str(record["breakpoint_status"]) for record in target_records
            ),
            "factor_distribution": _sorted_counter(
                str(record["breakpoint_factor"] or "none") for record in target_records
            ),
            "month_distribution": _sorted_counter(
                "none" if record["breakpoint_month"] is None else str(record["breakpoint_month"])
                for record in target_records
            ),
        },
        "target_records": target_records,
    }


def _build_comparisons_to_canonical(run_records: list[dict[str, Any]]) -> dict[str, Any]:
    baseline = next(
        (
            record
            for record in run_records
            if record["seed"] == settings.RANDOM_SEED and record["top_k"] == settings.TOP_K_MATCHES
        ),
        None,
    )
    if baseline is None:
        return {
            "baseline_available": False,
            "reason": "Validation grid does not contain seed=42 and top_k=200.",
            "comparisons": [],
        }
    baseline_by_target = {
        str(record["target_customer_id"]): record for record in baseline["target_records"]
    }
    comparisons = []
    for record in run_records:
        candidate_by_target = {
            str(target["target_customer_id"]): target for target in record["target_records"]
        }
        common_ids = tuple(sorted(set(baseline_by_target) & set(candidate_by_target)))
        pairs = [(baseline_by_target[customer_id], candidate_by_target[customer_id]) for customer_id in common_ids]
        both_found = [
            pair
            for pair in pairs
            if pair[0]["breakpoint_status"] == "found"
            and pair[1]["breakpoint_status"] == "found"
        ]
        comparisons.append(
            {
                "seed": record["seed"],
                "top_k": record["top_k"],
                "is_canonical_baseline": record is baseline,
                "common_target_count": len(pairs),
                "matched_distance_mean_delta": _difference_or_none(
                    record["matched_distance"]["mean_of_target_means"],
                    baseline["matched_distance"]["mean_of_target_means"],
                ),
                "historical_outcome_share_mean_deltas": {
                    outcome: _difference_or_none(
                        record["historical_outcome_share_distribution"][outcome]["mean"],
                        baseline["historical_outcome_share_distribution"][outcome]["mean"],
                    )
                    for outcome in settings.FINAL_OUTCOMES
                },
                "breakpoint_found_rate_delta": _difference_or_none(
                    record["breakpoint"]["found_rate"], baseline["breakpoint"]["found_rate"]
                ),
                "breakpoint_status_agreement_rate": _rate_or_none(
                    sum(left["breakpoint_status"] == right["breakpoint_status"] for left, right in pairs),
                    len(pairs),
                ),
                "both_found_count": len(both_found),
                "factor_agreement_rate_when_both_found": _rate_or_none(
                    sum(left["breakpoint_factor"] == right["breakpoint_factor"] for left, right in both_found),
                    len(both_found),
                ),
                "month_exact_agreement_rate_when_both_found": _rate_or_none(
                    sum(left["breakpoint_month"] == right["breakpoint_month"] for left, right in both_found),
                    len(both_found),
                ),
                "month_mean_absolute_difference_when_both_found": _mean_or_none(
                    [
                        abs(int(left["breakpoint_month"]) - int(right["breakpoint_month"]))
                        for left, right in both_found
                        if left["breakpoint_month"] is not None
                        and right["breakpoint_month"] is not None
                    ]
                ),
            }
        )
    return {"baseline_available": True, "baseline": {"seed": 42, "top_k": 200}, "comparisons": comparisons}


def _build_direction_and_variance(run_records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "run_count": len(run_records),
        "matched_distance_mean_of_target_means": _numeric_summary(
            [float(record["matched_distance"]["mean_of_target_means"]) for record in run_records]
        ),
        "breakpoint_found_rate": _numeric_summary(
            [float(record["breakpoint"]["found_rate"]) for record in run_records]
        ),
        "historical_outcome_share_means": {
            outcome: _numeric_summary(
                [
                    float(record["historical_outcome_share_distribution"][outcome]["mean"])
                    for record in run_records
                ]
            )
            for outcome in settings.FINAL_OUTCOMES
        },
        "interpretation": (
            "This records spread across the predefined seed and K grid. It does not select "
            "a favorable run or authorize a production setting change."
        ),
    }


def _normalize_seeds(seeds: Sequence[int]) -> tuple[int, ...]:
    normalized = tuple(int(seed) for seed in seeds)
    if not normalized:
        raise ValueError("seeds must be non-empty")
    if len(set(normalized)) != len(normalized):
        raise ValueError("seeds must not contain duplicates")
    return normalized


def _normalize_top_k_grid(top_k_grid: Sequence[int], customer_count: int) -> tuple[int, ...]:
    normalized = tuple(int(top_k) for top_k in top_k_grid)
    if not normalized:
        raise ValueError("top_k_grid must be non-empty")
    if len(set(normalized)) != len(normalized):
        raise ValueError("top_k_grid must not contain duplicates")
    if any(top_k <= 0 or top_k >= customer_count for top_k in normalized):
        raise ValueError("each validation top_k must be between 1 and customer_count - 1")
    return normalized


def _validate_target_sample_size(target_sample_size: int, customer_count: int) -> None:
    if target_sample_size <= 0 or target_sample_size > customer_count:
        raise ValueError("target_sample_size must be between 1 and customer_count")


def _select_target_ids(
    customer_count: int,
    target_sample_size: int,
    target_selection_seed: int,
) -> tuple[str, ...]:
    customer_ids = np.asarray(
        [f"C{customer_number:06d}" for customer_number in range(1, customer_count + 1)],
        dtype=object,
    )
    rng = np.random.default_rng(target_selection_seed)
    selected = rng.choice(customer_ids, size=target_sample_size, replace=False)
    return tuple(sorted(str(customer_id) for customer_id in selected))


def _validate_generated_seed_data(
    master_df: pd.DataFrame,
    monthly_df: pd.DataFrame,
    features_df: pd.DataFrame,
    customer_count: int,
    seed: int,
) -> None:
    if len(master_df) != customer_count or len(features_df) != customer_count:
        raise ValueError("generated seed data does not have the requested customer count")
    if len(monthly_df) != customer_count * settings.TOTAL_MONTHS:
        raise ValueError("generated seed data does not have the expected monthly row count")
    if set(master_df["random_seed"].astype(int)) != {seed}:
        raise ValueError("generated seed data does not retain the requested seed")
    monthly_counts = monthly_df.groupby("customer_id")["month"].nunique()
    if not monthly_counts.eq(settings.TOTAL_MONTHS).all():
        raise ValueError("generated seed data must have all months for every customer")
    if set(features_df["customer_id"].astype(str)) != set(master_df["customer_id"].astype(str)):
        raise ValueError("feature customer IDs do not reconcile with generated seed data")


def _canonical_paths(paths: Mapping[str, Path] | None) -> dict[str, Path]:
    default_paths = {
        "customer_master": settings.CUSTOMER_MASTER_PATH,
        "customer_monthly": settings.CUSTOMER_MONTHLY_PATH,
        "trajectory_features": settings.TRAJECTORY_FEATURES_PATH,
    }
    normalized = {key: Path(value) for key, value in (paths or default_paths).items()}
    if set(normalized) != set(default_paths):
        raise ValueError(f"canonical_input_paths must contain exactly {sorted(default_paths)}")
    missing = [str(path) for path in normalized.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"canonical input paths are missing: {missing}")
    return normalized


def _capture_file_integrity(paths: Mapping[str, Path]) -> dict[str, dict[str, str | int]]:
    return {
        key: {
            "path": str(path.resolve()),
            "bytes": int(path.stat().st_size),
            "sha256": _sha256_file(path),
        }
        for key, path in sorted(paths.items())
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1_048_576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dataframe_fingerprint(dataframe: pd.DataFrame) -> str:
    hashed_rows = pd.util.hash_pandas_object(dataframe, index=False).to_numpy(dtype=np.uint64)
    return hashlib.sha256(hashed_rows.tobytes()).hexdigest()


def _assert_separate_validation_output_dir(output_dir: Path) -> None:
    resolved_output = output_dir.resolve()
    canonical_dirs = (
        settings.DATA_RAW_DIR,
        settings.DATA_PROCESSED_DIR,
        settings.DATA_DEMO_DIR,
        settings.REPORTS_DIR,
    )
    for canonical_dir in canonical_dirs:
        try:
            resolved_output.relative_to(canonical_dir.resolve())
        except ValueError:
            continue
        raise ValueError("sensitivity validation artifacts must be outside canonical analytics directories")


def _numeric_summary(values: Iterable[float]) -> dict[str, float | int | None]:
    numeric_values = [float(value) for value in values]
    if not numeric_values:
        return {"count": 0, "min": None, "mean": None, "median": None, "max": None, "std": None}
    series = pd.Series(numeric_values, dtype=float)
    return {
        "count": int(len(series)),
        "min": float(series.min()),
        "mean": float(series.mean()),
        "median": float(series.median()),
        "max": float(series.max()),
        "std": float(series.std(ddof=0)),
    }


def _sorted_counter(values: Iterable[str]) -> dict[str, int]:
    counter = Counter(str(value) for value in values)
    return {key: int(counter[key]) for key in sorted(counter)}


def _mean_or_none(values: Iterable[float]) -> float | None:
    numeric_values = [float(value) for value in values]
    return None if not numeric_values else float(np.mean(numeric_values))


def _median_or_none(values: Iterable[float]) -> float | None:
    numeric_values = [float(value) for value in values]
    return None if not numeric_values else float(np.median(numeric_values))


def _difference_or_none(left: float | None, right: float | None) -> float | None:
    return None if left is None or right is None else float(left - right)


def _rate_or_none(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else float(numerator / denominator)


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary_path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary_path.replace(path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
