"""Contracts for atomic Alert/Case file storage and episode lifecycle rules."""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from config import settings
from src.alert_case import AlertCase, TimingEvidenceReference, create_alert_case
from src.alert_episode import AlertEpisodeService, EpisodeLifecyclePolicy, default_episode_lifecycle_policy
from src.alert_repository import (
    ALERT_CASE_REPOSITORY_FILENAME,
    AlertCaseRepositoryConflictError,
    AlertCaseRepositoryCorruptError,
    AlertCaseRepositoryDuplicateError,
    FileAlertCaseRepository,
)
import src.alert_episode as alert_episode
import src.alert_repository as alert_repository


BASE_TIME = datetime(2026, 8, 23, 9, 0, tzinfo=timezone.utc)


def _case(
    alert_id: str,
    episode_key: str,
    *,
    created_at: datetime = BASE_TIME,
    due_at: datetime | None = None,
    customer_id: str = "C000001",
) -> AlertCase:
    return create_alert_case(
        alert_id=alert_id,
        customer_id=customer_id,
        policy_id="synthetic_early_warning_demo",
        policy_version="0.1.0",
        selection_policy_id="transparent_triage_selection_demo",
        selection_policy_version="0.1.0",
        signal_run_id="crossfit_seed42_5fold_asof12",
        signal_version="prospective_signal_snapshot.v1",
        signal_as_of_month=12,
        created_at=created_at,
        due_at=due_at or created_at + timedelta(days=2),
        operational_priority="PRIORITY_REVIEW",
        why_now_reason_codes=("CURRENT_STATUS_CONCERNING",),
        selection_reason_codes=("PRIORITY_BAND_PRIORITY_REVIEW",),
        timing_evidence_reference=TimingEvidenceReference(
            source="prospective_signal",
            candidate_month=12,
            evaluation_status="not_evaluated",
        ),
        episode_key=episode_key,
    )


def _close_case(repo: FileAlertCaseRepository, alert_case: AlertCase) -> AlertCase:
    acknowledged = alert_case.transition_to(
        "ACKNOWLEDGED",
        occurred_at=alert_case.updated_at + timedelta(hours=1),
        state_change_reason="ACKNOWLEDGED_FOR_TEST",
    )
    repo.update(acknowledged, expected_updated_at=alert_case.updated_at)
    closed = acknowledged.transition_to(
        "CLOSED",
        occurred_at=acknowledged.updated_at + timedelta(hours=1),
        state_change_reason="CLOSED_FOR_TEST",
        case_resolution="RESOLVED_NO_ACTION",
    )
    return repo.update(closed, expected_updated_at=acknowledged.updated_at)


def test_file_repository_missing_roundtrip_atomic_and_separate_path(tmp_path: Path) -> None:
    repo = FileAlertCaseRepository(tmp_path / "workflow")
    case = _case("ALT-001", "episode-a")

    assert repo.get("ALT-001") is None
    assert repo.list_cases() == ()
    assert not repo.storage_path.exists()
    assert repo.create(case) == case
    assert repo.get("ALT-001") == case
    assert FileAlertCaseRepository(tmp_path / "workflow").list_cases() == (case,)
    assert repo.storage_path.name == ALERT_CASE_REPOSITORY_FILENAME
    assert not list(repo.storage_dir.glob("*.tmp"))
    assert '"schema_version": "alert_case_repository.v1"' in repo.storage_path.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="separate from analytics"):
        FileAlertCaseRepository(settings.DATA_DEMO_DIR)


