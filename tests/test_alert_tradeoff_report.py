"""Tests for aggregate-only synthetic RM workload trade-off reports."""

from __future__ import annotations

import pytest

from src.alert_tradeoff_report import (
    CandidatePolicyTimingEvidence,
    ReviewCapacityScenario,
    TradeoffMeasurementContext,
    build_alert_tradeoff_report,
)
from src.prospective_evaluator import SyntheticEventAnchor
from src.timing_evidence import CandidateAlertMoment, build_timing_evidence


CUSTOMER_IDS = ("C000001", "C000002", "C000003")
ANALYSIS_MONTHS = (12, 13, 14, 15)
ANCHORS = (
    SyntheticEventAnchor("C000001", 15, "job_loss"),
    SyntheticEventAnchor("C000002", None, None),
    SyntheticEventAnchor("C000003", 14, "new_loan"),
)


def _evidence(*candidates: CandidateAlertMoment):
    return build_timing_evidence(
        customer_ids=CUSTOMER_IDS,
        candidate_alert_moments=candidates,
        synthetic_event_anchors=ANCHORS,
    )


def test_tradeoff_metrics_share_denominator_and_preserve_all_candidate_policies() -> None:
    context = TradeoffMeasurementContext(
        customer_ids=CUSTOMER_IDS,
        analysis_months=ANALYSIS_MONTHS,
        period_days=4,
    )
    report = build_alert_tradeoff_report(
        context=context,
        policy_evidence=(
            CandidatePolicyTimingEvidence(
                "broad",
                "Broad candidate",
                _evidence(
                    CandidateAlertMoment("C000001", 12),
                    CandidateAlertMoment("C000001", 13),
                    CandidateAlertMoment("C000002", 12),
                ),
            ),
            CandidatePolicyTimingEvidence(
                "narrow",
                "Narrow candidate",
                _evidence(
                    CandidateAlertMoment("C000001", 12),
                    CandidateAlertMoment("C000003", 12),
                ),
            ),
        ),
        review_capacity_scenarios=(ReviewCapacityScenario("illustrative_one", 1, 2),),
    )
    metrics = {policy.policy_id: policy for policy in report.policies}
    broad = metrics["broad"]
    narrow = metrics["narrow"]

    assert report.context.customer_month_denominator == 12
    assert [policy.policy_id for policy in report.policies] == ["broad", "narrow"]
    assert broad.alert_moment_count == 3
    assert broad.review_episode_count == 2
    assert broad.alerts_per_1000_customer_months == pytest.approx(2 / 12 * 1000)
    assert broad.unique_alerted_customer_count == 2
    assert broad.synthetic_precision_proxy == pytest.approx(0.5)
    assert broad.synthetic_recall_proxy == pytest.approx(0.5)
    assert broad.no_event_alert_rate == pytest.approx(0.5)
    assert broad.lead_time_median_months == pytest.approx(2.5)
    assert broad.lead_time_q1_months == pytest.approx(2.25)
    assert broad.lead_time_q3_months == pytest.approx(2.75)
    assert broad.persistence_rate == pytest.approx(1 / 3)
    assert broad.mean_episode_length_months == pytest.approx(1.5)
    assert broad.flip_rate == pytest.approx(2 / 9)
    assert broad.estimated_reviews_per_period == 2
    assert broad.estimated_reviews_per_day == pytest.approx(0.5)
    assert broad.capacity_comparisons[0].cycles_required == 2
    assert broad.capacity_comparisons[0].episodes_beyond_one_cycle == 1
    assert broad.capacity_comparisons[0].comparison_only is True
    assert narrow.synthetic_precision_proxy == pytest.approx(1.0)
    assert narrow.synthetic_recall_proxy == pytest.approx(1.0)
    assert narrow.no_event_alert_rate == pytest.approx(0.0)
    serialized = report.to_dict()
    assert serialized["selection"] == {
        "automatic_threshold_selection": False,
        "rm_queue_selection": False,
        "alert_creation": False,
    }
    assert "customer_ids" not in serialized["context"]
    assert len(serialized["policies"]) == 2


def test_zero_event_denominator_and_no_event_alert_rate_are_explicit() -> None:
    customer_ids = ("C000001", "C000002")
    context = TradeoffMeasurementContext(
        customer_ids=customer_ids,
        analysis_months=(12, 13),
        period_days=2,
    )
    anchors = (
        SyntheticEventAnchor("C000001", None, None),
        SyntheticEventAnchor("C000002", None, None),
    )
    with_candidate = build_timing_evidence(
        customer_ids=customer_ids,
        candidate_alert_moments=(CandidateAlertMoment("C000001", 12),),
        synthetic_event_anchors=anchors,
    )
    without_candidate = build_timing_evidence(
        customer_ids=customer_ids,
        candidate_alert_moments=(),
        synthetic_event_anchors=anchors,
    )
    report = build_alert_tradeoff_report(
        context=context,
        policy_evidence=(
            CandidatePolicyTimingEvidence("with", "With candidate", with_candidate),
            CandidatePolicyTimingEvidence("without", "Without candidate", without_candidate),
        ),
    )
    metrics = {policy.policy_id: policy for policy in report.policies}

    assert metrics["with"].synthetic_precision_proxy == pytest.approx(0.0)
    assert metrics["with"].synthetic_recall_proxy is None
    assert metrics["with"].no_event_alert_rate == pytest.approx(1.0)
    assert metrics["without"].synthetic_precision_proxy is None
    assert metrics["without"].synthetic_recall_proxy is None
    assert metrics["without"].no_event_alert_rate is None
    assert metrics["without"].review_episode_count == 0


def test_contiguous_alert_months_form_one_review_episode_without_dropping_gaps() -> None:
    context = TradeoffMeasurementContext(
        customer_ids=CUSTOMER_IDS,
        analysis_months=ANALYSIS_MONTHS,
        period_days=4,
    )
    episodic = _evidence(
        CandidateAlertMoment("C000001", 12),
        CandidateAlertMoment("C000001", 13),
        CandidateAlertMoment("C000001", 15),
    )
    comparison = _evidence(CandidateAlertMoment("C000003", 12))
    report = build_alert_tradeoff_report(
        context=context,
        policy_evidence=(
            CandidatePolicyTimingEvidence("episodic", "Episodic", episodic),
            CandidatePolicyTimingEvidence("comparison", "Comparison", comparison),
        ),
    )
    episodic_metrics = next(policy for policy in report.policies if policy.policy_id == "episodic")

    assert episodic_metrics.alert_moment_count == 3
    assert episodic_metrics.review_episode_count == 2
    assert episodic_metrics.mean_episode_length_months == pytest.approx(1.5)
    assert episodic_metrics.persistence_rate == pytest.approx(0.5)


def test_report_rejects_single_policy_and_mismatched_candidate_period() -> None:
    context = TradeoffMeasurementContext(
        customer_ids=CUSTOMER_IDS,
        analysis_months=(12, 13),
        period_days=2,
    )
    evidence = _evidence(CandidateAlertMoment("C000001", 12))
    outside_period = _evidence(CandidateAlertMoment("C000001", 14))

    with pytest.raises(ValueError, match="at least two"):
        build_alert_tradeoff_report(
            context=context,
            policy_evidence=(CandidatePolicyTimingEvidence("one", "One", evidence),),
        )
    with pytest.raises(ValueError, match="outside the shared analysis period"):
        build_alert_tradeoff_report(
            context=context,
            policy_evidence=(
                CandidatePolicyTimingEvidence("inside", "Inside", evidence),
                CandidatePolicyTimingEvidence("outside", "Outside", outside_period),
            ),
        )
