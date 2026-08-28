"""Tests for the standalone minimal RM review-result JSONL store."""

from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import src.rm_review_store as review_store
from config import settings
from src.rm_review_store import (
    REVIEW_COMPLETED,
    REVIEW_FOLLOW_UP,
    REVIEW_MONITOR,
    append_review_event,
    create_review_event,
    load_review_events,
)


def _reviewed_at() -> datetime:
    return datetime(2026, 8, 29, 9, 30, tzinfo=timezone.utc)


def test_creates_minimal_review_event_with_optional_note() -> None:
    event = create_review_event(
        review_id="review-0001",
        customer_id="C000001",
        snapshot_id="monthly-2026-08",
        reviewed_at=_reviewed_at(),
        result=REVIEW_COMPLETED,
    )
    event_with_note = create_review_event(
        review_id="review-0002",
        customer_id="C000002",
        snapshot_id="monthly-2026-08",
        reviewed_at=_reviewed_at(),
        result=REVIEW_FOLLOW_UP,
        note="  고객 확인 사항을 기록했습니다.  ",
    )

    assert event.as_dict() == {
        "review_id": "review-0001",
        "customer_id": "C000001",
        "snapshot_id": "monthly-2026-08",
        "reviewed_at": "2026-08-29T09:30:00+00:00",
        "result": REVIEW_COMPLETED,
    }
    assert event_with_note.as_dict()["note"] == "고객 확인 사항을 기록했습니다."
    assert event_with_note.result == REVIEW_FOLLOW_UP


def test_appends_and_loads_jsonl_events_in_order(tmp_path: Path) -> None:
    event_path = tmp_path / "artifacts" / "rm_daily_review" / "reviews" / "review_events.jsonl"
    first = create_review_event(
        review_id="review-0001",
        customer_id="C000001",
        snapshot_id="monthly-2026-08",
        reviewed_at=_reviewed_at(),
        result=REVIEW_COMPLETED,
    )
    second = create_review_event(
        review_id="review-0002",
        customer_id="C000002",
        snapshot_id="monthly-2026-08",
        reviewed_at=datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc),
        result=REVIEW_MONITOR,
        note="다음 월별 Snapshot에서 다시 확인",
    )

    assert append_review_event(first, event_path) == event_path
    assert append_review_event(second, event_path) == event_path

    rows = [json.loads(line) for line in event_path.read_text(encoding="utf-8").splitlines()]
    loaded = load_review_events(event_path)
    assert [row["review_id"] for row in rows] == ["review-0001", "review-0002"]
    assert loaded == (first, second)
    assert load_review_events(tmp_path / "missing.jsonl") == ()


@pytest.mark.parametrize("result", ["", "UNKNOWN", "completed_later"])
def test_rejects_invalid_result_or_review_timestamp(result: str) -> None:
    with pytest.raises(ValueError, match="result must be one of"):
        create_review_event(
            customer_id="C000001",
            snapshot_id="monthly-2026-08",
            reviewed_at=_reviewed_at(),
            result=result,
        )
    with pytest.raises(ValueError, match="timezone offset"):
        create_review_event(
            customer_id="C000001",
            snapshot_id="monthly-2026-08",
            reviewed_at=datetime(2026, 8, 29, 9, 30),
            result=REVIEW_COMPLETED,
        )


def test_rejects_core_data_paths_and_malformed_jsonl(tmp_path: Path) -> None:
    event = create_review_event(
        review_id="review-0001",
        customer_id="C000001",
        snapshot_id="monthly-2026-08",
        reviewed_at=_reviewed_at(),
        result=REVIEW_COMPLETED,
    )
    with pytest.raises(ValueError, match="must not overwrite core data"):
        append_review_event(event, settings.DATA_DEMO_DIR / "review_events.jsonl")

    malformed_path = tmp_path / "malformed.jsonl"
    malformed_path.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        load_review_events(malformed_path)


def test_module_has_no_database_or_case_lifecycle_dependencies() -> None:
    module_path = Path(review_store.__file__)
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert imported_modules.issubset(
        {
            "__future__",
            "json",
            "dataclasses",
            "datetime",
            "pathlib",
            "typing",
            "uuid",
            "config",
        }
    )
    source = module_path.read_text(encoding="utf-8").lower()
    assert "sqlalchemy" not in source
    assert "sqlite" not in source
    assert "src.case" not in source
    fields = set(review_store.RmReviewEvent.__dataclass_fields__)
    assert fields == {"review_id", "customer_id", "snapshot_id", "reviewed_at", "result", "note"}
