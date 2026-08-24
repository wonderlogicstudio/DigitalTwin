"""Configurable episode dedupe, cooldown, snooze, and closed-case handling."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Literal

from src.alert_case import AlertCase, AlertCaseState
from src.alert_repository import AlertCaseRepository


EPISODE_POLICY_SCHEMA_VERSION = "alert_episode_policy.v1"
EPISODE_ACTIONS = (
    "CREATED_NEW_EPISODE",
    "UPDATED_OPEN_EPISODE",
    "NOOP_OPEN_EPISODE",
    "NOOP_SNOOZE_ACTIVE",
    "UPDATED_SNOOZE_EXPIRED",
    "NOOP_COOLDOWN",
    "REOPENED_AS_NEW_CASE",
    "NOOP_CLOSED_EPISODE",
)

EpisodeAction = Literal[
    "CREATED_NEW_EPISODE",
    "UPDATED_OPEN_EPISODE",
    "NOOP_OPEN_EPISODE",
    "NOOP_SNOOZE_ACTIVE",
    "UPDATED_SNOOZE_EXPIRED",
    "NOOP_COOLDOWN",
    "REOPENED_AS_NEW_CASE",
    "NOOP_CLOSED_EPISODE",
]
SnoozeResumeState = Literal["ACKNOWLEDGED", "IN_REVIEW"]


@dataclass(frozen=True)
class EpisodeLifecyclePolicy:
    """Declared prototype rules; no capacity or analytical scoring is adjusted."""

    policy_id: str
    version: str
    cooldown_hours: int
    allow_closed_episode_reopen: bool
    reopen_window_hours: int
    snooze_resume_state: SnoozeResumeState = "ACKNOWLEDGED"
    schema_version: str = EPISODE_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not str(self.policy_id).strip() or not str(self.version).strip():
            raise ValueError("policy_id and version must be non-empty")
        for name, value in (
            ("cooldown_hours", self.cooldown_hours),
            ("reopen_window_hours", self.reopen_window_hours),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if not isinstance(self.allow_closed_episode_reopen, bool):
            raise ValueError("allow_closed_episode_reopen must be a bool")
        if self.snooze_resume_state not in {"ACKNOWLEDGED", "IN_REVIEW"}:
            raise ValueError("snooze_resume_state must be ACKNOWLEDGED or IN_REVIEW")
        if self.schema_version != EPISODE_POLICY_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {EPISODE_POLICY_SCHEMA_VERSION}")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "version": self.version,
            "cooldown_hours": self.cooldown_hours,
            "allow_closed_episode_reopen": self.allow_closed_episode_reopen,
            "reopen_window_hours": self.reopen_window_hours,
            "snooze_resume_state": self.snooze_resume_state,
        }


def default_episode_lifecycle_policy() -> EpisodeLifecyclePolicy:
    """Return conservative demo defaults; closed-episode reopening is opt-in."""

    return EpisodeLifecyclePolicy(
        policy_id="alert_episode_lifecycle_demo",
        version="0.1.0",
        cooldown_hours=72,
        allow_closed_episode_reopen=False,
        reopen_window_hours=168,
        snooze_resume_state="ACKNOWLEDGED",
    )


@dataclass(frozen=True)
class EpisodeHandlingResult:
    """One explicit idempotency/dedupe outcome; no external action is performed."""

    action: EpisodeAction
    alert_case: AlertCase | None
    related_alert_id: str | None
    created: bool
    updated: bool

    def __post_init__(self) -> None:
        if self.action not in EPISODE_ACTIONS:
            raise ValueError(f"action must be one of {EPISODE_ACTIONS}")
        if self.created and self.updated:
            raise ValueError("an episode result cannot be created and updated together")
        if self.action in {"CREATED_NEW_EPISODE", "REOPENED_AS_NEW_CASE"} and not self.created:
            raise ValueError("creation actions must set created=True")
        if self.action in {"UPDATED_OPEN_EPISODE", "UPDATED_SNOOZE_EXPIRED"} and not self.updated:
            raise ValueError("update actions must set updated=True")
        if self.alert_case is not None and self.related_alert_id != self.alert_case.alert_id:
            raise ValueError("related_alert_id must identify alert_case when a case is returned")

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "alert_case": None if self.alert_case is None else self.alert_case.to_dict(),
            "related_alert_id": self.related_alert_id,
            "created": self.created,
            "updated": self.updated,
            "scope": {
                "queue_selection_changed": False,
                "external_delivery_implemented": False,
            },
        }


class AlertEpisodeService:
    """Apply declared lifecycle rules over an injected AlertCase repository."""

    def __init__(self, repository: AlertCaseRepository, policy: EpisodeLifecyclePolicy) -> None:
        self.repository = repository
        self.policy = policy

    def handle(self, candidate: AlertCase, *, occurred_at: datetime) -> EpisodeHandlingResult:
        """Create, refresh, suppress, or reopen a case without duplicate open episodes."""

        _validate_aware_datetime(occurred_at, "occurred_at")
        if candidate.state != "NEW":
            raise ValueError("episode candidates must start in NEW state")
        if candidate.created_at > occurred_at or candidate.updated_at > occurred_at:
            raise ValueError("candidate timestamps must not be after occurred_at")

        open_case = self.repository.open_by_episode(candidate.customer_id, candidate.episode_key)
        if open_case is not None:
            return self._handle_open_episode(open_case, candidate, occurred_at)

        closed_same_episode = _latest_case(
            case
            for case in self.repository.list_cases()
            if case.customer_id == candidate.customer_id
            and case.episode_key == candidate.episode_key
            and case.state == "CLOSED"
        )
        if closed_same_episode is not None:
            _ensure_not_before(occurred_at, closed_same_episode.updated_at)
            if (
                self.policy.allow_closed_episode_reopen
                and occurred_at - closed_same_episode.updated_at
                <= timedelta(hours=self.policy.reopen_window_hours)
            ):
                created = self.repository.create(candidate)
                return EpisodeHandlingResult(
                    action="REOPENED_AS_NEW_CASE",
                    alert_case=created,
                    related_alert_id=created.alert_id,
                    created=True,
                    updated=False,
                )
            return EpisodeHandlingResult(
                action="NOOP_CLOSED_EPISODE",
                alert_case=closed_same_episode,
                related_alert_id=closed_same_episode.alert_id,
                created=False,
                updated=False,
            )

        latest_closed_same_policy = _latest_case(
            case
            for case in self.repository.list_cases()
            if case.customer_id == candidate.customer_id
            and case.policy_id == candidate.policy_id
            and case.state == "CLOSED"
        )
        if latest_closed_same_policy is not None:
            _ensure_not_before(occurred_at, latest_closed_same_policy.updated_at)
            if occurred_at - latest_closed_same_policy.updated_at < timedelta(
                hours=self.policy.cooldown_hours
            ):
                return EpisodeHandlingResult(
                    action="NOOP_COOLDOWN",
                    alert_case=latest_closed_same_policy,
                    related_alert_id=latest_closed_same_policy.alert_id,
                    created=False,
                    updated=False,
                )

        created = self.repository.create(candidate)
        return EpisodeHandlingResult(
            action="CREATED_NEW_EPISODE",
            alert_case=created,
            related_alert_id=created.alert_id,
            created=True,
            updated=False,
        )

    def _handle_open_episode(
        self,
        current: AlertCase,
        candidate: AlertCase,
        occurred_at: datetime,
    ) -> EpisodeHandlingResult:
        _ensure_not_before(occurred_at, current.updated_at)
        if current.state == "SNOOZED":
            assert current.snoozed_until is not None
            if occurred_at < current.snoozed_until:
                return EpisodeHandlingResult(
                    action="NOOP_SNOOZE_ACTIVE",
                    alert_case=current,
                    related_alert_id=current.alert_id,
                    created=False,
                    updated=False,
                )
            resumed = current.transition_to(
                self.policy.snooze_resume_state,
                occurred_at=occurred_at,
                state_change_reason="SNOOZE_EXPIRED_SIGNAL_REPEATED",
            )
            refreshed = _refresh_case(resumed, candidate, occurred_at, "SNOOZE_EXPIRED_SIGNAL_REPEATED")
            stored = self.repository.update(refreshed, expected_updated_at=current.updated_at)
            return EpisodeHandlingResult(
                action="UPDATED_SNOOZE_EXPIRED",
                alert_case=stored,
                related_alert_id=stored.alert_id,
                created=False,
                updated=True,
            )
        refreshed = _refresh_case(current, candidate, occurred_at, "EPISODE_REFRESHED")
        if refreshed == current:
            return EpisodeHandlingResult(
                action="NOOP_OPEN_EPISODE",
                alert_case=current,
                related_alert_id=current.alert_id,
                created=False,
                updated=False,
            )
        stored = self.repository.update(refreshed, expected_updated_at=current.updated_at)
        return EpisodeHandlingResult(
            action="UPDATED_OPEN_EPISODE",
            alert_case=stored,
            related_alert_id=stored.alert_id,
            created=False,
            updated=True,
        )


def _refresh_case(
    current: AlertCase,
    candidate: AlertCase,
    occurred_at: datetime,
    refresh_reason: str,
) -> AlertCase:
    """Retain workflow ownership/state while replacing current signal references."""

    if occurred_at == current.updated_at:
        return current
    return replace(
        current,
        policy_id=candidate.policy_id,
        policy_version=candidate.policy_version,
        selection_policy_id=candidate.selection_policy_id,
        selection_policy_version=candidate.selection_policy_version,
        signal_run_id=candidate.signal_run_id,
        signal_version=candidate.signal_version,
        signal_as_of_month=candidate.signal_as_of_month,
        updated_at=occurred_at,
        due_at=candidate.due_at,
        operational_priority=candidate.operational_priority,
        why_now_reason_codes=candidate.why_now_reason_codes,
        selection_reason_codes=candidate.selection_reason_codes,
        timing_evidence_reference=candidate.timing_evidence_reference,
        last_state_change_reason=refresh_reason,
    )


def _latest_case(cases) -> AlertCase | None:  # type: ignore[no-untyped-def]
    normalized = tuple(cases)
    return None if not normalized else max(normalized, key=lambda item: (item.updated_at, item.alert_id))


def _ensure_not_before(occurred_at: datetime, current_updated_at: datetime) -> None:
    if occurred_at < current_updated_at:
        raise ValueError("occurred_at must not be before the current case version")


def _validate_aware_datetime(value: datetime, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be a timezone-aware datetime")
