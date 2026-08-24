"""Atomic, file-backed repository for provider-neutral Alert/Case work items."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from config import settings
from src.alert_case import AlertCase


ALERT_CASE_REPOSITORY_SCHEMA_VERSION = "alert_case_repository.v1"
ALERT_CASE_REPOSITORY_FILENAME = "alert_cases.json"
WORKFLOW_ARTIFACT_DIR = settings.BASE_DIR / "artifacts" / "workflow"


class AlertCaseRepositoryError(RuntimeError):
    """Base error for the file repository."""


class AlertCaseRepositoryCorruptError(AlertCaseRepositoryError):
    """The repository file cannot be parsed or fails its schema contract."""


class AlertCaseRepositoryConflictError(AlertCaseRepositoryError):
    """An update was based on a stale case snapshot."""


class AlertCaseRepositoryDuplicateError(AlertCaseRepositoryError):
    """A create request would duplicate an ID or an open signal episode."""


class AlertCaseRepository(Protocol):
    """Storage boundary for AlertCase lifecycle operations."""

    def get(self, alert_id: str) -> AlertCase | None:
        """Return one case by ID, or None when it does not exist."""

    def list_cases(self) -> tuple[AlertCase, ...]:
        """Return all cases in deterministic ID order."""

    def create(self, alert_case: AlertCase) -> AlertCase:
        """Create one new case, rejecting duplicates."""

    def update(self, alert_case: AlertCase, *, expected_updated_at: datetime) -> AlertCase:
        """Persist a new version only when the caller has the current version."""

    def open_by_episode(self, customer_id: str, episode_key: str) -> AlertCase | None:
        """Return the sole open case for a customer/signal episode, if present."""


class FileAlertCaseRepository:
    """Single-file JSON repository with strict schema validation and atomic writes."""

    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = Path(storage_dir)
        _assert_separate_workflow_dir(self.storage_dir)
        self.storage_path = self.storage_dir / ALERT_CASE_REPOSITORY_FILENAME

    def get(self, alert_id: str) -> AlertCase | None:
        if not str(alert_id).strip():
            raise ValueError("alert_id must be non-empty")
        return self._load_cases().get(str(alert_id))

    def list_cases(self) -> tuple[AlertCase, ...]:
        return tuple(sorted(self._load_cases().values(), key=lambda item: item.alert_id))

    def create(self, alert_case: AlertCase) -> AlertCase:
        cases_by_id = self._load_cases()
        if alert_case.alert_id in cases_by_id:
            raise AlertCaseRepositoryDuplicateError(f"alert_id already exists: {alert_case.alert_id}")
        duplicate_open = _find_open_episode(
            cases_by_id.values(),
            customer_id=alert_case.customer_id,
            episode_key=alert_case.episode_key,
        )
        if duplicate_open is not None:
            raise AlertCaseRepositoryDuplicateError(
                "an open AlertCase already exists for customer and episode: "
                f"{alert_case.customer_id}/{alert_case.episode_key}"
            )
        cases_by_id[alert_case.alert_id] = alert_case
        self._write_cases(cases_by_id.values())
        return alert_case

    def update(self, alert_case: AlertCase, *, expected_updated_at: datetime) -> AlertCase:
        _validate_aware_datetime(expected_updated_at, "expected_updated_at")
        cases_by_id = self._load_cases()
        current = cases_by_id.get(alert_case.alert_id)
        if current is None:
            raise KeyError(f"unknown alert_id: {alert_case.alert_id}")
        if current.updated_at != expected_updated_at:
            raise AlertCaseRepositoryConflictError(
                f"stale AlertCase update for {alert_case.alert_id}; current state changed"
            )
        if alert_case.customer_id != current.customer_id or alert_case.episode_key != current.episode_key:
            raise ValueError("customer_id and episode_key are immutable repository identities")
        if alert_case.updated_at <= current.updated_at:
            raise AlertCaseRepositoryConflictError("updated_at must advance beyond the current version")
        if alert_case.state != current.state and not current.can_transition_to(alert_case.state):
            raise ValueError(f"illegal persisted state transition: {current.state} -> {alert_case.state}")
        if alert_case.state != current.state:
            duplicate_open = _find_open_episode(
                (
                    item
                    for alert_id, item in cases_by_id.items()
                    if alert_id != alert_case.alert_id
                ),
                customer_id=alert_case.customer_id,
                episode_key=alert_case.episode_key,
            )
            if duplicate_open is not None and alert_case.state != "CLOSED":
                raise AlertCaseRepositoryDuplicateError(
                    "state update would create multiple open cases for one customer and episode"
                )
        cases_by_id[alert_case.alert_id] = alert_case
        self._write_cases(cases_by_id.values())
        return alert_case

    def open_by_episode(self, customer_id: str, episode_key: str) -> AlertCase | None:
        if not str(customer_id).strip() or not str(episode_key).strip():
            raise ValueError("customer_id and episode_key must be non-empty")
        return _find_open_episode(
            self._load_cases().values(),
            customer_id=str(customer_id),
            episode_key=str(episode_key),
        )

    def _load_cases(self) -> dict[str, AlertCase]:
        if not self.storage_path.exists():
            return {}
        try:
            value = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise AlertCaseRepositoryCorruptError(
                f"Cannot read AlertCase repository: {self.storage_path}"
            ) from error
        if not isinstance(value, dict) or set(value) != {"schema_version", "cases"}:
            raise AlertCaseRepositoryCorruptError("AlertCase repository schema is invalid")
        if value["schema_version"] != ALERT_CASE_REPOSITORY_SCHEMA_VERSION:
            raise AlertCaseRepositoryCorruptError("Unexpected AlertCase repository schema version")
        if not isinstance(value["cases"], list):
            raise AlertCaseRepositoryCorruptError("AlertCase repository cases must be a list")
        cases: list[AlertCase] = []
        try:
            for raw_case in value["cases"]:
                if not isinstance(raw_case, dict):
                    raise ValueError("case entry must be an object")
                cases.append(AlertCase.from_dict(raw_case))
        except (TypeError, ValueError) as error:
            raise AlertCaseRepositoryCorruptError("AlertCase repository contains an invalid case") from error
        case_ids = [item.alert_id for item in cases]
        if len(case_ids) != len(set(case_ids)):
            raise AlertCaseRepositoryCorruptError("AlertCase repository contains duplicate alert IDs")
        for item in cases:
            other_open = _find_open_episode(
                (candidate for candidate in cases if candidate.alert_id != item.alert_id),
                customer_id=item.customer_id,
                episode_key=item.episode_key,
            )
            if item.state != "CLOSED" and other_open is not None:
                raise AlertCaseRepositoryCorruptError(
                    "AlertCase repository contains duplicate open customer/episode records"
                )
        return {item.alert_id: item for item in cases}

    def _write_cases(self, cases: Iterable[AlertCase]) -> None:
        ordered = tuple(sorted(cases, key=lambda item: item.alert_id))
        payload: dict[str, Any] = {
            "schema_version": ALERT_CASE_REPOSITORY_SCHEMA_VERSION,
            "cases": [item.to_dict() for item in ordered],
        }
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        temporary_path = self.storage_path.with_name(
            f".{self.storage_path.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            temporary_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            temporary_path.replace(self.storage_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()


def _find_open_episode(
    cases: Iterable[AlertCase],
    *,
    customer_id: str,
    episode_key: str,
) -> AlertCase | None:
    matches = sorted(
        (
            item
            for item in cases
            if item.customer_id == customer_id
            and item.episode_key == episode_key
            and item.state != "CLOSED"
        ),
        key=lambda item: item.alert_id,
    )
    if len(matches) > 1:
        raise AlertCaseRepositoryCorruptError(
            "more than one open AlertCase exists for customer and episode"
        )
    return None if not matches else matches[0]


def _assert_separate_workflow_dir(storage_dir: Path) -> None:
    resolved_storage = storage_dir.resolve()
    analytics_dirs = (
        settings.DATA_RAW_DIR,
        settings.DATA_PROCESSED_DIR,
        settings.DATA_DEMO_DIR,
        settings.REPORTS_DIR,
        settings.BASE_DIR / "artifacts" / "population",
        settings.BASE_DIR / "artifacts" / "validation",
        settings.BASE_DIR / "artifacts" / "triage",
    )
    for analytics_dir in analytics_dirs:
        try:
            resolved_storage.relative_to(analytics_dir.resolve())
        except ValueError:
            continue
        raise ValueError("workflow repository must be separate from analytics and demo artifact directories")


def _validate_aware_datetime(value: datetime, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be a timezone-aware datetime")
