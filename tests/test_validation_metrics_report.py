"""Tests for predeclared aggregate-only synthetic/real validation metrics."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from config import settings
from src.validation_metrics_report import (
    TRIAGE_DISPOSITION_KEYS,
    AggregateValidationMetricInput,
    CapacityScenarioDeclaration,
    OutcomeDefinition,
    ValidationMetricsContractError,
    build_validation_comparison_report,
    export_validation_comparison_report,
    validation_metrics_report_template,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _metric_input(
    *,
    source: str,
    outcome_basis_id: str | None,
    outcome_available: bool = True,
    independently_agreed: bool | None = None,
    capacity_id: str = "demo-capacity-2",
) -> AggregateValidationMetricInput:
    agreed = source == "approved_real" if independently_agreed is None else independently_agreed
    return AggregateValidationMetricInput(
        source=source,  # type: ignore[arg-type]
        customer_count=4,
        expected_customer_month_count=48,
        admitted_customer_month_count=46,
        missing_customer_month_count=2,
        analysis_customer_month_denominator=46,
        feature_values={"savings_rate": (0.10, 0.05, -0.02, 0.20)},
        match_distances=(0.2, 0.4, 0.7, 0.9),
        neighbor_support_counts=(5, 5, 4, 5),
        historical_cohort_outcome_shares=(0.1, 0.2, 0.4, 0.3),
        review_episode_count=2,
        unique_alerted_customer_count=2,
        no_event_review_episode_count=1,
        lead_time_months=(2, 4) if outcome_available else (),
        persistence_rate=0.5,
        flip_rate=0.25,
        triage_counts={
            "selected": 1,
            "deferred": 1,
            "monitor": 1,
            "no_actionable_signal": 0,
            "insufficient_evidence": 1,
        },
        insufficient_evidence_count=1,
        capacity_scenario=CapacityScenarioDeclaration(capacity_id, 2, status="demo"),
        outcome_definition=OutcomeDefinition(
            definition_id=f"{source}-outcome-v1",
            comparison_basis_id=outcome_basis_id,
            independently_agreed=agreed,
            availability="available" if outcome_available else "unavailable",
            description="Aggregate evaluator-only event definition for contract testing.",
        ),
    )


def test_absent_real_report_has_fixed_denominators_and_no_direct_comparison() -> None:
    report = build_validation_comparison_report(_metric_input(source="synthetic", outcome_basis_id="event-v1"))
    payload = report.to_dict()

    assert payload["report_status"] == "template_real_absent"
    assert payload["approved_real"]["status"] == "absent_not_validated"
    assert payload["comparison"] == {
        "outcome_compatibility_status": "real_absent",
        "direct_outcome_comparison_allowed": False,
        "capacity_scenario_comparison_status": "real_absent",
        "feature_distribution_shift": {"status": "real_absent"},
        "match_distance_neighbor_support_shift": {"status": "real_absent"},
    }
    metrics = payload["synthetic"]["prospective_alert_metrics"]
    assert metrics["analysis_customer_month_denominator"] == 46
    assert metrics["alerts_per_1000_customer_months"] == pytest.approx(2 / 46 * 1000)
    assert metrics["no_event_alert_rate"] == pytest.approx(0.5)
    assert metrics["lead_time_distribution_months"]["median"] == pytest.approx(3.0)
    assert "probability" not in str(payload["synthetic"]["historical_cohort_outcome_share_distribution"]).lower().replace(
        "not a target prediction probability", ""
    )


def test_incompatible_outcome_definitions_disable_direct_comparison() -> None:
    report = build_validation_comparison_report(
        _metric_input(source="synthetic", outcome_basis_id="synthetic-event-v1"),
        _metric_input(source="approved_real", outcome_basis_id="independent-real-event-v1"),
    )

    assert report.comparison["outcome_compatibility_status"] == "incompatible_outcome_definitions"
    assert report.comparison["direct_outcome_comparison_allowed"] is False


def test_compatible_independently_agreed_outcomes_and_capacity_enable_only_comparison_flag() -> None:
    report = build_validation_comparison_report(
        _metric_input(source="synthetic", outcome_basis_id="shared-event-v1"),
        _metric_input(source="approved_real", outcome_basis_id="shared-event-v1"),
    )
    payload = report.to_dict()

    assert payload["comparison"]["outcome_compatibility_status"] == "compatible_predeclared"
    assert payload["comparison"]["direct_outcome_comparison_allowed"] is True
    assert payload["comparison"]["capacity_scenario_comparison_status"] == "same_declared_scenario"
    assert payload["comparison"]["feature_distribution_shift"]["threshold_declared"] is False
    assert payload["prohibitions"]["single_actual_accuracy_score"] is False
    assert payload["prohibitions"]["automatic_capacity_selection"] is False


def test_outcome_unavailable_lead_time_and_triage_reconciliation_are_explicit() -> None:
    unavailable = _metric_input(
        source="approved_real",
        outcome_basis_id=None,
        outcome_available=False,
        independently_agreed=False,
    )
    report = build_validation_comparison_report(
        _metric_input(source="synthetic", outcome_basis_id="synthetic-event-v1"),
        unavailable,
    )

    assert report.comparison["outcome_compatibility_status"] == "outcome_unavailable"
    assert report.approved_real is not None
    assert report.approved_real.prospective_alert_metrics["lead_time_distribution_months"] is None
    assert report.approved_real.triage_capacity_metrics["counts"] == {
        key: 1 if key != "no_actionable_signal" else 0 for key in TRIAGE_DISPOSITION_KEYS
    }


def test_invalid_denominators_and_post_hoc_triage_shape_are_rejected() -> None:
    with pytest.raises(ValidationMetricsContractError, match="must reconcile"):
        AggregateValidationMetricInput(
            **{
                **_metric_input(source="synthetic", outcome_basis_id="event-v1").__dict__,
                "admitted_customer_month_count": 45,
            }
        )

    bad_triage = dict(_metric_input(source="synthetic", outcome_basis_id="event-v1").__dict__)
    bad_triage["triage_counts"] = {"selected": 4}
    with pytest.raises(ValidationMetricsContractError, match="predeclared disposition keys"):
        AggregateValidationMetricInput(**bad_triage)

    with pytest.raises(ValidationMetricsContractError, match="approved-real outcome definition"):
        _metric_input(
            source="approved_real",
            outcome_basis_id="real-event-v1",
            independently_agreed=False,
        )


def test_template_and_atomic_report_export_are_source_free(tmp_path: Path) -> None:
    report = build_validation_comparison_report(_metric_input(source="synthetic", outcome_basis_id="event-v1"))
    output_root = tmp_path / "validation_metrics"
    output = export_validation_comparison_report(
        report,
        output_root / "report.json",
        allowed_root=output_root,
    )
    assert json.loads(output.read_text(encoding="utf-8"))["prohibitions"]["row_level_values_exported"] is False
    assert not list(output_root.glob(".*.tmp"))
    with pytest.raises(ValidationMetricsContractError, match="injected output root"):
        export_validation_comparison_report(
            report,
            tmp_path / "outside" / "report.json",
            allowed_root=output_root,
        )
    with pytest.raises(ValidationMetricsContractError, match="canonical data paths"):
        export_validation_comparison_report(
            report,
            settings.DATA_RAW_DIR / "report.json",
            allowed_root=settings.DATA_RAW_DIR,
        )

    template_path = (
        PROJECT_ROOT
        / "artifacts"
        / "post_p0"
        / "real_data_readiness"
        / "synthetic_vs_real_validation_report_template.json"
    )
    assert json.loads(template_path.read_text(encoding="utf-8")) == validation_metrics_report_template()


def test_metrics_module_has_no_data_reader_network_scorer_or_ui_imports() -> None:
    source = (PROJECT_ROOT / "src" / "validation_metrics_report.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots: set[str] = set()
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
            imported_modules.add(node.module)

    assert {"requests", "httpx", "urllib", "socket", "pandas", "streamlit"}.isdisjoint(imported_roots)
    assert not any("scoring" in module or "triage" in module or "evaluator" in module for module in imported_modules)
    assert "read_csv" not in source
    assert "final_outcome" not in source
    assert "persona" not in source


def test_metrics_document_has_no_accuracy_claim_and_keeps_outcome_gate() -> None:
    document = (PROJECT_ROOT / "SYNTHETIC_REAL_VALIDATION_METRICS_CONTRACT.md").read_text(encoding="utf-8")
    assert "single “actual accuracy” score" in document
    assert "never a target prediction probability" in document
    assert "Outcome-dependent comparison is disabled" in document
