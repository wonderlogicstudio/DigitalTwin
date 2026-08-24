"""Run a bounded, synthetic-only RM pilot rehearsal into an isolated output path."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.synthetic_rm_pilot_dry_run import run_synthetic_rm_pilot_dry_run


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection-manifest", required=True, type=Path)
    parser.add_argument("--representative-cohort", required=True, type=Path)
    parser.add_argument("--capacity", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-id", default="synthetic_rm_pilot_dry_run")
    parser.add_argument(
        "--occurred-at",
        default="2026-08-24T09:00:00+00:00",
        help="Timezone-aware deterministic rehearsal timestamp in ISO-8601 form.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    occurred_at = datetime.fromisoformat(args.occurred_at)
    result = run_synthetic_rm_pilot_dry_run(
        selection_manifest_path=args.selection_manifest,
        representative_cohort_path=args.representative_cohort,
        output_dir=args.output,
        max_reviews_per_cycle=args.capacity,
        occurred_at=occurred_at,
        run_id=args.run_id,
    )
    print(f"Synthetic RM pilot dry run complete: {result.output_dir}")
    print("This output is a synthetic rehearsal only; it is not policy/capacity approval.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
