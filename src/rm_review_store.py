"""Minimal JSONL storage for RM review results, independent of audit or Case flows."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, Mapping, Sequence
from uuid import uuid4

from config import settings


REVIEW_COMPLETED = "COMPLETED"
REVIEW_FOLLOW_UP = "FOLLOW_UP"
REVIEW_MONITOR = "MONITOR"
REVIEW_RESULTS = (REVIEW_COMPLETED, REVIEW_FOLLOW_UP, REVIEW_MONITOR)
ReviewResult = Literal["COMPLETED", "FOLLOW_UP", "MONITOR"]

DEFAULT_REVIEW_EVENTS_PATH = (
    Path(__file__).resolve().parents[1]
    / "artifacts"
    / "rm_daily_review"
    / "reviews"
    / "review_events.jsonl"
)


@dataclass(frozen=True)
class RmReviewEvent:
    """One manually recorded RM review outcome for a saved Snapshot customer."""

    review_id: str
    customer_id: str
    snapshot_id: str
    reviewed_at: datetime
    result: ReviewResult
    note: str | None = None

    def as_dict(self) -> dict[str, str]:
        """Return the standalone JSONL row, omitting an absent optional note."""

        payload = {
            "review_id": self.review_id,
            "customer_id": self.customer_id,
            "snapshot_id": self.snapshot_id,
            "reviewed_at": self.reviewed_at.isoformat(),
            "result": self.result,
        }
        if self.note is not None:
            payload["note"] = self.note
        return payload


def create_review_event(
    *,
    customer_id: str,
    snapshot_id: str,
    reviewed_at: datetime,
    result: ReviewResult | str,
    note: str | None = None,
    review_id: str | None = None,
) -> RmReviewEvent:
    """Create a validated manual review event; no Snapshot analysis is invoked."""

    normalized_result = str(result).strip().upper()
    if normalized_result not in REVIEW_RESULTS:
        raise ValueError(f"result must be one of: {', '.join(REVIEW_RESULTS)}")
    _validate_reviewed_at(reviewed_at)
    normalized_review_id = (
        str(uuid4()) if review_id is None else _required_text(review_id, "review_id")
    )
    return RmReviewEvent(
        review_id=normalized_review_id,
        customer_id=_required_text(customer_id, "customer_id"),
        snapshot_id=_required_text(snapshot_id, "snapshot_id"),
        reviewed_at=reviewed_at,
        result=normalized_result,  # type: ignore[arg-type]
        note=_optional_note(note),
    )


def append_review_event(
    event: RmReviewEvent,
    output_path: Path | str = DEFAULT_REVIEW_EVENTS_PATH,
) -> Path:
    """Append one event to the standalone JSONL artifact without database access."""

    path = Path(output_path)
    _ensure_separate_artifact_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as output_file:
        output_file.write(json.dumps(event.as_dict(), ensure_ascii=False, sort_keys=True))
        output_file.write("\n")
    return path


def load_review_events(
    input_path: Path | str = DEFAULT_REVIEW_EVENTS_PATH,
) -> tuple[RmReviewEvent, ...]:
    """Load review events from the independent JSONL artifact in append order."""

    path = Path(input_path)
    if not path.exists():
        return ()

    events: list[RmReviewEvent] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid review event JSON at line {line_number}.") from exc
        if not isinstance(payload, Mapping):
            raise ValueError(f"Review event at line {line_number} must be a JSON object.")
        try:
            events.append(_event_from_dict(payload))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid review event at line {line_number}: {exc}") from exc
    return tuple(events)


def find_latest_review_event(
    events: Sequence[RmReviewEvent],
    *,
    customer_id: str,
    snapshot_id: str,
) -> RmReviewEvent | None:
    """Return the newest standalone RM review for one saved Snapshot customer."""

    normalized_customer_id = _required_text(customer_id, "customer_id")
    normalized_snapshot_id = _required_text(snapshot_id, "snapshot_id")
    matching = [
        (index, event)
        for index, event in enumerate(events)
        if event.customer_id == normalized_customer_id
        and event.snapshot_id == normalized_snapshot_id
    ]
    if not matching:
        return None
    return max(matching, key=lambda pair: (pair[1].reviewed_at, pair[0]))[1]


def replace_customer_review(
    event: RmReviewEvent,
    output_path: Path | str = DEFAULT_REVIEW_EVENTS_PATH,
) -> Path:
    """Replace the current RM record for one customer/Snapshot without touching core data.

    This compact PoC store keeps one effective review record per customer and
    Snapshot. It is intentionally separate from a Case or audit lifecycle.
    """

    path = Path(output_path)
    _ensure_separate_artifact_path(path)
    existing_events = load_review_events(path)
    if not any(
        current.customer_id == event.customer_id
        and current.snapshot_id == event.snapshot_id
        for current in existing_events
    ):
        raise ValueError("No existing RM review record is available to update.")
    remaining_events = [
        current
        for current in existing_events
        if not (
            current.customer_id == event.customer_id
            and current.snapshot_id == event.snapshot_id
        )
    ]
    _write_review_events((*remaining_events, event), path)
    return path


def cancel_customer_review(
    *,
    customer_id: str,
    snapshot_id: str,
    output_path: Path | str = DEFAULT_REVIEW_EVENTS_PATH,
) -> int:
    """Cancel an RM review record so the customer returns to its saved timing bucket.

    Only the separate RM review artifact is changed. A caller can use the
    returned count to distinguish a completed cancellation from a stale view.
    """

    normalized_customer_id = _required_text(customer_id, "customer_id")
    normalized_snapshot_id = _required_text(snapshot_id, "snapshot_id")
    path = Path(output_path)
    _ensure_separate_artifact_path(path)
    existing_events = load_review_events(path)
    remaining_events = [
        event
        for event in existing_events
        if not (
            event.customer_id == normalized_customer_id
            and event.snapshot_id == normalized_snapshot_id
        )
    ]
    removed_count = len(existing_events) - len(remaining_events)
    if removed_count:
        _write_review_events(remaining_events, path)
    return removed_count


def _event_from_dict(payload: Mapping[str, object]) -> RmReviewEvent:
    reviewed_at_raw = payload.get("reviewed_at")
    if not isinstance(reviewed_at_raw, str):
        raise ValueError("reviewed_at must be an ISO-8601 datetime string.")
    try:
        reviewed_at = datetime.fromisoformat(reviewed_at_raw)
    except ValueError as exc:
        raise ValueError("reviewed_at must be an ISO-8601 datetime string.") from exc
    note = payload.get("note")
    if note is not None and not isinstance(note, str):
        raise ValueError("note must be a string when supplied.")
    return create_review_event(
        review_id=_required_text(payload.get("review_id"), "review_id"),
        customer_id=_required_text(payload.get("customer_id"), "customer_id"),
        snapshot_id=_required_text(payload.get("snapshot_id"), "snapshot_id"),
        reviewed_at=reviewed_at,
        result=_required_text(payload.get("result"), "result"),
        note=note,
    )


def _write_review_events(events: Sequence[RmReviewEvent], path: Path) -> None:
    """Atomically rewrite only the standalone RM review JSONL artifact."""

    _ensure_separate_artifact_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as output_file:
            for event in events:
                output_file.write(json.dumps(event.as_dict(), ensure_ascii=False, sort_keys=True))
                output_file.write("\n")
        temporary_path.replace(path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _required_text(value: object, field_name: str) -> str:
    normalized_value = str(value or "").strip()
    if not normalized_value:
        raise ValueError(f"{field_name} must not be blank.")
    return normalized_value


def _optional_note(value: str | None) -> str | None:
    if value is None:
        return None
    normalized_note = str(value).strip()
    return normalized_note or None


def _validate_reviewed_at(reviewed_at: datetime) -> None:
    if not isinstance(reviewed_at, datetime):
        raise ValueError("reviewed_at must be a datetime.")
    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
        raise ValueError("reviewed_at must include a timezone offset.")


def _ensure_separate_artifact_path(path: Path) -> None:
    resolved_path = path.resolve()
    for core_directory in (
        settings.DATA_RAW_DIR,
        settings.DATA_PROCESSED_DIR,
        settings.DATA_DEMO_DIR,
    ):
        if resolved_path.is_relative_to(core_directory.resolve()):
            raise ValueError("RM review events must not overwrite core data artifacts.")
