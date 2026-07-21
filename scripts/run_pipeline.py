"""Run the full Financial Path Twin data and demo pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings  # noqa: E402
from src.pipeline import PipelineConfig, PipelineError, run_pipeline  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(description="Run the Financial Path Twin pipeline.")
    parser.add_argument("--skip-generation", action="store_true", help="Reuse existing raw CSV files.")
    parser.add_argument("--skip-validation", action="store_true", help="Skip required validation checks.")
    parser.add_argument("--customer-count", type=int, default=settings.CUSTOMER_COUNT, help="Synthetic customer count.")
    parser.add_argument("--random-seed", type=int, default=settings.RANDOM_SEED, help="Synthetic random seed.")
    parser.add_argument("--top-k", type=int, default=settings.TOP_K_MATCHES, help="Number of matched customers.")
    parser.add_argument("--force", action="store_true", help="Regenerate outputs even when files already exist.")
    parser.add_argument("--export-charts", action="store_true", help="Export demo Plotly charts to HTML.")
    parser.add_argument("--verbose", action="store_true", help="Print step start and completion logs.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the pipeline CLI."""

    args = parse_args(argv)
    try:
        config = PipelineConfig(
            customer_count=args.customer_count,
            random_seed=args.random_seed,
            top_k=args.top_k,
            skip_generation=args.skip_generation,
            skip_validation=args.skip_validation,
            force=args.force,
            export_charts=args.export_charts,
            verbose=args.verbose,
        )
        summary = run_pipeline(config)
    except (ValueError, PipelineError) as exc:
        print(f"pipeline_failed: {exc}", file=sys.stderr)
        return 1

    _print_summary(summary)
    return 0


def _print_summary(summary: dict) -> None:
    print("pipeline_summary:")
    print(f"  customer_count: {summary['customer_count']:,}")
    print(f"  monthly_row_count: {summary['monthly_row_count']:,}")
    print(f"  feature_row_count: {summary['feature_row_count']:,}")
    print(f"  main_customer_id: {summary['main_customer_id']}")
    print(f"  matched_count: {summary['matched_count']:,}")
    print(f"  risk_group_ratio: {summary['risk_group_ratio']:.1%}")
    breakpoint_result = summary["breakpoint"]
    print(
        "  breakpoint: "
        f"{breakpoint_result.get('status')} month={breakpoint_result.get('breakpoint_month')}"
    )
    best = summary["best_whatif_scenario"]
    print(
        "  best_whatif_scenario: "
        f"{best['scenario_name']} improvement={best['improvement_vs_baseline']:,.0f}"
    )
    print(f"  elapsed_seconds: {summary['elapsed_seconds']:.2f}")
    print("  stage_timings:")
    for step, seconds in summary["stage_timings"].items():
        print(f"    {step}: {seconds:.3f}")
    print("  generated_files:")
    for path in summary["generated_files"]:
        print(f"    {path}")
    print("  json:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
