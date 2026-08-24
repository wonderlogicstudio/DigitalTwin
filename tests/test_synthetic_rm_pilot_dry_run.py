"""Synthetic-only rehearsal tests for the bounded RM pilot dry run."""

from __future__ import annotations

import ast
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.synthetic_rm_pilot_dry_run import (
    SyntheticPilotDryRunError,
    run_synthetic_rm_pilot_dry_run,
)


RUN_AT = datetime(2026, 8, 24, 9, 0, tzinfo=timezone.utc)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _record(
    customer_id: str,
    *,
    rank: int | None,
    disposition: str,
    label: str,
    selected: bool,
    eligible: bool | None,
) -> dict[str, object]:
    return {
        "customer_id": customer_id,
        "as_of_month": 12,
        "policy_id": "synthetic_early_warning_demo",
        "policy_version": "0.1.0",
        "signal_run_id": "fixture_crossfit_asof12",
        "primary_disposition": disposition,
        "eligibility_label": label,
        "eligible_for_review": eligible,
        "review_priority_rank": rank,
        "selection_disposition": "SELECTED_FOR_REVIEW" if selected else "NOT_QUEUE_ELIGIBLE",
        "routing_disposition": "CREATE_NEW_CASE" if selected else "NO_ROUTING",
        "selection_reason_codes": ["FIXTURE_REASON"],
        "why_now_reason_codes": ["FIXTURE_CURRENT_SIGNAL"],
        "timing_evidence_reference": {
            "source": "prospective_signal",
            "candidate_month": 12,
            "evaluation_status": "not_evaluated",
            "lead_time_months": None,
            "lead_time_unit": "months",
        },
    }


def _selection_fixture() -> dict[str, object]:
    records = [
        _record("C000001", rank=1, disposition="ELIGIBLE_PRIORITY", label="Priority Review", selected=True, eligible=True),
        _record("C000002", rank=2, disposition="ELIGIBLE_PRIORITY", label="Priority Review", selected=True, eligible=True),
        _record("C000003", rank=3, disposition="ELIGIBLE_REVIEW", label="Review", selected=True, eligible=True),
        _record("C000004", rank=4, disposition="ELIGIBLE_REVIEW", label="Review", selected=True, eligible=True),
        _record("C000005", rank=None, disposition="MONITOR_ONLY", label="Monitor", selected=False, eligible=True),
        _record("C000006", rank=None, disposition="NO_ACTIONABLE_SIGNAL", label="Monitor", selected=False, eligible=False),
    ]
    return {
        "run_id": "fixture_run",
        "schema_version": "rm_selection_manifest.v1",
        "signal_run_id": "fixture_crossfit_asof12",
        "triage_as_of_month": 12,
        "selection_policy": {"policy_id": "fixture_selection", "version": "1", "status": "demo"},
        "funnel": {"monitored_total": len(records), "eligible_total": 4},
        "records": records,
    }


def _representative_fixture() -> dict[str, object]:
    return {
        "schema_version": "rm_representative_cohort.v1",
        "records": [
            {"category_id": "priority_review", "status": "selected", "customer_id": "C000001"},
            {"category_id": "early_signal_review", "status": "selected", "customer_id": "C000003"},
            {"category_id": "monitor_no_alert_comparison", "status": "selected", "customer_id": "C000005"},
            {"category_id": "insufficient_or_landmark_not_found", "status": "unavailable", "customer_id": None},
        ],
    }


def _write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    selection_path = source_dir / "selection.json"
    representative_path = source_dir / "representatives.json"
    selection_path.write_text(json.dumps(_selection_fixture(), indent=2), encoding="utf-8")
    representative_path.write_text(json.dumps(_representative_fixture(), indent=2), encoding="utf-8")
    return selection_path, representative_path


