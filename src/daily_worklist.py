"""Daily RM worklists assembled only from saved Monthly Snapshot artifacts."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Literal

from src.daily_review import (
    MONITOR,
    REVIEW_NOW,
    UPCOMING,
    DailyReviewDecision,
    SnapshotTimingRecord,
    classify_daily_review_timing,
)
from src.rm_portfolio import RELATIONSHIP_PRIORITY_ORDER


COMPLETED_TODAY = "COMPLETED_TODAY"
FRESHNESS_CURRENT_MONTH = "CURRENT_MONTH"
FRESHNESS_PRIOR_MONTH = "PRIOR_MONTH"
FRESHNESS_FUTURE_PUBLICATION_DATE = "FUTURE_PUBLICATION_DATE"
FRESHNESS_UNKNOWN = "UNKNOWN"

WorklistState = Literal["REVIEW_NOW", "UPCOMING", "MONITOR"]


@dataclass(frozen=True)
class DailyWorklistItem:
    """One customer task derived from saved timing and CRM overlay metadata."""

    customer_id: str
    snapshot_id: str
    review_state: WorklistState
    timing_months: int | None
    reason_code: str
    primary_factor: str | None
    current_status: str | None
    relationship_priority: str
    relationship_label: str
    completed_today: bool = False
    current_summary: Mapping[str, object] = field(default_factory=dict)
    matched_count: int = 0
    outcome_summary: Mapping[str, object] | None = None
    breakpoint_month: int | None = None
    breakpoint_status: str | None = None


@dataclass(frozen=True)
class MonitorSummary:
    """Count active monitoring customers by existing timing evidence reason."""

    item_count: int
    reason_counts: dict[str, int]


@dataclass(frozen=True)
class SnapshotFreshness:
    """Calendar freshness metadata; it never changes saved timing months."""

    snapshot_id: str
    analysis_as_of_month: int
    daily_date: date
    snapshot_published_on: date | None
    age_days: int | None
    status: str


@dataclass(frozen=True)
class DailyWorklist:
    """Daily presentation of a saved Snapshot with no financial recalculation."""

    snapshot_id: str
    daily_date: date
    today_items: tuple[DailyWorklistItem, ...]
    upcoming_items: tuple[DailyWorklistItem, ...]
    monitor_items: tuple[DailyWorklistItem, ...]
    monitor_summary: MonitorSummary
    completed_today: tuple[DailyWorklistItem, ...]
    snapshot_freshness: SnapshotFreshness
    relationship_priority_breakdown: dict[str, dict[str, int]]


def build_daily_worklist(
    snapshot_artifact: Mapping[str, object],
    *,
    daily_date: date,
    completed_customer_ids: Iterable[str] = (),
    snapshot_published_on: date | None = None,
) -> DailyWorklist:
    """Build a deterministic worklist from one already-saved Monthly Snapshot.

    ``daily_date`` affects only completion grouping and freshness metadata. The
    saved ``months_from_current`` values pass unchanged to the Daily classifier.
    """

    snapshot_id, analysis_as_of_month, records = _validate_snapshot_artifact(snapshot_artifact)
    completed_ids = {str(customer_id) for customer_id in completed_customer_ids}
    known_customer_ids = {str(record["customer_id"]) for record in records}
    unknown_completed_ids = sorted(completed_ids - known_customer_ids)
    if unknown_completed_ids:
        raise ValueError(
            "completed_customer_ids must belong to the saved RM Portfolio Snapshot: "
            f"{unknown_completed_ids[:3]}"
        )

    active_by_state: dict[str, list[DailyWorklistItem]] = {
        REVIEW_NOW: [],
        UPCOMING: [],
        MONITOR: [],
    }
    completed_items: list[DailyWorklistItem] = []
    relationship_breakdown = _empty_relationship_breakdown(records)

    for record in records:
        item = _build_worklist_item(record, snapshot_id)
        relationship_breakdown.setdefault(
            item.relationship_priority,
            _empty_relationship_counts(),
        )
        if item.customer_id in completed_ids:
            completed_item = replace(item, completed_today=True)
            completed_items.append(completed_item)
            relationship_breakdown[item.relationship_priority][COMPLETED_TODAY] += 1
            continue

        active_by_state[item.review_state].append(item)
        relationship_breakdown[item.relationship_priority][item.review_state] += 1

    today_items = _sort_items(active_by_state[REVIEW_NOW])
    upcoming_items = _sort_items(active_by_state[UPCOMING])
    monitor_items = _sort_items(active_by_state[MONITOR])
    completed_today = _sort_items(completed_items)
    monitor_summary = MonitorSummary(
        item_count=len(monitor_items),
        reason_counts={
            reason: int(count)
            for reason, count in sorted(Counter(item.reason_code for item in monitor_items).items())
        },
    )
    return DailyWorklist(
        snapshot_id=snapshot_id,
        daily_date=daily_date,
        today_items=today_items,
        upcoming_items=upcoming_items,
        monitor_items=monitor_items,
        monitor_summary=monitor_summary,
        completed_today=completed_today,
        snapshot_freshness=_build_snapshot_freshness(
            snapshot_id,
            analysis_as_of_month,
            daily_date,
            snapshot_published_on,
        ),
        relationship_priority_breakdown=_ordered_relationship_breakdown(
            relationship_breakdown
        ),
    )


def filter_worklist_items_by_relationship(
    items: Iterable[DailyWorklistItem],
    relationship_priority: str,
) -> tuple[DailyWorklistItem, ...]:
    """Return a presentation filter within an existing timing bucket only."""

    normalized_priority = str(relationship_priority).strip().upper()
    return tuple(
        item
        for item in items
        if item.relationship_priority == normalized_priority
    )


def _validate_snapshot_artifact(
    snapshot_artifact: Mapping[str, object],
) -> tuple[str, int, tuple[Mapping[str, object], ...]]:
    snapshot_id = str(snapshot_artifact.get("snapshot_id") or "").strip()
    if not snapshot_id:
        raise ValueError("Snapshot artifact must include snapshot_id.")
    analysis_as_of_month = snapshot_artifact.get("analysis_as_of_month")
    if not isinstance(analysis_as_of_month, int) or isinstance(analysis_as_of_month, bool):
        raise ValueError("Snapshot artifact must include an integer analysis_as_of_month.")
    raw_records = snapshot_artifact.get("records")
    if not isinstance(raw_records, Sequence) or isinstance(raw_records, (str, bytes)):
        raise ValueError("Snapshot artifact must include a records sequence.")

    records: list[Mapping[str, object]] = []
    for raw_record in raw_records:
        if not isinstance(raw_record, Mapping):
            raise ValueError("Snapshot records must be mapping objects.")
        customer_id = str(raw_record.get("customer_id") or "").strip()
        record_snapshot_id = str(raw_record.get("snapshot_id") or "").strip()
        if not customer_id:
            raise ValueError("Snapshot records must include customer_id.")
        if record_snapshot_id != snapshot_id:
            raise ValueError("All Snapshot records must belong to the supplied snapshot_id.")
        records.append(raw_record)
    if len({str(record["customer_id"]) for record in records}) != len(records):
        raise ValueError("Snapshot records must not contain duplicate customer_id values.")
    return snapshot_id, analysis_as_of_month, tuple(records)


def _build_worklist_item(
    record: Mapping[str, object],
    snapshot_id: str,
) -> DailyWorklistItem:
    breakpoint = _mapping_value(record, "breakpoint")
    evidence = _mapping_value(record, "evidence")
    current_summary = _mapping_value(record, "current_summary")
    relationship_metadata = _mapping_value(record, "relationship_metadata")
    decision = classify_daily_review_timing(
        SnapshotTimingRecord(
            customer_id=str(record["customer_id"]),
            snapshot_id=snapshot_id,
            breakpoint_status=str(breakpoint.get("status") or ""),
            months_from_current=_timing_months(breakpoint.get("months_from_current")),
            primary_factor=_optional_text(breakpoint.get("primary_factor")),
            evidence_available=evidence.get("available") is True,
            current_status=_optional_text(current_summary.get("current_status")),
        )
    )
    return DailyWorklistItem(
        customer_id=decision.customer_id,
        snapshot_id=decision.snapshot_id,
        review_state=decision.review_state,
        timing_months=decision.timing_months,
        reason_code=decision.reason_code,
        primary_factor=_optional_text(breakpoint.get("primary_factor")),
        current_status=_optional_text(current_summary.get("current_status")),
        relationship_priority=_optional_text(
            relationship_metadata.get("relationship_priority")
        ) or "UNSPECIFIED",
        relationship_label=_optional_text(relationship_metadata.get("relationship_label"))
        or "관계 중요도 미지정",
        current_summary=dict(current_summary),
        matched_count=_nonnegative_int(record.get("matched_count")),
        outcome_summary=_optional_mapping(record.get("outcome_summary")),
        breakpoint_month=_optional_int(breakpoint.get("breakpoint_month")),
        breakpoint_status=_optional_text(breakpoint.get("status")),
    )


def _mapping_value(record: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = record.get(key)
    return value if isinstance(value, Mapping) else {}


def _timing_months(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized_value = str(value).strip()
    return normalized_value or None


def _optional_mapping(value: object) -> Mapping[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    return dict(value)


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _nonnegative_int(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def _sort_items(items: Iterable[DailyWorklistItem]) -> tuple[DailyWorklistItem, ...]:
    priority_rank = {
        priority: index for index, priority in enumerate(RELATIONSHIP_PRIORITY_ORDER)
    }
    return tuple(
        sorted(
            items,
            key=lambda item: (
                priority_rank.get(item.relationship_priority, len(priority_rank)),
                item.timing_months if item.timing_months is not None else 999,
                item.customer_id,
            ),
        )
    )


def _empty_relationship_counts() -> dict[str, int]:
    return {
        REVIEW_NOW: 0,
        UPCOMING: 0,
        MONITOR: 0,
        COMPLETED_TODAY: 0,
    }


def _empty_relationship_breakdown(
    records: Iterable[Mapping[str, object]],
) -> dict[str, dict[str, int]]:
    priorities = {
        _optional_text(
            _mapping_value(record, "relationship_metadata").get("relationship_priority")
        )
        or "UNSPECIFIED"
        for record in records
    }
    return {
        priority: _empty_relationship_counts()
        for priority in [
            *RELATIONSHIP_PRIORITY_ORDER,
            *sorted(priority for priority in priorities if priority not in RELATIONSHIP_PRIORITY_ORDER),
        ]
    }


def _ordered_relationship_breakdown(
    breakdown: Mapping[str, dict[str, int]],
) -> dict[str, dict[str, int]]:
    return {
        priority: dict(breakdown[priority])
        for priority in [
            *RELATIONSHIP_PRIORITY_ORDER,
            *sorted(priority for priority in breakdown if priority not in RELATIONSHIP_PRIORITY_ORDER),
        ]
    }


def _build_snapshot_freshness(
    snapshot_id: str,
    analysis_as_of_month: int,
    daily_date: date,
    snapshot_published_on: date | None,
) -> SnapshotFreshness:
    if snapshot_published_on is None:
        return SnapshotFreshness(
            snapshot_id=snapshot_id,
            analysis_as_of_month=analysis_as_of_month,
            daily_date=daily_date,
            snapshot_published_on=None,
            age_days=None,
            status=FRESHNESS_UNKNOWN,
        )

    age_days = (daily_date - snapshot_published_on).days
    if age_days < 0:
        status = FRESHNESS_FUTURE_PUBLICATION_DATE
    elif (daily_date.year, daily_date.month) == (
        snapshot_published_on.year,
        snapshot_published_on.month,
    ):
        status = FRESHNESS_CURRENT_MONTH
    else:
        status = FRESHNESS_PRIOR_MONTH
    return SnapshotFreshness(
        snapshot_id=snapshot_id,
        analysis_as_of_month=analysis_as_of_month,
        daily_date=daily_date,
        snapshot_published_on=snapshot_published_on,
        age_days=age_days,
        status=status,
    )
