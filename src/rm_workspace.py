"""Read-only display models for the separate RM Workspace application mode.

This module joins exported triage decisions with the workflow repository for
display only. It never re-runs analytics, ranks customers, changes triage, or
mutates Alert/Case data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from config import settings
from src.alert_case import AlertCase
from src.alert_repository import AlertCaseRepositoryError, FileAlertCaseRepository
from src.i18n import t
from src.triage_explainability import humanize_reason_codes


# Keep the RM route import-safe even while the page is reloading an older
# in-memory copy of the sidebar options that predates the third mode. The
# sidebar still receives its canonical three-mode list from ``src.copy``.
RM_WORKSPACE_MODE = "RM 업무 모드"
RM_WORKSPACE_TAB_KEYS = (
    "rm.tab.portfolio",
    "rm.tab.review_queue",
    "rm.tab.customer_review",
    "rm.tab.activity_audit",
)
_COHORT_CATEGORIES = (
    ("priority_review", "rm.representative.priority"),
    ("early_signal_review", "rm.representative.review"),
    ("monitor_no_alert_comparison", "rm.representative.monitor"),
    ("insufficient_or_landmark_not_found", "rm.representative.insufficient"),
)
_SAFE_CUSTOMER_ID_CHARACTERS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
)
_REQUIRED_FUNNEL_KEYS = (
    "monitored_total",
    "eligible_priority",
    "eligible_review",
    "eligible_total",
    "selected_queue_ready",
    "deferred_capacity",
    "monitor_only",
    "no_actionable_signal",
    "insufficient_evidence",
    "data_unavailable",
)
_OPEN_ALERT_STATES = frozenset(
    {"NEW", "ACKNOWLEDGED", "IN_REVIEW", "FOLLOW_UP", "SNOOZED", "ESCALATED"}
)
_PRIORITY_ORDER = {"Priority Review": 0, "Review": 1}


@dataclass(frozen=True)
class RMWorkspaceArtifacts:
    """A non-mutating snapshot of optional triage exports for UI display."""

    funnel: Mapping[str, object] | None
    representative_cohort: Mapping[str, object] | None
    source_reference: str | None
    load_error: str | None = None
    selection_manifest: Mapping[str, object] | None = None


@dataclass(frozen=True)
class RMAlertRepositorySnapshot:
    """A read-only workflow snapshot; failures do not hide the triage queue."""

    cases: tuple[AlertCase, ...]
    load_error: str | None = None


def get_rm_workspace_tab_labels(language: str = "ko") -> list[str]:
    """Return the four localized RM workspace tabs, separate from Presentation."""

    return [t(key, language) for key in RM_WORKSPACE_TAB_KEYS]


def load_rm_workspace_artifacts(
    artifact_root: Path | None = None,
) -> RMWorkspaceArtifacts:
    """Load the most recent deterministic triage export without changing it."""

    root = Path(artifact_root or (settings.BASE_DIR / "artifacts" / "triage"))
    manifest_paths = sorted(root.glob("*/rm_selection_manifest.json"))
    if not manifest_paths:
        return RMWorkspaceArtifacts(None, None, None)
    manifest_path = manifest_paths[-1]
    cohort_path = manifest_path.with_name("rm_representative_cohort.json")
    try:
        manifest = _read_object(manifest_path)
        cohort = _read_object(cohort_path) if cohort_path.exists() else None
    except (OSError, ValueError, json.JSONDecodeError):
        return RMWorkspaceArtifacts(None, None, str(manifest_path), load_error="artifact_unavailable")
    if not _manifest_is_usable(manifest):
        return RMWorkspaceArtifacts(None, None, str(manifest_path), load_error="artifact_unavailable")
    funnel = manifest["funnel"]
    assert isinstance(funnel, Mapping)
    return RMWorkspaceArtifacts(
        funnel=funnel,
        representative_cohort=cohort,
        source_reference=str(manifest_path),
        selection_manifest=manifest,
    )


def load_rm_alert_cases(
    workflow_root: Path | None = None,
) -> RMAlertRepositorySnapshot:
    """Read workflow cases through their repository boundary; never write files."""

    root = Path(workflow_root or (settings.BASE_DIR / "artifacts" / "workflow"))
    try:
        cases = FileAlertCaseRepository(root).list_cases()
    except (AlertCaseRepositoryError, OSError, ValueError):
        return RMAlertRepositorySnapshot((), load_error="repository_unavailable")
    return RMAlertRepositorySnapshot(cases)


def build_rm_workspace_view_model(
    *,
    language: str = "ko",
    funnel: Mapping[str, object] | None = None,
    representative_cohort: Mapping[str, object] | None = None,
    customer_context: str | None = None,
) -> dict[str, Any]:
    """Build the compact shell from exports; never compute RM selection."""

    total = _count_or_none((funnel or {}).get("monitored_total"))
    candidates = _count_or_none((funnel or {}).get("eligible_total"))
    selected = _count_or_none((funnel or {}).get("selected_queue_ready"))
    return {
        "mode": RM_WORKSPACE_MODE,
        "title": t("rm.header.title", language),
        "subtitle": t("rm.header.subtitle", language),
        "tabs": get_rm_workspace_tab_labels(language),
        "funnel": (
            _funnel_stage("population", "rm.funnel.population", total, language),
            _funnel_stage("review_candidates", "rm.funnel.candidates", candidates, language),
            _funnel_stage("selected_queue", "rm.funnel.selected_queue", selected, language),
        ),
        "representative_quick_selects": _representative_quick_selects(
            representative_cohort,
            language=language,
        ),
        "customer_review_target": _safe_customer_context(customer_context),
        "scope": {
            "analytics_recomputed": False,
            "triage_selection_changed": False,
            "case_mutated": False,
            "notification_sent": False,
        },
    }


def build_rm_portfolio_queue_view_model(
    *,
    selection_manifest: Mapping[str, object] | None,
    representative_cohort: Mapping[str, object] | None,
    alert_cases: Sequence[AlertCase] = (),
    language: str = "ko",
    priority_scope: str = "all",
    owner_scope: str = "all",
    due_scope: str = "all",
    search_query: str = "",
    sort_by: str = "rank",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Create a reconciled Portfolio and selected-only Review Queue view.

    Counts come directly from the selection manifest. The only derived values
    are display reconciliation checks and filters/sorting over those already
    selected records. Historical-landmark fields are deliberately excluded
    from queue rows.
    """

    if not _manifest_is_usable(selection_manifest):
        return _unavailable_portfolio_queue_model(language=language)

    assert selection_manifest is not None
    funnel = selection_manifest["funnel"]
    assert isinstance(funnel, Mapping)
    records = _selection_records(selection_manifest)
    selected_records = [record for record in records if _is_operational_queue_record(record)]
    selected_records.sort(key=_record_rank_key)
    case_by_customer = _matching_open_cases_by_customer(selected_records, alert_cases)
    reference_time = now or datetime.now(timezone.utc)
    queue_rows = [
        _queue_row(
            record,
            case_by_customer.get(str(record["customer_id"])),
            reference_time,
            language=language,
        )
        for record in selected_records
    ]
    queue_rows = _filter_queue_rows(
        queue_rows,
        priority_scope=priority_scope,
        owner_scope=owner_scope,
        due_scope=due_scope,
        search_query=search_query,
    )
    queue_rows = _sort_queue_rows(queue_rows, sort_by=sort_by)

    queue_open_cases = list(case_by_customer.values())
    reconciliation = _portfolio_reconciliation(
        selection_manifest,
        records=records,
        selected_records=selected_records,
        alert_case_count=len(queue_open_cases),
    )
    return {
        "available": True,
        "portfolio": {
            "funnel": tuple(
                _manifest_funnel_stage(key, _count_or_none(funnel.get(key)), language)
                for key in _REQUIRED_FUNNEL_KEYS
            ),
            "new_alert_count": sum(case.state == "NEW" for case in queue_open_cases),
            "open_alert_count": len(queue_open_cases),
            "case_in_rm_queue_count": len(queue_open_cases),
            "selected_case_pending_count": len(selected_records) - len(queue_open_cases),
            "due_alert_count": sum(_is_due(case, reference_time) for case in queue_open_cases),
            "overdue_alert_count": sum(_is_overdue(case, reference_time) for case in queue_open_cases),
            "reconciliation": reconciliation,
            "provenance": _selection_manifest_provenance(selection_manifest),
            "synthetic_demo": True,
            "delivery_definition": "in_app_rm_work_queue_case",
            "external_delivery_implemented": False,
        },
        "queue": {
            "source": "triage_selected_or_routed_existing_case",
            "unfiltered_count": len(selected_records),
            "filtered_count": len(queue_rows),
            "rows": tuple(queue_rows),
            "filters": {
                "priority_scope": priority_scope,
                "owner_scope": owner_scope,
                "due_scope": due_scope,
                "search_query": search_query,
                "sort_by": sort_by,
            },
        },
        "representative_comparisons": _representative_quick_selects(
            representative_cohort,
            language=language,
            allowed_customer_ids=_manifest_customer_ids(selection_manifest),
        ),
    }


