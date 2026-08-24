"""Regression tests for the no-data governance readiness contract."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from config import settings
from src.real_data_governance import (
    EXCLUDED_DATA_CONCEPTS,
    MINIMUM_DATA_CONCEPTS,
    REAL_DATA_GOVERNANCE_FILENAME,
    ApprovalRequirement,
    GovernanceBoundaryError,
    assert_path_outside_public_repository,
    default_real_data_governance_requirements,
    export_governance_requirements,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_default_contract_is_explicitly_not_ready_and_contains_no_actual_data() -> None:
    requirements = default_real_data_governance_requirements()
    payload = requirements.to_dict()

    assert payload["readiness_status"] == "not_ready_for_real_data_admission"
    assert payload["actual_data_present"] is False
    assert payload["approval_roles_complete"] is False
    assert all(item["status"] == "not_requested" for item in payload["approval_requirements"])
    assert payload["data_boundary"]["public_repository_data_allowed"] is False
    assert payload["data_boundary"]["raw_data_download_or_copy_allowed"] is False
    assert payload["next_preparation"]["real_data_adapter_execution_allowed"] is False


def test_minimum_concepts_and_forbidden_pii_checklist_are_explicit() -> None:
    assert "pseudonymous_customer_key" in MINIMUM_DATA_CONCEPTS
    assert "independently_defined_future_outcome_or_event" in MINIMUM_DATA_CONCEPTS
    assert set(EXCLUDED_DATA_CONCEPTS) == {
        "direct_identifier",
        "contact_detail",
        "address",
        "account_number",
        "authentication_credential",
    }


def test_approval_cannot_be_claimed_without_external_evidence_reference() -> None:
    with pytest.raises(ValueError, match="requires an external evidence reference"):
        ApprovalRequirement(role="security", status="approved")


def test_public_repository_boundary_rejects_canonical_and_post_p0_paths(tmp_path: Path) -> None:
    with pytest.raises(GovernanceBoundaryError):
        assert_path_outside_public_repository(settings.DATA_RAW_DIR)
    with pytest.raises(GovernanceBoundaryError):
        assert_path_outside_public_repository(PROJECT_ROOT / "artifacts" / "post_p0")

    assert assert_path_outside_public_repository(tmp_path).is_absolute()


def test_metadata_export_is_atomic_injected_output_only(tmp_path: Path) -> None:
    output_root = tmp_path / "real_data_readiness"
    destination = export_governance_requirements(
        default_real_data_governance_requirements(),
        output_root / REAL_DATA_GOVERNANCE_FILENAME,
        allowed_root=output_root,
    )

    assert destination.read_text(encoding="utf-8").endswith("\n")
    assert not list(output_root.glob(".*.tmp"))
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["actual_data_present"] is False
    assert payload["readiness_status"] == "not_ready_for_real_data_admission"

    with pytest.raises(GovernanceBoundaryError):
        export_governance_requirements(
            default_real_data_governance_requirements(),
            tmp_path / "outside" / REAL_DATA_GOVERNANCE_FILENAME,
            allowed_root=output_root,
        )


def test_checked_in_artifact_matches_default_no_data_contract() -> None:
    artifact_path = (
        PROJECT_ROOT / "artifacts" / "post_p0" / "real_data_readiness" / REAL_DATA_GOVERNANCE_FILENAME
    )
    checked_in = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert checked_in == default_real_data_governance_requirements().to_dict()


def test_governance_module_has_no_network_or_data_reader_imports() -> None:
    source_path = PROJECT_ROOT / "src" / "real_data_governance.py"
    source = source_path.read_text(encoding="utf-8")
    imported_roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])

    assert {"requests", "httpx", "urllib", "socket", "pandas", "numpy"}.isdisjoint(imported_roots)
    assert "read_csv" not in source
    assert "streamlit" not in source.lower()


def test_governance_document_states_non_admission_and_independent_outcome() -> None:
    document = (PROJECT_ROOT / "REAL_DATA_VALIDATION_GOVERNANCE.md").read_text(encoding="utf-8")
    assert "NOT READY FOR REAL-DATA ADMISSION" in document
    assert "not requested" in document
    assert "approved secure environment" in document
    assert "outside this public" in document
    assert "synthetic `final_outcome` label must not be copied" in document
