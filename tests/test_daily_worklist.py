"""Tests for the saved-Snapshot Daily Worklist application layer."""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest

import src.daily_worklist as daily_worklist
from src.daily_review import MONITOR, REVIEW_NOW, UPCOMING
from src.daily_worklist import (
    COMPLETED_TODAY,
    FRESHNESS_CURRENT_MONTH,
    FRESHNESS_PRIOR_MONTH,
    FRESHNESS_UNKNOWN,
    build_daily_worklist,
    filter_worklist_items_by_relationship,
)


def _record(
    customer_id: str,
    relationship_priority: str,
    *,
    breakpoint_status: str = "found",
    months_from_current: int | None = 1,
    current_status: str | None = "healthy",
    evidence_available: bool = True,
) -> dict[str, object]:
    return {
        "customer_id": customer_id,
        "snapshot_id": "monthly-2026-08",
        "analysis_as_of_month": 12,
        "current_summary": {"current_status": current_status},
        "matched_count": 200,
        "breakpoint": {
            "status": breakpoint_status,
            "breakpoint_month": 13 if breakpoint_status == "found" else None,
            "months_from_current": months_from_current,
            "primary_factor": "cash_balance_ratio",
        },
        "evidence": {"available": evidence_available, "status": "available", "errors": {}},
        "relationship_metadata": {
            "source": "synthetic_crm_overlay",
            "rm_portfolio_id": "RM-POC-001",
            "relationship_priority": relationship_priority,
            "relationship_label": relationship_priority,
        },
        "outcome_summary": None,
    }


def _snapshot_artifact() -> dict[str, object]:
    return {
        "snapshot_id": "monthly-2026-08",
        "analysis_as_of_month": 12,
        "rm_portfolio_id": "RM-POC-001",
        "universe_customer_count": 5_000,
        "portfolio_size": 6,
        "records": [
            _record("C000003", "STANDARD", current_status="watch"),
            _record("C000001", "CORE", current_status="stress"),
            _record("C000002", "PRIORITY", current_status="healthy"),
            _record("C000004", "CORE", months_from_current=3, current_status="healthy"),
            _record(
                "C000005",
                "STANDARD",
                breakpoint_status="insufficient_group_size",
                months_from_current=None,
            ),
            _record(
                "C000006",
                "PRIORITY",
                breakpoint_status="not_found",
                months_from_current=None,
            ),
        ],
    }


def test_builds_bucketed_worklist_with_completion_and_relationship_breakdown() -> None:
    worklist = build_daily_worklist(
        _snapshot_artifact(),
        daily_date=date(2026, 8, 29),
        completed_customer_ids=["C000001"],
        snapshot_published_on=date(2026, 8, 1),
    )

    assert [item.customer_id for item in worklist.today_items] == ["C000003"]
    assert [item.customer_id for item in worklist.upcoming_items] == ["C000004", "C000002"]
    assert [item.customer_id for item in worklist.monitor_items] == ["C000006", "C000005"]
    assert [item.customer_id for item in worklist.completed_today] == ["C000001"]
    assert worklist.completed_today[0].completed_today is True
    assert worklist.monitor_summary.item_count == 2
    assert sum(worklist.monitor_summary.reason_counts.values()) == 2
    assert worklist.relationship_priority_breakdown == {
        "CORE": {REVIEW_NOW: 0, UPCOMING: 1, MONITOR: 0, COMPLETED_TODAY: 1},
        "PRIORITY": {REVIEW_NOW: 0, UPCOMING: 1, MONITOR: 1, COMPLETED_TODAY: 0},
        "STANDARD": {REVIEW_NOW: 1, UPCOMING: 0, MONITOR: 1, COMPLETED_TODAY: 0},
    }
    assert worklist.snapshot_freshness.status == FRESHNESS_CURRENT_MONTH
    assert worklist.snapshot_freshness.age_days == 28


def test_relationship_filter_stays_inside_existing_bucket() -> None:
    worklist = build_daily_worklist(
        _snapshot_artifact(),
        daily_date=date(2026, 8, 29),
    )

    upcoming_core = filter_worklist_items_by_relationship(worklist.upcoming_items, "core")
    assert [item.customer_id for item in upcoming_core] == ["C000004"]
    assert all(item.review_state == UPCOMING for item in upcoming_core)
    assert [item.customer_id for item in worklist.today_items] == ["C000001", "C000003"]
    assert all(item.review_state == REVIEW_NOW for item in worklist.today_items)


def test_daily_date_changes_freshness_not_saved_timing_or_bucket() -> None:
    artifact = _snapshot_artifact()
    august = build_daily_worklist(
        artifact,
        daily_date=date(2026, 8, 29),
        snapshot_published_on=date(2026, 8, 1),
    )
    september = build_daily_worklist(
        artifact,
        daily_date=date(2026, 9, 1),
        snapshot_published_on=date(2026, 8, 1),
    )

    assert [item.timing_months for item in august.today_items] == [
        item.timing_months for item in september.today_items
    ]
    assert [item.review_state for item in august.upcoming_items] == [
        item.review_state for item in september.upcoming_items
    ]
    assert september.snapshot_freshness.status == FRESHNESS_PRIOR_MONTH
    assert september.snapshot_freshness.age_days == 31


def test_freshness_is_unknown_without_explicit_snapshot_publication_date() -> None:
    worklist = build_daily_worklist(
        _snapshot_artifact(),
        daily_date=date(2026, 8, 29),
    )

    assert worklist.snapshot_freshness.status == FRESHNESS_UNKNOWN
    assert worklist.snapshot_freshness.age_days is None
    assert worklist.snapshot_freshness.snapshot_published_on is None


def test_invalid_completed_customer_or_snapshot_record_is_rejected() -> None:
    with pytest.raises(ValueError, match="completed_customer_ids"):
        build_daily_worklist(
            _snapshot_artifact(),
            daily_date=date(2026, 8, 29),
            completed_customer_ids=["C999999"],
        )

    artifact = _snapshot_artifact()
    artifact["records"][0]["snapshot_id"] = "another-snapshot"  # type: ignore[index]
    with pytest.raises(ValueError, match="supplied snapshot_id"):
        build_daily_worklist(artifact, daily_date=date(2026, 8, 29))


def test_worklist_has_no_analysis_imports_or_risk_score_fields() -> None:
    module_path = Path(daily_worklist.__file__)
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert imported_modules.issubset(
        {
            "__future__",
            "collections",
            "collections.abc",
            "dataclasses",
            "datetime",
            "typing",
            "src.daily_review",
            "src.rm_portfolio",
        }
    )
    item_fields = set(daily_worklist.DailyWorklistItem.__dataclass_fields__)
    assert not {"score", "risk_score", "probability", "prediction_probability"}.intersection(
        item_fields
    )
    assert {REVIEW_NOW, UPCOMING, MONITOR}.isdisjoint({COMPLETED_TODAY})
