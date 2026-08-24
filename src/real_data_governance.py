"""Governance-only readiness contract for a future approved real-data validation.

This module intentionally has no reader, adapter, client, or transport for
external data. It serializes conditions that must be met outside this public
repository before a separately approved validation environment can handle
anonymized customer data.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from config import settings


REAL_DATA_GOVERNANCE_SCHEMA_VERSION = "real_data_governance.v1"
REAL_DATA_READINESS_ARTIFACT_DIR = (
    settings.BASE_DIR / "artifacts" / "post_p0" / "real_data_readiness"
)
REAL_DATA_GOVERNANCE_FILENAME = "governance_requirements.json"

ApprovalStatus = Literal["not_requested", "pending", "approved"]
_APPROVAL_STATUSES = frozenset({"not_requested", "pending", "approved"})

REQUIRED_APPROVAL_ROLES = (
    "data_owner",
    "security",
    "privacy_dpo_or_legal_as_applicable",
)

MINIMUM_DATA_CONCEPTS = (
    "pseudonymous_customer_key",
    "monthly_timestamp_or_order",
    "income_mappable_field",
    "expense_mappable_field",
    "debt_mappable_field",
    "cash_mappable_field",
    "current_status_mappable_field",
    "observation_window",
    "independently_defined_future_outcome_or_event",
)

EXCLUDED_DATA_CONCEPTS = (
    "direct_identifier",
    "contact_detail",
    "address",
    "account_number",
    "authentication_credential",
)


class GovernanceBoundaryError(ValueError):
    """A requested path would cross the public-repository data boundary."""


@dataclass(frozen=True)
class ApprovalRequirement:
    """One generic approval requirement; the default never asserts approval."""

    role: str
    status: ApprovalStatus = "not_requested"
    evidence_reference: str | None = None

    def __post_init__(self) -> None:
        if self.role not in REQUIRED_APPROVAL_ROLES:
            raise ValueError(f"unsupported governance approval role: {self.role}")
        if self.status not in _APPROVAL_STATUSES:
            raise ValueError("approval status must be not_requested, pending, or approved")
        evidence = self.evidence_reference
        if evidence is not None and (not str(evidence).strip() or "\n" in str(evidence)):
            raise ValueError("approval evidence reference must be a non-empty single line")
        if self.status == "approved" and evidence is None:
            raise ValueError("an approved status requires an external evidence reference")

    def to_dict(self) -> dict[str, str | None]:
        return {
            "role": self.role,
            "status": self.status,
            "evidence_reference": self.evidence_reference,
        }


@dataclass(frozen=True)
class RealDataGovernanceRequirements:
    """Serializable prerequisites, not an authorization or a data adapter."""

    approvals: tuple[ApprovalRequirement, ...]
    schema_version: str = REAL_DATA_GOVERNANCE_SCHEMA_VERSION
    readiness_status: str = "not_ready_for_real_data_admission"
    actual_data_present: bool = False
    public_repository_data_allowed: bool = False
    approved_secure_environment_required: bool = True
    raw_data_download_or_copy_allowed: bool = False
    export_from_secure_environment_allowed: bool = False
    synthetic_final_outcome_reuse_prohibited: bool = True
    canonical_p0_settings_mutated: bool = False

    def __post_init__(self) -> None:
        roles = tuple(item.role for item in self.approvals)
        if roles != REQUIRED_APPROVAL_ROLES:
            raise ValueError("approval requirements must contain each required role in canonical order")
        if self.schema_version != REAL_DATA_GOVERNANCE_SCHEMA_VERSION:
            raise ValueError("unexpected governance schema version")
        if self.readiness_status != "not_ready_for_real_data_admission":
            raise ValueError("this public-repository contract must remain not ready for admission")
        if self.actual_data_present:
            raise ValueError("actual data must never be present in this public-repository contract")
        if self.public_repository_data_allowed:
            raise ValueError("public repository storage of actual data is forbidden")
        if not self.approved_secure_environment_required:
            raise ValueError("an approved secure environment is required")
        if self.raw_data_download_or_copy_allowed:
            raise ValueError("this contract cannot authorize data download or copying")
        if self.export_from_secure_environment_allowed:
            raise ValueError("export from an approved secure environment is forbidden by default")
        if not self.synthetic_final_outcome_reuse_prohibited:
            raise ValueError("synthetic final_outcome reuse must remain prohibited")
        if self.canonical_p0_settings_mutated:
            raise ValueError("governance readiness cannot mutate canonical P0 settings")

    @property
    def approvals_complete(self) -> bool:
        """Report generic role state only; this does not grant data access."""

        return all(item.status == "approved" for item in self.approvals)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "scope": "governance_readiness_only_no_actual_data",
            "readiness_status": self.readiness_status,
            "actual_data_present": self.actual_data_present,
            "approval_requirements": [item.to_dict() for item in self.approvals],
            "approval_roles_complete": self.approvals_complete,
            "data_boundary": {
                "public_repository_data_allowed": self.public_repository_data_allowed,
                "approved_secure_environment_required": self.approved_secure_environment_required,
                "raw_data_download_or_copy_allowed": self.raw_data_download_or_copy_allowed,
                "export_from_secure_environment_allowed": self.export_from_secure_environment_allowed,
                "environment_reference": "external_approval_required_not_recorded_here",
            },
            "minimum_data_concepts": list(MINIMUM_DATA_CONCEPTS),
            "excluded_data_concepts": list(EXCLUDED_DATA_CONCEPTS),
            "controls": {
                "data_minimization_required": True,
                "least_privilege_access_control_required": True,
                "access_and_processing_auditability_required": True,
                "retention_and_deletion_schedule_required": True,
                "environment_separation_required": True,
                "export_prohibition_required": True,
            },
            "outcome_and_horizon_boundary": {
                "independent_actual_owner_outcome_definition_required": True,
                "synthetic_final_outcome_reuse_prohibited": self.synthetic_final_outcome_reuse_prohibited,
                "p0_horizon_comparison_allowed": True,
                "canonical_p0_settings_mutated": self.canonical_p0_settings_mutated,
                "actual_data_availability_requires_separate_approval": True,
            },
            "next_preparation": {
                "synthetic_fixture_harness_allowed": True,
                "real_data_adapter_execution_allowed": False,
                "report_template_development_allowed": True,
            },
            "limitations": [
                "This artifact does not prove organizational approval, data access, or bank performance.",
                "No actual, anonymized, or external customer data is included, read, copied, or processed.",
            ],
        }


def default_real_data_governance_requirements() -> RealDataGovernanceRequirements:
    """Return the explicit no-data, no-approval default for this repository."""

    return RealDataGovernanceRequirements(
        approvals=tuple(ApprovalRequirement(role=role) for role in REQUIRED_APPROVAL_ROLES),
    )


def assert_path_outside_public_repository(candidate_path: Path) -> Path:
    """Reject a proposed actual-data location beneath this public repository."""

    candidate = Path(candidate_path).resolve()
    repository_root = settings.BASE_DIR.resolve()
    try:
        candidate.relative_to(repository_root)
    except ValueError:
        return candidate
    raise GovernanceBoundaryError(
        "actual data must remain outside the public repository in an approved secure environment"
    )


def export_governance_requirements(
    requirements: RealDataGovernanceRequirements,
    output_path: Path,
    *,
    allowed_root: Path | None = None,
) -> Path:
    """Atomically write only metadata under the dedicated Post-P0 artifact root."""

    root = Path(allowed_root) if allowed_root is not None else REAL_DATA_READINESS_ARTIFACT_DIR
    destination = Path(output_path)
    _assert_metadata_output_path(destination, root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    payload = json.dumps(requirements.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, destination)
    except OSError:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
        raise
    return destination


def _assert_metadata_output_path(destination: Path, allowed_root: Path) -> None:
    resolved_destination = destination.resolve()
    resolved_root = allowed_root.resolve()
    try:
        resolved_destination.relative_to(resolved_root)
    except ValueError as error:
        raise GovernanceBoundaryError(
            "governance metadata must be written under its injected Post-P0 readiness root"
        ) from error