def customer_context_from_queue_row(
    model: Mapping[str, object],
    customer_id: str | None,
) -> str | None:
    """Return a safe Customer Review context only for a visible queue row."""

    safe_id = _safe_customer_context(customer_id)
    queue = model.get("queue")
    rows = queue.get("rows") if isinstance(queue, Mapping) else None
    if safe_id is None or not isinstance(rows, Sequence):
        return None
    return (
        safe_id
        if any(isinstance(row, Mapping) and row.get("customer_id") == safe_id for row in rows)
        else None
    )


def _unavailable_portfolio_queue_model(*, language: str) -> dict[str, Any]:
    return {
        "available": False,
        "portfolio": {
            "funnel": tuple(_manifest_funnel_stage(key, None, language) for key in _REQUIRED_FUNNEL_KEYS),
            "new_alert_count": None,
            "open_alert_count": None,
            "case_in_rm_queue_count": None,
            "selected_case_pending_count": None,
            "due_alert_count": None,
            "overdue_alert_count": None,
            "reconciliation": {"is_exact": False, "status": "artifact_unavailable"},
            "provenance": _selection_manifest_provenance(None),
            "synthetic_demo": True,
            "delivery_definition": "in_app_rm_work_queue_case",
            "external_delivery_implemented": False,
        },
        "queue": {
            "source": "triage_selected_or_routed_existing_case",
            "unfiltered_count": 0,
            "filtered_count": 0,
            "rows": (),
            "filters": {},
        },
        "representative_comparisons": _representative_quick_selects(None, language=language),
    }


