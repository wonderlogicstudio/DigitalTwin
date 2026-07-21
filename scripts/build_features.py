"""Build trajectory feature CSV from generated monthly data."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings  # noqa: E402
from src.feature_engineering import build_trajectory_features, save_trajectory_features  # noqa: E402


def main() -> None:
    """Load monthly data, build observation-window features, and save them."""

    started_at = time.perf_counter()
    monthly_df = pd.read_csv(settings.CUSTOMER_MONTHLY_PATH)
    features_df = build_trajectory_features(monthly_df)
    output_path = save_trajectory_features(features_df)
    elapsed = time.perf_counter() - started_at

    print(f"trajectory_features: {output_path} ({len(features_df):,} rows)")
    print(f"feature_columns: {len(features_df.columns)}")
    print(f"elapsed_seconds: {elapsed:.2f}")


if __name__ == "__main__":
    main()