def test_repository_dedupes_open_episode_and_rejects_stale_updates(tmp_path: Path) -> None:
    repo = FileAlertCaseRepository(tmp_path / "workflow")
    original = repo.create(_case("ALT-001", "episode-a"))

    with pytest.raises(AlertCaseRepositoryDuplicateError, match="open AlertCase"):
        repo.create(_case("ALT-002", "episode-a"))
    assert repo.open_by_episode("C000001", "episode-a") == original

    current = repo.get("ALT-001")
    assert current is not None
    acknowledged = current.transition_to(
        "ACKNOWLEDGED",
        occurred_at=BASE_TIME + timedelta(hours=1),
        state_change_reason="ACKNOWLEDGED_FOR_TEST",
    )
    assert repo.update(acknowledged, expected_updated_at=current.updated_at) == acknowledged
    stale = original.transition_to(
        "IN_REVIEW",
        occurred_at=BASE_TIME + timedelta(hours=2),
        state_change_reason="STALE_UPDATE",
    )
    with pytest.raises(AlertCaseRepositoryConflictError, match="stale AlertCase update"):
        repo.update(stale, expected_updated_at=original.updated_at)


def test_repository_rejects_corrupt_file_and_does_not_leave_partial_temporary_files(tmp_path: Path) -> None:
    repo = FileAlertCaseRepository(tmp_path / "workflow")
    repo.storage_dir.mkdir(parents=True)
    repo.storage_path.write_text("{broken-json", encoding="utf-8")
    with pytest.raises(AlertCaseRepositoryCorruptError, match="Cannot read"):
        repo.list_cases()

    clean_repo = FileAlertCaseRepository(tmp_path / "clean-workflow")
    clean_repo.create(_case("ALT-001", "episode-a"))
    assert not list(clean_repo.storage_dir.glob("*.tmp"))


def test_same_open_episode_refreshes_without_creating_duplicate_and_new_episode_creates(tmp_path: Path) -> None:
    repo = FileAlertCaseRepository(tmp_path / "workflow")
    service = AlertEpisodeService(repo, default_episode_lifecycle_policy())
    first = _case("ALT-001", "episode-a")

    created = service.handle(first, occurred_at=BASE_TIME)
    assert created.action == "CREATED_NEW_EPISODE"
    refreshed_candidate = _case(
        "ALT-002",
        "episode-a",
        created_at=BASE_TIME + timedelta(hours=1),
        due_at=BASE_TIME + timedelta(days=4),
    )
    refreshed = service.handle(refreshed_candidate, occurred_at=BASE_TIME + timedelta(hours=1))
    assert refreshed.action == "UPDATED_OPEN_EPISODE"
    assert refreshed.alert_case is not None
    assert refreshed.alert_case.alert_id == "ALT-001"
    assert refreshed.alert_case.due_at == BASE_TIME + timedelta(days=4)
    assert len(repo.list_cases()) == 1

    noop_candidate = _case(
        "ALT-003",
        "episode-a",
        created_at=BASE_TIME + timedelta(hours=1),
        due_at=BASE_TIME + timedelta(days=4),
    )
    assert service.handle(noop_candidate, occurred_at=BASE_TIME + timedelta(hours=1)).action == "NOOP_OPEN_EPISODE"

    new_episode = _case("ALT-004", "episode-b", created_at=BASE_TIME + timedelta(hours=2))
    assert service.handle(new_episode, occurred_at=BASE_TIME + timedelta(hours=2)).action == "CREATED_NEW_EPISODE"
    assert len(repo.list_cases()) == 2


def test_snooze_active_is_noop_then_expiry_resumes_and_refreshes_same_case(tmp_path: Path) -> None:
    repo = FileAlertCaseRepository(tmp_path / "workflow")
    service = AlertEpisodeService(repo, default_episode_lifecycle_policy())
    created = service.handle(_case("ALT-001", "episode-a"), occurred_at=BASE_TIME)
    assert created.alert_case is not None
    snoozed = created.alert_case.transition_to(
        "SNOOZED",
        occurred_at=BASE_TIME + timedelta(hours=1),
        state_change_reason="SNOOZED_FOR_TEST",
        snoozed_until=BASE_TIME + timedelta(hours=4),
    )
    repo.update(snoozed, expected_updated_at=created.alert_case.updated_at)

    active_candidate = _case("ALT-002", "episode-a", created_at=BASE_TIME + timedelta(hours=2))
    active = service.handle(active_candidate, occurred_at=BASE_TIME + timedelta(hours=2))
    assert active.action == "NOOP_SNOOZE_ACTIVE"
    assert active.alert_case is not None and active.alert_case.state == "SNOOZED"

    expired_candidate = _case(
        "ALT-003",
        "episode-a",
        created_at=BASE_TIME + timedelta(hours=5),
        due_at=BASE_TIME + timedelta(days=3, hours=5),
    )
    resumed = service.handle(expired_candidate, occurred_at=BASE_TIME + timedelta(hours=5))
    assert resumed.action == "UPDATED_SNOOZE_EXPIRED"
    assert resumed.alert_case is not None
    assert resumed.alert_case.alert_id == "ALT-001"
    assert resumed.alert_case.state == "ACKNOWLEDGED"
    assert resumed.alert_case.snoozed_until is None
    assert len(repo.list_cases()) == 1


