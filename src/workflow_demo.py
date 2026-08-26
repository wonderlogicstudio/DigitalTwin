"""Deterministic, isolated synthetic workflow-demo fixture contract.

This module creates no work at import time.  A caller must explicitly invoke
``reset_demo`` before the separate demo runtime contains any cases.  The
fixture is intentionally tiny and immutable; only the isolated runtime may be
changed later through the existing application-service boundary.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from csv import DictReader
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Mapping

from config import settings
from src.alert_case import AlertCase, TimingEvidenceReference, create_alert_case
from src.alert_repository import (
    ALERT_CASE_REPOSITORY_FILENAME,
    AlertCaseRepositoryCorruptError,
    FileAlertCaseRepository,
)
from src.audit_trail import AUDIT_LOG_FILENAME, AuditTrailCorruptError, FileAuditEventStore


WORKFLOW_DEMO_FIXTURE_SCHEMA_VERSION = "workflow_demo_fixture.v1"
WORKFLOW_DEMO_RUNTIME_SCHEMA_VERSION = "workflow_demo_runtime.v1"
WORKFLOW_DEMO_FIXTURE_FILENAME = "workflow_demo_fixture.json"
WORKFLOW_DEMO_RUNTIME_MANIFEST_FILENAME = "runtime_manifest.json"
WORKFLOW_DEMO_RESET_MARKER_FILENAME = ".resetting.json"
WORKFLOW_DEMO_MAX_CASES = 3

WorkflowDemoStatus = Literal["DEMO_NOT_INITIALIZED", "DEMO_READY", "DEMO_CORRUPT"]


class WorkflowDemoError(ValueError):
    """The isolated synthetic workflow-demo contract was not satisfied."""


@dataclass(frozen=True)
class WorkflowDemoPaths:
    """Immutable fixture and mutable-runtime paths, separated from defaults."""

    fixture_path: Path
    runtime_root: Path

    def __post_init__(self) -> None:
        fixture_path = Path(self.fixture_path)
        runtime_root = Path(self.runtime_root)
        object.__setattr__(self, "fixture_path", fixture_path)
        object.__setattr__(self, "runtime_root", runtime_root)
        _assert_isolated_paths(fixture_path, runtime_root)

    @classmethod
    def default(cls) -> "WorkflowDemoPaths":
        root = settings.BASE_DIR / "artifacts" / "workflow_demo"
        return cls(
            fixture_path=root / "fixture_v1" / WORKFLOW_DEMO_FIXTURE_FILENAME,
            runtime_root=root / "runtime",
        )

    @property
    def workflow_root(self) -> Path:
        return self.runtime_root / "workflow"

    @property
    def audit_root(self) -> Path:
        return self.runtime_root / "audit"

    @property
    def runtime_manifest_path(self) -> Path:
        return self.runtime_root / WORKFLOW_DEMO_RUNTIME_MANIFEST_FILENAME

    @property
    def reset_marker_path(self) -> Path:
        return self.runtime_root / WORKFLOW_DEMO_RESET_MARKER_FILENAME


@dataclass(frozen=True)
class WorkflowDemoFixtureCase:
    """One pre-defined synthetic case source; it is not a selection engine."""

    fixture_case_id: str
    fixture_order: int
    alert_id: str
    customer_id: str
    policy_id: str
    policy_version: str
    selection_policy_id: str
    selection_policy_version: str
    signal_run_id: str
    signal_version: str
    signal_as_of_month: int
    created_at: datetime
    due_at: datetime
    operational_priority: str
    why_now_reason_codes: tuple[str, ...]
    selection_reason_codes: tuple[str, ...]
    timing_evidence_reference: TimingEvidenceReference
    episode_key: str
    actor_reference: str
    initial_state: str

    def __post_init__(self) -> None:
        _require_text(self.fixture_case_id, "fixture_case_id")
        _require_text(self.alert_id, "alert_id")
        _require_synthetic_customer_id(self.customer_id)
        _require_positive_int(self.fixture_order, "fixture_order")
        for label, value in (
            ("policy_id", self.policy_id),
            ("policy_version", self.policy_version),
            ("selection_policy_id", self.selection_policy_id),
            ("selection_policy_version", self.selection_policy_version),
            ("signal_run_id", self.signal_run_id),
            ("signal_version", self.signal_version),
            ("episode_key", self.episode_key),
            ("actor_reference", self.actor_reference),
        ):
            _require_text(value, label)
        _require_month(self.signal_as_of_month, "signal_as_of_month")
        _require_aware_datetime(self.created_at, "created_at")
        _require_aware_datetime(self.due_at, "due_at")
        if self.due_at < self.created_at:
            raise WorkflowDemoError("due_at must not precede created_at")
        if self.operational_priority not in {"REVIEW", "PRIORITY_REVIEW"}:
            raise WorkflowDemoError("operational_priority is invalid")
        _require_reason_codes(self.why_now_reason_codes, "why_now_reason_codes")
        _require_reason_codes(self.selection_reason_codes, "selection_reason_codes")
        if self.timing_evidence_reference.candidate_month != self.signal_as_of_month:
            raise WorkflowDemoError("timing evidence must match signal_as_of_month")
        if self.initial_state != "NEW":
            raise WorkflowDemoError("workflow-demo fixture cases must start in NEW")

    def to_alert_case(self) -> AlertCase:
        """Build a deterministic initial case without persisting or delivering it."""

        return create_alert_case(
            alert_id=self.alert_id,
            customer_id=self.customer_id,
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            selection_policy_id=self.selection_policy_id,
            selection_policy_version=self.selection_policy_version,
            signal_run_id=self.signal_run_id,
            signal_version=self.signal_version,
            signal_as_of_month=self.signal_as_of_month,
            created_at=self.created_at,
            due_at=self.due_at,
            operational_priority=self.operational_priority,  # type: ignore[arg-type]
            why_now_reason_codes=self.why_now_reason_codes,
            selection_reason_codes=self.selection_reason_codes,
            timing_evidence_reference=self.timing_evidence_reference,
            episode_key=self.episode_key,
            owner_reference=None,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "fixture_case_id": self.fixture_case_id,
            "fixture_order": self.fixture_order,
            "alert_id": self.alert_id,
            "customer_id": self.customer_id,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "selection_policy_id": self.selection_policy_id,
            "selection_policy_version": self.selection_policy_version,
            "signal_run_id": self.signal_run_id,
            "signal_version": self.signal_version,
            "signal_as_of_month": self.signal_as_of_month,
            "created_at": self.created_at.isoformat(),
            "due_at": self.due_at.isoformat(),
            "operational_priority": self.operational_priority,
            "why_now_reason_codes": list(self.why_now_reason_codes),
            "selection_reason_codes": list(self.selection_reason_codes),
            "timing_evidence_reference": self.timing_evidence_reference.to_dict(),
            "episode_key": self.episode_key,
            "actor_reference": self.actor_reference,
            "initial_state": self.initial_state,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "WorkflowDemoFixtureCase":
        expected = {
            "fixture_case_id",
            "fixture_order",
            "alert_id",
            "customer_id",
            "policy_id",
            "policy_version",
            "selection_policy_id",
            "selection_policy_version",
            "signal_run_id",
            "signal_version",
            "signal_as_of_month",
            "created_at",
            "due_at",
            "operational_priority",
            "why_now_reason_codes",
            "selection_reason_codes",
            "timing_evidence_reference",
            "episode_key",
            "actor_reference",
            "initial_state",
        }
        _require_exact_keys(payload, expected, "workflow-demo fixture case")
        timing = _as_mapping(payload["timing_evidence_reference"], "timing_evidence_reference")
        return cls(
            fixture_case_id=_as_text(payload["fixture_case_id"], "fixture_case_id"),
            fixture_order=_as_int(payload["fixture_order"], "fixture_order"),
            alert_id=_as_text(payload["alert_id"], "alert_id"),
            customer_id=_as_text(payload["customer_id"], "customer_id"),
            policy_id=_as_text(payload["policy_id"], "policy_id"),
            policy_version=_as_text(payload["policy_version"], "policy_version"),
            selection_policy_id=_as_text(payload["selection_policy_id"], "selection_policy_id"),
            selection_policy_version=_as_text(
                payload["selection_policy_version"], "selection_policy_version"
            ),
            signal_run_id=_as_text(payload["signal_run_id"], "signal_run_id"),
            signal_version=_as_text(payload["signal_version"], "signal_version"),
            signal_as_of_month=_as_int(payload["signal_as_of_month"], "signal_as_of_month"),
            created_at=_as_datetime(payload["created_at"], "created_at"),
            due_at=_as_datetime(payload["due_at"], "due_at"),
            operational_priority=_as_text(payload["operational_priority"], "operational_priority"),
            why_now_reason_codes=_as_text_tuple(payload["why_now_reason_codes"], "why_now_reason_codes"),
            selection_reason_codes=_as_text_tuple(
                payload["selection_reason_codes"], "selection_reason_codes"
            ),
            timing_evidence_reference=TimingEvidenceReference.from_dict(timing),
            episode_key=_as_text(payload["episode_key"], "episode_key"),
            actor_reference=_as_text(payload["actor_reference"], "actor_reference"),
            initial_state=_as_text(payload["initial_state"], "initial_state"),
        )


@dataclass(frozen=True)
class WorkflowDemoFixture:
    """Versioned immutable input for exactly one small synthetic demo."""

    fixture_id: str
    fixture_version: str
    source_reference: Mapping[str, str]
    deterministic_time_policy: Mapping[str, str]
    cases: tuple[WorkflowDemoFixtureCase, ...]
    synthetic_demo: bool = True
    external_delivery_attempted: bool = False
    network_called: bool = False
    sent: bool = False
    future_label_selection: bool = False
    schema_version: str = WORKFLOW_DEMO_FIXTURE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_text(self.fixture_id, "fixture_id")
        _require_text(self.fixture_version, "fixture_version")
        if self.schema_version != WORKFLOW_DEMO_FIXTURE_SCHEMA_VERSION:
            raise WorkflowDemoError("unexpected workflow-demo fixture schema version")
        if self.synthetic_demo is not True:
            raise WorkflowDemoError("workflow-demo fixture must be synthetic")
        if any((self.external_delivery_attempted, self.network_called, self.sent)):
            raise WorkflowDemoError("workflow-demo fixture cannot deliver or send")
        if self.future_label_selection is not False:
            raise WorkflowDemoError("workflow-demo fixture selection contract is invalid")
        _require_string_mapping(self.source_reference, "source_reference")
        _require_string_mapping(self.deterministic_time_policy, "deterministic_time_policy")
        if not 1 <= len(self.cases) <= WORKFLOW_DEMO_MAX_CASES:
            raise WorkflowDemoError(f"fixture must contain 1 to {WORKFLOW_DEMO_MAX_CASES} cases")
        fixture_case_ids = [case.fixture_case_id for case in self.cases]
        alert_ids = [case.alert_id for case in self.cases]
        customer_ids = [case.customer_id for case in self.cases]
        orders = [case.fixture_order for case in self.cases]
        if any(len(values) != len(set(values)) for values in (fixture_case_ids, alert_ids, customer_ids, orders)):
            raise WorkflowDemoError("fixture case identifiers, customers, alerts, and order must be unique")
        if tuple(sorted(orders)) != tuple(range(1, len(self.cases) + 1)):
            raise WorkflowDemoError("fixture order must be a contiguous deterministic prefix")
        if tuple(case.fixture_order for case in self.cases) != tuple(sorted(orders)):
            raise WorkflowDemoError("fixture cases must be stored in deterministic order")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "fixture_id": self.fixture_id,
            "fixture_version": self.fixture_version,
            "synthetic_demo": self.synthetic_demo,
            "source_reference": dict(sorted(self.source_reference.items())),
            "deterministic_time_policy": dict(sorted(self.deterministic_time_policy.items())),
            "external_delivery_attempted": self.external_delivery_attempted,
            "network_called": self.network_called,
            "sent": self.sent,
            "future_label_selection": self.future_label_selection,
            "cases": [case.to_dict() for case in self.cases],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "WorkflowDemoFixture":
        expected = {
            "schema_version",
            "fixture_id",
            "fixture_version",
            "synthetic_demo",
            "source_reference",
            "deterministic_time_policy",
            "external_delivery_attempted",
            "network_called",
            "sent",
            "future_label_selection",
            "cases",
        }
        _require_exact_keys(payload, expected, "workflow-demo fixture")
        raw_cases = payload["cases"]
        if not isinstance(raw_cases, list):
            raise WorkflowDemoError("fixture cases must be a list")
        return cls(
            schema_version=_as_text(payload["schema_version"], "schema_version"),
            fixture_id=_as_text(payload["fixture_id"], "fixture_id"),
            fixture_version=_as_text(payload["fixture_version"], "fixture_version"),
            synthetic_demo=_as_bool(payload["synthetic_demo"], "synthetic_demo"),
            source_reference=_as_string_mapping(payload["source_reference"], "source_reference"),
            deterministic_time_policy=_as_string_mapping(
                payload["deterministic_time_policy"], "deterministic_time_policy"
            ),
            external_delivery_attempted=_as_bool(
                payload["external_delivery_attempted"], "external_delivery_attempted"
            ),
            network_called=_as_bool(payload["network_called"], "network_called"),
            sent=_as_bool(payload["sent"], "sent"),
            future_label_selection=_as_bool(
                payload["future_label_selection"], "future_label_selection"
            ),
            cases=tuple(
                WorkflowDemoFixtureCase.from_dict(_as_mapping(item, "fixture case"))
                for item in raw_cases
            ),
        )


@dataclass(frozen=True)
class WorkflowDemoRuntimeManifest:
    """Provenance for a reset runtime, not an operational delivery record."""

    fixture_id: str
    fixture_version: str
    fixture_sha256: str
    source_reference: Mapping[str, str]
    source_digest: str
    alert_ids: tuple[str, ...]
    customer_ids: tuple[str, ...]
    initial_states: Mapping[str, str]
    deterministic_time_policy: Mapping[str, str]
    case_repository_sha256: str
    audit_log_sha256: str | None
    synthetic_actor_reference: str
    runtime_case_count: int
    synthetic_demo: bool = True
    external_delivery_attempted: bool = False
    network_called: bool = False
    sent: bool = False
    future_label_selection: bool = False
    default_workflow_root_used: bool = False
    default_audit_root_used: bool = False
    runtime_status: str = "DEMO_READY"
    schema_version: str = WORKFLOW_DEMO_RUNTIME_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != WORKFLOW_DEMO_RUNTIME_SCHEMA_VERSION:
            raise WorkflowDemoError("unexpected workflow-demo runtime schema version")
        if self.runtime_status != "DEMO_READY":
            raise WorkflowDemoError("runtime manifest must be ready")
        if self.synthetic_demo is not True or self.future_label_selection is not False:
            raise WorkflowDemoError("runtime manifest synthetic selection contract is invalid")
        if any(
            (
                self.external_delivery_attempted,
                self.network_called,
                self.sent,
                self.default_workflow_root_used,
                self.default_audit_root_used,
            )
        ):
            raise WorkflowDemoError("runtime manifest cannot use default roots or delivery")
        _require_text(self.fixture_id, "fixture_id")
        _require_text(self.fixture_version, "fixture_version")
        _require_text(self.fixture_sha256, "fixture_sha256")
        _require_text(self.source_digest, "source_digest")
        _require_text(self.case_repository_sha256, "case_repository_sha256")
        _require_text(self.synthetic_actor_reference, "synthetic_actor_reference")
        _require_string_mapping(self.source_reference, "source_reference")
        _require_string_mapping(self.deterministic_time_policy, "deterministic_time_policy")
        _require_positive_int(self.runtime_case_count, "runtime_case_count")
        if self.runtime_case_count > WORKFLOW_DEMO_MAX_CASES:
            raise WorkflowDemoError("runtime manifest exceeds workflow-demo case limit")
        if len(self.alert_ids) != self.runtime_case_count or len(self.customer_ids) != self.runtime_case_count:
            raise WorkflowDemoError("runtime manifest identifiers do not reconcile")
        if len(self.alert_ids) != len(set(self.alert_ids)) or len(self.customer_ids) != len(set(self.customer_ids)):
            raise WorkflowDemoError("runtime manifest identifiers must be unique")
        if set(self.initial_states) != set(self.alert_ids) or set(self.initial_states.values()) != {"NEW"}:
            raise WorkflowDemoError("runtime manifest initial states must be NEW for every fixture case")
        if self.audit_log_sha256 is not None:
            _require_text(self.audit_log_sha256, "audit_log_sha256")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "runtime_status": self.runtime_status,
            "fixture_id": self.fixture_id,
            "fixture_version": self.fixture_version,
            "fixture_sha256": self.fixture_sha256,
            "source_reference": dict(sorted(self.source_reference.items())),
            "source_digest": self.source_digest,
            "synthetic_demo": self.synthetic_demo,
            "alert_ids": list(self.alert_ids),
            "customer_ids": list(self.customer_ids),
            "runtime_case_count": self.runtime_case_count,
            "initial_states": dict(sorted(self.initial_states.items())),
            "deterministic_time_policy": dict(sorted(self.deterministic_time_policy.items())),
            "case_repository_sha256": self.case_repository_sha256,
            "audit_log_sha256": self.audit_log_sha256,
            "synthetic_actor_reference": self.synthetic_actor_reference,
            "default_workflow_root_used": self.default_workflow_root_used,
            "default_audit_root_used": self.default_audit_root_used,
            "external_delivery_attempted": self.external_delivery_attempted,
            "network_called": self.network_called,
            "sent": self.sent,
            "future_label_selection": self.future_label_selection,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "WorkflowDemoRuntimeManifest":
        expected = {
            "schema_version",
            "runtime_status",
            "fixture_id",
            "fixture_version",
            "fixture_sha256",
            "source_reference",
            "source_digest",
            "synthetic_demo",
            "alert_ids",
            "customer_ids",
            "runtime_case_count",
            "initial_states",
            "deterministic_time_policy",
            "case_repository_sha256",
            "audit_log_sha256",
            "synthetic_actor_reference",
            "default_workflow_root_used",
            "default_audit_root_used",
            "external_delivery_attempted",
            "network_called",
            "sent",
            "future_label_selection",
        }
        _require_exact_keys(payload, expected, "workflow-demo runtime manifest")
        return cls(
            schema_version=_as_text(payload["schema_version"], "schema_version"),
            runtime_status=_as_text(payload["runtime_status"], "runtime_status"),
            fixture_id=_as_text(payload["fixture_id"], "fixture_id"),
            fixture_version=_as_text(payload["fixture_version"], "fixture_version"),
            fixture_sha256=_as_text(payload["fixture_sha256"], "fixture_sha256"),
            source_reference=_as_string_mapping(payload["source_reference"], "source_reference"),
            source_digest=_as_text(payload["source_digest"], "source_digest"),
            synthetic_demo=_as_bool(payload["synthetic_demo"], "synthetic_demo"),
            alert_ids=_as_text_tuple(payload["alert_ids"], "alert_ids"),
            customer_ids=_as_text_tuple(payload["customer_ids"], "customer_ids"),
            runtime_case_count=_as_int(payload["runtime_case_count"], "runtime_case_count"),
            initial_states=_as_string_mapping(payload["initial_states"], "initial_states"),
            deterministic_time_policy=_as_string_mapping(
                payload["deterministic_time_policy"], "deterministic_time_policy"
            ),
            case_repository_sha256=_as_text(
                payload["case_repository_sha256"], "case_repository_sha256"
            ),
            audit_log_sha256=(
                None
                if payload["audit_log_sha256"] is None
                else _as_text(payload["audit_log_sha256"], "audit_log_sha256")
            ),
            synthetic_actor_reference=_as_text(
                payload["synthetic_actor_reference"], "synthetic_actor_reference"
            ),
            default_workflow_root_used=_as_bool(
                payload["default_workflow_root_used"], "default_workflow_root_used"
            ),
            default_audit_root_used=_as_bool(
                payload["default_audit_root_used"], "default_audit_root_used"
            ),
            external_delivery_attempted=_as_bool(
                payload["external_delivery_attempted"], "external_delivery_attempted"
            ),
            network_called=_as_bool(payload["network_called"], "network_called"),
            sent=_as_bool(payload["sent"], "sent"),
            future_label_selection=_as_bool(
                payload["future_label_selection"], "future_label_selection"
            ),
        )


@dataclass(frozen=True)
class WorkflowDemoRuntimeSnapshot:
    """A fail-closed read result that never uses the default workflow store."""

    status: WorkflowDemoStatus
    paths: WorkflowDemoPaths
    cases: tuple[AlertCase, ...] = ()
    manifest: WorkflowDemoRuntimeManifest | None = None
    detail: str | None = None

    @property
    def is_ready(self) -> bool:
        return self.status == "DEMO_READY"


def load_demo_fixture(paths: WorkflowDemoPaths | None = None) -> WorkflowDemoFixture:
    """Read and validate the immutable fixture without creating a runtime."""

    resolved_paths = paths or WorkflowDemoPaths.default()
    payload = _read_json_object(resolved_paths.fixture_path, "workflow-demo fixture")
    fixture = WorkflowDemoFixture.from_dict(payload)
    _validate_fixture_customer_universe(fixture)
    return fixture


def load_demo_runtime(paths: WorkflowDemoPaths | None = None) -> WorkflowDemoRuntimeSnapshot:
    """Load only the isolated runtime and fail closed for missing/corrupt state."""

    resolved_paths = paths or WorkflowDemoPaths.default()
    if resolved_paths.reset_marker_path.exists():
        return WorkflowDemoRuntimeSnapshot(
            status="DEMO_NOT_INITIALIZED",
            paths=resolved_paths,
            detail="workflow-demo reset is incomplete",
        )
    manifest_path = resolved_paths.runtime_manifest_path
    runtime_children_exist = any(
        path.exists()
        for path in (
            resolved_paths.workflow_root,
            resolved_paths.audit_root,
            manifest_path,
        )
    )
    if not manifest_path.exists():
        status: WorkflowDemoStatus = "DEMO_CORRUPT" if runtime_children_exist else "DEMO_NOT_INITIALIZED"
        return WorkflowDemoRuntimeSnapshot(
            status=status,
            paths=resolved_paths,
            detail="workflow-demo runtime manifest is missing",
        )
    try:
        fixture = load_demo_fixture(resolved_paths)
        manifest = WorkflowDemoRuntimeManifest.from_dict(
            _read_json_object(manifest_path, "workflow-demo runtime manifest")
        )
        if manifest.fixture_id != fixture.fixture_id or manifest.fixture_version != fixture.fixture_version:
            raise WorkflowDemoError("runtime manifest fixture identity differs from fixture")
        if manifest.fixture_sha256 != _sha256_file(resolved_paths.fixture_path):
            raise WorkflowDemoError("runtime manifest fixture digest differs from fixture")
        if manifest.source_reference != fixture.source_reference:
            raise WorkflowDemoError("runtime manifest provenance differs from fixture")
        expected_source_digest = _sha256_json(fixture.source_reference)
        if manifest.source_digest != expected_source_digest:
            raise WorkflowDemoError("runtime manifest source digest differs from fixture")
        repository = FileAlertCaseRepository(resolved_paths.workflow_root)
        cases = repository.list_cases()
        FileAuditEventStore(resolved_paths.audit_root).list_events()
        _validate_runtime_cases(fixture, manifest, cases)
    except (
        AlertCaseRepositoryCorruptError,
        AuditTrailCorruptError,
        OSError,
        WorkflowDemoError,
        ValueError,
    ) as error:
        return WorkflowDemoRuntimeSnapshot(
            status="DEMO_CORRUPT",
            paths=resolved_paths,
            detail=str(error),
        )
    return WorkflowDemoRuntimeSnapshot(
        status="DEMO_READY",
        paths=resolved_paths,
        cases=cases,
        manifest=manifest,
    )


def reset_demo(paths: WorkflowDemoPaths | None = None) -> WorkflowDemoRuntimeSnapshot:
    """Explicitly rebuild the small demo runtime from its immutable fixture.

    A resetting marker is written before mutable children are replaced and is
    removed only after the final manifest is atomically installed.  Readers
    therefore return a non-ready status rather than expose a partial reset.
    """

    resolved_paths = paths or WorkflowDemoPaths.default()
    fixture = load_demo_fixture(resolved_paths)
    fixture_digest = _sha256_file(resolved_paths.fixture_path)
    stage_root = resolved_paths.runtime_root.parent / (
        f".{resolved_paths.runtime_root.name}.stage-{uuid.uuid4().hex}"
    )
    try:
        stage_paths = WorkflowDemoPaths(
            fixture_path=resolved_paths.fixture_path,
            runtime_root=stage_root,
        )
        stage_paths.runtime_root.mkdir(parents=True, exist_ok=False)
        repository = FileAlertCaseRepository(stage_paths.workflow_root)
        for case in fixture.cases:
            repository.create(case.to_alert_case())
        stage_paths.audit_root.mkdir(parents=True, exist_ok=True)
        cases = repository.list_cases()
        manifest = _build_runtime_manifest(
            fixture=fixture,
            fixture_digest=fixture_digest,
            cases=cases,
            workflow_path=repository.storage_path,
            audit_path=stage_paths.audit_root / AUDIT_LOG_FILENAME,
        )
        _write_json_atomic(stage_paths.runtime_manifest_path, manifest.to_dict())
        staged = load_demo_runtime(stage_paths)
        if not staged.is_ready:
            raise WorkflowDemoError(f"staged runtime is not valid: {staged.detail}")

        resolved_paths.runtime_root.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(
            resolved_paths.reset_marker_path,
            {
                "schema_version": WORKFLOW_DEMO_RUNTIME_SCHEMA_VERSION,
                "runtime_status": "RESETTING",
                "synthetic_demo": True,
            },
        )
        _remove_runtime_contents_except_reset_marker(resolved_paths)
        stage_paths.workflow_root.replace(resolved_paths.workflow_root)
        stage_paths.audit_root.replace(resolved_paths.audit_root)
        stage_paths.runtime_manifest_path.replace(resolved_paths.runtime_manifest_path)
        resolved_paths.reset_marker_path.unlink(missing_ok=True)
    finally:
        if stage_root.exists():
            shutil.rmtree(stage_root)

    snapshot = load_demo_runtime(resolved_paths)
    if not snapshot.is_ready:
        raise WorkflowDemoError(f"reset did not produce a ready demo runtime: {snapshot.detail}")
    return snapshot


def _build_runtime_manifest(
    *,
    fixture: WorkflowDemoFixture,
    fixture_digest: str,
    cases: tuple[AlertCase, ...],
    workflow_path: Path,
    audit_path: Path,
) -> WorkflowDemoRuntimeManifest:
    expected_cases = tuple(case.to_alert_case() for case in fixture.cases)
    if cases != tuple(sorted(expected_cases, key=lambda item: item.alert_id)):
        raise WorkflowDemoError("runtime bootstrap cases differ from fixture")
    return WorkflowDemoRuntimeManifest(
        fixture_id=fixture.fixture_id,
        fixture_version=fixture.fixture_version,
        fixture_sha256=fixture_digest,
        source_reference=fixture.source_reference,
        source_digest=_sha256_json(fixture.source_reference),
        alert_ids=tuple(case.alert_id for case in fixture.cases),
        customer_ids=tuple(case.customer_id for case in fixture.cases),
        initial_states={case.alert_id: case.initial_state for case in fixture.cases},
        deterministic_time_policy=fixture.deterministic_time_policy,
        case_repository_sha256=_sha256_file(workflow_path),
        audit_log_sha256=None if not audit_path.exists() else _sha256_file(audit_path),
        synthetic_actor_reference=fixture.cases[0].actor_reference,
        runtime_case_count=len(cases),
    )


def _validate_runtime_cases(
    fixture: WorkflowDemoFixture,
    manifest: WorkflowDemoRuntimeManifest,
    cases: tuple[AlertCase, ...],
) -> None:
    if not 1 <= len(cases) <= WORKFLOW_DEMO_MAX_CASES:
        raise WorkflowDemoError("runtime case count is outside the fixture limit")
    if len(cases) != manifest.runtime_case_count:
        raise WorkflowDemoError("runtime case count differs from manifest")
    if tuple(case.alert_id for case in cases) != tuple(sorted(manifest.alert_ids)):
        raise WorkflowDemoError("runtime alert identifiers differ from manifest")
    fixture_by_alert = {case.alert_id: case for case in fixture.cases}
    if set(fixture_by_alert) != set(manifest.alert_ids):
        raise WorkflowDemoError("fixture alert identifiers differ from manifest")
    if tuple(case.customer_id for case in fixture.cases) != manifest.customer_ids:
        raise WorkflowDemoError("fixture customer identifiers differ from manifest")
    for alert_case in cases:
        fixture_case = fixture_by_alert.get(alert_case.alert_id)
        if fixture_case is None or alert_case.customer_id != fixture_case.customer_id:
            raise WorkflowDemoError("runtime case identity differs from fixture")


def _assert_isolated_paths(fixture_path: Path, runtime_root: Path) -> None:
    resolved_fixture = fixture_path.resolve()
    resolved_runtime = runtime_root.resolve()
    if _is_within(resolved_fixture, resolved_runtime) or _is_within(resolved_runtime, resolved_fixture):
        raise WorkflowDemoError("fixture and runtime paths must be separate")
    protected_roots = (
        settings.DATA_RAW_DIR,
        settings.DATA_PROCESSED_DIR,
        settings.DATA_DEMO_DIR,
        settings.REPORTS_DIR,
        settings.BASE_DIR / "artifacts" / "population",
        settings.BASE_DIR / "artifacts" / "validation",
        settings.BASE_DIR / "artifacts" / "triage",
        settings.BASE_DIR / "artifacts" / "workflow",
        settings.BASE_DIR / "artifacts" / "audit",
    )
    for protected in protected_roots:
        resolved_protected = protected.resolve()
        if _is_within(resolved_runtime, resolved_protected) or _is_within(
            resolved_protected, resolved_runtime
        ):
            raise WorkflowDemoError("workflow-demo runtime must be separate from default and analytics roots")


def _validate_fixture_customer_universe(fixture: WorkflowDemoFixture) -> None:
    """Confirm fixture IDs exist in the seed-42 synthetic customer universe.

    Only the identifier column is consulted.  This validates a fixture source;
    it does not score, rank, or choose customers.
    """

    master_path = settings.DATA_RAW_DIR / "customer_master.csv"
    if not master_path.is_file():
        raise WorkflowDemoError("synthetic customer universe source is unavailable")
    try:
        with master_path.open("r", encoding="utf-8", newline="") as source:
            reader = DictReader(source)
            if reader.fieldnames is None or "customer_id" not in reader.fieldnames:
                raise WorkflowDemoError("synthetic customer universe has no customer_id column")
            customer_ids = {str(row.get("customer_id", "")).strip() for row in reader}
    except OSError as error:
        raise WorkflowDemoError("cannot read synthetic customer universe") from error
    missing = sorted({case.customer_id for case in fixture.cases} - customer_ids)
    if missing:
        raise WorkflowDemoError(f"fixture customer IDs are not in the synthetic universe: {missing}")


def _remove_runtime_child(paths: WorkflowDemoPaths, child: Path) -> None:
    resolved_child = child.resolve()
    try:
        resolved_child.relative_to(paths.runtime_root.resolve())
    except ValueError as error:
        raise WorkflowDemoError("only an isolated workflow-demo runtime child may be reset") from error
    if child.is_dir():
        shutil.rmtree(child)
    elif child.exists():
        child.unlink()


def _remove_runtime_contents_except_reset_marker(paths: WorkflowDemoPaths) -> None:
    """Clear only the isolated runtime, keeping its non-ready marker visible."""

    for child in tuple(paths.runtime_root.iterdir()):
        if child == paths.reset_marker_path:
            continue
        _remove_runtime_child(paths, child)


def _read_json_object(path: Path, label: str) -> dict[str, object]:
    if not path.is_file():
        raise WorkflowDemoError(f"{label} does not exist: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WorkflowDemoError(f"cannot read {label}") from error
    if not isinstance(value, dict):
        raise WorkflowDemoError(f"{label} must be a JSON object")
    return {str(key): item for key, item in value.items()}


def _write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary_path.replace(path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_json(payload: Mapping[str, str]) -> str:
    encoded = json.dumps(dict(sorted(payload.items())), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _require_exact_keys(payload: Mapping[str, object], expected: set[str], label: str) -> None:
    actual = set(payload)
    if actual != expected:
        raise WorkflowDemoError(
            f"{label} keys differ; missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )


def _as_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise WorkflowDemoError(f"{label} must be an object")
    return {str(key): item for key, item in value.items()}


def _as_string_mapping(value: object, label: str) -> Mapping[str, str]:
    mapping = _as_mapping(value, label)
    parsed = {str(key): _as_text(item, f"{label}.{key}") for key, item in mapping.items()}
    _require_string_mapping(parsed, label)
    return parsed


def _require_string_mapping(value: Mapping[str, str], label: str) -> None:
    if not value:
        raise WorkflowDemoError(f"{label} must not be empty")
    for key, item in value.items():
        _require_text(str(key), label)
        _require_text(item, label)


def _as_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowDemoError(f"{label} must be non-empty text")
    return value


def _require_text(value: str, label: str) -> None:
    _as_text(value, label)


def _as_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise WorkflowDemoError(f"{label} must be a boolean")
    return value


def _as_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorkflowDemoError(f"{label} must be an integer")
    return value


def _require_positive_int(value: int, label: str) -> None:
    if value <= 0:
        raise WorkflowDemoError(f"{label} must be positive")


def _require_month(value: int, label: str) -> None:
    _require_positive_int(value, label)
    if value > settings.TOTAL_MONTHS:
        raise WorkflowDemoError(f"{label} must not exceed configured months")


def _as_datetime(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise WorkflowDemoError(f"{label} must be an ISO datetime")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise WorkflowDemoError(f"{label} must be an ISO datetime") from error
    _require_aware_datetime(parsed, label)
    return parsed


def _require_aware_datetime(value: datetime, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise WorkflowDemoError(f"{label} must be timezone-aware")


def _as_text_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise WorkflowDemoError(f"{label} must be a list")
    parsed = tuple(_as_text(item, label) for item in value)
    _require_reason_codes(parsed, label)
    return parsed


def _require_reason_codes(value: tuple[str, ...], label: str) -> None:
    if not value or len(value) != len(set(value)):
        raise WorkflowDemoError(f"{label} must contain unique non-empty values")


def _require_synthetic_customer_id(value: str) -> None:
    _require_text(value, "customer_id")
    if len(value) != 7 or not value.startswith("C") or not value[1:].isdigit():
        raise WorkflowDemoError("customer_id must use the synthetic customer identifier format")
