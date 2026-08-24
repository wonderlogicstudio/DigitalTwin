"""Contracts for display-only, non-score triage ranking explanations."""

from __future__ import annotations

import ast
from pathlib import Path

from src.triage_explainability import (
    build_triage_ranking_explanation,
    humanize_reason_codes,
)
from src.triage_selector import SELECTION_REASON_COPY
from src.triage_universe import TRIAGE_REASON_COPY


def _record() -> dict[str, object]:
    return {
        "review_priority_rank": 7,
        "selection_reason_codes": [
            "PRIORITY_BAND_PRIORITY_REVIEW",
            "TIMING_PROSPECTIVE_SIGNAL_AVAILABLE",
            "PERSISTENCE_PRESENT",
            "STABILITY_STABLE",
            "EVIDENCE_SUFFICIENT",
            "CAPACITY_WITHIN_LIMIT",
            "CREATE_NEW_CASE",
        ],
        "why_now_reason_codes": [
            "CURRENT_STATUS_CONCERNING",
            "PERSISTENT_FINANCIAL_STRESS",
        ],
    }


def test_every_declared_reason_has_human_text_and_unknown_codes_fail_safely() -> None:
    known_codes = tuple(sorted(set(TRIAGE_REASON_COPY) | set(SELECTION_REASON_COPY)))

    for language in ("ko", "en"):
        details = humanize_reason_codes(known_codes, language=language)
        assert len(details) == len(known_codes)
        assert all(detail.strip() for detail in details)
        assert all(code not in details for code in known_codes)
        unknown = humanize_reason_codes(["UNDECLARED_REASON"], language=language)
        assert unknown and "UNDECLARED_REASON" not in unknown[0]


def test_explanation_keeps_actual_rank_order_separate_from_why_now_and_risk_score() -> None:
    explanation = build_triage_ranking_explanation(_record(), language="en")

    assert explanation["selection_rank"] == 7
    assert explanation["is_composite_risk_score"] is False
    assert "risk or credit score" in explanation["rank_semantics"]
    assert explanation["why_now"]["reason_codes"] == (
        "CURRENT_STATUS_CONCERNING",
        "PERSISTENT_FINANCIAL_STRESS",
    )
    assert [section["id"] for section in explanation["selection_order"]] == [
        "operational_priority",
        "prospective_timing",
        "signal_persistence",
        "evidence_stability_sufficiency",
        "capacity_and_routing",
        "deterministic_tie_breaker",
    ]
    assert explanation["selection_order"][-1]["technical_only"] is True
    assert "not as risk evidence" in explanation["selection_order"][-1]["reasons"][0]


def test_explainability_module_has_no_future_label_evaluator_or_ui_dependency() -> None:
    import src.triage_explainability as triage_explainability

    source = Path(triage_explainability.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    ]

    assert "final_outcome" not in source
    assert "persona" not in source
    assert "streamlit" not in source.lower()
    assert not any("evaluator" in module or "matcher" in module for module in imported_modules)
