"""Tests for validation-only synthetic circularity negative controls."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from config import settings
from src.circularity_validation import (
    CIRCULARITY_SCHEMA_VERSION,
    build_signal_overlap_table,
    export_circularity_validation_report,
    run_synthetic_circularity_validation,
)


def _controlled_cohort_data(customer_count: int = 60) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create a strong label-to-future-path relation for falsification testing."""

    monthly_rows: list[dict[str, object]] = []
    feature_rows: list[dict[str, object]] = []
    for customer_number in range(1, customer_count + 1):
        customer_id = f"C{customer_number:06d}"
        is_risk = customer_number <= 35
        final_outcome = "stress" if is_risk else "healthy"
        for month in range(1, settings.TOTAL_MONTHS + 1):
            future = month >= settings.FUTURE_START_MONTH
            offset = ((customer_number % 5) - 2) * 0.001
            dsr = (0.75 if is_risk and future else 0.20) + offset
            monthly_rows.append(
                {
                    "customer_id": customer_id,
                    "month": month,
                    "income": 1_000_000,
                    "savings_rate": 0.10 + offset,
                    "fixed_expense_ratio": 0.30 + offset,
                    "variable_expense_ratio": 0.20 + offset,
                    "dsr": dsr,
                    "cash_balance": 2_000_000,
                    "loan_balance": 1_000_000,
                    "final_outcome": final_outcome,
                }
            )
        feature_rows.append(
            {
                "customer_id": customer_id,
                **{feature: 0.0 for feature in settings.MATCH_FEATURES},
            }
        )
    return pd.DataFrame(monthly_rows), pd.DataFrame(feature_rows)


def test_negative_control_is_reproducible_and_weakens_controlled_signal() -> None:
    monthly_df, features_df = _controlled_cohort_data()
    monthly_before = monthly_df.copy(deep=True)
    features_before = features_df.copy(deep=True)

    first = run_synthetic_circularity_validation(
        monthly_df,
        features_df,
        top_k=59,
        sample_size=1,
        random_seed=93,
    )
    second = run_synthetic_circularity_validation(
        monthly_df,
        features_df,
        top_k=59,
        sample_size=1,
        random_seed=93,
    )

    assert first == second
    assert first["schema_version"] == CIRCULARITY_SCHEMA_VERSION
    assert first["negative_control_summary"]["recommendation"] == "GO"
    assert first["negative_control_summary"]["weakening"]["effect_weakened"] is True
    assert first["negative_control_summary"]["weakening"]["breakpoint_rate_weakened"] is True
    assert first["target_records"][0]["risk_membership_changed"] is True
    pd.testing.assert_frame_equal(monthly_df, monthly_before)
    pd.testing.assert_frame_equal(features_df, features_before)


def test_overlap_table_names_direct_and_indirect_signal_relationships() -> None:
    rows = build_signal_overlap_table()
    by_signal = {row["signal"]: row for row in rows}

    assert by_signal["savings_rate"]["overlap_type"].startswith("direct")
    assert by_signal["variable_expense_ratio"]["overlap_type"].startswith("indirect")
    assert by_signal["loan_balance_ratio"]["overlap_type"].startswith("indirect")
    assert "future monthly_status" in by_signal
    assert all("prediction" not in str(row).lower() for row in rows)


def test_export_is_atomic_and_rejects_canonical_output_path(tmp_path: Path) -> None:
    monthly_df, features_df = _controlled_cohort_data()
    report = run_synthetic_circularity_validation(
        monthly_df,
        features_df,
        top_k=59,
        sample_size=1,
    )

    output_path = export_circularity_validation_report(report, output_dir=tmp_path / "validation")
    assert output_path.exists()
    assert output_path.name == "circularity_negative_control_report.json"
    assert not list(output_path.parent.glob("*.tmp"))
    with pytest.raises(ValueError, match="outside canonical analytics"):
        export_circularity_validation_report(report, output_dir=settings.DATA_RAW_DIR)


def test_production_modules_do_not_import_validation_module() -> None:
    source_dir = Path(__file__).resolve().parents[1] / "src"
    for source_path in source_dir.glob("*.py"):
        if source_path.name == "circularity_validation.py":
            continue
        assert "circularity_validation" not in source_path.read_text(encoding="utf-8")
