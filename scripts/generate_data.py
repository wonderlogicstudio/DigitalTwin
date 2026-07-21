"""Generate synthetic Financial Path Twin CSV files."""

from __future__ import annotations

import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data_generator import generate_dataset, save_dataset  # noqa: E402
from src.models import GeneratorConfig  # noqa: E402


def main() -> None:
    """Generate and save customer master and monthly snapshot CSV files."""

    started_at = time.perf_counter()
    config = GeneratorConfig()
    master_df, monthly_df = generate_dataset(config)
    master_path, monthly_path = save_dataset(master_df, monthly_df, config)
    elapsed = time.perf_counter() - started_at

    print(f"customer_master: {master_path} ({len(master_df):,} rows)")
    print(f"customer_monthly: {monthly_path} ({len(monthly_df):,} rows)")
    print(f"elapsed_seconds: {elapsed:.2f}")


if __name__ == "__main__":
    main()
