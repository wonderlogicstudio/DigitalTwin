"""Atomic, separate artifact export for population batch analysis."""

from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from config import settings
from src.population_batch import PopulationBatchResult
from src.population_result import PopulationCustomerResult


POPULATION_ARTIFACT_DIR = settings.BASE_DIR / "artifacts" / "population"
DETAIL_SCHEMA_VERSION = "population_detail.v1"
SUMMARY_SCHEMA_VERSION = "population_summary.v1"
MANIFEST_SCHEMA_VERSION = "population_manifest.v1"

DETAIL_CSV_FILENAME = "population_detail.csv"
DETAIL_JSON_FILENAME = "population_detail.json"
SUMMARY_FILENAME = "population_summary.json"
MANIFEST_FILENAME = "population_manifest.json"

POPULATION_DETAIL_COLUMNS = (
    "schema_version",
    "customer_id",
    "matched_count",
    "distance_min",
    "distance_mean",
    "distance_median",
    "distance_max",
    "outcome_share_healthy",
    "outcome_share_recovered",
    "outcome_share_stress",
    "outcome_share_delinquent",
    "breakpoint_status",
    "breakpoint_month",
    "breakpoint_factor",
    "breakpoint_risk_group_count",
    "breakpoint_avoidance_group_count",
    "breakpoint_persistence_months",
    "analysis_status",
    "error_category",
    "error_message",
)


@dataclass(frozen=True)
class PopulationArtifactPaths:
    """Paths created by one population artifact export."""

    detail_csv: Path
    detail_json: Path
    summary_json: Path
    manifest_json: Path

    def to_dict(self) -> dict[str, str]:
        return {
            "detail_csv": str(self.detail_csv),
            "detail_json": str(self.detail_json),
            "summary_json": str(self.summary_json),
            "manifest_json": str(self.manifest_json),
        }


def export_population_artifacts(
    batch_result: PopulationBatchResult,
    expected_customer_ids: Iterable[str],
    *,
    run_id: str,
    output_dir: Path = POPULATION_ARTIFACT_DIR,
    created_at: str | None = None,
    code_ref: str | None = None,
    settings_snapshot: Mapping[str, Any] | None = None,
) -> PopulationArtifactPaths:
    """Write validated population detail, summary, and manifest artifacts.

    Export refuses non-reconciling results before creating the output directory.
    Each artifact file uses a write-then-replace operation, and the target
    directory is deliberately kept outside the canonical analytics paths.
    """

    if not str(run_id).strip():
        raise ValueError("run_id must be non-empty")

    destination = Path(output_dir)
    _assert_separate_output_dir(destination)
    expected_ids = _unique_ids(expected_customer_ids, label="expected_customer_ids")
    reconciliation = _validate_batch_reconciliation(batch_result, expected_ids)
    snapshot = dict(settings_snapshot or _default_settings_snapshot())
    if "random_seed" not in snapshot:
        raise ValueError("settings_snapshot must include random_seed")

    paths = PopulationArtifactPaths(
        detail_csv=destination / DETAIL_CSV_FILENAME,
        detail_json=destination / DETAIL_JSON_FILENAME,
        summary_json=destination / SUMMARY_FILENAME,
        manifest_json=destination / MANIFEST_FILENAME,
    )
    detail_records = [result.to_dict() for result in batch_result.results]
    detail_frame = _detail_frame(batch_result.results)
    summary = build_population_summary(batch_result, run_id=str(run_id))
    timestamp = created_at or datetime.now(timezone.utc).isoformat()
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": str(run_id),
        "created_at": timestamp,
        "code_ref": code_ref if code_ref is not None else _resolve_code_ref(),
        "seed": snapshot["random_seed"],
        "settings_snapshot": snapshot,
        "counters": {
            "expected": batch_result.expected_count,
            "processed": batch_result.processed_count,
            "succeeded": batch_result.succeeded_count,
            "partial_failure": batch_result.partial_failure_count,
            "hard_failure": batch_result.hard_failure_count,
            "failed": batch_result.failed_count,
        },
        "output_paths": paths.to_dict(),
        "reconciliation": reconciliation,
    }
    detail_payload = {
        "schema_version": DETAIL_SCHEMA_VERSION,
        "run_id": str(run_id),
        "results": detail_records,
    }

    destination.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(paths.detail_csv, detail_frame.to_csv(index=False))
    _atomic_write_json(paths.detail_json, detail_payload)
    _atomic_write_json(paths.summary_json, summary)
    _atomic_write_json(paths.manifest_json, manifest)
    return paths


