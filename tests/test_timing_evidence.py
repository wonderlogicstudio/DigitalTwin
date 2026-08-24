"""Tests for separated prospective lead-time and historical-landmark evidence."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import src.timing_evidence as timing_evidence
from src.prospective_evaluator import (
    SyntheticEventAnchor,
    extract_synthetic_future_event_anchors,
)
from src.timing_evidence import (
    CandidateAlertMoment,
    HistoricalBreakpointLandmark,
    LEAD_TIME_STATUS,
    NEVER_ALERT_STATUS,
    NO_EVENT_ALERT_STATUS,
    TOO_LATE_STATUS,
    build_timing_evidence,
)


def _anchors() -> tuple[SyntheticEventAnchor, ...]:
    return (
        SyntheticEventAnchor("C000001", 16, "job_loss"),
        SyntheticEventAnchor("C000002", 13, "medical_cost"),
        SyntheticEventAnchor("C000003", None, None),
        SyntheticEventAnchor("C000004", 14, "new_loan"),
        SyntheticEventAnchor("C000005", None, None),
    )


def test_lead_time_metrics_handle_before_at_after_no_event_and_never_alert() -> None:
    result = build_timing_evidence(
        customer_ids=("C000001", "C000002", "C000003", "C000004", "C000005"),
        candidate_alert_moments=(
            CandidateAlertMoment("C000001", 12),
            CandidateAlertMoment("C000001", 14),
            CandidateAlertMoment("C000001", 16),
            CandidateAlertMoment("C000002", 13),
            CandidateAlertMoment("C000003", 12),
        ),
        synthetic_event_anchors=_anchors(),
    )
    by_key = {(record.customer_id, record.alert_month): record for record in result.prospective_records}
    summary = result.summary

    assert by_key[("C000001", 12)].status == LEAD_TIME_STATUS
    assert by_key[("C000001", 12)].lead_time_months == 4
    assert by_key[("C000001", 14)].lead_time_months == 2
    assert by_key[("C000001", 16)].status == TOO_LATE_STATUS
    assert by_key[("C000001", 16)].lead_time_months is None
    assert by_key[("C000002", 13)].status == TOO_LATE_STATUS
    assert by_key[("C000003", 12)].status == NO_EVENT_ALERT_STATUS
    assert by_key[("C000004", None)].status == NEVER_ALERT_STATUS
    assert by_key[("C000004", None)].event_observed is True
    assert by_key[("C000005", None)].status == NEVER_ALERT_STATUS
    assert by_key[("C000005", None)].event_observed is False
    assert summary.candidate_alert_count == 5
    assert summary.lead_time_count == 2
    assert summary.too_late_count == 2
    assert summary.no_event_alert_count == 1
    assert summary.never_alert_count == 2
    assert summary.never_alert_with_event_count == 1
    assert summary.never_alert_censored_no_event_count == 1
    assert summary.lead_time_median_months == pytest.approx(3.0)
    assert summary.lead_time_q1_months == pytest.approx(2.5)
    assert summary.lead_time_q3_months == pytest.approx(3.5)
    assert summary.to_dict()["lead_time_unit"] == "months"
    assert [
        (record.customer_id, record.alert_month) for record in result.prospective_records
    ] == [
        ("C000001", 12),
        ("C000001", 14),
        ("C000001", 16),
        ("C000002", 13),
        ("C000003", 12),
        ("C000004", None),
        ("C000005", None),
    ]


def test_invalid_or_incomplete_timing_inputs_are_not_silently_reconciled() -> None:
    with pytest.raises(ValueError, match="unique customer_id and alert_month"):
        build_timing_evidence(
            customer_ids=("C000001",),
            candidate_alert_moments=(
                CandidateAlertMoment("C000001", 12),
                CandidateAlertMoment("C000001", 12),
            ),
            synthetic_event_anchors=(SyntheticEventAnchor("C000001", None, None),),
        )
    with pytest.raises(ValueError, match="exactly cover customer_ids"):
        build_timing_evidence(
            customer_ids=("C000001", "C000002"),
            candidate_alert_moments=(),
            synthetic_event_anchors=(SyntheticEventAnchor("C000001", None, None),),
        )
    with pytest.raises(ValueError, match="unknown customer IDs"):
        build_timing_evidence(
            customer_ids=("C000001",),
            candidate_alert_moments=(CandidateAlertMoment("C000002", 12),),
            synthetic_event_anchors=(SyntheticEventAnchor("C000001", None, None),),
        )


def test_historical_breakpoints_remain_separate_non_trigger_landmarks() -> None:
    result = build_timing_evidence(
        customer_ids=("C000001", "C000002"),
        candidate_alert_moments=(CandidateAlertMoment("C000001", 12),),
        synthetic_event_anchors=(
            SyntheticEventAnchor("C000001", 16, "job_loss"),
            SyntheticEventAnchor("C000002", None, None),
        ),
        historical_landmarks=(
            HistoricalBreakpointLandmark("C000001", "found", 14),
            HistoricalBreakpointLandmark("C000002", "not_found", None),
        ),
    )
    timing_source = Path(timing_evidence.__file__).read_text(encoding="utf-8")

    assert all(record.source == "prospective_signal" for record in result.prospective_records)
    assert all(landmark.source == "historical_landmark" for landmark in result.historical_landmarks)
    assert all(landmark.to_dict()["is_live_alert_trigger"] is False for landmark in result.historical_landmarks)
    assert all("lead_time_months" not in landmark.to_dict() for landmark in result.historical_landmarks)
    assert "breakpoint_analyzer" not in timing_source
    assert "find_breakpoint" not in timing_source


def test_synthetic_event_anchor_uses_first_non_none_event_in_configured_future_window() -> None:
    monthly_df = pd.DataFrame(
        [
            {"customer_id": "C000001", "month": 12, "event_type": "medical_cost"},
            {"customer_id": "C000001", "month": 13, "event_type": "none"},
            {"customer_id": "C000001", "month": 14, "event_type": "job_loss"},
            {"customer_id": "C000001", "month": 15, "event_type": "job_loss"},
            {"customer_id": "C000002", "month": 13, "event_type": "none"},
            {"customer_id": "C000002", "month": 36, "event_type": "none"},
        ]
    )

    anchors = extract_synthetic_future_event_anchors(
        monthly_df,
        customer_ids=("C000001", "C000002"),
    )

    assert anchors == (
        SyntheticEventAnchor("C000001", 14, "job_loss"),
        SyntheticEventAnchor("C000002", None, None),
    )
