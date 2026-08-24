"""Validation-only synthetic circularity mapping and negative controls.

This module deliberately leaves the generator, canonical artifacts, matching,
and breakpoint rules unchanged.  It measures how much matched-cohort future
label associations depend on the synthetic label-to-trajectory relationship by
permuting labels only in an in-memory matched-cohort copy.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from config import settings
from src.breakpoint_analyzer import (
    AVOIDANCE_OUTCOMES,
    RISK_OUTCOMES,
    calculate_monthly_smd,
    find_breakpoint,
    prepare_breakpoint_data,
)
from src.matcher import TrajectoryMatcher


CIRCULARITY_SCHEMA_VERSION = "synthetic_circularity_validation.v1"
CIRCULARITY_VALIDATION_DIR = settings.BASE_DIR / "artifacts" / "validation" / "circularity"
CIRCULARITY_REPORT_FILENAME = "circularity_negative_control_report.json"


def build_signal_overlap_table() -> list[dict[str, str]]:
    """Describe generator-label and breakpoint/trajectory signal overlap.

    ``direct_overlap`` means the listed raw metric appears in a documented
    monthly-status or final-outcome rule and also in the breakpoint metric.
    Trajectory features use months 1..12 only; semantic overlap does not mean
    that the matcher receives a target customer's future values or label.
    """

    rows = [
        {
            "signal_family": "final_outcome",
            "signal": "future monthly_status",
            "label_rule": (
                "delinquent if any future delinquent status; recovered and stress "
                "rules use future status counts and terminal statuses"
            ),
            "breakpoint_or_trajectory_signal": "none directly",
            "overlap_type": "label-only grouping input",
            "temporal_scope": "future months 13-36",
        },
        {
            "signal_family": "breakpoint",
            "signal": "savings_rate",
            "label_rule": (
                "monthly watch threshold; recovered terminal 3-month mean savings "
                "rate threshold"
            ),
            "breakpoint_or_trajectory_signal": "breakpoint metric; 1-12 savings-rate matcher features",
            "overlap_type": "direct metric / observation-window analogue",
            "temporal_scope": "labels and breakpoint: 13-36; matcher: 1-12",
        },
        {
            "signal_family": "breakpoint",
            "signal": "fixed_expense_ratio",
            "label_rule": "monthly watch and stress thresholds",
            "breakpoint_or_trajectory_signal": "breakpoint metric; 1-12 average matcher feature",
            "overlap_type": "direct metric / observation-window analogue",
            "temporal_scope": "labels and breakpoint: 13-36; matcher: 1-12",
        },
        {
            "signal_family": "breakpoint",
            "signal": "variable_expense_ratio",
            "label_rule": "no direct threshold; affects total expense, savings, and cash balance",
            "breakpoint_or_trajectory_signal": "breakpoint metric",
            "overlap_type": "indirect through cashflow identity",
            "temporal_scope": "breakpoint: 13-36",
        },
        {
            "signal_family": "breakpoint",
            "signal": "dsr",
            "label_rule": "monthly watch and stress thresholds; final stress terminal mean threshold",
            "breakpoint_or_trajectory_signal": "breakpoint metric; 1-12 average/change matcher features",
            "overlap_type": "direct metric / observation-window analogue",
            "temporal_scope": "labels and breakpoint: 13-36; matcher: 1-12",
        },
        {
            "signal_family": "breakpoint",
            "signal": "cash_balance_ratio",
            "label_rule": "monthly and final-outcome cash_balance thresholds",
            "breakpoint_or_trajectory_signal": "cash balance divided by mean month-10-12 income",
            "overlap_type": "derived direct metric",
            "temporal_scope": "labels and breakpoint: 13-36; denominator: months 10-12",
        },
        {
            "signal_family": "breakpoint",
            "signal": "loan_balance_ratio",
            "label_rule": "no direct monthly-status or final-outcome threshold",
            "breakpoint_or_trajectory_signal": "loan balance divided by mean month-10-12 income",
            "overlap_type": "indirect debt-path signal",
            "temporal_scope": "breakpoint: 13-36; denominator: months 10-12",
        },
        {
            "signal_family": "trajectory_matcher",
            "signal": "expense_growth_12m and expense_cv_12m",
            "label_rule": "no direct final-outcome threshold; expenses drive savings and cash balance",
            "breakpoint_or_trajectory_signal": "observation-only weighted matching features",
            "overlap_type": "indirect trajectory analogue",
            "temporal_scope": "matcher: months 1-12 only",
        },
        {
            "signal_family": "trajectory_matcher",
            "signal": "balance_change_ratio_12m and consecutive balance decline",
            "label_rule": "monthly watch/stress balance-decline rules",
            "breakpoint_or_trajectory_signal": "observation-only weighted matching features",
            "overlap_type": "direct rule analogue in an earlier window",
            "temporal_scope": "matcher: months 1-12 only; labels: future months 13-36",
        },
        {
            "signal_family": "trajectory_matcher",
            "signal": "income_cv_12m",
            "label_rule": "no direct final-outcome threshold; income affects ratio denominators and cashflow",
            "breakpoint_or_trajectory_signal": "observation-only weighted matching feature",
            "overlap_type": "indirect trajectory analogue",
            "temporal_scope": "matcher: months 1-12 only",
        },
    ]
    return [dict(row) for row in rows]


def run_synthetic_circularity_validation(
    monthly_df: pd.DataFrame,
    features_df: pd.DataFrame,
    *,
    top_k: int = settings.TOP_K_MATCHES,
    sample_size: int = 100,
    random_seed: int = settings.RANDOM_SEED,
    matcher: TrajectoryMatcher | None = None,
) -> dict[str, Any]:
    """Run a reproducible in-memory matched-cohort label permutation control.

    Target IDs are sampled only from ``features_df.customer_id``.  Therefore
    selecting the validation sample does not inspect target future months,
    target labels, or personas.  Future labels are used solely to construct
    retrospective matched-cohort groups and their permuted validation control.
    """

    _validate_validation_inputs(monthly_df, features_df, top_k=top_k, sample_size=sample_size)
    feature_ids = tuple(sorted(features_df["customer_id"].astype(str)))
    target_ids = _select_validation_target_ids(feature_ids, sample_size, random_seed)
    fitted_matcher = matcher or TrajectoryMatcher().fit(features_df)
    rng = np.random.default_rng(random_seed)

    target_records = []
    for target_id in target_ids:
        matches = fitted_matcher.match(target_id, top_k=top_k)
        matched_ids = matches["matched_customer_id"].astype(str).tolist()
        cohort_df = monthly_df[monthly_df["customer_id"].astype(str).isin(set(matched_ids))].copy()
        original = _evaluate_labeled_cohort(matched_ids, cohort_df)
        controlled_df, changed_memberships = _permuted_cohort_outcomes(
            matched_ids,
            cohort_df,
            rng,
        )
        control = _evaluate_labeled_cohort(matched_ids, controlled_df)
        target_records.append(
            {
                "target_customer_id": target_id,
                "matched_count": len(matched_ids),
                "risk_membership_changed": changed_memberships,
                "original": original,
                "permuted_label_control": control,
            }
        )

    summary = _build_negative_control_summary(target_records)
    return {
        "schema_version": CIRCULARITY_SCHEMA_VERSION,
        "validation_scope": "synthetic, retrospective, matched-cohort only",
        "signal_overlap_table": build_signal_overlap_table(),
        "method": {
            "target_selection": (
                "Seeded sample from sorted features_df.customer_id only; it does not use "
                "target final_outcome, persona, or months 13-36."
            ),
            "matching": {
                "feature_window": f"months {settings.OBSERVATION_START_MONTH}-{settings.OBSERVATION_END_MONTH}",
                "top_k": int(top_k),
                "feature_names": list(settings.MATCH_FEATURES),
            },
            "negative_control": (
                "For each matched cohort, final_outcome values are seed-permuted across "
                "matched IDs in an in-memory copy. Outcome counts and group sizes are "
                "preserved while the label-to-trajectory relationship is broken."
            ),
            "effect_measure": (
                "Maximum and mean absolute monthly SMD across the unchanged breakpoint "
                "metrics and future months; breakpoint detection uses the unchanged "
                "threshold, persistence, and group-size rules."
            ),
        },
        "settings": {
            "random_seed": int(random_seed),
            "sample_size_requested": int(sample_size),
            "sample_size_processed": len(target_records),
            "top_k": int(top_k),
            "future_months": [settings.FUTURE_START_MONTH, settings.FUTURE_END_MONTH],
            "breakpoint_effect_threshold": settings.BREAKPOINT_EFFECT_THRESHOLD,
            "breakpoint_persistence_months": settings.BREAKPOINT_PERSISTENCE_MONTHS,
            "breakpoint_min_group_size": settings.BREAKPOINT_MIN_GROUP_SIZE,
        },
        "negative_control_summary": summary,
        "target_records": target_records,
        "synthetic_limitations": [
            "This is synthetic data generated by shared rules, not observed bank data.",
            "A detected original-versus-permuted difference demonstrates dependence within "
            "this synthetic generator; it is not model accuracy, calibration, causal effect, "
            "or intervention efficacy evidence.",
            "Breakpoint results remain retrospective landmarks in matched synthetic cohorts; "
            "they do not state that a target customer will reach a future month or outcome.",
            "The control permutes outcome labels for validation only. It does not change the "
            "production generator, canonical CSV/JSON artifacts, matcher, or breakpoint rule.",
        ],
    }


def export_circularity_validation_report(
    report: Mapping[str, Any],
    *,
    output_dir: Path = CIRCULARITY_VALIDATION_DIR,
    filename: str = CIRCULARITY_REPORT_FILENAME,
) -> Path:
    """Atomically write a validation report outside canonical analytics paths."""

    destination = Path(output_dir)
    _assert_separate_validation_output_dir(destination)
    if not str(filename).strip() or Path(filename).name != filename:
        raise ValueError("filename must be a non-empty file name")
    if report.get("schema_version") != CIRCULARITY_SCHEMA_VERSION:
        raise ValueError("unexpected circularity validation report schema version")
    destination.mkdir(parents=True, exist_ok=True)
    output_path = destination / filename
    _atomic_write_json(output_path, dict(report))
    return output_path


def _validate_validation_inputs(
    monthly_df: pd.DataFrame,
    features_df: pd.DataFrame,
    *,
    top_k: int,
    sample_size: int,
) -> None:
    required_monthly_columns = {
        "customer_id",
        "month",
        "income",
        "savings_rate",
        "fixed_expense_ratio",
        "variable_expense_ratio",
        "dsr",
        "cash_balance",
        "loan_balance",
        "final_outcome",
    }
    missing_monthly_columns = sorted(required_monthly_columns - set(monthly_df.columns))
    if missing_monthly_columns:
        raise ValueError(f"monthly_df is missing required columns: {missing_monthly_columns}")
    if "customer_id" not in features_df.columns:
        raise ValueError("features_df must include customer_id")
    customer_ids = features_df["customer_id"].astype(str)
    if customer_ids.duplicated().any():
        raise ValueError("features_df customer_id values must be unique")
    if len(customer_ids) < 2:
        raise ValueError("features_df must contain at least two customers")
    if top_k <= 0 or top_k > len(customer_ids) - 1:
        raise ValueError("top_k must be between 1 and the non-target customer count")
    if sample_size <= 0:
        raise ValueError("sample_size must be positive")
    monthly_ids = set(monthly_df["customer_id"].astype(str))
    missing_monthly_ids = sorted(set(customer_ids) - monthly_ids)
    if missing_monthly_ids:
        raise ValueError(f"monthly_df is missing feature customer IDs: {missing_monthly_ids}")


def _select_validation_target_ids(
    feature_ids: tuple[str, ...],
    sample_size: int,
    random_seed: int,
) -> tuple[str, ...]:
    count = min(int(sample_size), len(feature_ids))
    rng = np.random.default_rng(random_seed)
    selected = rng.choice(np.asarray(feature_ids, dtype=object), size=count, replace=False)
    return tuple(sorted(str(customer_id) for customer_id in selected))


def _evaluate_labeled_cohort(matched_ids: list[str], cohort_df: pd.DataFrame) -> dict[str, Any]:
    enriched_df = prepare_breakpoint_data(matched_ids, cohort_df)
    outcomes = (
        enriched_df[["customer_id", "final_outcome"]]
        .drop_duplicates("customer_id")
        .set_index("customer_id")["final_outcome"]
    )
    risk_ids = sorted(outcomes[outcomes.isin(RISK_OUTCOMES)].index.astype(str))
    avoidance_ids = sorted(outcomes[outcomes.isin(AVOIDANCE_OUTCOMES)].index.astype(str))
    eligible = (
        len(risk_ids) >= settings.BREAKPOINT_MIN_GROUP_SIZE
        and len(avoidance_ids) >= settings.BREAKPOINT_MIN_GROUP_SIZE
    )
    future_df = enriched_df[
        enriched_df["month"].between(settings.FUTURE_START_MONTH, settings.FUTURE_END_MONTH)
    ]
    smd_df = calculate_monthly_smd(
        future_df,
        risk_ids,
        avoidance_ids,
        min_group_size=settings.BREAKPOINT_MIN_GROUP_SIZE,
    )
    absolute_smd = smd_df["standardized_difference"].abs() if not smd_df.empty else pd.Series(dtype=float)
    breakpoint = find_breakpoint(matched_ids, cohort_df)
    return {
        "eligible": eligible,
        "risk_group_count": len(risk_ids),
        "avoidance_group_count": len(avoidance_ids),
        "smd_row_count": int(len(smd_df)),
        "max_absolute_smd": None if absolute_smd.empty else float(absolute_smd.max()),
        "mean_absolute_smd": None if absolute_smd.empty else float(absolute_smd.mean()),
        "breakpoint_status": str(breakpoint["status"]),
        "breakpoint_month": breakpoint["breakpoint_month"],
        "breakpoint_factor": breakpoint["primary_factor"],
    }


def _permuted_cohort_outcomes(
    matched_ids: list[str],
    cohort_df: pd.DataFrame,
    rng: np.random.Generator,
) -> tuple[pd.DataFrame, bool]:
    ordered_ids = tuple(sorted(str(customer_id) for customer_id in matched_ids))
    labels = (
        cohort_df[["customer_id", "final_outcome"]]
        .drop_duplicates("customer_id")
        .assign(customer_id=lambda frame: frame["customer_id"].astype(str))
        .set_index("customer_id")["final_outcome"]
        .reindex(ordered_ids)
    )
    if labels.isna().any():
        raise ValueError("matched cohort is missing final_outcome values")
    original = labels.to_numpy(dtype=object)
    permuted = _risk_membership_changing_permutation(original, rng)
    remapped = dict(zip(ordered_ids, permuted, strict=True))
    output = cohort_df.copy()
    output["customer_id"] = output["customer_id"].astype(str)
    output["final_outcome"] = output["customer_id"].map(remapped)
    original_risk = np.isin(original, tuple(RISK_OUTCOMES))
    permuted_risk = np.isin(permuted, tuple(RISK_OUTCOMES))
    return output, bool(not np.array_equal(original_risk, permuted_risk))


def _risk_membership_changing_permutation(
    labels: np.ndarray,
    rng: np.random.Generator,
) -> np.ndarray:
    original_risk = np.isin(labels, tuple(RISK_OUTCOMES))
    for _ in range(32):
        candidate = rng.permutation(labels)
        if not np.array_equal(original_risk, np.isin(candidate, tuple(RISK_OUTCOMES))):
            return candidate

    risk_positions = np.flatnonzero(original_risk)
    avoidance_positions = np.flatnonzero(~original_risk)
    if len(risk_positions) and len(avoidance_positions):
        candidate = labels.copy()
        risk_position = int(rng.choice(risk_positions))
        avoidance_position = int(rng.choice(avoidance_positions))
        candidate[risk_position], candidate[avoidance_position] = (
            candidate[avoidance_position],
            candidate[risk_position],
        )
        return candidate
    return rng.permutation(labels)


def _build_negative_control_summary(target_records: list[dict[str, Any]]) -> dict[str, Any]:
    original_eligible = [record["original"] for record in target_records if record["original"]["eligible"]]
    control_eligible = [
        record["permuted_label_control"]
        for record in target_records
        if record["permuted_label_control"]["eligible"]
    ]
    if len(original_eligible) != len(control_eligible):
        raise ValueError("permuted control must preserve breakpoint group eligibility")

    original_effects = _available_metric(original_eligible, "max_absolute_smd")
    control_effects = _available_metric(control_eligible, "max_absolute_smd")
    original_found = sum(result["breakpoint_status"] == "found" for result in original_eligible)
    control_found = sum(result["breakpoint_status"] == "found" for result in control_eligible)
    eligible_count = len(original_eligible)
    original_effect_mean = _mean_or_none(original_effects)
    control_effect_mean = _mean_or_none(control_effects)
    effect_delta = _difference_or_none(original_effect_mean, control_effect_mean)
    original_found_rate = _rate_or_none(original_found, eligible_count)
    control_found_rate = _rate_or_none(control_found, eligible_count)
    found_rate_delta = _difference_or_none(original_found_rate, control_found_rate)
    effect_weakened = effect_delta is not None and effect_delta > 0
    breakpoint_weakened = found_rate_delta is not None and found_rate_delta > 0
    if eligible_count == 0:
        recommendation = "INSUFFICIENT_EVIDENCE"
    elif effect_weakened and breakpoint_weakened:
        recommendation = "GO"
    else:
        recommendation = "NO-GO"

    return {
        "target_count": len(target_records),
        "eligible_cohort_count": eligible_count,
        "risk_membership_changed_count": sum(
            bool(record["risk_membership_changed"]) for record in target_records
        ),
        "original": {
            "found_count": int(original_found),
            "found_rate": original_found_rate,
            "max_absolute_smd_mean": original_effect_mean,
            "max_absolute_smd_median": _median_or_none(original_effects),
        },
        "permuted_label_control": {
            "found_count": int(control_found),
            "found_rate": control_found_rate,
            "max_absolute_smd_mean": control_effect_mean,
            "max_absolute_smd_median": _median_or_none(control_effects),
        },
        "weakening": {
            "max_absolute_smd_mean_delta": effect_delta,
            "breakpoint_found_rate_delta": found_rate_delta,
            "effect_weakened": effect_weakened,
            "breakpoint_rate_weakened": breakpoint_weakened,
        },
        "recommendation": recommendation,
        "recommendation_interpretation": (
            "GO requires both lower mean maximum absolute SMD and a lower breakpoint found "
            "rate after the label-to-trajectory relationship is broken. NO-GO means this "
            "sample did not show both weakening conditions; it must not be described as "
            "evidence of a distinct synthetic signal."
        ),
    }


def _available_metric(results: list[dict[str, Any]], key: str) -> list[float]:
    return [float(result[key]) for result in results if result[key] is not None]


def _mean_or_none(values: list[float]) -> float | None:
    return None if not values else float(np.mean(values))


def _median_or_none(values: list[float]) -> float | None:
    return None if not values else float(np.median(values))


def _difference_or_none(left: float | None, right: float | None) -> float | None:
    return None if left is None or right is None else float(left - right)


def _rate_or_none(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else float(numerator / denominator)


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
        raise ValueError("circularity validation artifacts must be outside canonical analytics directories")


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