def build_population_summary(batch_result: PopulationBatchResult, *, run_id: str) -> dict[str, Any]:
    """Aggregate all processed results, including partial and failed customers."""

    results = batch_result.results
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "run_id": str(run_id),
        "total_count": batch_result.expected_count,
        "processed_count": batch_result.processed_count,
        "succeeded_count": batch_result.succeeded_count,
        "partial_failure_count": batch_result.partial_failure_count,
        "hard_failure_count": batch_result.hard_failure_count,
        "failed_count": batch_result.failed_count,
        "analysis_status_counts": _sorted_counter(result.analysis_status for result in results),
        "breakpoint_status_counts": _sorted_counter(result.breakpoint_status for result in results),
        "matched_count_distribution": _sorted_counter(str(result.matched_count) for result in results),
        "matched_count_summary": _numeric_summary([float(result.matched_count) for result in results]),
        "outcome_share_distributions": {
            outcome: _numeric_summary(
                [float(result.historical_outcome_shares.get(outcome, 0.0)) for result in results]
            )
            for outcome in settings.FINAL_OUTCOMES
        },
        "breakpoint_month_distribution": _sorted_counter(
            "none" if result.breakpoint_month is None else str(result.breakpoint_month)
            for result in results
        ),
        "breakpoint_factor_distribution": _sorted_counter(
            result.breakpoint_factor or "none" for result in results
        ),
    }


def load_population_artifacts(output_dir: Path) -> dict[str, Any]:
    """Load and validate a complete population artifact set."""

    paths = PopulationArtifactPaths(
        detail_csv=Path(output_dir) / DETAIL_CSV_FILENAME,
        detail_json=Path(output_dir) / DETAIL_JSON_FILENAME,
        summary_json=Path(output_dir) / SUMMARY_FILENAME,
        manifest_json=Path(output_dir) / MANIFEST_FILENAME,
    )
    missing_paths = [path for path in paths.to_dict().values() if not Path(path).exists()]
    if missing_paths:
        raise FileNotFoundError(f"Incomplete population artifact set: {missing_paths}")

    detail_frame = pd.read_csv(paths.detail_csv)
    if list(detail_frame.columns) != list(POPULATION_DETAIL_COLUMNS):
        raise ValueError("Unexpected population detail CSV schema")
    detail = _read_json(paths.detail_json)
    summary = _read_json(paths.summary_json)
    manifest = _read_json(paths.manifest_json)
    if detail.get("schema_version") != DETAIL_SCHEMA_VERSION:
        raise ValueError("Unexpected population detail JSON schema version")
    if summary.get("schema_version") != SUMMARY_SCHEMA_VERSION:
        raise ValueError("Unexpected population summary schema version")
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError("Unexpected population manifest schema version")
    if not isinstance(detail.get("results"), list):
        raise ValueError("Population detail JSON must include a results list")
    if len(detail_frame) != len(detail["results"]):
        raise ValueError("Population detail CSV and JSON row counts do not match")
    detail_records = detail["results"]
    if not all(isinstance(record, dict) and "customer_id" in record for record in detail_records):
        raise ValueError("Population detail JSON records must include customer_id")
    detail_ids = [str(record["customer_id"]) for record in detail_records]
    csv_ids = detail_frame["customer_id"].astype(str).tolist()
    if csv_ids != detail_ids:
        raise ValueError("Population detail CSV and JSON customer IDs do not match")
    if _duplicates(detail_ids):
        raise ValueError("Population detail contains duplicate customer IDs")

    status_counts = _sorted_counter(str(record.get("analysis_status", "")) for record in detail_records)
    partial_failure_count = status_counts.get("partial_failure", 0)
    hard_failure_count = status_counts.get("failed", 0)
    expected_summary_counts = {
        "total_count": len(detail_records),
        "processed_count": len(detail_records),
        "succeeded_count": status_counts.get("success", 0),
        "partial_failure_count": partial_failure_count,
        "hard_failure_count": hard_failure_count,
        "failed_count": partial_failure_count + hard_failure_count,
        "analysis_status_counts": status_counts,
    }
    if any(summary.get(key) != value for key, value in expected_summary_counts.items()):
        raise ValueError("Population summary counters do not reconcile with detail")

    manifest_counts = manifest.get("counters")
    if not isinstance(manifest_counts, dict) or manifest_counts != {
        "expected": expected_summary_counts["total_count"],
        "processed": expected_summary_counts["processed_count"],
        "succeeded": expected_summary_counts["succeeded_count"],
        "partial_failure": expected_summary_counts["partial_failure_count"],
        "hard_failure": expected_summary_counts["hard_failure_count"],
        "failed": expected_summary_counts["failed_count"],
    }:
        raise ValueError("Population manifest counters do not reconcile with detail")
    reconciliation = manifest.get("reconciliation")
    if not isinstance(reconciliation, dict) or (
        reconciliation.get("expected_id_count") != len(detail_ids)
        or reconciliation.get("output_id_count") != len(detail_ids)
        or reconciliation.get("missing_ids") != []
        or reconciliation.get("unexpected_ids") != []
        or reconciliation.get("duplicate_output_ids") != []
        or reconciliation.get("expected_ids_sha256") != _id_digest(detail_ids)
        or reconciliation.get("output_ids_sha256") != _id_digest(detail_ids)
    ):
        raise ValueError("Population manifest reconciliation does not match detail")
    return {
        "paths": paths,
        "detail_csv": detail_frame,
        "detail_json": detail,
        "summary": summary,
        "manifest": manifest,
    }


