"""Append-only, file-backed workflow audit events for the prototype.

The store is intentionally separate from analytics artifacts and exposes only
append and read operations.  It accepts compact, allow-listed metadata rather
than arbitrary payload dumps so that workflow evidence does not become a
repository for secrets or personal contact details.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Protocol

from config import settings
from src.alert_case import AlertCase, AlertCaseState


AUDIT_EVENT_SCHEMA_VERSION = "workflow_audit_event.v1"
AUDIT_LOG_FILENAME = "audit_events.jsonl"
AUDIT_ARTIFACT_DIR = settings.BASE_DIR / "artifacts" / "audit"
AUDIT_CONSISTENCY_POLICY = "AUDIT_FIRST_FAIL_CLOSED"
_ALLOWED_METADATA_KEYS = frozenset(
    {
        "operation",
        "idempotency_key_digest",
        "consistency_policy",
        "transition_status",
        "rm_action",
        "case_outcome",
        "closure_reason",
        "reopened_from_alert_id",
    }
)
_SENSITIVE_METADATA_MARKERS = ("@", "secret", "password", "bearer ", "http://", "https://")
_ALERT_CASE_STATES = frozenset(
    {"NEW", "ACKNOWLEDGED", "IN_REVIEW", "FOLLOW_UP", "SNOOZED", "ESCALATED", "CLOSED"}
)


class AuditTrailError(RuntimeError):
    """Base error for audit trail operations."""


class AuditTrailCorruptError(AuditTrailError):
    """The JSONL audit log cannot be read as an append-only sequence."""


class AuditTrailDuplicateError(AuditTrailError):
    """An event ID was reused for different audit content."""


class AuditEventStore(Protocol):
    """Append-only repository boundary; no update or delete operations exist."""

    def append(self, event: "AuditEvent") -> "AuditEvent":
        """Persist an event once and return its assigned sequence."""

    def list_events(self) -> tuple["AuditEvent", ...]:
        """Return events in immutable append order."""


@dataclass(frozen=True)
class AuditEvent:
    """A compact, versioned record of one requested workflow operation."""

    event_id: str
    alert_id: str
    customer_id: str
    event_type: str
    timestamp: datetime
    actor_reference: str
    previous_state: AlertCaseState
    new_state: AlertCaseState
    policy_id: str
    policy_version: str
    selection_policy_id: str
    selection_policy_version: str
    signal_run_id: str
    signal_version: str
    data_version_ref: str
    metadata: Mapping[str, str | int | bool | None]
    sequence: int = 0
    schema_version: str = AUDIT_EVENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_non_empty(
            {
                "event_id": self.event_id,
                "alert_id": self.alert_id,
                "customer_id": self.customer_id,
                "event_type": self.event_type,
                "actor_reference": self.actor_reference,
                "policy_id": self.policy_id,
                "policy_version": self.policy_version,
                "selection_policy_id": self.selection_policy_id,
                "selection_policy_version": self.selection_policy_version,
                "signal_run_id": self.signal_run_id,
                "signal_version": self.signal_version,
                "data_version_ref": self.data_version_ref,
            }
        )
        _validate_aware_datetime(self.timestamp, "timestamp")
        if self.previous_state not in _ALERT_CASE_STATES or self.new_state not in _ALERT_CASE_STATES:
            raise ValueError("previous_state and new_state must be valid AlertCase states")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 0:
            raise ValueError("sequence must be a non-negative integer")
        if self.schema_version != AUDIT_EVENT_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {AUDIT_EVENT_SCHEMA_VERSION}")
        _validate_actor_reference(self.actor_reference)
        _validate_metadata(self.metadata)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "event_id": self.event_id,
            "alert_id": self.alert_id,
            "customer_id": self.customer_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "actor_reference": self.actor_reference,
            "previous_state": self.previous_state,
            "new_state": self.new_state,
            "version_references": {
                "policy_id": self.policy_id,
                "policy_version": self.policy_version,
                "selection_policy_id": self.selection_policy_id,
                "selection_policy_version": self.selection_policy_version,
                "signal_run_id": self.signal_run_id,
                "signal_version": self.signal_version,
                "data_version_ref": self.data_version_ref,
            },
            "metadata": dict(sorted(self.metadata.items())),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "AuditEvent":
        _require_exact_keys(
            payload,
            {
                "schema_version",
                "sequence",
                "event_id",
                "alert_id",
                "customer_id",
                "event_type",
                "timestamp",
                "actor_reference",
                "previous_state",
                "new_state",
                "version_references",
                "metadata",
            },
            "audit event",
        )
        if payload["schema_version"] != AUDIT_EVENT_SCHEMA_VERSION:
            raise ValueError("unexpected audit event schema version")
        version_references = _as_mapping(payload["version_references"], "version_references")
        _require_exact_keys(
            version_references,
            {
                "policy_id",
                "policy_version",
                "selection_policy_id",
                "selection_policy_version",
                "signal_run_id",
                "signal_version",
                "data_version_ref",
            },
            "version_references",
        )
        metadata = _as_mapping(payload["metadata"], "metadata")
        parsed = cls(
            event_id=str(payload["event_id"]),
            alert_id=str(payload["alert_id"]),
            customer_id=str(payload["customer_id"]),
            event_type=str(payload["event_type"]),
            timestamp=_parse_datetime(payload["timestamp"], "timestamp"),
            actor_reference=str(payload["actor_reference"]),
            previous_state=str(payload["previous_state"]),  # type: ignore[arg-type]
            new_state=str(payload["new_state"]),  # type: ignore[arg-type]
            policy_id=str(version_references["policy_id"]),
            policy_version=str(version_references["policy_version"]),
            selection_policy_id=str(version_references["selection_policy_id"]),
            selection_policy_version=str(version_references["selection_policy_version"]),
            signal_run_id=str(version_references["signal_run_id"]),
            signal_version=str(version_references["signal_version"]),
            data_version_ref=str(version_references["data_version_ref"]),
            metadata={str(key): value for key, value in metadata.items()},
            sequence=_as_positive_int(payload["sequence"], "sequence"),
        )
        return parsed


class FileAuditEventStore:
    """Strict JSONL store with logical append-only semantics and atomic writes."""

    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = Path(storage_dir)
        _assert_separate_audit_dir(self.storage_dir)
        self.storage_path = self.storage_dir / AUDIT_LOG_FILENAME

    def append(self, event: AuditEvent) -> AuditEvent:
        if event.sequence != 0:
            raise ValueError("only unsequenced AuditEvent instances can be appended")
        existing_events = self._load_events()
        for existing in existing_events:
            if existing.event_id != event.event_id:
                continue
            if replace(existing, sequence=0) == event:
                return existing
            raise AuditTrailDuplicateError("event_id already exists with different audit content")
        stored = replace(event, sequence=len(existing_events) + 1)
        self._write_events((*existing_events, stored))
        return stored

    def list_events(self) -> tuple[AuditEvent, ...]:
        return self._load_events()

    def _load_events(self) -> tuple[AuditEvent, ...]:
        if not self.storage_path.exists():
            return ()
        try:
            content = self.storage_path.read_text(encoding="utf-8")
        except OSError as error:
            raise AuditTrailCorruptError(f"cannot read audit log: {self.storage_path}") from error
        if not content:
            raise AuditTrailCorruptError("audit log must not be empty when it exists")
        lines = content.splitlines()
        events: list[AuditEvent] = []
        try:
            for index, line in enumerate(lines, start=1):
                if not line.strip():
                    raise ValueError("audit log cannot contain blank lines")
                raw = json.loads(line)
                if not isinstance(raw, dict):
                    raise ValueError("audit log entries must be JSON objects")
                event = AuditEvent.from_dict(raw)
                if event.sequence != index:
                    raise ValueError("audit event sequence must match append order")
                events.append(event)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise AuditTrailCorruptError("audit log contains an invalid append-only event") from error
        event_ids = [event.event_id for event in events]
        if len(event_ids) != len(set(event_ids)):
            raise AuditTrailCorruptError("audit log contains duplicate event IDs")
        return tuple(events)

    def _write_events(self, events: tuple[AuditEvent, ...]) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        lines = "".join(
            json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            for event in events
        )
        temporary_path = self.storage_path.with_name(
            f".{self.storage_path.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            temporary_path.write_text(lines, encoding="utf-8")
            temporary_path.replace(self.storage_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()


def build_banker_audit_event(
    alert_case: AlertCase,
    *,
    operation: str,
    operation_fingerprint: str,
    timestamp: datetime,
    actor_reference: str,
    previous_state: AlertCaseState,
    new_state: AlertCaseState,
    metadata: Mapping[str, str | int | bool | None] | None = None,
) -> AuditEvent:
    """Build a compact audit event from existing case and operation evidence."""

    digest = hashlib.sha256(operation_fingerprint.encode("utf-8")).hexdigest()
    combined_metadata: dict[str, str | int | bool | None] = {
        "operation": operation,
        "idempotency_key_digest": digest,
        "consistency_policy": AUDIT_CONSISTENCY_POLICY,
        "transition_status": "REQUESTED",
    }
    if metadata:
        combined_metadata.update(metadata)
    return AuditEvent(
        event_id=f"AUD-{uuid.uuid5(uuid.NAMESPACE_URL, f'{alert_case.alert_id}|{digest}').hex.upper()}",
        alert_id=alert_case.alert_id,
        customer_id=alert_case.customer_id,
        event_type=f"BANKER_{operation}_REQUESTED",
        timestamp=timestamp,
        actor_reference=actor_reference,
        previous_state=previous_state,
        new_state=new_state,
        policy_id=alert_case.policy_id,
        policy_version=alert_case.policy_version,
        selection_policy_id=alert_case.selection_policy_id,
        selection_policy_version=alert_case.selection_policy_version,
        signal_run_id=alert_case.signal_run_id,
        signal_version=alert_case.signal_version,
        data_version_ref=f"source-signal-run:{alert_case.signal_run_id}",
        metadata=combined_metadata,
    )


def _validate_metadata(values: Mapping[str, str | int | bool | None]) -> None:
    if not isinstance(values, Mapping):
        raise ValueError("metadata must be a mapping")
    keys = {str(key) for key in values}
    unknown = sorted(keys - _ALLOWED_METADATA_KEYS)
    if unknown:
        raise ValueError(f"metadata keys are not allowed: {unknown}")
    if not keys:
        raise ValueError("metadata must not be empty")
    for key, value in values.items():
        if not isinstance(key, str) or key not in _ALLOWED_METADATA_KEYS:
            raise ValueError("metadata keys must be allow-listed strings")
        if value is not None and (isinstance(value, bool) is False and not isinstance(value, (str, int))):
            raise ValueError("metadata values must be scalar")
        if isinstance(value, str):
            normalized = value.strip().lower()
            if not normalized or len(value) > 160:
                raise ValueError("metadata strings must be non-empty and bounded")
            if any(marker in normalized for marker in _SENSITIVE_METADATA_MARKERS):
                raise ValueError("metadata must not contain sensitive or contact details")


def _assert_separate_audit_dir(storage_dir: Path) -> None:
    resolved_storage = storage_dir.resolve()
    analytics_dirs = (
        settings.DATA_RAW_DIR,
        settings.DATA_PROCESSED_DIR,
        settings.DATA_DEMO_DIR,
        settings.REPORTS_DIR,
        settings.BASE_DIR / "artifacts" / "population",
        settings.BASE_DIR / "artifacts" / "validation",
        settings.BASE_DIR / "artifacts" / "triage",
        settings.BASE_DIR / "artifacts" / "workflow",
    )
    for analytics_dir in analytics_dirs:
        try:
            resolved_storage.relative_to(analytics_dir.resolve())
        except ValueError:
            continue
        raise ValueError("audit store must be separate from analytics and workflow artifact directories")


def _require_non_empty(values: Mapping[str, str]) -> None:
    missing = sorted(name for name, value in values.items() if not str(value).strip())
    if missing:
        raise ValueError(f"required fields must be non-empty: {', '.join(missing)}")


def _validate_actor_reference(value: str) -> None:
    normalized = str(value).strip().lower()
    if not normalized or any(marker in normalized for marker in _SENSITIVE_METADATA_MARKERS):
        raise ValueError("actor_reference must be a non-sensitive non-empty identifier")


def _validate_aware_datetime(value: datetime, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be a timezone-aware datetime")


def _require_exact_keys(payload: Mapping[str, object], expected: set[str], label: str) -> None:
    actual = set(payload)
    if actual != expected:
        raise ValueError(f"{label} keys differ: expected {sorted(expected)}, got {sorted(actual)}")


def _as_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _as_positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _parse_datetime(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO datetime string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{label} must be an ISO datetime string") from error
    _validate_aware_datetime(parsed, label)
    return parsed
