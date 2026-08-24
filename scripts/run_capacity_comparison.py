"""Export caller-supplied, comparison-only cutoffs for a saved triage manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings  # noqa: E402
from src.capacity_scenarios import (  # noqa: E402
    CapacityScenario,
    build_capacity_comparison_report,
    export_capacity_comparison_report,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse explicit draft comparison capacities; no approval option is exposed."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection-manifest", type=Path, default=None)
    parser.add_argument(
        "--capacity",
        type=int,
        action="append",
        default=[],
        help="Draft comparison capacity. Repeat to compare several caller-supplied values.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=settings.BASE_DIR
        / "artifacts"
        / "post_p0"
        / "capacity"
        / "draft_capacity_comparison.json",
    )
    return parser.parse_args(argv)


def run_capacity_comparison(args: argparse.Namespace) -> dict[str, object]:
    """Read one saved triage manifest and atomically export only comparison output."""

    manifest_path = _resolve_manifest_path(args.selection_manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("selection manifest root must be an object")
    scenarios = [CapacityScenario("source_unbounded_reference", None, status="demo")]
    scenarios.extend(
        CapacityScenario(f"draft_capacity_{capacity}", capacity, status="draft")
        for capacity in args.capacity
    )
    report = build_capacity_comparison_report(manifest, scenarios)
    destination = export_capacity_comparison_report(report, Path(args.output))
    return {
        "output_path": str(destination),
        "source_manifest": str(manifest_path),
        "scenario_count": len(report.scenarios),
        "reconciliation": dict(report.reconciliation),
        "scenarios": [
            {
                "scenario_id": result.scenario.scenario_id,
                "status": result.scenario.status,
                "max_reviews_per_cycle": result.scenario.max_reviews_per_cycle,
                "selected_count": result.selected_count,
                "deferred_count": result.deferred_count,
            }
            for result in report.scenarios
        ],
    }


def _resolve_manifest_path(candidate: Path | None) -> Path:
    if candidate is not None:
        path = Path(candidate)
        if not path.is_file():
            raise ValueError("selection manifest path does not exist")
        return path
    manifests = sorted((settings.BASE_DIR / "artifacts" / "triage").glob("*/rm_selection_manifest.json"))
    if not manifests:
        raise ValueError("no selection manifest is available")
    return manifests[-1]


def main(argv: list[str] | None = None) -> int:
    try:
        result = run_capacity_comparison(parse_args(argv))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"capacity_comparison_failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