def test_dry_run_rehearses_capacity_workflow_measurements_and_failure_paths(tmp_path: Path) -> None:
    selection_path, representative_path = _write_inputs(tmp_path)
    source_checksums = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (selection_path, representative_path)
    }
    root = tmp_path / "post_p0" / "pilot_dry_run"
    result = run_synthetic_rm_pilot_dry_run(
        selection_manifest_path=selection_path,
        representative_cohort_path=representative_path,
        output_dir=root / "fixture_capacity_3",
        allowed_output_root=root,
        max_reviews_per_cycle=3,
        occurred_at=RUN_AT,
        run_id="fixture_dry_run",
    )
    payload = result.to_dict()

    assert payload["run_mode"] == "synthetic_operational_rehearsal_only"
    assert payload["capacity_comparison"]["eligible_count"] == 4
    assert payload["capacity_comparison"]["selected_count"] == 3
    assert payload["capacity_comparison"]["deferred_count"] == 1
    assert payload["capacity_comparison"]["workflow_rehearsal_selected_sample_count"] == 3
    assert payload["capacity_comparison"]["automatically_approved"] is False
    assert payload["alert_cycles"]["initial"] == {
        "triage_received": 5,
        "selected": 3,
        "new_case": 3,
        "existing_case_routed": 0,
        "deferred_or_nonreview": 2,
        "noop": 0,
        "failed": 0,
    }
    assert payload["alert_cycles"]["duplicate_signal"]["new_case"] == 0
    assert payload["alert_cycles"]["snooze_active"]["noop"] == 1
    assert payload["workflow"] == {
        "synthetic_case_count": 3,
        "closed_case_count": 1,
        "in_review_case_count": 1,
        "snoozed_case_count": 1,
        "append_only_audit_event_count": 10,
        "synthetic_actor_reference": "rm-synthetic-01",
        "time_instrumentation_seconds": 600,
        "productivity_or_sla_claimed": False,
    }
    assert payload["measurements"]["measurement_count"] == 3
    assert payload["measurements"]["insufficient_evidence_count"] == 1
    assert payload["failure_scenarios"]["no_historical_landmark"] == {
        "status": "handled_without_live_trigger",
        "historical_landmark_used_as_trigger": False,
    }
    assert payload["failure_scenarios"]["duplicate_signal"]["new_case_count"] == 0
    assert payload["failure_scenarios"]["preview_unavailable"] == {
        "status": "handled_without_case_or_audit_mutation",
        "error_type": "RuntimeError",
    }
    assert payload["notification_preview"] == {
        "status": "PREVIEW",
        "sent": False,
        "external_delivery_attempted": False,
        "network_called": False,
    }
    assert payload["safety"] == {
        "actual_rm_participants": False,
        "actual_customer_data": False,
        "external_notification_delivery": False,
        "automatic_policy_approval": False,
        "automatic_capacity_approval": False,
        "customer_financial_outcome_improvement_claimed": False,
        "canonical_analytics_mutated": False,
    }
    assert payload["input_artifacts"]["canonical_source_artifacts_unchanged"] is True
    assert json.loads((result.output_dir / "run_manifest.json").read_text(encoding="utf-8")) == payload
    assert json.loads((result.output_dir / "measurement_summary.json").read_text(encoding="utf-8")) == payload["measurements"]
    assert all(hashlib.sha256(path.read_bytes()).hexdigest() == digest for path, digest in source_checksums.items())


def test_reset_replaces_only_isolated_output_and_small_capacity_is_rejected(tmp_path: Path) -> None:
    selection_path, representative_path = _write_inputs(tmp_path)
    root = tmp_path / "post_p0" / "pilot_dry_run"
    output = root / "fixture"
    with pytest.raises(SyntheticPilotDryRunError, match="at least three"):
        run_synthetic_rm_pilot_dry_run(
            selection_manifest_path=selection_path,
            representative_cohort_path=representative_path,
            output_dir=output,
            allowed_output_root=root,
            max_reviews_per_cycle=2,
            occurred_at=RUN_AT,
        )
    assert not output.exists()

    first = run_synthetic_rm_pilot_dry_run(
        selection_manifest_path=selection_path,
        representative_cohort_path=representative_path,
        output_dir=output,
        allowed_output_root=root,
        max_reviews_per_cycle=3,
        occurred_at=RUN_AT,
    )
    (output / "sentinel.txt").write_text("isolated only", encoding="utf-8")
    second = run_synthetic_rm_pilot_dry_run(
        selection_manifest_path=selection_path,
        representative_cohort_path=representative_path,
        output_dir=output,
        allowed_output_root=root,
        max_reviews_per_cycle=3,
        occurred_at=RUN_AT,
    )
    assert first.to_dict() == second.to_dict() | {"reset_performed": False}
    assert second.to_dict()["reset_performed"] is True
    assert not (output / "sentinel.txt").exists()
    assert json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))["reset_performed"] is True


def test_dry_run_output_cannot_target_source_or_canonical_artifact_roots(tmp_path: Path) -> None:
    selection_path, representative_path = _write_inputs(tmp_path)
    with pytest.raises(SyntheticPilotDryRunError, match="child of the injected"):
        run_synthetic_rm_pilot_dry_run(
            selection_manifest_path=selection_path,
            representative_cohort_path=representative_path,
            output_dir=tmp_path / "outside",
            allowed_output_root=tmp_path / "post_p0" / "pilot_dry_run",
            max_reviews_per_cycle=3,
            occurred_at=RUN_AT,
        )
    with pytest.raises(SyntheticPilotDryRunError, match="cannot contain a source"):
        root = tmp_path / "post_p0" / "pilot_dry_run"
        contained_source_dir = root / "contains_source" / "source"
        contained_source_dir.mkdir(parents=True)
        contained_selection = contained_source_dir / "selection.json"
        contained_representative = contained_source_dir / "representatives.json"
        contained_selection.write_text(json.dumps(_selection_fixture()), encoding="utf-8")
        contained_representative.write_text(json.dumps(_representative_fixture()), encoding="utf-8")
        run_synthetic_rm_pilot_dry_run(
            selection_manifest_path=contained_selection,
            representative_cohort_path=contained_representative,
            output_dir=root / "contains_source",
            allowed_output_root=root,
            max_reviews_per_cycle=3,
            occurred_at=RUN_AT,
        )


def test_dry_run_module_is_synthetic_only_without_ui_network_or_analytics_imports() -> None:
    source = (PROJECT_ROOT / "src" / "synthetic_rm_pilot_dry_run.py").read_text(encoding="utf-8")
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
        for forbidden in ("data_generator", "crossfit", "matcher", "evaluator", "scorer")
    )
    assert "final_outcome" not in source
    assert "persona" not in source
    assert "real RM" not in source