def _detail_frame(results: Iterable[PopulationCustomerResult]) -> pd.DataFrame:
    rows = []
    for result in results:
        rows.append(
            {
                "schema_version": DETAIL_SCHEMA_VERSION,
                "customer_id": result.customer_id,
                "matched_count": result.matched_count,
                "distance_min": result.distance_summary.get("min"),
                "distance_mean": result.distance_summary.get("mean"),
                "distance_median": result.distance_summary.get("median"),
                "distance_max": result.distance_summary.get("max"),
                **{
                    f"outcome_share_{outcome}": result.historical_outcome_shares.get(outcome, 0.0)
                    for outcome in settings.FINAL_OUTCOMES
                },
                "breakpoint_status": result.breakpoint_status,
                "breakpoint_month": result.breakpoint_month,
                "breakpoint_factor": result.breakpoint_factor,
                "breakpoint_risk_group_count": result.breakpoint_support.get("risk_group_count", 0),
                "breakpoint_avoidance_group_count": result.breakpoint_support.get(
                    "avoidance_group_count", 0
                ),
                "breakpoint_persistence_months": result.breakpoint_support.get(
                    "persistence_months", 0
                ),
                "analysis_status": result.analysis_status,
                "error_category": result.error_category,
                "error_message": result.error_message,
            }
        )
    return pd.DataFrame(rows, columns=POPULATION_DETAIL_COLUMNS)


