"""Read-only Customer Review models for the RM Workspace.

The module formats already-exported triage and population evidence with the
customer's observed history through its as-of month. It never scores,
matches, ranks, mutates cases, or loads target future-path fields.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from config import settings
from src.alert_case import AlertCase
from src.formatters import format_krw_compact, format_percent
from src.i18n import t
from src.labels import label_metric, label_status
from src.recommended_followup import build_recommended_follow_up
from src.triage_explainability import build_triage_ranking_explanation
from src.triage_selector import SELECTION_REASON_COPY
from src.triage_universe import TRIAGE_REASON_COPY


_OBSERVATION_COLUMNS = (
    "customer_id",
    "month",
    "savings_rate",
    "dsr",
    "fixed_expense_ratio",
    "cash_balance",
    "monthly_status",
)
_OPEN_ALERT_STATES = frozenset(
    {"NEW", "ACKNOWLEDGED", "IN_REVIEW", "FOLLOW_UP", "SNOOZED", "ESCALATED"}
)
_HISTORICAL_OUTCOME_ORDER = ("healthy", "recovered", "stress", "delinquent")
_SAFE_CUSTOMER_ID_CHARACTERS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
)
_PROSPECTIVE_SIGNAL_SOURCE = "prospective_signal"
_HISTORICAL_LANDMARK_SOURCE = "historical_landmark"
_POLICY_STATUSES = frozenset({"draft", "demo", "approved"})


@dataclass(frozen=True)
class RMCustomerObservation:
    """Current observed values and chart-ready history through one as-of month."""

    customer_id: str
    as_of_month: int
    current_values: Mapping[str, object] | None
    trajectory: pd.DataFrame
    load_error: str | None = None


def load_population_result_index(
    detail_path: Path | None = None,
) -> Mapping[str, Mapping[str, object]]:
    """Read the separate population detail artifact without changing it."""

    path = Path(
        detail_path
        or (settings.BASE_DIR / "artifacts" / "population" / "seed42_full_run" / "population_detail.json")
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    results = payload.get("results") if isinstance(payload, Mapping) else None
    if not isinstance(results, list):
        return {}
    index: dict[str, Mapping[str, object]] = {}
    for result in results:
        if not isinstance(result, Mapping):
            return {}
        customer_id = _safe_customer_id(result.get("customer_id"))
        if customer_id is None or customer_id in index:
            return {}
        index[customer_id] = result
    return index


def load_customer_observation(
    customer_id: str,
    *,
    as_of_month: int,
    monthly_path: Path | None = None,
) -> RMCustomerObservation:
    """Load only current/past display columns through the declared as-of month."""

    safe_customer_id = _safe_customer_id(customer_id)
    if safe_customer_id is None:
        return RMCustomerObservation("", as_of_month, None, pd.DataFrame(), "invalid_customer")
    path = Path(monthly_path or settings.CUSTOMER_MONTHLY_PATH)
    try:
        monthly_df = pd.read_csv(path, usecols=list(_OBSERVATION_COLUMNS))
    except (OSError, ValueError, pd.errors.ParserError):
        return RMCustomerObservation(safe_customer_id, as_of_month, None, pd.DataFrame(), "observation_unavailable")
    observed = monthly_df.loc[
        (monthly_df["customer_id"].astype(str) == safe_customer_id)
        & (monthly_df["month"] <= as_of_month),
        list(_OBSERVATION_COLUMNS),
    ].copy()
    observed = observed.sort_values("month").reset_index(drop=True)
    current = observed.loc[observed["month"] == as_of_month]
    if current.empty:
        return RMCustomerObservation(safe_customer_id, as_of_month, None, observed, "as_of_observation_missing")
    latest = current.iloc[-1]
    return RMCustomerObservation(
        customer_id=safe_customer_id,
        as_of_month=as_of_month,
        current_values={
            "savings_rate": float(latest["savings_rate"]),
            "dsr": float(latest["dsr"]),
            "fixed_expense_ratio": float(latest["fixed_expense_ratio"]),
            "cash_balance": float(latest["cash_balance"]),
            "monthly_status": str(latest["monthly_status"]),
        },
        trajectory=observed,
    )


def build_rm_customer_review_view_model(
    *,
    customer_id: str | None,
    selection_manifest: Mapping[str, object] | None,
    representative_cohort: Mapping[str, object] | None,
    population_results: Mapping[str, Mapping[str, object]],
    observation: RMCustomerObservation | None,
    alert_cases: Sequence[AlertCase] = (),
    language: str = "ko",
) -> dict[str, Any]:
    """Format one RM review page from persisted evidence only.

    Selection and why-now text are mapped directly from triage reason codes.
    Historical landmark information remains a separate retrospective section.
    """

    safe_customer_id = _safe_customer_id(customer_id)
    if safe_customer_id is None:
        return _unavailable_review_model(language=language, status="customer_not_selected")
    record = _selection_record(selection_manifest, safe_customer_id)
    if record is None:
        return _unavailable_review_model(language=language, status="selection_record_unavailable", customer_id=safe_customer_id)
    population_result = population_results.get(safe_customer_id)
    cohort_record = _representative_record(representative_cohort, safe_customer_id)
    as_of_month = _positive_int(record.get("as_of_month")) or _positive_int(record.get("signal_as_of_month"))
    matching_case = _matching_case(record, alert_cases)
    monitored_total = _manifest_monitored_total(selection_manifest)
    policy_metadata = _policy_display_metadata(selection_manifest)
    return {
        "available": True,
        "customer_id": safe_customer_id,
        "header": _header_model(
            record,
            cohort_record=cohort_record,
            matching_case=matching_case,
            monitored_total=monitored_total,
            policy_metadata=policy_metadata,
            language=language,
        ),
        "current_signals": _current_signal_model(observation, language=language),
        "chart_trajectory": pd.DataFrame() if observation is None else observation.trajectory.copy(),
        "prospective_timing": _prospective_timing_model(
            record,
            policy_metadata=policy_metadata,
            language=language,
        ),
        "twin_evidence": _twin_evidence_model(population_result, record, language=language),
        "historical_landmark": _historical_landmark_model(population_result, language=language),
        "recommended_follow_up": _recommended_follow_up_model(matching_case, language=language),
        "workflow_case": _workflow_case_model(matching_case),
        "provenance": {
            "policy_id": record.get("policy_id"),
            "policy_version": record.get("policy_version"),
            "selection_as_of_month": as_of_month,
            "signal_run_id": record.get("signal_run_id"),
            "selection_manifest_only": True,
            "policy_status": policy_metadata["status"],
            "policy_limitations": policy_metadata["limitations"],
        },
        "scope": {
            "analytics_recomputed": False,
            "triage_recomputed": False,
            "future_data_loaded": False,
            "case_mutated": False,
        },
    }


def _unavailable_review_model(
    *, language: str,
    status: str,
    customer_id: str | None = None,
) -> dict[str, Any]:
    return {
        "available": False,
        "customer_id": customer_id,
        "status": status,
        "message": t("rm.review.unavailable", language),
        "scope": {
            "analytics_recomputed": False,
            "triage_recomputed": False,
            "future_data_loaded": False,
            "case_mutated": False,
        },
    }


def _selection_record(
    manifest: Mapping[str, object] | None,
    customer_id: str,
) -> Mapping[str, object] | None:
    records = manifest.get("records") if isinstance(manifest, Mapping) else None
    if not isinstance(records, list):
        return None
    matches = [
        record
        for record in records
        if isinstance(record, Mapping) and record.get("customer_id") == customer_id
    ]
    return matches[0] if len(matches) == 1 else None


def _representative_record(
    cohort: Mapping[str, object] | None,
    customer_id: str,
) -> Mapping[str, object] | None:
    records = cohort.get("records") if isinstance(cohort, Mapping) else None
    if not isinstance(records, list):
        return None
    matches = [
        record
        for record in records
        if isinstance(record, Mapping)
        and record.get("customer_id") == customer_id
        and record.get("status") == "selected"
    ]
    return matches[0] if len(matches) == 1 else None


def _header_model(
    record: Mapping[str, object],
    *,
    cohort_record: Mapping[str, object] | None,
    matching_case: AlertCase | None,
    monitored_total: int | None,
    policy_metadata: Mapping[str, object],
    language: str,
) -> dict[str, object]:
    selected = bool(record.get("selected_for_review")) and record.get("selection_disposition") == "SELECTED_FOR_REVIEW"
    deferred = record.get("selection_disposition") == "DEFERRED_CAPACITY"
    context_type = (
        "operational_queue"
        if selected
        else "deferred_capacity"
        if deferred
        else "representative_comparison"
        if cohort_record is not None
        else "non_operational"
    )
    reason_codes = _string_tuple(record.get("selection_reason_codes"))
    why_now_codes = _string_tuple(record.get("why_now_reason_codes"))
    return {
        "operational_label": str(record.get("eligibility_label", "")),
        "case_state": matching_case.state if matching_case is not None else "NO_OPEN_ALERT",
        "alert_id": None if matching_case is None else matching_case.alert_id,
        "due_at": None if matching_case is None else matching_case.due_at.isoformat(),
        "context_type": context_type,
        "context_label": t(f"rm.review.context.{context_type}", language),
        "selection_rank": _positive_int(record.get("review_priority_rank")),
        "selection_reason": _selection_reason_sentence(
            selected=selected,
            deferred=deferred,
            monitored_total=monitored_total,
            rank=_positive_int(record.get("review_priority_rank")),
            reason_codes=reason_codes,
            language=language,
        ),
        "why_now": _why_now_sentence(why_now_codes, language=language),
        "selection_reason_codes": reason_codes,
        "why_now_reason_codes": why_now_codes,
        "why_now_evidence": {
            "source": _PROSPECTIVE_SIGNAL_SOURCE,
            "reason_codes": why_now_codes,
            "observation_window": "current_and_prior_only",
            "policy_status": policy_metadata["status"],
            "policy_limitations": policy_metadata["limitations"],
        },
        "ranking_explanation": build_triage_ranking_explanation(record, language=language),
        "representative_category": None if cohort_record is None else cohort_record.get("category_id"),
    }


def _manifest_monitored_total(manifest: Mapping[str, object] | None) -> int | None:
    funnel = manifest.get("funnel") if isinstance(manifest, Mapping) else None
    value = funnel.get("monitored_total") if isinstance(funnel, Mapping) else None
    return _positive_int(value)


def _policy_display_metadata(manifest: Mapping[str, object] | None) -> dict[str, object]:
    """Read persisted demo-policy provenance without evaluating a policy in the UI."""

    policy = manifest.get("selection_policy") if isinstance(manifest, Mapping) else None
    if not isinstance(policy, Mapping):
        return {"status": "unavailable", "limitations": ()}
    status = str(policy.get("status", "unavailable"))
    if status not in _POLICY_STATUSES:
        status = "unavailable"
    limitations_value = policy.get("limitations")
    limitations = (
        tuple(item for item in limitations_value if isinstance(item, str) and item.strip())
        if isinstance(limitations_value, list)
        else ()
    )
    return {"status": status, "limitations": limitations}


def _selection_reason_sentence(
    *,
    selected: bool,
    deferred: bool,
    monitored_total: int | None,
    rank: int | None,
    reason_codes: tuple[str, ...],
    language: str,
) -> str:
    if selected:
        return t(
            "rm.review.selection.selected",
            language,
            population=("—" if monitored_total is None else f"{monitored_total:,}"),
            rank=("—" if rank is None else f"{rank:,}"),
            reason=_reason_copy(reason_codes[0] if reason_codes else "", language),
        )
    if deferred:
        return t("rm.review.selection.deferred", language, reason=_reason_copy(reason_codes[0] if reason_codes else "", language))
    return t("rm.review.selection.not_queue", language, reason=_reason_copy(reason_codes[0] if reason_codes else "", language))


def _why_now_sentence(reason_codes: tuple[str, ...], *, language: str) -> str:
    if not reason_codes:
        return t("rm.review.why_now.unavailable", language)
    return t("rm.review.why_now", language, reasons="; ".join(_reason_copy(code, language) for code in reason_codes))


def _current_signal_model(
    observation: RMCustomerObservation | None,
    *,
    language: str,
) -> dict[str, object]:
    if observation is None or observation.current_values is None:
        return {"available": False, "message": t("rm.review.current.unavailable", language), "items": ()}
    values = observation.current_values
    return {
        "available": True,
        "as_of_month": observation.as_of_month,
        "items": (
            _signal_item("savings_rate", values.get("savings_rate"), format_percent(values.get("savings_rate")), language),
            _signal_item("dsr", values.get("dsr"), format_percent(values.get("dsr")), language),
            _signal_item("fixed_expense_ratio", values.get("fixed_expense_ratio"), format_percent(values.get("fixed_expense_ratio")), language),
            _signal_item("cash_balance", values.get("cash_balance"), format_krw_compact(values.get("cash_balance"), language=language), language),
            {
                "id": "monthly_status",
                "label": t("rm.review.current.status", language),
                "value": label_status(values.get("monthly_status"), language),
                "raw_value": values.get("monthly_status"),
            },
        ),
    }


def _signal_item(metric: str, raw_value: object, display_value: str, language: str) -> dict[str, object]:
    return {
        "id": metric,
        "label": label_metric(metric, language),
        "value": display_value,
        "raw_value": raw_value,
    }


def _prospective_timing_model(
    record: Mapping[str, object],
    *,
    policy_metadata: Mapping[str, object],
    language: str,
) -> dict[str, object]:
    evidence = record.get("timing_evidence_reference")
    if not isinstance(evidence, Mapping) or evidence.get("source") != _PROSPECTIVE_SIGNAL_SOURCE:
        return {"available": False, "message": t("rm.review.timing.unavailable", language)}
    label = str(record.get("eligibility_label", ""))
    return {
        "available": True,
        "operational_label": label,
        "timing_bucket": str(record.get("timing_bucket", "unavailable")),
        "candidate_month": _positive_int(evidence.get("candidate_month")),
        "evaluation_status": str(evidence.get("evaluation_status", "unavailable")),
        "source": _PROSPECTIVE_SIGNAL_SOURCE,
        "source_metadata": {
            "observation_window": "current_and_prior_only",
            "retrospective_backtest_scope": "policy_validation_only",
            "historical_landmark_used": False,
        },
        "policy_status": policy_metadata["status"],
        "policy_limitations": policy_metadata["limitations"],
        "message": t("rm.review.timing.current", language, label=label),
        "lead_time_message": t("rm.review.timing.not_evaluated", language),
    }


def _twin_evidence_model(
    population_result: Mapping[str, object] | None,
    record: Mapping[str, object],
    *,
    language: str,
) -> dict[str, object]:
    if not isinstance(population_result, Mapping) or population_result.get("analysis_status") != "success":
        return {"available": False, "message": t("rm.review.twin.unavailable", language)}
    shares = population_result.get("historical_outcome_shares")
    distance = population_result.get("distance_summary")
    distribution = []
    if isinstance(shares, Mapping):
        for outcome in _HISTORICAL_OUTCOME_ORDER:
            share = shares.get(outcome)
            if isinstance(share, (int, float)) and not isinstance(share, bool):
                distribution.append(
                    {"outcome": label_status(outcome, language), "share": float(share), "display_share": format_percent(float(share))}
                )
    return {
        "available": True,
        "matched_count": _positive_int(population_result.get("matched_count")),
        "historical_outcome_distribution": tuple(distribution),
        "distance_mean": _number_or_none(distance.get("mean")) if isinstance(distance, Mapping) else None,
        "distance_median": _number_or_none(distance.get("median")) if isinstance(distance, Mapping) else None,
        "neighbor_stability": str(record.get("signal_stability", "not_available")),
        "signal_persistence": str(record.get("signal_persistence", "not_available")),
        "description": t("rm.review.twin.description", language),
    }


def _historical_landmark_model(
    population_result: Mapping[str, object] | None,
    *,
    language: str,
) -> dict[str, object]:
    if not isinstance(population_result, Mapping):
        return {
            "status": "unavailable",
            "source": _HISTORICAL_LANDMARK_SOURCE,
            "is_live_alert_trigger": False,
            "message": t("rm.review.landmark.unavailable", language),
        }
    status = str(population_result.get("breakpoint_status", "not_found"))
    if status == "found":
        return {
            "status": "found",
            "source": _HISTORICAL_LANDMARK_SOURCE,
            "is_live_alert_trigger": False,
            "month": _positive_int(population_result.get("breakpoint_month")),
            "factor": label_metric(population_result.get("breakpoint_factor"), language),
            "message": t("rm.review.landmark.found", language),
            "caption": t("rm.review.landmark.caption", language),
        }
    if status == "insufficient_group_size":
        message_key = "rm.review.landmark.insufficient"
    else:
        message_key = "rm.review.landmark.not_found"
    return {
        "status": status,
        "source": _HISTORICAL_LANDMARK_SOURCE,
        "is_live_alert_trigger": False,
        "month": None,
        "factor": None,
        "message": t(message_key, language),
        "caption": t("rm.review.landmark.caption", language),
    }


def _recommended_follow_up_model(case: AlertCase | None, *, language: str) -> dict[str, object]:
    if case is None:
        return {
            "available": False,
            "title": "Recommended Follow-up",
            "message": t("rm.review.follow_up.pending", language),
            "actions": (),
            "reason_codes": (),
            "timing_evidence_reference": None,
            "scope": {
                "automatic_execution": False,
                "automatic_financial_decision": False,
                "action_effectiveness_estimated": False,
            },
            "whatif_supporting_evidence": {
                "available": False,
                "message": t("rm.review.whatif.unavailable", language),
                "estimates_action_effectiveness": False,
            },
        }
    if case.state == "CLOSED":
        return {
            "available": False,
            "title": "Recommended Follow-up",
            "message": t("rm.review.follow_up.closed", language),
            "actions": (),
            "reason_codes": (),
            "timing_evidence_reference": None,
            "scope": {
                "automatic_execution": False,
                "automatic_financial_decision": False,
                "action_effectiveness_estimated": False,
            },
            "whatif_supporting_evidence": {
                "available": False,
                "message": t("rm.review.whatif.unavailable", language),
                "estimates_action_effectiveness": False,
            },
        }
    follow_up = build_recommended_follow_up(case)
    return {
        "available": True,
        "title": follow_up.title,
        "urgency": follow_up.urgency,
        "actions": follow_up.recommended_actions,
        "reason_codes": follow_up.reason_codes,
        "timing_evidence_reference": follow_up.timing_evidence_reference.to_dict(),
        "scope": follow_up.to_dict()["scope"],
        "message": t("rm.review.follow_up.available", language),
        "whatif_supporting_evidence": {
            "available": False,
            "message": t("rm.review.whatif.unavailable", language),
            "estimates_action_effectiveness": False,
        },
    }


def _workflow_case_model(case: AlertCase | None) -> dict[str, object]:
    """Expose only the case identity/state needed by the UI service boundary."""

    if case is None:
        return {"available": False, "alert_id": None, "state": None}
    return {
        "available": True,
        "alert_id": case.alert_id,
        "state": case.state,
    }


def _matching_case(record: Mapping[str, object], cases: Sequence[AlertCase]) -> AlertCase | None:
    """Prefer an open case, falling back to the newest closed case for audit/reopen."""

    matches = [
        case
        for case in cases
        if case.customer_id == record.get("customer_id")
        and case.policy_id == record.get("policy_id")
        and case.policy_version == record.get("policy_version")
        and case.signal_run_id == record.get("signal_run_id")
        and case.signal_as_of_month == record.get("signal_as_of_month")
    ]
    open_matches = [case for case in matches if case.state in _OPEN_ALERT_STATES]
    if open_matches:
        return min(open_matches, key=lambda case: case.alert_id)
    return max(matches, key=lambda case: (case.updated_at, case.alert_id)) if matches else None


def _reason_copy(code: str, language: str) -> str:
    if not code:
        return t("rm.review.reason.unavailable", language)
    translated = t(f"rm.review.reason.{code}", language)
    if translated != f"rm.review.reason.{code}":
        return translated
    return TRIAGE_REASON_COPY.get(code, SELECTION_REASON_COPY.get(code, code))


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item.strip())


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def _number_or_none(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _safe_customer_id(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    if any(character not in _SAFE_CUSTOMER_ID_CHARACTERS for character in value):
        return None
    return value
