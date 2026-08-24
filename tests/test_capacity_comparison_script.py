"""CLI contract for isolated Post-P0 capacity-comparison exports."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from scripts.run_capacity_comparison import run_capacity_comparison


def _manifest() -> dict[str, object]:
    return {
        "run_id": "fixture_run",
        "schema_version": "selection_manifest.v1",
        "signal_run_id": "fixture_signal",
        "triage_as_of_month": 12,
        "selection_policy": {"policy_id": "fixture", "version": "0.1.0", "status": "demo"},
        "funnel": {"monitored_total": 2, "eligible_total": 1},
        "records": [
            {
                "customer_id": "C000001",
                "review_priority_rank": 1,
                "eligible_for_review": True,
                "eligibility_label": "Priority Review",
            },
            {
                "customer_id": "C000002",
                "review_priority_rank": None,
                "eligible_for_review": False,
                "eligibility_label": "Monitor",
            },
        ],
    }


def test_capacity_comparison_cli_exports_only_draft_post_p0_scenarios(tmp_path: Path) -> None:
    source = tmp_path / "source" / "rm_selection_manifest.json"
    source.parent.mkdir()
    source.write_text(json.dumps(_manifest()), encoding="utf-8")
    destination = tmp_path / "post_p0" / "capacity.json"

    result = run_capacity_comparison(
        Namespace(selection_manifest=source, capacity=[0, 1], output=destination)
    )

    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert source.read_text(encoding="utf-8") == json.dumps(_manifest())
    assert result["scenario_count"] == 3
    assert payload["scenarios"][0]["scenario"]["is_unbounded_reference"] is True
    assert [item["scenario"]["status"] for item in payload["scenarios"]] == ["demo", "draft", "draft"]
    assert [item["selected_count"] for item in payload["scenarios"]] == [1, 0, 1]
