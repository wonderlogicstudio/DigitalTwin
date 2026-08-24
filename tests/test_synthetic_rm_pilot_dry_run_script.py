"""CLI wiring tests for the synthetic-only pilot rehearsal command."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from scripts import run_synthetic_rm_pilot_dry_run as script


def test_cli_passes_only_explicit_synthetic_rehearsal_inputs(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    captured: dict[str, object] = {}

    class Result:
        output_dir = tmp_path / "output"

    def fake_run(**kwargs: object) -> Result:
        captured.update(kwargs)
        return Result()

    monkeypatch.setattr(script, "run_synthetic_rm_pilot_dry_run", fake_run)
    assert script.main(
        [
            "--selection-manifest",
            "selection.json",
            "--representative-cohort",
            "representatives.json",
            "--capacity",
            "3",
            "--output",
            "artifacts/post_p0/pilot_dry_run/fixture",
            "--run-id",
            "fixture-run",
            "--occurred-at",
            "2026-08-24T09:00:00+00:00",
        ]
    ) == 0
    assert captured == {
        "selection_manifest_path": Path("selection.json"),
        "representative_cohort_path": Path("representatives.json"),
        "output_dir": Path("artifacts/post_p0/pilot_dry_run/fixture"),
        "max_reviews_per_cycle": 3,
        "occurred_at": datetime(2026, 8, 24, 9, 0, tzinfo=timezone.utc),
        "run_id": "fixture-run",
    }