def _manifest_is_usable(manifest: Mapping[str, object] | None) -> bool:
    if not isinstance(manifest, Mapping):
        return False
    funnel = manifest.get("funnel")
    records = manifest.get("records")
    return (
        isinstance(funnel, Mapping)
        and isinstance(records, list)
        and all(key in funnel for key in _REQUIRED_FUNNEL_KEYS)
    )


def _selection_records(manifest: Mapping[str, object]) -> list[Mapping[str, object]]:
    records = manifest.get("records")
    if not isinstance(records, list):
        return []
    return [
        record
        for record in records
        if isinstance(record, Mapping)
        and _safe_customer_context(
            record.get("customer_id") if isinstance(record.get("customer_id"), str) else None
        )
    ]


def _is_operational_queue_record(record: Mapping[str, object]) -> bool:
    return (
        bool(record.get("selected_for_review"))
        and record.get("selection_disposition") == "SELECTED_FOR_REVIEW"
        and record.get("routing_disposition") in {"CREATE_NEW_CASE", "ROUTE_EXISTING_CASE"}
    )


def _record_rank_key(record: Mapping[str, object]) -> tuple[int, str]:
    rank = _count_or_none(record.get("review_priority_rank"))
    customer_id = str(record.get("customer_id", ""))
    return (rank if rank is not None else 2**31 - 1, customer_id)


def _matching_open_cases_by_customer(
    selected_records: Sequence[Mapping[str, object]],
    cases: Sequence[AlertCase],
) -> dict[str, AlertCase]:
    selected_by_customer = {str(record["customer_id"]): record for record in selected_records}
    result: dict[str, AlertCase] = {}
    for case in cases:
        record = selected_by_customer.get(case.customer_id)
        if (
            case.state not in _OPEN_ALERT_STATES
            or record is None
            or not _case_matches_selection_record(case, record)
        ):
            continue
        prior = result.get(case.customer_id)
        if prior is None or case.updated_at > prior.updated_at or (
            case.updated_at == prior.updated_at and case.alert_id < prior.alert_id
        ):
            result[case.customer_id] = case
    return result


def _case_matches_selection_record(case: AlertCase, record: Mapping[str, object]) -> bool:
    """Keep unrelated workflow cases out of the versioned triage queue."""

    return (
        case.policy_id == record.get("policy_id")
        and case.policy_version == record.get("policy_version")
        and case.signal_run_id == record.get("signal_run_id")
        and case.signal_as_of_month == record.get("signal_as_of_month")
    )


