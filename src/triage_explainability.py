"""Display-only explanations for persisted triage ranking decisions.

This module formats declared reason codes and ranking metadata.  It never
re-ranks a customer, evaluates policy, opens target future data, or creates a
numeric risk score.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.i18n import t
from src.triage_selector import SELECTION_REASON_COPY
from src.triage_universe import TRIAGE_REASON_COPY


_SELECTION_GROUPS = (
    (
        "operational_priority",
        ("PRIORITY_BAND_",),
        "rm.ranking.section.operational_priority",
    ),
    (
        "prospective_timing",
        ("TIMING_",),
        "rm.ranking.section.prospective_timing",
    ),
    (
        "signal_persistence",
        ("PERSISTENCE_",),
        "rm.ranking.section.signal_persistence",
    ),
    (
        "evidence_stability_sufficiency",
        ("STABILITY_", "EVIDENCE_"),
        "rm.ranking.section.evidence",
    ),
    (
        "capacity_and_routing",
        ("CAPACITY_", "ROUTE_", "CREATE_", "NO_ROUTING", "NOT_QUEUE_"),
        "rm.ranking.section.capacity_routing",
    ),
)


def humanize_reason_codes(reason_codes: object, *, language: str = "ko") -> tuple[str, ...]:
    """Return safe localized text for each declared code in input order."""

    if not isinstance(reason_codes, Sequence) or isinstance(reason_codes, (str, bytes)):
        return ()
    return tuple(
        _humanize_reason_code(code, language=language)
        for code in reason_codes
        if isinstance(code, str) and code.strip()
    )


def build_triage_ranking_explanation(
    record: Mapping[str, object],
    *,
    language: str = "ko",
) -> dict[str, object]:
    """Explain a saved selection record without recalculating its priority."""

    selection_codes = _string_codes(record.get("selection_reason_codes"))
    why_now_codes = _string_codes(record.get("why_now_reason_codes"))
    sections: list[dict[str, object]] = []
    assigned_codes: set[str] = set()
    for section_id, prefixes, label_key in _SELECTION_GROUPS:
        matching = tuple(
            code for code in selection_codes if any(code.startswith(prefix) for prefix in prefixes)
        )
        assigned_codes.update(matching)
        if matching:
            sections.append(
                {
                    "id": section_id,
                    "label": t(label_key, language),
                    "reason_codes": matching,
                    "reasons": humanize_reason_codes(matching, language=language),
                }
            )
    remaining = tuple(code for code in selection_codes if code not in assigned_codes)
    if remaining:
        sections.append(
            {
                "id": "other_declared_selection_reason",
                "label": t("rm.ranking.section.other", language),
                "reason_codes": remaining,
                "reasons": humanize_reason_codes(remaining, language=language),
            }
        )
    sections.append(
        {
            "id": "deterministic_tie_breaker",
            "label": t("rm.ranking.section.tie_breaker", language),
            "reason_codes": (),
            "reasons": (t("rm.ranking.tie_breaker", language),),
            "technical_only": True,
        }
    )
    return {
        "selection_rank": _positive_int(record.get("review_priority_rank")),
        "is_composite_risk_score": False,
        "rank_semantics": t("rm.ranking.rank_semantics", language),
        "why_now": {
            "label": t("rm.ranking.section.why_now", language),
            "reason_codes": why_now_codes,
            "reasons": humanize_reason_codes(why_now_codes, language=language),
        },
        "selection_order": tuple(sections),
    }


def _humanize_reason_code(code: str, *, language: str) -> str:
    for translation_key in (
        f"rm.ranking.reason.{code}",
        f"rm.review.reason.{code}",
        f"rm.queue.reason.{code}",
    ):
        translated = t(translation_key, language)
        if translated != translation_key:
            return translated
    return TRIAGE_REASON_COPY.get(code, SELECTION_REASON_COPY.get(code, t("rm.ranking.reason.unknown", language)))


def _string_codes(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(code for code in value if isinstance(code, str) and code.strip())


def _positive_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None
