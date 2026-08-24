"""Contracts for auditable RM selection exports and independent demo cohorts."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from config import settings
from src.demo_policy import HistoricalLandmarkContext, assess_policy_snapshot, default_demo_policy
from src.prospective_signals import SignalSnapshot
from src.selection_manifest import (
    REPRESENTATIVE_CATEGORY_IDS,
    SELECTION_MANIFEST_FILENAME,
    build_operational_selection_manifest,
    export_selection_artifacts,
    load_selection_artifacts,
    select_representative_demo_cohort,
)
from src.triage_selector import TriageSelector, default_triage_selection_policy
from src.triage_universe import TriageDecisionInput, build_triage_universe
import src.selection_manifest as selection_manifest


def _snapshot(customer_id: str, **overrides: object) -> SignalSnapshot:
    values: dict[str, object] = {
        "customer_id": customer_id,
        "as_of_month": 12,
        "matched_count": 5,
        "neighbor_ids": ("C900001", "C900002"),
        "historical_cohort_risk_share": 0.30,
        "historical_cohort_risk_share_delta": None,
        "match_distance_mean": 0.20,
        "match_distance_mean_delta": None,
        "neighbor_jaccard_similarity": None,
        "current_status": "healthy",
        "current_status_transition": "initial",
        "financial_stress_factors": (),
        "persistent_financial_stress_factors": (),
        "previous_as_of_month": None,
    }
    values.update(overrides)
    return SignalSnapshot(**values)  # type: ignore[arg-type]


def _input(
    customer_id: str,
    *,
    existing_open_case_reference: str | None = None,
    landmark: HistoricalLandmarkContext | None = None,
    **snapshot_overrides: object,
) -> TriageDecisionInput:
    snapshot = _snapshot(customer_id, **snapshot_overrides)
    assessment = assess_policy_snapshot(
        default_demo_policy(),
        snapshot,
        historical_landmark_context=landmark,
    )
    return TriageDecisionInput(
        customer_id,
        snapshot,
        assessment,
        existing_open_case_reference=existing_open_case_reference,
    )


def _universe():  # type: ignore[no-untyped-def]
    return build_triage_universe(
        expected_customer_ids=tuple(f"C{index:06d}" for index in range(1, 8)),
        triage_as_of_month=12,
        signal_run_id="crossfit_seed42_5fold_asof12",
        decision_inputs=(
            _input(
                "C000001",
                existing_open_case_reference="CASE-001",
                current_status="stress",
            ),
            _input(
                "C000002",
                financial_stress_factors=("low_savings_rate",),
                persistent_financial_stress_factors=("low_savings_rate",),
                previous_as_of_month=11,
                neighbor_jaccard_similarity=0.9,
            ),
            _input(
                "C000003",
                financial_stress_factors=("low_savings_rate",),
            ),
            _input("C000004"),
            _input("C000005", matched_count=0, financial_stress_factors=("low_savings_rate",)),
            _input("C000006", landmark=HistoricalLandmarkContext("not_found", None)),
        ),
    )


def test_selection_manifest_has_exact_all_customer_detail_and_reconciled_funnel() -> None:
    universe = _universe()
    selection = TriageSelector().select(universe, default_triage_selection_policy(max_reviews_per_cycle=1))

    manifest = build_operational_selection_manifest(
        universe,
        selection,
        run_id="selection-run",
        capacity_scenario_id="illustrative_one",
    )
    payload = manifest.to_dict()

    assert [record.customer_id for record in manifest.records] == [f"C{index:06d}" for index in range(1, 8)]
    assert manifest.funnel == {
        "monitored_total": 7,
        "eligible_priority": 1,
        "eligible_review": 1,
        "eligible_total": 2,
        "selected_queue_ready": 1,
        "deferred_capacity": 1,
        "monitor_only": 1,
        "no_actionable_signal": 2,
        "insufficient_evidence": 1,
        "data_unavailable": 1,
    }
    assert manifest.reconciliation["is_exact"] is True
    assert manifest.reconciliation["duplicate_output_ids"] == []
    assert payload["capacity_scenario"] == {
        "scenario_id": "illustrative_one",
        "max_reviews_per_cycle": 1,
        "automatically_chosen": False,
    }
    selected = [record for record in payload["records"] if record["selected_for_review"]]
    assert [record["customer_id"] for record in selected] == ["C000001"]
    assert {
        "customer_id",
        "as_of_month",
        "signal_run_id",
        "policy_id",
        "eligibility_label",
        "review_priority_rank",
        "selected_for_review",
        "selection_disposition",
        "routing_disposition",
        "why_now_reason_codes",
        "selection_reason_codes",
        "timing_evidence_reference",
    } <= set(payload["records"][0])


def test_manifest_exactly_covers_5000_without_duplicate_or_silent_drop() -> None:
    expected_ids = tuple(f"C{index:06d}" for index in range(1, 5_001))
    inputs = tuple(_input(customer_id) for customer_id in reversed(expected_ids))
    universe = build_triage_universe(
        expected_customer_ids=expected_ids,
        triage_as_of_month=12,
        signal_run_id="crossfit_seed42_5fold_asof12",
        decision_inputs=inputs,
    )
    manifest = build_operational_selection_manifest(
        universe,
        TriageSelector().select(universe, default_triage_selection_policy()),
        run_id="selection-5000",
    )

    assert len(manifest.records) == 5_000
    assert manifest.funnel["monitored_total"] == 5_000
    assert manifest.funnel["no_actionable_signal"] == 5_000
    assert manifest.reconciliation["is_exact"] is True
    assert manifest.reconciliation["duplicate_output_ids"] == []
    assert manifest.reconciliation["missing_ids"] == []


def test_representative_cohort_is_deterministic_and_independent_of_capacity() -> None:
    universe = _universe()
    first = select_representative_demo_cohort(universe)
    second = select_representative_demo_cohort(universe)
    zero_capacity = TriageSelector().select(universe, default_triage_selection_policy(max_reviews_per_cycle=0))
    one_capacity = TriageSelector().select(universe, default_triage_selection_policy(max_reviews_per_cycle=1))

    assert first.to_dict() == second.to_dict()
    assert [record.category_id for record in first.records] == list(REPRESENTATIVE_CATEGORY_IDS)
    assert {record.category_id: record.customer_id for record in first.records} == {
        "priority_review": "C000001",
        "early_signal_review": "C000002",
        "monitor_no_alert_comparison": "C000003",
        "insufficient_or_landmark_not_found": "C000005",
    }
    assert all(record.status == "selected" for record in first.records)
    assert all("customer_id ascending" in record.selection_explanation for record in first.records)
    assert zero_capacity.selected_for_review_count == 0
    assert one_capacity.selected_for_review_count == 1
    assert first.to_dict() == select_representative_demo_cohort(universe).to_dict()
    assert first.to_dict()["selection_rules"]["capacity_independent"] is True
    assert first.to_dict()["selection_rules"]["uses_operational_selection_result"] is False


def test_unavailable_representative_categories_are_explicit_not_tuned() -> None:
    universe = build_triage_universe(
        expected_customer_ids=("C000001",),
        triage_as_of_month=12,
        signal_run_id="run-12",
        decision_inputs=(_input("C000001", current_status="stress"),),
    )
    cohort = select_representative_demo_cohort(universe)
    records = {record.category_id: record for record in cohort.records}

    assert records["priority_review"].status == "selected"
    for category_id in REPRESENTATIVE_CATEGORY_IDS[1:]:
        assert records[category_id].status == "unavailable"
        assert records[category_id].customer_id is None
        assert "no customer condition was changed" in records[category_id].selection_explanation


def test_export_roundtrip_is_separate_from_legacy_demo_and_rejects_partial_output(tmp_path: Path) -> None:
    universe = _universe()
    selection = TriageSelector().select(universe, default_triage_selection_policy(max_reviews_per_cycle=1))
    legacy_demo_paths = (
        settings.DEMO_CUSTOMERS_PATH,
        settings.MAIN_DEMO_CUSTOMER_PATH,
        settings.DEMO_MATCHED_CUSTOMERS_PATH,
        settings.DEMO_MATCHED_FUTURE_TRAJECTORY_PATH,
        settings.DEMO_OUTCOME_SUMMARY_PATH,
        settings.DEMO_BREAKPOINT_RESULT_PATH,
        settings.DEMO_WHATIF_RESULTS_PATH,
    )
    before = {path: path.read_bytes() for path in legacy_demo_paths if path.exists()}
    output_dir = tmp_path / "artifacts" / "triage" / "selection-run"

    paths = export_selection_artifacts(
        universe,
        selection,
        run_id="selection-run",
        output_dir=output_dir,
        capacity_scenario_id="illustrative_one",
        created_at="2026-08-23T00:00:00+00:00",
        code_ref="test-ref",
    )
    loaded = load_selection_artifacts(output_dir)

    assert paths.selection_manifest_json == output_dir / SELECTION_MANIFEST_FILENAME
    assert loaded["selection_manifest"]["reconciliation"]["is_exact"] is True
    assert len(loaded["selection_manifest"]["records"]) == 7
    assert loaded["representative_cohort"]["selection_rules"] == {
        "uses_triage_universe_only": True,
        "uses_operational_selection_result": False,
        "capacity_independent": True,
        "stable_tie_breaker": "customer_id ascending after category evidence order",
        "unavailable_category_policy": "record unavailable; do not alter customer conditions",
    }
    assert {path: path.read_bytes() for path in before} == before

    partial_dir = tmp_path / "partial"
    partial_dir.mkdir()
    (partial_dir / SELECTION_MANIFEST_FILENAME).write_text("{}", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="Incomplete selection artifact set"):
        load_selection_artifacts(partial_dir)
    (output_dir / SELECTION_MANIFEST_FILENAME).write_text("{not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON artifact"):
        load_selection_artifacts(output_dir)
    with pytest.raises(ValueError, match="outside canonical analytics and demo"):
        export_selection_artifacts(universe, selection, run_id="bad-output", output_dir=settings.DATA_DEMO_DIR)


def test_selection_manifest_module_has_no_future_label_or_ui_or_legacy_demo_dependency() -> None:
    source = Path(selection_manifest.__file__).read_text(encoding="utf-8")
    source_tree = ast.parse(source)
    imported_modules = [
        alias.name
        for node in ast.walk(source_tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    ]

    assert "final_outcome" not in source
    assert "persona" not in source
    assert "event_type" not in source
    assert "streamlit" not in source.lower()
    assert not any("evaluator" in module for module in imported_modules)
    assert not any("demo_selector" in module or "demo_cache" in module for module in imported_modules)
    assert not any("notification" in module or "provider" in module for module in imported_modules)