def _queue_row(
    record: Mapping[str, object], case: AlertCase | None, now: datetime, *, language: str
) -> dict[str, object]:
    timing = record.get("timing_evidence_reference")
    timing_reference = (
        timing
        if isinstance(timing, Mapping) and timing.get("source") == "prospective_signal"
        else {}
    )
    due_at = case.due_at if case is not None else None
    return {
        "customer_id": str(record["customer_id"]),
        "selection_rank": _count_or_none(record.get("review_priority_rank")),
        "priority": str(record.get("eligibility_label", "")),
        "case_state": case.state if case is not None else "NO_OPEN_ALERT",
        "work_queue_delivery_status": (
            "CASE_IN_RM_QUEUE" if case is not None else "SELECTED_CASE_PENDING"
        ),
        "selection_reason_codes": _string_tuple(record.get("selection_reason_codes")),
        "why_now_reason_codes": _string_tuple(record.get("why_now_reason_codes")),
        "selection_reason_details": humanize_reason_codes(
            record.get("selection_reason_codes"), language=language
        ),
        "why_now_reason_details": humanize_reason_codes(
            record.get("why_now_reason_codes"), language=language
        ),
        "timing_bucket": str(record.get("timing_bucket", "unavailable")),
        "timing_evidence_reference": dict(timing_reference),
        "due_at": due_at.isoformat() if due_at is not None else None,
        "due_status": _due_status(due_at, now),
        "created_at": case.created_at.isoformat() if case is not None else None,
        "owner_reference": case.owner_reference if case is not None else None,
        "updated_at": case.updated_at.isoformat() if case is not None else None,
        "routing_disposition": str(record.get("routing_disposition", "")),
        "case_alert_id": case.alert_id if case is not None else None,
    }


def _filter_queue_rows(
    rows: Sequence[dict[str, object]],
    *,
    priority_scope: str,
    owner_scope: str,
    due_scope: str,
    search_query: str,
) -> list[dict[str, object]]:
    query = search_query.strip().casefold()
    filtered: list[dict[str, object]] = []
    for row in rows:
        if priority_scope == "priority" and row["priority"] != "Priority Review":
            continue
        if priority_scope == "review" and row["priority"] != "Review":
            continue
        if owner_scope == "unassigned" and row["owner_reference"] is not None:
            continue
        if due_scope == "due_soon" and row["due_status"] not in {"due", "overdue"}:
            continue
        searchable = " ".join(
            [
                str(row["customer_id"]),
                " ".join(row["selection_reason_codes"]),
                " ".join(row["why_now_reason_codes"]),
            ]
        ).casefold()
        if query and query not in searchable:
            continue
        filtered.append(row)
    return filtered


def _sort_queue_rows(rows: Sequence[dict[str, object]], *, sort_by: str) -> list[dict[str, object]]:
    if sort_by == "due":
        return sorted(
            rows,
            key=lambda row: (row["due_at"] is None, row["due_at"] or "", row["customer_id"]),
        )
    if sort_by == "updated":
        return sorted(
            rows,
            key=lambda row: (row["updated_at"] is None, row["updated_at"] or "", row["customer_id"]),
            reverse=True,
        )
    return sorted(
        rows,
        key=lambda row: (
            row["selection_rank"] is None,
            row["selection_rank"] or 0,
            _PRIORITY_ORDER.get(str(row["priority"]), 99),
            row["customer_id"],
        ),
    )


def _portfolio_reconciliation(
    manifest: Mapping[str, object],
    *,
    records: Sequence[Mapping[str, object]],
    selected_records: Sequence[Mapping[str, object]],
    alert_case_count: int,
) -> dict[str, object]:
    funnel = manifest.get("funnel")
    manifest_reconciliation = manifest.get("reconciliation")
    assert isinstance(funnel, Mapping)
    expected_records = _count_or_none(funnel.get("monitored_total"))
    expected_selected = _count_or_none(funnel.get("selected_queue_ready"))
    declared_exact = (
        bool(manifest_reconciliation.get("is_exact"))
        if isinstance(manifest_reconciliation, Mapping)
        else False
    )
    records_exact = expected_records == len(records)
    unique_customer_ids = len({str(record["customer_id"]) for record in records}) == len(records)
    selected_exact = expected_selected == len(selected_records)
    return {
        "is_exact": bool(declared_exact and records_exact and unique_customer_ids and selected_exact),
        "manifest_exact": declared_exact,
        "record_count": len(records),
        "expected_record_count": expected_records,
        "unique_customer_ids": unique_customer_ids,
        "selected_count": len(selected_records),
        "expected_selected_count": expected_selected,
        "open_alert_count": alert_case_count,
        "status": "exact"
        if declared_exact and records_exact and unique_customer_ids and selected_exact
        else "reconciliation_failed",
    }


