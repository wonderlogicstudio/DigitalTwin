"""Read-only loading boundary for the RM Daily Review query experience.

This module deliberately loads only a saved Monthly Snapshot, the optional
synthetic presentation overlay, and manual RM review events.  It has no
Financial Path Twin analysis dependency and never creates a Snapshot.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from src.daily_worklist import DailyWorklist, build_daily_worklist, previous_business_day
from src.i18n import t
from src.rm_daily_review_view import RmDailyReviewDashboardView, build_rm_daily_review_view
from src.rm_review_store import RmReviewEvent, load_review_events


DEFAULT_SNAPSHOT_DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "artifacts"
    / "rm_daily_review"
    / "monthly"
)
DEFAULT_PRESENTATION_OVERLAY_PATH = (
    Path(__file__).resolve().parents[1]
    / "artifacts"
    / "rm_daily_review"
    / "presentation"
    / "rm_presentation_overlay.json"
)
LOADING_MESSAGE_KEY = "rm.query.loading"
DEFAULT_MIN_LOADING_SECONDS = 1.5
MAX_LOADING_SECONDS = 2.0

LoadStatus = Literal["READY", "MISSING_SNAPSHOT", "INVALID_SNAPSHOT"]


@dataclass(frozen=True)
class ControlledLoadingAdapter:
    """Injectable clock boundary for the 1.5--2 second loading feedback.

    Production uses ``time.sleep`` and ``time.monotonic``.  Tests can provide
    no-op adapters, so validating the UX timing never forces a real wait.
    """

    sleep: Callable[[float], None] = time.sleep
    monotonic: Callable[[], float] = time.monotonic
    minimum_seconds: float = DEFAULT_MIN_LOADING_SECONDS
    maximum_seconds: float = MAX_LOADING_SECONDS

    def __post_init__(self) -> None:
        if not 1.5 <= self.minimum_seconds <= self.maximum_seconds <= 2.0:
            raise ValueError("Loading feedback must be controlled within 1.5 to 2 seconds.")

    def started_at(self) -> float:
        """Return a monotonic start value for one explicit user query."""

        return self.monotonic()

    def complete(self, started_at: float) -> None:
        """Wait only for the remainder of the controlled visual feedback."""

        elapsed = max(0.0, self.monotonic() - started_at)
        remaining = max(0.0, self.minimum_seconds - elapsed)
        if remaining:
            self.sleep(remaining)


@dataclass(frozen=True)
class SavedDailyReviewLoadResult:
    """Result of one explicit, read-only Daily Review query."""

    status: LoadStatus
    message: str
    cli_command: str
    snapshot_path: Path | None = None
    worklist: DailyWorklist | None = None
    dashboard: RmDailyReviewDashboardView | None = None


def load_saved_rm_daily_review(
    *,
    daily_date: date,
    snapshot_directory: Path | str = DEFAULT_SNAPSHOT_DIRECTORY,
    presentation_overlay_path: Path | str = DEFAULT_PRESENTATION_OVERLAY_PATH,
    review_events_loader: Callable[[], Sequence[RmReviewEvent]] = load_review_events,
    loading_adapter: ControlledLoadingAdapter | None = None,
    language: str = "ko",
) -> SavedDailyReviewLoadResult:
    """Build a Daily screen projection from saved artifacts without analytics.

    A missing or invalid Snapshot is returned as guidance only.  This function
    never falls back to a builder, pipeline, matcher, or Financial Path Twin
    service.
    """

    adapter = loading_adapter or ControlledLoadingAdapter()
    started_at = adapter.started_at()
    cli_command = _snapshot_cli_command()
    try:
        snapshot_path = _latest_snapshot_path(Path(snapshot_directory))
        if snapshot_path is None:
            return SavedDailyReviewLoadResult(
                status="MISSING_SNAPSHOT",
                message=t("rm.snapshot.none", language),
                cli_command=cli_command,
            )

        snapshot_artifact = _load_snapshot_artifact(snapshot_path)
        review_events = review_events_loader()
        completed_customer_ids = _completed_customer_ids(
            review_events,
            snapshot_id=str(snapshot_artifact.get("snapshot_id") or ""),
        )
        completed_today_customer_ids = _completed_customer_ids(
            review_events,
            snapshot_id=str(snapshot_artifact.get("snapshot_id") or ""),
            daily_date=daily_date,
        )
        previous_workday_completed_count = len(
            _completed_customer_ids(
                review_events,
                snapshot_id=str(snapshot_artifact.get("snapshot_id") or ""),
                daily_date=previous_business_day(daily_date),
            )
        )
        worklist = build_daily_worklist(
            snapshot_artifact,
            daily_date=daily_date,
            completed_customer_ids=completed_customer_ids,
            completed_today_customer_ids=completed_today_customer_ids,
            previous_workday_completed_count=previous_workday_completed_count,
            snapshot_published_on=datetime.fromtimestamp(snapshot_path.stat().st_mtime).date(),
        )
        presentation_metadata = _load_presentation_metadata(
            Path(presentation_overlay_path),
            snapshot_customer_ids={
                item.customer_id
                for bucket in (
                    worklist.today_items,
                    worklist.upcoming_items,
                    worklist.monitor_items,
                    worklist.completed_today,
                )
                for item in bucket
            },
        )
        return SavedDailyReviewLoadResult(
            status="READY",
            message=t(LOADING_MESSAGE_KEY, language),
            cli_command=cli_command,
            snapshot_path=snapshot_path,
            worklist=worklist,
            dashboard=build_rm_daily_review_view(
                worklist,
                presentation_metadata_by_customer=presentation_metadata,
                language=language,
            ),
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return SavedDailyReviewLoadResult(
            status="INVALID_SNAPSHOT",
            message=t("rm.snapshot.worklist_error", language),
            cli_command=cli_command,
        )
    finally:
        adapter.complete(started_at)


def _latest_snapshot_path(snapshot_directory: Path) -> Path | None:
    if not snapshot_directory.exists():
        return None
    snapshot_paths = [
        path
        for path in snapshot_directory.glob("*.json")
        if not path.name.endswith("_workload_report.json")
    ]
    if not snapshot_paths:
        return None
    return max(snapshot_paths, key=lambda path: (path.stat().st_mtime_ns, path.name))


def _load_snapshot_artifact(snapshot_path: Path) -> Mapping[str, object]:
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Monthly Snapshot artifact must contain a JSON object.")
    return dict(payload)


def _completed_customer_ids(
    review_events: Sequence[RmReviewEvent],
    *,
    snapshot_id: str,
    daily_date: date | None = None,
) -> set[str]:
    return {
        event.customer_id
        for event in review_events
        if event.snapshot_id == snapshot_id
        and (
            daily_date is None
            or event.reviewed_at.astimezone().date() == daily_date
        )
    }


def _load_presentation_metadata(
    overlay_path: Path,
    *,
    snapshot_customer_ids: set[str],
) -> dict[str, Mapping[str, object]]:
    """Load only display fields for customers present in this saved Snapshot."""

    if not overlay_path.exists():
        return {}
    payload = json.loads(overlay_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Presentation overlay must contain a JSON object.")
    customers = payload.get("customers")
    if not isinstance(customers, Sequence) or isinstance(customers, (str, bytes)):
        raise ValueError("Presentation overlay must contain a customers list.")

    metadata: dict[str, Mapping[str, object]] = {}
    for row in customers:
        if not isinstance(row, Mapping):
            raise ValueError("Presentation overlay customer rows must be JSON objects.")
        customer_id = str(row.get("customer_id") or "").strip()
        if not customer_id:
            raise ValueError("Presentation overlay customer rows require customer_id.")
        if customer_id not in snapshot_customer_ids:
            continue
        if customer_id in metadata:
            raise ValueError("Presentation overlay must not contain duplicate customer_id values.")
        metadata[customer_id] = {
            field: row[field]
            for field in (
                "display_name",
                "display_name_ko",
                "display_name_en",
                "display_owner_or_team",
                "display_owner_or_team_ko",
                "display_owner_or_team_en",
                "presentation_label",
                "presentation_label_ko",
                "presentation_label_en",
            )
            if field in row
        }
    return metadata


def _snapshot_cli_command() -> str:
    return "python scripts/build_rm_monthly_snapshot.py --snapshot-id YYYY-MM"
