"""Build a standalone synthetic RM Portfolio and CRM overlay artifact."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.rm_portfolio import (  # noqa: E402
    DEFAULT_PORTFOLIO_SELECTION_SEED,
    DEFAULT_PORTFOLIO_SIZE,
    DEFAULT_RELATIONSHIP_ASSIGNMENT_SEED,
    DEFAULT_RM_PORTFOLIO_ID,
    SYNTHETIC_CRM_DISCLAIMER,
    build_rm_portfolio,
    write_rm_portfolio_artifacts,
)


DEFAULT_CUSTOMER_MASTER_PATH = PROJECT_ROOT / "data" / "raw" / "customer_master.csv"
DEFAULT_OUTPUT_PATH = (
    PROJECT_ROOT / "artifacts" / "rm_daily_review" / "portfolio" / "rm_portfolio.json"
)


def load_customer_ids_from_csv(customer_master_path: Path | str) -> list[str]:
    """Read only the customer_id column from an existing master CSV."""

    input_path = Path(customer_master_path)
    with input_path.open("r", encoding="utf-8", newline="") as input_file:
        reader = csv.reader(input_file)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError("customer master CSV is empty.") from exc
        if "customer_id" not in header:
            raise ValueError("customer master CSV must include customer_id.")
        customer_id_index = header.index("customer_id")
        return [row[customer_id_index] for row in reader if row]


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser without Financial Path Twin options."""

    parser = argparse.ArgumentParser(
        description="Build a deterministic synthetic RM Portfolio metadata overlay."
    )
    parser.add_argument(
        "--customer-master",
        type=Path,
        default=DEFAULT_CUSTOMER_MASTER_PATH,
        help="Existing customer master CSV; only its customer_id column is read.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Standalone RM Portfolio JSON artifact path.",
    )
    parser.add_argument("--portfolio-size", type=int, default=DEFAULT_PORTFOLIO_SIZE)
    parser.add_argument(
        "--portfolio-seed",
        type=int,
        default=DEFAULT_PORTFOLIO_SELECTION_SEED,
    )
    parser.add_argument(
        "--relationship-seed",
        type=int,
        default=DEFAULT_RELATIONSHIP_ASSIGNMENT_SEED,
    )
    parser.add_argument(
        "--rm-portfolio-id",
        default=DEFAULT_RM_PORTFOLIO_ID,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Build the overlay artifact without changing the input core CSV."""

    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.customer_master.exists():
        parser.error(f"customer master does not exist: {args.customer_master}")

    customer_ids = load_customer_ids_from_csv(args.customer_master)
    portfolio = build_rm_portfolio(
        customer_ids,
        portfolio_size=args.portfolio_size,
        portfolio_selection_seed=args.portfolio_seed,
        relationship_assignment_seed=args.relationship_seed,
        rm_portfolio_id=args.rm_portfolio_id,
    )
    json_path, csv_path = write_rm_portfolio_artifacts(portfolio, args.output)
    print(f"rm_portfolio_json: {json_path}")
    print(f"rm_portfolio_csv: {csv_path}")
    print(f"portfolio_size: {portfolio.portfolio_size}")
    print(SYNTHETIC_CRM_DISCLAIMER)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
