"""Pure Daily Review timing classification over saved Snapshot values."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


REVIEW_NOW = "REVIEW_NOW"
UPCOMING = "UPCOMING"
MONITOR = "MONITOR"

BREAKPOINT_FOUND = "found"
BREAKPOINT_NOT_FOUND = "not_found"
BREAKPOINT_INSUFFICIENT_GROUP_SIZE = "insufficient_group_size"

CURRENT_STATUS_HEALTHY = "healthy"
CURRENT_STATUS_REVIEW = frozenset({"watch", "stress", "delinquent"})

REASON_REVIEW_NOW_CURRENT_OBSERVATION = "NEAR_TIMING_WITH_CURRENT_OBSERVATION"
REASON_UPCOMING_HEALTHY_NEAR_TIMING = "NEAR_TIMING_CURRENTLY_HEALTHY"
REASON_UPCOMING_FUTURE_TIMING = "TIMING_IN_3_TO_4_MONTHS"
REASON_MONITOR_EVIDENCE_UNAVAILABLE = "EVIDENCE_UNAVAILABLE"
REASON_MONITOR_BREAKPOINT_NOT_FOUND = "BREAKPOINT_NOT_FOUND"
REASON_MONITOR_INSUFFICIENT_GROUP_SIZE = "INSUFFICIENT_GROUP_SIZE"
REASON_MONITOR_INVALID_TIMING = "INVALID_TIMING_EVIDENCE"
REASON_MONITOR_DISTANT_TIMING = "TIMING_5_OR_MORE_MONTHS"
REASON_MONITOR_INVALID_CURRENT_STATUS = "CURRENT_OBSERVATION_UNAVAILABLE"

ReviewState = Literal["REVIEW_NOW", "UPCOMING", "MONITOR"]


@dataclass(frozen=True)
class SnapshotTimingRecord:
    """Saved customer-level timing values consumed by Daily Review.

    The optional current_status is the existing month-12 status in the Snapshot
    current summary. It is required to classify a 1-2 month found breakpoint as
    REVIEW_NOW or UPCOMING.
    """

    customer_id: str
    snapshot_id: str
    breakpoint_status: str
    months_from_current: int | None
    primary_factor: str | None
    evidence_available: bool
    current_status: str | None = None


@dataclass(frozen=True)
class DailyReviewDecision:
    """A deterministic Daily Review timing result with no score or probability."""

    review_state: ReviewState
    timing_months: int | None
    reason_code: str
    customer_id: str
    snapshot_id: str


def classify_daily_review_timing(record: SnapshotTimingRecord) -> DailyReviewDecision:
    """Classify one saved Snapshot record without invoking financial analysis."""

    if not record.evidence_available:
        return _monitor(record, REASON_MONITOR_EVIDENCE_UNAVAILABLE)

    if record.breakpoint_status == BREAKPOINT_NOT_FOUND:
        return _monitor(record, REASON_MONITOR_BREAKPOINT_NOT_FOUND)
    if record.breakpoint_status == BREAKPOINT_INSUFFICIENT_GROUP_SIZE:
        return _monitor(record, REASON_MONITOR_INSUFFICIENT_GROUP_SIZE)
    if record.breakpoint_status != BREAKPOINT_FOUND:
        return _monitor(record, REASON_MONITOR_EVIDENCE_UNAVAILABLE)

    months = record.months_from_current
    if not _is_valid_timing_month(months):
        return _monitor(record, REASON_MONITOR_INVALID_TIMING)
    assert months is not None

    if months >= 5:
        return _monitor(record, REASON_MONITOR_DISTANT_TIMING)
    if months in {3, 4}:
        return DailyReviewDecision(
            review_state=UPCOMING,
            timing_months=months,
            reason_code=REASON_UPCOMING_FUTURE_TIMING,
            customer_id=record.customer_id,
            snapshot_id=record.snapshot_id,
        )

    current_status = _normalized_current_status(record.current_status)
    if current_status in CURRENT_STATUS_REVIEW:
        return DailyReviewDecision(
            review_state=REVIEW_NOW,
            timing_months=months,
            reason_code=REASON_REVIEW_NOW_CURRENT_OBSERVATION,
            customer_id=record.customer_id,
            snapshot_id=record.snapshot_id,
        )
    if current_status == CURRENT_STATUS_HEALTHY:
        return DailyReviewDecision(
            review_state=UPCOMING,
            timing_months=months,
            reason_code=REASON_UPCOMING_HEALTHY_NEAR_TIMING,
            customer_id=record.customer_id,
            snapshot_id=record.snapshot_id,
        )
    return _monitor(record, REASON_MONITOR_INVALID_CURRENT_STATUS)


def _is_valid_timing_month(value: int | None) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 24


def _normalized_current_status(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return normalized or None


def _monitor(record: SnapshotTimingRecord, reason_code: str) -> DailyReviewDecision:
    return DailyReviewDecision(
        review_state=MONITOR,
        timing_months=record.months_from_current,
        reason_code=reason_code,
        customer_id=record.customer_id,
        snapshot_id=record.snapshot_id,
    )
