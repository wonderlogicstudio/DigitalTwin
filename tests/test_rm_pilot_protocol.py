"""Synthetic-only contract tests for the future RM pilot protocol."""

from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

from config import settings
from src.rm_pilot_protocol import (
    PilotMeasurement,
    PilotScope,
    PilotStopSignal,
    RMPilotProtocol,
    RMPilotProtocolError,
    build_pilot_governance_review,
    build_pilot_measurement_summary,
    export_pilot_metadata,
    pilot_governance_checklist_template,
    pilot_measurement_schema_template,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _measurement(
    suffix: str,
    *,
    period: str = "SYNTHETIC_CYCLE_01",
    outcome: str = "REVIEWED",
    recommendation: str = "ACCEPTED",
    completed: bool = True,
    seconds: int | None = 120,
    insufficient: bool = False,
) -> PilotMeasurement:
    return PilotMeasurement(
        case_reference=f"CASE_SYN_{suffix}",
        alert_reference=f"ALERT_SYN_{suffix}",
        reviewer_pseudonymous_reference="RM_SYN_01",
        review_period=period,
        evidence_usefulness_rating=4,
        actionability_rating=3,
        perceived_timeliness_rating=5,
        review_completed=completed,
        review_completion_seconds=seconds,
        review_outcome=outcome,  # type: ignore[arg-type]
        recommendation_decision=recommendation,  # type: ignore[arg-type]
        recommendation_reason_code=(
            "TIMING_UNCLEAR" if recommendation in {"MODIFIED", "REJECTED"} else None
        ),
        follow_up_status="CREATED",
        insufficient_evidence=insufficient,
        human_override=False,
        sanitized_feedback_code="EVIDENCE_CLEAR",
    )


def test_protocol_stays_synthetic_not_initiated_and_requires_human_scope_approval() -> None:
    protocol = RMPilotProtocol()
    payload = protocol.to_dict()

    assert payload["protocol_status"] == "protocol_only_not_initiated"
    assert payload["data_scope"] == "synthetic_pseudonymous_cases_only"
    assert payload["scope"]["approval_status"] == "not_requested"
    assert payload["scope"]["participating_rm_count"] is None
    assert payload["execution_boundary"] == {
        "actual_rm_recruitment_performed": False,
        "actual_customer_data_processed": False,
        "external_notification_delivery_enabled": False,
        "automatic_alert_or_financial_decision_enabled": False,
    }
    assert payload["governance_boundary"]["automatic_policy_approval"] is False
    assert payload["governance_boundary"]["automatic_capacity_approval"] is False

    with pytest.raises(RMPilotProtocolError, match="approval_reference"):
        PilotScope(
            participating_rm_count=2,
            synthetic_cohort_reference="SYNTHETIC_COHORT_01",
            duration_period_count=2,
            review_capacity_per_period=5,
            approval_status="approved",
        )


def test_synthetic_measurements_validate_and_report_all_primary_process_metrics() -> None:
    records = (
        _measurement("001"),
        _measurement(
            "002",
            outcome="DEFERRED",
            recommendation="MODIFIED",
            completed=False,
            seconds=None,
            insufficient=True,
        ),
        _measurement("003", outcome="NO_ACTION", recommendation="REJECTED", seconds=180),
    )
    summary = build_pilot_measurement_summary(records, declared_review_period_count=2)
    payload = summary.to_dict()

    assert payload["measurement_count"] == 3
    assert payload["review_completed_count"] == 2
    assert payload["alerts_reviewed_per_period"] == 1.0
    assert payload["review_outcome_counts"] == {
        "REVIEWED": 1,
        "DEFERRED": 1,
        "MONITOR": 0,
        "NO_ACTION": 1,
    }
    assert payload["recommendation_decision_counts"]["ACCEPTED"] == 1
    assert payload["recommendation_decision_counts"]["MODIFIED"] == 1
    assert payload["recommendation_decision_counts"]["REJECTED"] == 1
    assert payload["follow_up_status_counts"]["CREATED"] == 3
    assert payload["insufficient_evidence_frequency"] == pytest.approx(1 / 3, abs=0.0001)
    assert payload["rating_summary"]["evidence_usefulness"] == {"observed_count": 3, "mean": 4.0}
    assert payload["review_completion_seconds_median"] == 150.0
    assert payload["customer_financial_outcome_improvement_proven"] is False


def test_measurement_rejects_pii_like_references_unsanitized_reasons_and_duplicates() -> None:
    with pytest.raises(RMPilotProtocolError, match="opaque"):
        _measurement("001@example.com")
    with pytest.raises(RMPilotProtocolError, match="sanitized reason"):
        replace(_measurement("002", recommendation="REJECTED"), recommendation_reason_code=None)
    with pytest.raises(RMPilotProtocolError, match="unique"):
        build_pilot_measurement_summary(
            (_measurement("001"), _measurement("001")),
            declared_review_period_count=1,
        )


def test_measurement_schema_has_no_customer_pii_or_raw_free_text_field() -> None:
    payload = _measurement("001").to_dict()
    forbidden_field_names = {
        "customer_id",
        "customer_name",
        "email",
        "phone",
        "address",
        "account_number",
        "free_text",
    }
    assert forbidden_field_names.isdisjoint(payload)
    assert payload["public_raw_feedback_export_allowed"] is False

    schema = pilot_measurement_schema_template()
    assert schema["privacy"] == {
        "customer_pii_fields_allowed": False,
        "raw_free_text_stored_in_public_repository": False,
        "raw_feedback_public_export_allowed": False,
        "sanitized_code_only_in_public_contract": True,
    }


def test_stop_signals_require_human_review_without_auto_stop_or_approval() -> None:
    scope = PilotScope(
        participating_rm_count=2,
        synthetic_cohort_reference="SYNTHETIC_COHORT_01",
        duration_period_count=2,
        review_capacity_per_period=5,
        approval_status="pending",
    )
    review = build_pilot_governance_review(
        scope,
        (
            PilotStopSignal(
                "TIMING_SEMANTICS_CONFUSING",
                observed=True,
                evidence_reference="STOP_NOTE_001",
            ),
        ),
    ).to_dict()

    assert review["scope_approval_status"] == "pending"
    assert review["active_stop_criteria"] == ["TIMING_SEMANTICS_CONFUSING"]
    assert review["human_governance_review_required"] is True
    assert review["automatic_pilot_start_allowed"] is False
    assert review["automatic_pilot_stop"] is False
    assert review["automatic_policy_approval"] is False
    assert review["automatic_capacity_approval"] is False
    assert review["actual_pilot_execution_authorized"] is False


def test_templates_and_atomic_metadata_export_are_source_free(tmp_path: Path) -> None:
    output_root = tmp_path / "rm_pilot"
    output = export_pilot_metadata(
        pilot_governance_checklist_template(),
        output_root / "checklist.json",
        allowed_root=output_root,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "not_ready_for_actual_pilot_execution"
    assert not list(output_root.glob(".*.tmp"))
    with pytest.raises(RMPilotProtocolError, match="injected Post-P0 root"):
        export_pilot_metadata(
            pilot_governance_checklist_template(),
            tmp_path / "outside" / "checklist.json",
            allowed_root=output_root,
        )
    with pytest.raises(RMPilotProtocolError, match="canonical data paths"):
        export_pilot_metadata(
            pilot_governance_checklist_template(),
            settings.DATA_RAW_DIR / "checklist.json",
            allowed_root=settings.DATA_RAW_DIR,
        )

    artifact_root = PROJECT_ROOT / "artifacts" / "post_p0" / "rm_pilot"
    assert json.loads(
        (artifact_root / "pilot_measurement_schema_template.json").read_text(encoding="utf-8")
    ) == pilot_measurement_schema_template()
    assert json.loads(
        (artifact_root / "pilot_governance_checklist.json").read_text(encoding="utf-8")
    ) == pilot_governance_checklist_template()
    assert json.loads(
        (artifact_root / "pilot_protocol_template.json").read_text(encoding="utf-8")
    ) == RMPilotProtocol().to_dict()


def test_protocol_module_has_no_workflow_ui_network_or_analytics_leakage() -> None:
    source_path = PROJECT_ROOT / "src" / "rm_pilot_protocol.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots: set[str] = set()
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
            imported_modules.add(node.module)

    assert {"streamlit", "requests", "httpx", "urllib", "socket", "pandas"}.isdisjoint(imported_roots)
    assert not any(
        forbidden in module
        for module in imported_modules
        for forbidden in ("scorer", "matcher", "triage", "evaluator", "alert", "banker", "audit", "notification")
    )
    assert "final_outcome" not in source
    assert "persona" not in source
    assert "read_csv" not in source


def test_protocol_document_keeps_protocol_only_and_no_auto_approval_boundaries() -> None:
    document = (PROJECT_ROOT / "RM_PILOT_VALIDATION_PROTOCOL.md").read_text(encoding="utf-8")
    assert "**Status: protocol only; no pilot has been initiated.**" in document
    assert "Policy and\ncapacity are not automatically approved" in document
    assert "Raw feedback is never exported to the public" in document
    assert "customer\nfinancial outcomes" in document
