"""Population-evidence display helpers for Presentation mode.

This module contains display-only adapters for saved triage artifacts.  It is
intentionally separate from the legacy :mod:`src.presentation` scene module so
that Population/RM additions cannot make the established Presentation import
contract unavailable.  No analytics or triage calculation is performed here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from config import settings
from src.i18n import t


PRESENTATION_REPRESENTATIVE_CATEGORY_KEYS = (
    "priority_review",
    "early_signal_review",
    "monitor_no_alert_comparison",
    "insufficient_or_landmark_not_found",
)


def load_presentation_population_evidence(
    artifact_dir: Path | None = None,
) -> dict[str, Any]:
    """Load saved, display-safe population and representative evidence only."""

    manifest_path = _resolve_population_manifest_path(artifact_dir)
    if manifest_path is None:
        return _population_evidence_unavailable()

    try:
        manifest = _read_json(manifest_path)
        cohort = _read_json(manifest_path.with_name("rm_representative_cohort.json"))
        funnel = manifest.get("funnel")
        reconciliation = manifest.get("reconciliation")
        records = manifest.get("records")
        cohort_records = cohort.get("records")
        if not isinstance(funnel, Mapping) or not isinstance(reconciliation, Mapping):
            return _population_evidence_unavailable()
        if not isinstance(records, list) or not isinstance(cohort_records, list):
            return _population_evidence_unavailable()
        if not reconciliation.get("is_exact"):
            return _population_evidence_unavailable()

        monitored_total = _required_nonnegative_int(funnel.get("monitored_total"))
        eligible_total = _required_nonnegative_int(funnel.get("eligible_total"))
        selected_total = _required_nonnegative_int(funnel.get("selected_queue_ready"))
        if None in (monitored_total, eligible_total, selected_total):
            return _population_evidence_unavailable()

        representative_records = tuple(
            _presentation_representative_record(record)
            for record in cohort_records
            if isinstance(record, Mapping)
            and str(record.get("category_id", "")) in PRESENTATION_REPRESENTATIVE_CATEGORY_KEYS
        )
        current_signals = {
            str(record["customer_id"]): _presentation_current_signal(record)
            for record in records
            if isinstance(record, Mapping) and isinstance(record.get("customer_id"), str)
        }
        return {
            "available": True,
            "population_count": monitored_total,
            "eligible_count": eligible_total,
            "selected_count": selected_total,
            "funnel": {str(key): value for key, value in funnel.items()},
            "representatives": representative_records,
            "current_signals": current_signals,
            "manifest_path": str(manifest_path),
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return _population_evidence_unavailable()


def build_presentation_customer_options(
    *,
    demo_options: list[Mapping[str, Any]],
    population_evidence: Mapping[str, Any] | None,
    language: str = "ko",
) -> list[dict[str, str]]:
    """Combine current demo choices with already-selected representative cases."""

    options = [
        {
            "option_id": f"demo:{index}:{option.get('customer_id', '')}",
            "customer_id": str(option.get("customer_id", "")),
            "role": str(option.get("role", "demo")),
            "label": str(option.get("label", option.get("customer_id", ""))),
            "source": "demo",
        }
        for index, option in enumerate(demo_options)
        if option.get("customer_id")
    ]
    if not population_evidence or not population_evidence.get("available"):
        return options

    for record in population_evidence.get("representatives", ()):
        if not isinstance(record, Mapping) or record.get("status") != "selected":
            continue
        customer_id = record.get("customer_id")
        category_id = record.get("category_id")
        if not isinstance(customer_id, str) or not customer_id or not isinstance(category_id, str):
            continue
        options.append(
            {
                "option_id": f"representative:{category_id}:{customer_id}",
                "customer_id": customer_id,
                "role": "representative",
                "label": t(f"presentation.representative.{category_id}", language)
                + f" ({customer_id}) · "
                + t("presentation.representative.auto_selected", language),
                "source": "representative",
            }
        )
    return options


def build_presentation_population_strip(
    *,
    customer_id: str,
    population_evidence: Mapping[str, Any] | None,
    language: str = "ko",
) -> dict[str, Any]:
    """Return compact, non-operational evidence for the Presentation header."""

    if not population_evidence or not population_evidence.get("available"):
        return {"available": False, "message": t("presentation.population.unavailable", language), "items": ()}

    representative = next(
        (
            item
            for item in population_evidence.get("representatives", ())
            if isinstance(item, Mapping)
            and item.get("customer_id") == customer_id
            and item.get("status") == "selected"
        ),
        None,
    )
    if representative is None:
        customer_context = t("presentation.population.existing_demo", language)
    else:
        customer_context = t(
            "presentation.population.representative_context",
            language,
            category=t(f"presentation.representative.{representative['category_id']}", language),
        )
    return {
        "available": True,
        "message": t("presentation.population.title", language),
        "items": (
            (t("presentation.population.analyzed", language), f"{int(population_evidence['population_count']):,}"),
            (t("presentation.population.review_eligible", language), f"{int(population_evidence['eligible_count']):,}"),
            (t("presentation.population.queue_ready", language), f"{int(population_evidence['selected_count']):,}"),
            (t("presentation.population.current_customer", language), customer_context),
        ),
    }


def build_presentation_current_review_signal(
    *,
    customer_id: str,
    population_evidence: Mapping[str, Any] | None,
    language: str = "ko",
) -> dict[str, str] | None:
    """Expose a prepared current review signal without producing one in the UI."""

    if not population_evidence or not population_evidence.get("available"):
        return None
    signal = population_evidence.get("current_signals", {}).get(customer_id)
    if not isinstance(signal, Mapping) or signal.get("source") != "prospective_signal":
        return None
    return {
        "label": t("presentation.current.review_signal", language),
        "value": t(f"presentation.signal_label.{signal['eligibility_label']}", language),
        "detail": t("presentation.current.review_signal_detail", language),
    }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return value


def _resolve_population_manifest_path(artifact_dir: Path | None) -> Path | None:
    root = artifact_dir or settings.BASE_DIR / "artifacts" / "triage"
    if root.is_file():
        return root if root.name == "rm_selection_manifest.json" else None
    direct = root / "rm_selection_manifest.json"
    if direct.exists():
        return direct
    candidates = sorted(root.glob("*/rm_selection_manifest.json"))
    return candidates[-1] if candidates else None


def _population_evidence_unavailable() -> dict[str, Any]:
    return {
        "available": False,
        "population_count": None,
        "eligible_count": None,
        "selected_count": None,
        "funnel": {},
        "representatives": (),
        "current_signals": {},
        "manifest_path": None,
    }


def _required_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _presentation_representative_record(record: Mapping[str, Any]) -> dict[str, Any]:
    customer_id = record.get("customer_id")
    return {
        "category_id": str(record.get("category_id", "")),
        "customer_id": str(customer_id) if isinstance(customer_id, str) else None,
        "status": str(record.get("status", "unavailable")),
        "source_as_of_month": _required_nonnegative_int(record.get("source_as_of_month")),
    }


def _presentation_current_signal(record: Mapping[str, Any]) -> dict[str, str]:
    timing_reference = record.get("timing_evidence_reference")
    source = timing_reference.get("source") if isinstance(timing_reference, Mapping) else ""
    label = str(record.get("eligibility_label", "Monitor"))
    supported_labels = {"Priority Review", "Review", "Monitor"}
    return {
        "source": str(source),
        "eligibility_label": label if label in supported_labels else "Monitor",
    }
