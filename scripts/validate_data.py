"""Validate generated Financial Path Twin CSV files."""

from __future__ import annotations

import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.validator import (  # noqa: E402
    build_outcome_distribution,
    build_persona_summary,
    has_failures,
    load_input_data,
    run_all_validations,
    save_validation_reports,
)


def main() -> int:
    """Run all data validations and write reports."""

    started_at = time.perf_counter()
    master_df, monthly_df = load_input_data()
    validation_report = run_all_validations(master_df, monthly_df)
    persona_summary = build_persona_summary(master_df)
    outcome_distribution = build_outcome_distribution(monthly_df)
    paths = save_validation_reports(validation_report, persona_summary, outcome_distribution)
    elapsed = time.perf_counter() - started_at

    status_counts = validation_report["status"].value_counts().to_dict()
    print(f"validation_status_counts: {status_counts}")
    print(f"data_validation_report: {paths[0]}")
    print(f"persona_summary: {paths[1]}")
    print(f"outcome_distribution: {paths[2]}")
    print(f"elapsed_seconds: {elapsed:.2f}")
    return 1 if has_failures(validation_report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
