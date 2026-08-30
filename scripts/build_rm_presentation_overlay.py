"""Build the standalone synthetic customer-display overlay for RM Daily."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_rm_portfolio import load_customer_ids_from_csv  # noqa: E402
from src.rm_portfolio import (  # noqa: E402
    DEFAULT_PORTFOLIO_SELECTION_SEED,
    DEFAULT_PORTFOLIO_SIZE,
    build_rm_portfolio,
)
from src.rm_presentation_overlay import (  # noqa: E402
    DEFAULT_PRESENTATION_SEED,
    SYNTHETIC_PRESENTATION_DISCLAIMER,
    build_rm_presentation_overlay,
    write_rm_presentation_overlay_artifact,
)


DEFAULT_CUSTOMER_MASTER_PATH = PROJECT_ROOT / "data" / "raw" / "customer_master.csv"
DEFAULT_OUTPUT_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "rm_daily_review"
    / "presentation"
    / "rm_presentation_overlay.json"
)


def build_parser() -> argparse.ArgumentParser:
    """Build a parser that accepts customer IDs and display-only seed options."""

    parser = argparse.ArgumentParser(
        description="Build deterministic PoC customer display metadata for RM Daily."
    )
    parser.add_argument(
        "--customer-master",
        type=Path,
        default=DEFAULT_CUSTOMER_MASTER_PATH,
        help="Existing master CSV; only its customer_id column is read.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Standalone presentation overlay JSON path.",
    )
    parser.add_argument("--portfolio-size", type=int, default=DEFAULT_PORTFOLIO_SIZE)
    parser.add_argument(
        "--portfolio-seed",
        type=int,
        default=DEFAULT_PORTFOLIO_SELECTION_SEED,
        help="Deterministic customer-ID-only RM Portfolio selection seed.",
    )
    parser.add_argument(
        "--presentation-seed",
        type=int,
        default=DEFAULT_PRESENTATION_SEED,
        help="Deterministic display-name seed.",
    )
    return parser


def build_presentation_overlay_from_customer_master(
    customer_master_path: Path | str,
    *,
    portfolio_size: int = DEFAULT_PORTFOLIO_SIZE,
    portfolio_seed: int = DEFAULT_PORTFOLIO_SELECTION_SEED,
    presentation_seed: int = DEFAULT_PRESENTATION_SEED,
):
    """Select Portfolio IDs then create display-only metadata without analytics."""

    customer_ids = load_customer_ids_from_csv(customer_master_path)
    portfolio = build_rm_portfolio(
        customer_ids,
        portfolio_size=portfolio_size,
        portfolio_selection_seed=portfolio_seed,
    )
    return build_rm_presentation_overlay(
        (customer.customer_id for customer in portfolio.customers),
        presentation_seed=presentation_seed,
        expected_customer_count=portfolio_size,
    )


def main(argv: list[str] | None = None) -> int:
    """Write a new standalone overlay only when this explicit command runs."""

    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.customer_master.exists():
        parser.error(f"customer master does not exist: {args.customer_master}")

    overlay = build_presentation_overlay_from_customer_master(
        args.customer_master,
        portfolio_size=args.portfolio_size,
        portfolio_seed=args.portfolio_seed,
        presentation_seed=args.presentation_seed,
    )
    output_path = write_rm_presentation_overlay_artifact(overlay, args.output)
    print(f"rm_presentation_overlay_json: {output_path}")
    print(f"portfolio_customer_count: {overlay.portfolio_customer_count}")
    print(SYNTHETIC_PRESENTATION_DISCLAIMER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
