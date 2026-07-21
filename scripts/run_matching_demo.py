"""Run a small matching demo for one configured trajectory customer."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings  # noqa: E402
from src.matcher import TrajectoryMatcher, load_trajectory_features  # noqa: E402


def load_demo_features() -> pd.DataFrame:
    """Load trajectory features with optional display-only labels."""

    features_df = load_trajectory_features()

    if settings.CUSTOMER_MASTER_PATH.exists():
        master_df = pd.read_csv(settings.CUSTOMER_MASTER_PATH, usecols=["customer_id", "persona"])
        features_df = features_df.merge(master_df, on="customer_id", how="left")

    if settings.CUSTOMER_MONTHLY_PATH.exists():
        monthly_df = pd.read_csv(
            settings.CUSTOMER_MONTHLY_PATH,
            usecols=["customer_id", "final_outcome"],
        )
        outcomes = monthly_df.drop_duplicates("customer_id")[["customer_id", "final_outcome"]]
        features_df = features_df.merge(outcomes, on="customer_id", how="left")

    return features_df


def main() -> None:
    """Fit the matcher and print the top matches for one customer."""

    started_at = time.perf_counter()
    features_df = load_demo_features()
    target_customer_id = str(features_df.iloc[0]["customer_id"])
    matcher = TrajectoryMatcher().fit(features_df)
    matches = matcher.match(target_customer_id, top_k=settings.TOP_K_MATCHES)
    elapsed = time.perf_counter() - started_at

    print(f"target_customer_id: {target_customer_id}")
    print("top_10_matches:")
    print(matches.head(10).to_string(index=False))

    if "matched_persona" in matches.columns:
        print("persona_distribution:")
        print(matches["matched_persona"].value_counts().sort_index().to_string())

    if "matched_final_outcome" in matches.columns:
        print("final_outcome_distribution:")
        print(matches["matched_final_outcome"].value_counts().sort_index().to_string())

    print(f"elapsed_seconds: {elapsed:.2f}")


if __name__ == "__main__":
    main()