def _selection_manifest_provenance(
    manifest: Mapping[str, object] | None,
) -> dict[str, object | None]:
    """Expose saved selection provenance without deriving any RM decision."""

    if not isinstance(manifest, Mapping):
        return {
            "run_id": None,
            "schema_version": None,
            "policy_id": None,
            "policy_version": None,
            "policy_status": None,
            "selection_as_of_month": None,
            "signal_run_id": None,
            "capacity_scenario_id": None,
        }
    policy = manifest.get("selection_policy")
    capacity = manifest.get("capacity_scenario")
    return {
        "run_id": _string_or_none(manifest.get("run_id")),
        "schema_version": _string_or_none(manifest.get("schema_version")),
        "policy_id": _string_or_none(policy.get("policy_id")) if isinstance(policy, Mapping) else None,
        "policy_version": _string_or_none(policy.get("version")) if isinstance(policy, Mapping) else None,
        "policy_status": _string_or_none(policy.get("status")) if isinstance(policy, Mapping) else None,
        "selection_as_of_month": _count_or_none(manifest.get("triage_as_of_month")),
        "signal_run_id": _string_or_none(manifest.get("signal_run_id")),
        "capacity_scenario_id": (
            _string_or_none(capacity.get("scenario_id")) if isinstance(capacity, Mapping) else None
        ),
    }


def _manifest_funnel_stage(key: str, count: int | None, language: str) -> dict[str, object]:
    return {
        "id": key,
        "label": t(f"rm.portfolio.{key}", language),
        "count": count,
        "display_value": t("rm.value.unavailable", language)
        if count is None
        else f"{count:,}",
    }


def _funnel_stage(
    stage_id: str, label_key: str, count: int | None, language: str
) -> dict[str, object]:
    return {
        "id": stage_id,
        "label": t(label_key, language),
        "count": count,
        "display_value": t("rm.value.unavailable", language)
        if count is None
        else f"{count:,}",
    }


def _representative_quick_selects(
    cohort: Mapping[str, object] | None,
    *,
    language: str,
    allowed_customer_ids: frozenset[str] | None = None,
) -> tuple[dict[str, object], ...]:
    records_by_category: dict[str, Mapping[str, object]] = {}
    if cohort is not None and isinstance(cohort.get("records"), list):
        for record in cohort["records"]:
            if not isinstance(record, Mapping):
                continue
            category_id = record.get("category_id")
            if isinstance(category_id, str):
                records_by_category[category_id] = record
    quick_selects: list[dict[str, object]] = []
    for category_id, label_key in _COHORT_CATEGORIES:
        record = records_by_category.get(category_id)
        customer_id = record.get("customer_id") if record is not None else None
        available = bool(
            record is not None
            and record.get("status") == "selected"
            and _safe_customer_context(customer_id if isinstance(customer_id, str) else None)
            and (allowed_customer_ids is None or customer_id in allowed_customer_ids)
        )
        quick_selects.append(
            {
                "category_id": category_id,
                "label": t(label_key, language),
                "customer_id": customer_id if available else None,
                "available": available,
                "status": "available" if available else "unavailable",
                "operational_queue_row": False,
                "selection_reason_codes": _string_tuple(
                    None if record is None else record.get("selection_reason_codes")
                ),
                "selection_explanation": _string_or_none(
                    None if record is None else record.get("selection_explanation")
                ),
            }
        )
    return tuple(quick_selects)


def _manifest_customer_ids(manifest: Mapping[str, object]) -> frozenset[str]:
    records = manifest.get("records")
    if not isinstance(records, list):
        return frozenset()
    return frozenset(
        customer_id
        for record in records
        if isinstance(record, Mapping)
        for customer_id in (_safe_customer_context(record.get("customer_id")),)
        if customer_id is not None
    )


def _read_object(path: Path) -> Mapping[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("workspace artifact must contain a JSON object")
    return value


def _count_or_none(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _string_or_none(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item.strip())


def _is_due(case: AlertCase, now: datetime) -> bool:
    return case.due_at <= now


def _is_overdue(case: AlertCase, now: datetime) -> bool:
    return case.due_at < now


def _due_status(due_at: datetime | None, now: datetime) -> str:
    if due_at is None:
        return "not_scheduled"
    if due_at < now:
        return "overdue"
    if due_at <= now:
        return "due"
    return "upcoming"


def _safe_customer_context(value: str | None) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    if any(character not in _SAFE_CUSTOMER_ID_CHARACTERS for character in value):
        return None
    return value
