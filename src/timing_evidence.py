"""Retrospective timing evidence for externally supplied candidate moments.

Candidate moments are not policy decisions or live alerts.  This module only
measures their relation to evaluator-provided synthetic event anchors and
keeps historical breakpoints as separate retrospective landmarks.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from config import settings
from src.prospective_evaluator import SyntheticEventAnchor


PROSPECTIVE_SIGNAL_SOURCE = "prospective_signal"
HISTORICAL_LANDMARK_SOURCE = "historical_landmark"
LEAD_TIME_STATUS = "lead_time"
TOO_LATE_STATUS = "too_late"
NO_EVENT_ALERT_STATUS = "no_event_alert"
NEVER_ALERT_STATUS = "never_alert"


@dataclass(frozen=True)
class CandidateAlertMoment:
    """One candidate moment supplied by a prospective-signal workflow."""

    customer_id: str
    alert_month: int
    source: str = PROSPECTIVE_SIGNAL_SOURCE

    def __post_init__(self) -> None:
        _validate_customer_id(self.customer_id)
        _validate_month(self.alert_month, label="alert_month")
        if self.source != PROSPECTIVE_SIGNAL_SOURCE:
            raise ValueError("candidate alert source must be prospective_signal")


@dataclass(frozen=True)
class HistoricalBreakpointLandmark:
    """Historical matched-cohort landmark, explicitly not a live trigger."""

    customer_id: str
    breakpoint_status: str
    breakpoint_month: int | None
    source: str = HISTORICAL_LANDMARK_SOURCE

    def __post_init__(self) -> None:
        _validate_customer_id(self.customer_id)
        if not str(self.breakpoint_status).strip():
            raise ValueError("breakpoint_status must be non-empty")
        if self.breakpoint_month is not None:
            _validate_month(self.breakpoint_month, label="breakpoint_month")
        if self.source != HISTORICAL_LANDMARK_SOURCE:
            raise ValueError("historical breakpoint source must be historical_landmark")

    def to_dict(self) -> dict[str, object]:
        return {
            "customer_id": self.customer_id,
            "breakpoint_status": self.breakpoint_status,
            "breakpoint_month": self.breakpoint_month,
            "source": self.source,
            "is_live_alert_trigger": False,
        }


@dataclass(frozen=True)
class ProspectiveTimingRecord:
    """One candidate relation or one explicit never-alert population record."""

    customer_id: str
    alert_month: int | None
    event_month: int | None
    event_type: str | None
    status: str
    lead_time_months: int | None
    event_observed: bool
    source: str = PROSPECTIVE_SIGNAL_SOURCE

    def to_dict(self) -> dict[str, object]:
        return {
            "customer_id": self.customer_id,
            "alert_month": self.alert_month,
            "event_month": self.event_month,
            "event_type": self.event_type,
            "status": self.status,
            "lead_time_months": self.lead_time_months,
            "event_observed": self.event_observed,
            "source": self.source,
        }


@dataclass(frozen=True)
class LeadTimeSummary:
    """Counts and month-unit distribution for prospective candidate evidence."""

    population_customer_count: int
    candidate_alert_count: int
    lead_time_count: int
    too_late_count: int
    no_event_alert_count: int
    never_alert_count: int
    never_alert_with_event_count: int
    never_alert_censored_no_event_count: int
    lead_time_median_months: float | None
    lead_time_q1_months: float | None
    lead_time_q3_months: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "population_customer_count": self.population_customer_count,
            "candidate_alert_count": self.candidate_alert_count,
            "lead_time_count": self.lead_time_count,
            "too_late_count": self.too_late_count,
            "no_event_alert_count": self.no_event_alert_count,
            "never_alert_count": self.never_alert_count,
            "never_alert_with_event_count": self.never_alert_with_event_count,
            "never_alert_censored_no_event_count": self.never_alert_censored_no_event_count,
            "lead_time_median_months": self.lead_time_median_months,
            "lead_time_q1_months": self.lead_time_q1_months,
            "lead_time_q3_months": self.lead_time_q3_months,
            "lead_time_unit": "months",
        }


@dataclass(frozen=True)
class TimingEvidenceResult:
    """Separated prospective timing evidence and historical landmark context."""

    prospective_records: tuple[ProspectiveTimingRecord, ...]
    historical_landmarks: tuple[HistoricalBreakpointLandmark, ...]
    summary: LeadTimeSummary

    def to_dict(self) -> dict[str, Any]:
        return {
            "prospective_records": [record.to_dict() for record in self.prospective_records],
            "historical_landmarks": [landmark.to_dict() for landmark in self.historical_landmarks],
            "summary": self.summary.to_dict(),
        }


def build_timing_evidence(
    *,
    customer_ids: Sequence[str],
    candidate_alert_moments: Iterable[CandidateAlertMoment],
    synthetic_event_anchors: Iterable[SyntheticEventAnchor],
    historical_landmarks: Iterable[HistoricalBreakpointLandmark] = (),
) -> TimingEvidenceResult:
    """Calculate lead-time without turning landmarks into prospective triggers.

    Lead time is counted only when ``alert_month < event_month``.  Alerts at
    or after the anchor are categorised as ``too_late`` and never contribute
    a lead-time value.  With no observed anchor in the synthetic future
    window, a candidate is ``no_event_alert``; customers with no candidate
    receive exactly one ``never_alert`` record.
    """

    normalized_ids = _normalize_customer_ids(customer_ids)
    anchor_by_customer = _index_anchors(synthetic_event_anchors, normalized_ids)
    candidates_by_customer = _index_candidates(candidate_alert_moments, normalized_ids)
    normalized_landmarks = _normalize_landmarks(historical_landmarks, normalized_ids)
    records = []
    for customer_id in normalized_ids:
        anchor = anchor_by_customer[customer_id]
        candidates = candidates_by_customer.get(customer_id, ())
        if not candidates:
            records.append(
                ProspectiveTimingRecord(
                    customer_id=customer_id,
                    alert_month=None,
                    event_month=anchor.event_month,
                    event_type=anchor.event_type,
                    status=NEVER_ALERT_STATUS,
                    lead_time_months=None,
                    event_observed=anchor.event_observed,
                )
            )
            continue
        for candidate in candidates:
            records.append(_build_candidate_record(candidate, anchor))
    ordered_records = tuple(
        sorted(
            records,
            key=lambda record: (record.customer_id, -1 if record.alert_month is None else record.alert_month),
        )
    )
    return TimingEvidenceResult(
        prospective_records=ordered_records,
        historical_landmarks=normalized_landmarks,
        summary=_build_summary(ordered_records, len(normalized_ids)),
    )


def _build_candidate_record(
    candidate: CandidateAlertMoment,
    anchor: SyntheticEventAnchor,
) -> ProspectiveTimingRecord:
    if not anchor.event_observed:
        return ProspectiveTimingRecord(
            customer_id=candidate.customer_id,
            alert_month=candidate.alert_month,
            event_month=None,
            event_type=None,
            status=NO_EVENT_ALERT_STATUS,
            lead_time_months=None,
            event_observed=False,
        )
    assert anchor.event_month is not None
    if candidate.alert_month >= anchor.event_month:
        return ProspectiveTimingRecord(
            customer_id=candidate.customer_id,
            alert_month=candidate.alert_month,
            event_month=anchor.event_month,
            event_type=anchor.event_type,
            status=TOO_LATE_STATUS,
            lead_time_months=None,
            event_observed=True,
        )
    return ProspectiveTimingRecord(
        customer_id=candidate.customer_id,
        alert_month=candidate.alert_month,
        event_month=anchor.event_month,
        event_type=anchor.event_type,
        status=LEAD_TIME_STATUS,
        lead_time_months=anchor.event_month - candidate.alert_month,
        event_observed=True,
    )


def _build_summary(
    records: Sequence[ProspectiveTimingRecord],
    population_customer_count: int,
) -> LeadTimeSummary:
    counts = Counter(record.status for record in records)
    lead_times = [record.lead_time_months for record in records if record.lead_time_months is not None]
    never_alert_records = [record for record in records if record.status == NEVER_ALERT_STATUS]
    return LeadTimeSummary(
        population_customer_count=population_customer_count,
        candidate_alert_count=sum(record.alert_month is not None for record in records),
        lead_time_count=counts[LEAD_TIME_STATUS],
        too_late_count=counts[TOO_LATE_STATUS],
        no_event_alert_count=counts[NO_EVENT_ALERT_STATUS],
        never_alert_count=counts[NEVER_ALERT_STATUS],
        never_alert_with_event_count=sum(record.event_observed for record in never_alert_records),
        never_alert_censored_no_event_count=sum(
            not record.event_observed for record in never_alert_records
        ),
        lead_time_median_months=_quantile_or_none(lead_times, 0.5),
        lead_time_q1_months=_quantile_or_none(lead_times, 0.25),
        lead_time_q3_months=_quantile_or_none(lead_times, 0.75),
    )


def _index_anchors(
    anchors: Iterable[SyntheticEventAnchor],
    customer_ids: Sequence[str],
) -> dict[str, SyntheticEventAnchor]:
    normalized_anchors = tuple(anchors)
    indexed = {str(anchor.customer_id): anchor for anchor in normalized_anchors}
    if len(indexed) != len(normalized_anchors):
        raise ValueError("synthetic event anchors must have unique customer IDs")
    expected_ids = set(customer_ids)
    if set(indexed) != expected_ids:
        raise ValueError("synthetic event anchors must exactly cover customer_ids")
    for anchor in indexed.values():
        if anchor.source != "synthetic_event_anchor":
            raise ValueError("synthetic event anchor source is invalid")
        if anchor.event_observed:
            assert anchor.event_month is not None
            _validate_month(anchor.event_month, label="event_month")
            if not settings.FUTURE_START_MONTH <= anchor.event_month <= settings.FUTURE_END_MONTH:
                raise ValueError("event_month must be in the configured synthetic future window")
            if not anchor.event_type or anchor.event_type == "none":
                raise ValueError("observed event anchors require a non-none event_type")
        elif anchor.event_type is not None:
            raise ValueError("unobserved event anchors must have event_type=None")
    return indexed


def _index_candidates(
    candidates: Iterable[CandidateAlertMoment],
    customer_ids: Sequence[str],
) -> dict[str, tuple[CandidateAlertMoment, ...]]:
    normalized_candidates = tuple(candidates)
    keys = [(candidate.customer_id, candidate.alert_month) for candidate in normalized_candidates]
    if len(keys) != len(set(keys)):
        raise ValueError("candidate alert moments must have unique customer_id and alert_month keys")
    unexpected_ids = sorted({candidate.customer_id for candidate in normalized_candidates} - set(customer_ids))
    if unexpected_ids:
        raise ValueError(f"candidate alert moments include unknown customer IDs: {unexpected_ids[:5]}")
    grouped: dict[str, list[CandidateAlertMoment]] = {}
    for candidate in normalized_candidates:
        grouped.setdefault(candidate.customer_id, []).append(candidate)
    return {
        customer_id: tuple(sorted(customer_candidates, key=lambda candidate: candidate.alert_month))
        for customer_id, customer_candidates in grouped.items()
    }


def _normalize_landmarks(
    landmarks: Iterable[HistoricalBreakpointLandmark],
    customer_ids: Sequence[str],
) -> tuple[HistoricalBreakpointLandmark, ...]:
    normalized = tuple(landmarks)
    keys = [landmark.customer_id for landmark in normalized]
    if len(keys) != len(set(keys)):
        raise ValueError("historical landmarks must have unique customer IDs")
    unexpected_ids = sorted(set(keys) - set(customer_ids))
    if unexpected_ids:
        raise ValueError(f"historical landmarks include unknown customer IDs: {unexpected_ids[:5]}")
    return tuple(sorted(normalized, key=lambda landmark: landmark.customer_id))


def _normalize_customer_ids(customer_ids: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(sorted(str(customer_id) for customer_id in customer_ids))
    if not normalized or len(normalized) != len(set(normalized)):
        raise ValueError("customer_ids must be non-empty and unique")
    return normalized


def _validate_customer_id(customer_id: str) -> None:
    if not str(customer_id).strip():
        raise ValueError("customer_id must be non-empty")


def _validate_month(value: int, *, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if not 1 <= value <= settings.TOTAL_MONTHS:
        raise ValueError(f"{label} must be between 1 and {settings.TOTAL_MONTHS}")


def _quantile_or_none(values: Sequence[int], quantile: float) -> float | None:
    if not values:
        return None
    return float(np.quantile(np.asarray(values, dtype=float), quantile))