def test_cooldown_and_closed_episode_reopen_rules_are_explicit_and_configurable(tmp_path: Path) -> None:
    repo = FileAlertCaseRepository(tmp_path / "workflow")
    cooldown_policy = EpisodeLifecyclePolicy(
        policy_id="episode-demo",
        version="1",
        cooldown_hours=24,
        allow_closed_episode_reopen=False,
        reopen_window_hours=12,
    )
    service = AlertEpisodeService(repo, cooldown_policy)
    first = service.handle(_case("ALT-001", "episode-a"), occurred_at=BASE_TIME)
    assert first.alert_case is not None
    closed = _close_case(repo, first.alert_case)

    suppressed = service.handle(
        _case("ALT-002", "episode-b", created_at=closed.updated_at + timedelta(hours=1)),
        occurred_at=closed.updated_at + timedelta(hours=1),
    )
    assert suppressed.action == "NOOP_COOLDOWN"
    assert len(repo.list_cases()) == 1
    later = service.handle(
        _case("ALT-003", "episode-b", created_at=closed.updated_at + timedelta(hours=25)),
        occurred_at=closed.updated_at + timedelta(hours=25),
    )
    assert later.action == "CREATED_NEW_EPISODE"

    closed_episode_attempt = service.handle(
        _case("ALT-004", "episode-a", created_at=closed.updated_at + timedelta(hours=2)),
        occurred_at=closed.updated_at + timedelta(hours=2),
    )
    assert closed_episode_attempt.action == "NOOP_CLOSED_EPISODE"

    reopen_repo = FileAlertCaseRepository(tmp_path / "reopen-workflow")
    reopen_service = AlertEpisodeService(
        reopen_repo,
        EpisodeLifecyclePolicy(
            policy_id="episode-demo",
            version="1",
            cooldown_hours=24,
            allow_closed_episode_reopen=True,
            reopen_window_hours=12,
        ),
    )
    reopened_first = reopen_service.handle(_case("ALT-101", "episode-a"), occurred_at=BASE_TIME)
    assert reopened_first.alert_case is not None
    reopened_closed = _close_case(reopen_repo, reopened_first.alert_case)
    reopened = reopen_service.handle(
        _case("ALT-102", "episode-a", created_at=reopened_closed.updated_at + timedelta(hours=2)),
        occurred_at=reopened_closed.updated_at + timedelta(hours=2),
    )
    assert reopened.action == "REOPENED_AS_NEW_CASE"
    assert reopened.alert_case is not None and reopened.alert_case.alert_id == "ALT-102"
    assert len(reopen_repo.list_cases()) == 2


def test_repository_and_episode_modules_have_no_db_or_delivery_or_analytics_label_dependency() -> None:
    sources = {
        "repository": Path(alert_repository.__file__).read_text(encoding="utf-8"),
        "episode": Path(alert_episode.__file__).read_text(encoding="utf-8"),
    }
    imports = [
        alias.name
        for source in sources.values()
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    ]

    assert all("final_outcome" not in source and "persona" not in source for source in sources.values())
    assert not any(
        token in module.lower()
        for module in imports
        for token in ("sqlalchemy", "sqlite", "orm", "notification", "provider", "streamlit")
    )