def _validate_batch_reconciliation(
    batch_result: PopulationBatchResult,
    expected_ids: tuple[str, ...],
) -> dict[str, Any]:
    result_ids = [result.customer_id for result in batch_result.results]
    duplicate_output_ids = _duplicates(result_ids)
    expected_set = set(expected_ids)
    output_set = set(result_ids)
    missing_ids = sorted(expected_set - output_set)
    unexpected_ids = sorted(output_set - expected_set)

    statuses = [result.analysis_status for result in batch_result.results]
    partial_count = statuses.count("partial_failure")
    hard_count = statuses.count("failed")
    failed_count = partial_count + hard_count
    failure_ids = [result.customer_id for result in batch_result.failure_results]
    if (
        len(expected_ids) != batch_result.expected_count
        or len(result_ids) != batch_result.processed_count
        or batch_result.succeeded_count != statuses.count("success")
        or batch_result.partial_failure_count != partial_count
        or batch_result.hard_failure_count != hard_count
        or batch_result.failed_count != failed_count
        or _duplicates(failure_ids)
        or set(failure_ids) != {result.customer_id for result in batch_result.results if result.analysis_status != "success"}
        or duplicate_output_ids
        or missing_ids
        or unexpected_ids
    ):
        raise ValueError(
            "Population batch reconciliation failed; "
            f"missing={missing_ids}; unexpected={unexpected_ids}; duplicates={duplicate_output_ids}"
        )
    return {
        "expected_id_count": len(expected_ids),
        "output_id_count": len(result_ids),
        "missing_ids": missing_ids,
        "unexpected_ids": unexpected_ids,
        "duplicate_output_ids": duplicate_output_ids,
        "expected_ids_sha256": _id_digest(expected_ids),
        "output_ids_sha256": _id_digest(tuple(sorted(output_set))),
    }


def _assert_separate_output_dir(output_dir: Path) -> None:
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
        raise ValueError("population artifacts must be written outside canonical analytics directories")


def _unique_ids(customer_ids: Iterable[str], *, label: str) -> tuple[str, ...]:
    normalized = tuple(str(customer_id) for customer_id in customer_ids)
    duplicates = _duplicates(normalized)
    if duplicates:
        raise ValueError(f"{label} contains duplicate customer IDs: {duplicates}")
    return tuple(sorted(normalized))


def _duplicates(customer_ids: Iterable[str]) -> list[str]:
    counts = Counter(str(customer_id) for customer_id in customer_ids)
    return sorted(customer_id for customer_id, count in counts.items() if count > 1)


def _sorted_counter(values: Iterable[str]) -> dict[str, int]:
    counts = Counter(str(value) for value in values)
    return {key: int(counts[key]) for key in sorted(counts)}


def _numeric_summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "min": None, "mean": None, "median": None, "max": None}
    series = pd.Series(values, dtype=float)
    return {
        "count": int(len(series)),
        "min": float(series.min()),
        "mean": float(series.mean()),
        "median": float(series.median()),
        "max": float(series.max()),
    }


def _id_digest(customer_ids: Iterable[str]) -> str:
    payload = "\n".join(sorted(str(customer_id) for customer_id in customer_ids))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _default_settings_snapshot() -> dict[str, Any]:
    return {
        "random_seed": settings.RANDOM_SEED,
        "customer_count": settings.CUSTOMER_COUNT,
        "total_months": settings.TOTAL_MONTHS,
        "observation_start_month": settings.OBSERVATION_START_MONTH,
        "observation_end_month": settings.OBSERVATION_END_MONTH,
        "future_start_month": settings.FUTURE_START_MONTH,
        "future_end_month": settings.FUTURE_END_MONTH,
        "top_k_matches": settings.TOP_K_MATCHES,
        "match_features": list(settings.MATCH_FEATURES),
        "match_weights": dict(settings.MATCH_WEIGHTS),
        "breakpoint_effect_threshold": settings.BREAKPOINT_EFFECT_THRESHOLD,
        "breakpoint_persistence_months": settings.BREAKPOINT_PERSISTENCE_MONTHS,
        "breakpoint_min_group_size": settings.BREAKPOINT_MIN_GROUP_SIZE,
        "whatif_simulation_months": settings.WHATIF_SIMULATION_MONTHS,
        "whatif_scenarios": [dict(scenario) for scenario in settings.WHATIF_SCENARIOS],
    }


def _resolve_code_ref() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=settings.BASE_DIR,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() or None


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _atomic_write_text(path: Path, text: str) -> None:
    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary_path.write_text(text, encoding="utf-8")
        temporary_path.replace(path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return value
