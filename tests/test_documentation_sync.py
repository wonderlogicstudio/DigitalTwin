"""Source-of-truth documentation and referenced P0-path sanity checks."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DOCS = (
    "README.md",
    "ARCHITECTURE.md",
    "PROJECT_HANDOFF.md",
    "DECISIONS.md",
    "BUSINESS_RULES.md",
    "DATA_DICTIONARY.md",
    "SPEC.md",
    "TEST_PLAN.md",
    "TASKS.md",
)


def test_source_of_truth_docs_record_the_implemented_p0_boundaries() -> None:
    contents = {
        name: (PROJECT_ROOT / name).read_text(encoding="utf-8")
        for name in SOURCE_DOCS
    }

    assert "Current P0 operational prototype" in contents["README.md"]
    assert "Current extension architecture (P0)" in contents["ARCHITECTURE.md"]
    assert "Current implementation snapshot (2026-08-24)" in contents["PROJECT_HANDOFF.md"]
    assert "DEC-016 Population artifact isolation" in contents["DECISIONS.md"]
    assert "P0 prospective, triage, and workflow boundaries" in contents["BUSINESS_RULES.md"]
    assert "Separate P0 prototype artifacts" in contents["DATA_DICTIONARY.md"]
    assert "P0 extension: RM operational prototype" in contents["SPEC.md"]
    assert "P0 regression extensions" in contents["TEST_PLAN.md"]
    assert "P0 Population, Early Warning, Triage, RM Workflow, and UI Status" in contents["TASKS.md"]


def test_documented_p0_paths_exist_and_external_delivery_remains_out_of_scope() -> None:
    expected_paths = (
        "scripts/run_triage_selection_manifest.py",
        "src/population_result.py",
        "src/population_batch.py",
        "src/population_artifacts.py",
        "src/as_of_features.py",
        "src/reference_matcher.py",
        "src/prospective_signals.py",
        "src/crossfit_backtest.py",
        "src/demo_policy.py",
        "src/triage_selector.py",
        "src/alert_case.py",
        "src/alert_repository.py",
        "src/banker_service.py",
        "src/audit_trail.py",
        "src/notifications.py",
        "NOTIFICATION_ADAPTER_CONTRACT.md",
        "artifacts/population/seed42_full_run/population_manifest.json",
        "artifacts/triage/seed42_crossfit_5fold_asof12_unbounded/rm_selection_manifest.json",
    )
    missing = [path for path in expected_paths if not (PROJECT_ROOT / path).exists()]
    assert not missing

    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    handoff = (PROJECT_ROOT / "PROJECT_HANDOFF.md").read_text(encoding="utf-8")
    assert "No external notification channel is implemented." in readme
    assert "DB remains unapproved and unimplemented." in handoff


def test_post_p0_docs_keep_feedback_claims_and_real_data_boundaries_explicit() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    handoff = (PROJECT_ROOT / "PROJECT_HANDOFF.md").read_text(encoding="utf-8")
    rules = (PROJECT_ROOT / "BUSINESS_RULES.md").read_text(encoding="utf-8")
    report = (PROJECT_ROOT / "reports" / "post_p0" / "12-17_feedback_security_sync.md").read_text(
        encoding="utf-8"
    )
    closure_matrix = PROJECT_ROOT / "artifacts" / "post_p0" / "feedback" / "coverage_matrix_12_17.json"

    assert "Post-P0 feedback-readiness status" in readme
    assert "not an approved workload" in readme
    assert "No approved real/anonymized data has been admitted or validated" in readme
    assert "Post-P0 feedback-readiness additions" in handoff
    assert "Post-P0 evidence and public-repository boundaries" in rules
    assert "actual RM pilot" in report
    assert "external notification delivery" in report
    assert closure_matrix.exists()
