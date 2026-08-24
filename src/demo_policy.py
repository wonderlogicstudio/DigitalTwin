"""Versioned, prospective-only demo policy for downstream triage input.

The policy evaluates a :class:`~src.prospective_signals.SignalSnapshot` that
was already constructed from current and prior observations.  It does not
select an RM queue, create an alert, or look up synthetic future outcomes.
Historical breakpoint landmarks are display-only context in a separate field
so they cannot become a policy trigger.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from src.prospective_signals import SignalSnapshot


POLICY_SCHEMA_VERSION = "versioned_demo_policy.v1"
POLICY_STATUSES = ("draft", "demo", "approved")
OPERATIONAL_LABELS = ("Monitor", "Review", "Priority Review")
PROSPECTIVE_SIGNAL_SOURCE = "prospective_signal"
HISTORICAL_LANDMARK_SOURCE = "historical_landmark"

PolicyStatus = Literal["draft", "demo", "approved"]
OperationalLabel = Literal["Monitor", "Review", "Priority Review"]
TimingSource = Literal["prospective_signal", "historical_landmark"]


@dataclass(frozen=True)
class DemoPolicyRule:
    """One declared signal rule; rules are policy metadata, not model tuning."""

    rule_id: str
    signal: Literal[
        "current_status",
        "financial_stress_factor_count",
        "persistent_financial_stress_factor_count",
    ]
    operator: Literal["in", "gte"]
    threshold: tuple[str, ...] | int
    operational_label: OperationalLabel
    reason_template: str

    def __post_init__(self) -> None:
        if not str(self.rule_id).strip() or not str(self.reason_template).strip():
            raise ValueError("rule_id and reason_template must be non-empty")
        if self.operational_label not in OPERATIONAL_LABELS:
            raise ValueError(f"operational_label must be one of {OPERATIONAL_LABELS}")
        if self.signal == "current_status":
            if self.operator != "in" or not isinstance(self.threshold, tuple) or not self.threshold:
                raise ValueError("current_status rules require a non-empty tuple threshold and 'in'")
            if any(not str(value).strip() for value in self.threshold):
                raise ValueError("current_status thresholds must be non-empty")
        elif self.operator != "gte" or isinstance(self.threshold, bool) or not isinstance(self.threshold, int):
            raise ValueError("factor-count rules require an integer threshold and 'gte'")
        elif self.threshold < 1:
            raise ValueError("factor-count thresholds must be at least one")

    def to_dict(self) -> dict[str, object]:
        threshold: object = list(self.threshold) if isinstance(self.threshold, tuple) else self.threshold
        return {
            "rule_id": self.rule_id,
            "signal": self.signal,
            "operator": self.operator,
            "threshold": threshold,
            "operational_label": self.operational_label,
            "reason_template": self.reason_template,
        }


@dataclass(frozen=True)
class VersionedDemoPolicy:
    """A versioned policy candidate, deliberately not production-approved by default."""

    policy_id: str
    version: str
    status: PolicyStatus = "draft"
    rules: tuple[DemoPolicyRule, ...] = ()
    persistence_months: int = 2
    cooldown_months: int = 1
    source_backtest_run: str = ""
    rationale: str = ""
    limitations: tuple[str, ...] = ()
    approval_evidence: str | None = None
    schema_version: str = POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not str(self.policy_id).strip() or not str(self.version).strip():
            raise ValueError("policy_id and version must be non-empty")
        if self.status not in POLICY_STATUSES:
            raise ValueError(f"status must be one of {POLICY_STATUSES}")
        if not self.rules:
            raise ValueError("a policy must declare at least one rule")
        rule_ids = [rule.rule_id for rule in self.rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("policy rule IDs must be unique")
        for field_name, value in (
            ("persistence_months", self.persistence_months),
            ("cooldown_months", self.cooldown_months),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if not str(self.source_backtest_run).strip():
            raise ValueError("source_backtest_run must be non-empty")
        if not str(self.rationale).strip():
            raise ValueError("rationale must be non-empty")
        if not self.limitations or any(not str(item).strip() for item in self.limitations):
            raise ValueError("limitations must contain at least one non-empty statement")
        if self.status == "approved" and not str(self.approval_evidence or "").strip():
            raise ValueError("approved policies require explicit approval_evidence")
        if self.schema_version != POLICY_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {POLICY_SCHEMA_VERSION}")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "version": self.version,
            "status": self.status,
            "rules": [rule.to_dict() for rule in self.rules],
            "persistence_months": self.persistence_months,
            "cooldown_months": self.cooldown_months,
            "source_backtest_run": self.source_backtest_run,
            "rationale": self.rationale,
            "limitations": list(self.limitations),
            "approval_evidence": self.approval_evidence,
        }


@dataclass(frozen=True)
class PolicyEvaluationContext:
    """Current policy-history input only; no future event information is accepted."""

    months_since_last_eligible: int | None = None

    def __post_init__(self) -> None:
        if self.months_since_last_eligible is not None and (
            isinstance(self.months_since_last_eligible, bool)
            or not isinstance(self.months_since_last_eligible, int)
            or self.months_since_last_eligible < 0
        ):
            raise ValueError("months_since_last_eligible must be a non-negative integer or None")


@dataclass(frozen=True)
class PolicyTimingEvidence:
    """Prospective timing context at the decision point, without a future event."""

    candidate_month: int
    source: Literal["prospective_signal"] = PROSPECTIVE_SIGNAL_SOURCE
    evaluation_status: str = "not_evaluated"
    lead_time_months: None = None

    def __post_init__(self) -> None:
        if isinstance(self.candidate_month, bool) or not isinstance(self.candidate_month, int) or self.candidate_month < 1:
            raise ValueError("candidate_month must be a positive integer")
        if self.source != PROSPECTIVE_SIGNAL_SOURCE:
            raise ValueError("prospective timing source must be prospective_signal")
        if not str(self.evaluation_status).strip():
            raise ValueError("evaluation_status must be non-empty")
        if self.lead_time_months is not None:
            raise ValueError("customer-level policy timing cannot contain lead_time_months")

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_month": self.candidate_month,
            "source": self.source,
            "evaluation_status": self.evaluation_status,
            "lead_time_months": self.lead_time_months,
            "lead_time_unit": "months",
        }


@dataclass(frozen=True)
class HistoricalLandmarkContext:
    """Display-only historical matched-cohort landmark, never a policy trigger."""

    breakpoint_status: str
    breakpoint_month: int | None
    source: Literal["historical_landmark"] = HISTORICAL_LANDMARK_SOURCE
    is_live_alert_trigger: bool = False

    def __post_init__(self) -> None:
        if not str(self.breakpoint_status).strip():
            raise ValueError("breakpoint_status must be non-empty")
        if self.breakpoint_month is not None and (
            isinstance(self.breakpoint_month, bool)
            or not isinstance(self.breakpoint_month, int)
            or self.breakpoint_month < 1
        ):
            raise ValueError("breakpoint_month must be a positive integer or None")
        if self.source != HISTORICAL_LANDMARK_SOURCE:
            raise ValueError("historical landmark source must be historical_landmark")
        if self.is_live_alert_trigger:
            raise ValueError("historical landmarks cannot be live alert triggers")

    def to_dict(self) -> dict[str, object]:
        return {
            "breakpoint_status": self.breakpoint_status,
            "breakpoint_month": self.breakpoint_month,
            "source": self.source,
            "is_live_alert_trigger": False,
        }


@dataclass(frozen=True)
class PolicyAssessment:
    """Triage input only; it is explicitly not an RM queue or alert decision."""

    customer_id: str
    as_of_month: int
    policy_id: str
    policy_version: str
    policy_status: PolicyStatus
    eligibility: bool
    operational_label: OperationalLabel
    matched_rule_ids: tuple[str, ...]
    why_now_reasons: tuple[str, ...]
    cooldown_applied: bool
    prospective_timing_evidence: PolicyTimingEvidence
    historical_landmark_context: HistoricalLandmarkContext | None
    triage_input_only: bool = True
    rm_queue_selection: bool = False
    alert_creation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "as_of_month": self.as_of_month,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "policy_status": self.policy_status,
            "eligibility": self.eligibility,
            "operational_label": self.operational_label,
            "matched_rule_ids": list(self.matched_rule_ids),
            "why_now_reasons": list(self.why_now_reasons),
            "cooldown_applied": self.cooldown_applied,
            "prospective_timing_evidence": self.prospective_timing_evidence.to_dict(),
            "historical_landmark_context": (
                None
                if self.historical_landmark_context is None
                else self.historical_landmark_context.to_dict()
            ),
            "scope": {
                "triage_input_only": self.triage_input_only,
                "rm_queue_selection": self.rm_queue_selection,
                "alert_creation": self.alert_creation,
            },
        }


def default_demo_policy() -> VersionedDemoPolicy:
    """Return the current synthetic demo policy, never an approved default."""

    return VersionedDemoPolicy(
        policy_id="synthetic_early_warning_demo",
        version="0.1.0",
        status="demo",
        rules=(
            DemoPolicyRule(
                rule_id="current_stress_or_delinquent",
                signal="current_status",
                operator="in",
                threshold=("stress", "delinquent"),
                operational_label="Priority Review",
                reason_template="Current status is {current_status}.",
            ),
            DemoPolicyRule(
                rule_id="persistent_financial_stress",
                signal="persistent_financial_stress_factor_count",
                operator="gte",
                threshold=1,
                operational_label="Review",
                reason_template="Persistent financial stress factors: {persistent_factors}.",
            ),
            DemoPolicyRule(
                rule_id="multiple_current_financial_stress_factors",
                signal="financial_stress_factor_count",
                operator="gte",
                threshold=2,
                operational_label="Review",
                reason_template="Multiple current financial stress factors: {current_factors}.",
            ),
            DemoPolicyRule(
                rule_id="current_financial_stress_factor",
                signal="financial_stress_factor_count",
                operator="gte",
                threshold=1,
                operational_label="Monitor",
                reason_template="Current financial stress factor: {current_factors}.",
            ),
        ),
        persistence_months=2,
        cooldown_months=1,
        source_backtest_run="crossfit_seed42_5fold_asof12",
        rationale=(
            "Synthetic demo policy that makes current financial stress and immediately prior-month "
            "persistence visible for downstream human triage."
        ),
        limitations=(
            "Synthetic results are not bank accuracy, effectiveness, or performance evidence.",
            "The policy is a demo candidate; no production threshold or RM review capacity is approved.",
            "Historical breakpoint context is retrospective and is not a prospective trigger.",
        ),
    )


def assess_policy_snapshot(
    policy: VersionedDemoPolicy,
    snapshot: SignalSnapshot,
    *,
    context: PolicyEvaluationContext | None = None,
    historical_landmark_context: HistoricalLandmarkContext | None = None,
) -> PolicyAssessment:
    """Evaluate declared rules against one current-and-prior-only snapshot.

    The returned eligibility is a policy signal for a later triage stage.  It
    does not decide a queue position or create a review work item.
    """

    evaluation_context = context or PolicyEvaluationContext()
    matched_rules = tuple(rule for rule in policy.rules if _rule_matches(rule, snapshot))
    highest_label = _highest_label((rule.operational_label for rule in matched_rules), default="Monitor")
    reasons = tuple(_format_reason(rule, snapshot) for rule in matched_rules)
    cooldown_applied = _cooldown_applies(policy, evaluation_context, bool(matched_rules))
    if cooldown_applied:
        eligibility = False
        operational_label: OperationalLabel = "Monitor"
        reasons = (*reasons, "Demo policy cooldown is active; defer this signal to subsequent triage.")
    elif matched_rules:
        eligibility = True
        operational_label = highest_label
    else:
        eligibility = False
        operational_label = "Monitor"
        reasons = ("No demo policy rule is currently met; retain monitor-only context.",)

    return PolicyAssessment(
        customer_id=snapshot.customer_id,
        as_of_month=snapshot.as_of_month,
        policy_id=policy.policy_id,
        policy_version=policy.version,
        policy_status=policy.status,
        eligibility=eligibility,
        operational_label=operational_label,
        matched_rule_ids=tuple(rule.rule_id for rule in matched_rules),
        why_now_reasons=reasons,
        cooldown_applied=cooldown_applied,
        prospective_timing_evidence=PolicyTimingEvidence(candidate_month=snapshot.as_of_month),
        historical_landmark_context=historical_landmark_context,
    )


def _rule_matches(rule: DemoPolicyRule, snapshot: SignalSnapshot) -> bool:
    if rule.signal == "current_status":
        assert isinstance(rule.threshold, tuple)
        return snapshot.current_status in rule.threshold
    if rule.signal == "financial_stress_factor_count":
        assert isinstance(rule.threshold, int)
        return len(snapshot.financial_stress_factors) >= rule.threshold
    assert rule.signal == "persistent_financial_stress_factor_count"
    assert isinstance(rule.threshold, int)
    return len(snapshot.persistent_financial_stress_factors) >= rule.threshold


def _format_reason(rule: DemoPolicyRule, snapshot: SignalSnapshot) -> str:
    return rule.reason_template.format(
        current_status=snapshot.current_status,
        current_factors=", ".join(snapshot.financial_stress_factors),
        persistent_factors=", ".join(snapshot.persistent_financial_stress_factors),
    )


def _highest_label(
    labels: object,
    *,
    default: OperationalLabel,
) -> OperationalLabel:
    priority = {"Monitor": 0, "Review": 1, "Priority Review": 2}
    return max(labels, key=lambda label: priority[label], default=default)


def _cooldown_applies(
    policy: VersionedDemoPolicy,
    context: PolicyEvaluationContext,
    has_matching_rule: bool,
) -> bool:
    return bool(
        has_matching_rule
        and policy.cooldown_months > 0
        and context.months_since_last_eligible is not None
        and context.months_since_last_eligible < policy.cooldown_months
    )
