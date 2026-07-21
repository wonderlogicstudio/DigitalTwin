"""Select fixed demo customers and save demo artifacts."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings  # noqa: E402
from src.demo_selector import save_demo_outputs, select_demo_customers  # noqa: E402


def main() -> None:
    """Prepare demo customer CSV and main demo customer JSON."""

    started_at = time.perf_counter()
    monthly_df = pd.read_csv(settings.CUSTOMER_MONTHLY_PATH)
    features_df = pd.read_csv(settings.TRAJECTORY_FEATURES_PATH)
    demo_df, main_demo_customer = select_demo_customers(monthly_df, features_df)
    demo_path, main_path = save_demo_outputs(demo_df, main_demo_customer)
    elapsed = time.perf_counter() - started_at

    print(f"demo_customers: {demo_path}")
    print(f"main_demo_customer: {main_path}")
    print("selected_customers:")
    print(demo_df.to_string(index=False))
    relaxed = demo_df["selection_reason"].str.contains("relaxed:", regex=False).any()
    if relaxed:
        print("relaxation_applied: true")
    print(f"elapsed_seconds: {elapsed:.2f}")


if __name__ == "__main__":
    main()
