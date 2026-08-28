"""Tests for pure Daily Review timing classification."""

from __future__ import annotations

import ast
from dataclasses import asdict, replace
import inspect
from pathlib import Path

import src.daily_review as daily_review
from src.daily_review import (
    MONITOR,
    REVIEW_NOW,
    UPCOMING,
    REASON_MONITOR_BREAKPOINT_NOT_FOUND,
    REASON_MONITOR_DISTANT_TIMING,
    REASON_MONITOR_EVIDENCE_UNAVAILABLE,
    REASON_MONITOR_INSUFFICIENT_GROUP_SIZE,
    REASON_MONITOR_INVALID_CURRENT_STATUS,
    REASON_MONITOR_INVALID_TIMING,
    REASON_REVIEW_NOW_CURRENT_OBSERVATION,
    REASON_UPCOMING_FUTURE_TIMING,
    REASON_UPCOMING_HEALTHY_NEAR_TIMING,
    DailyReviewDecision,
    SnapshotTimingRecord,
    classify_daily_review_timing,
)


def _record(**overrides: object) -> SnapshotTimingRecord:
    values: dict[str, object] = {
        "customer_id": "C000001",
        "snapshot_id": "snapshot-2026-08",
        "breakpoint_status": "found",
        "months_from_current": 1,
        "primary_factor": "cash_balance_ratio",
        "evidence_available": True,
        "current_status": "watch",
    }
    values.update(overrides)
    return SnapshotTimingRecord(**values)


def test_review_now_requires_near_timing_and_existing_current_observation() -> None:
    decision = classify_daily_review_timing(_record(months_from_current=2, current_status="stress"))

    assert decision.review_state == REVIEW_NOW
    assert decision.timing_months == 2
    assert decision.reason_code == REASON_REVIEW_NOW_CURRENT_OBSERVATION
    assert decision.customer_id == "C000001"
    assert decision.snapshot_id == "snapshot-2026-08"


def test_upcoming_for_healthy_near_timing_and_three_to_four_month_timing() -> None:
    healthy_near = classify_daily_review_timing(_record(current_status="healthy"))
    future_timing = classify_daily_review_timing(
        _record(months_from_current=3, current_status="delinquent")
    )

    assert healthy_near.review_state == UPCOMING
    assert healthy_near.reason_code == REASON_UPCOMING_HEALTHY_NEAR_TIMING
    assert future_timing.review_state == UPCOMING
    assert future_timing.reason_code == REASON_UPCOMING_FUTURE_TIMING


def test_monitor_for_distant_timing() -> None:
    decision = classify_daily_review_timing(_record(months_from_current=5))

    assert decision.review_state == MONITOR
    assert decision.reason_code == REASON_MONITOR_DISTANT_TIMING


def test_not_found_and_insufficient_group_size_are_monitor() -> None:
    not_found = classify_daily_review_timing(
        _record(breakpoint_status="not_found", months_from_current=None)
    )
    insufficient = classify_daily_review_timing(
        _record(breakpoint_status="insufficient_group_size", months_from_current=None)
    )

    assert not_found.review_state == MONITOR
    assert not_found.reason_code == REASON_MONITOR_BREAKPOINT_NOT_FOUND
    assert insufficient.review_state == MONITOR
    assert insufficient.reason_code == REASON_MONITOR_INSUFFICIENT_GROUP_SIZE


def test_invalid_evidence_and_invalid_timing_are_monitor() -> None:
    unavailable = classify_daily_review_timing(_record(evidence_available=False))
    invalid_timing = classify_daily_review_timing(_record(months_from_current=0))
    unavailable_current_status = classify_daily_review_timing(_record(current_status=None))

    assert unavailable.review_state == MONITOR
    assert unavailable.reason_code == REASON_MONITOR_EVIDENCE_UNAVAILABLE
    assert invalid_timing.review_state == MONITOR
    assert invalid_timing.reason_code == REASON_MONITOR_INVALID_TIMING
    assert unavailable_current_status.review_state == MONITOR
    assert unavailable_current_status.reason_code == REASON_MONITOR_INVALID_CURRENT_STATUS


def test_same_snapshot_is_deterministic_without_daily_date_input() -> None:
    record = _record()

    assert classify_daily_review_timing(record) == classify_daily_review_timing(record)
    assert "date" not in inspect.signature(classify_daily_review_timing).parameters


def test_relationship_priority_cannot_change_timing_bucket() -> None:
    record = _record()
    decision = classify_daily_review_timing(record)

    assert "relationship_priority" not in SnapshotTimingRecord.__dataclass_fields__
    assert "relationship_priority" not in inspect.signature(classify_daily_review_timing).parameters
    assert decision == classify_daily_review_timing(replace(record, primary_factor="dsr"))


def test_decision_has_no_risk_score_or_probability() -> None:
    decision = classify_daily_review_timing(_record())

    assert set(asdict(decision)) == {
        "review_state",
        "timing_months",
        "reason_code",
        "customer_id",
        "snapshot_id",
    }
    assert not {"score", "risk_score", "probability", "prediction_probability"}.intersection(
        DailyReviewDecision.__dataclass_fields__
    )


def test_module_has_no_streamlit_file_io_or_analysis_imports() -> None:
    module_path = Path(daily_review.__file__)
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported_modules = {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert imported_modules.issubset({"__future__", "dataclasses", "typing"})
