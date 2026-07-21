"""Tests for Streamlit MVP data-preparation helpers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from config import settings
from src.ui_components import (
    build_breakpoint_display_data,
    build_customer_summary,
    build_demo_options,
    build_outcome_table,
    build_whatif_comparison_table,
    load_demo_customers,
    run_customer_analysis,
)


def _demo_df() -> pd.DataFrame:
    rows = []
    for role, customer_id in (
        ("main", "C000001"),
        ("stable_comparison", "C000002"),
        ("high_risk", "C000003"),
    ):
        rows.append(
            {
                "demo_role": role,
                "customer_id": customer_id,
                "demo_score": 1.0,
                "current_status": "healthy",
                "recent_savings_rate": 0.1,
                "recent_dsr": 0.3,
                "recent_fixed_expense_ratio": 0.4,
                "matched_count": 200,
                "healthy_ratio": 0.5,
                "recovered_ratio": 0.1,
                "stress_ratio": 0.3,
                "delinquent_ratio": 0.1,
                "risk_group_ratio": 0.4,
                "breakpoint_status": "found",
                "breakpoint_month": 14,
                "months_from_current": 2,
                "primary_factor": "dsr",
                "best_scenario_id": 2,
                "best_scenario_improvement": 1000.0,
                "selection_reason": "test",
            }
        )
    return pd.DataFrame(rows).loc[:, settings.DEMO_CUSTOMER_COLUMNS]


def _monthly_df() -> pd.DataFrame:
    rows = []
    for month in range(1, 13):
        rows.append(
            {
                "customer_id": "C000001",
                "month": month,
                "savings_rate": 0.1 + month * 0.001,
                "dsr": 0.2 + month * 0.002,
                "fixed_expense_ratio": 0.35 + month * 0.001,
                "cash_balance": 10_000_000 + month * 100_000,
                "monthly_status": "watch" if month == 12 else "healthy",
            }
        )
    return pd.DataFrame(rows)


def test_load_demo_customers_and_options(tmp_path: Path) -> None:
    path = tmp_path / "demo_customers.csv"
    _demo_df().to_csv(path, index=False)

    loaded = load_demo_customers(path)
    options = build_demo_options(loaded)

    assert len(loaded) == 3
    assert [option["customer_id"] for option in options] == ["C000001", "C000002", "C000003"]


def test_build_customer_summary() -> None:
    summary = build_customer_summary(_monthly_df(), "C000001")

    assert summary["customer_id"] == "C000001"
    assert summary["current_status"] == "watch"
    assert summary["current_cash_balance"] == 11_200_000
    assert summary["recent_dsr"] == pytest.approx((0.22 + 0.222 + 0.224) / 3)


def test_build_outcome_table_fixed_order() -> None:
    table = build_outcome_table(
        {
            "matched_count": 200,
            "outcomes": {
                "stress": {"count": 60, "ratio": 0.3},
                "healthy": {"count": 100, "ratio": 0.5},
                "delinquent": {"count": 20, "ratio": 0.1},
                "recovered": {"count": 20, "ratio": 0.1},
            },
        }
    )

    assert table["결과"].tolist() == ["안정", "회복", "재무 스트레스", "연체"]
    assert table["인원"].sum() == 200
    assert table["비율"].tolist() == ["50.0%", "10.0%", "30.0%", "10.0%"]


def test_build_whatif_comparison_table() -> None:
    table = build_whatif_comparison_table(
        {
            "scenarios": [
                {
                    "scenario_name": "baseline",
                    "ending_cash_balance": 1_000_000,
                    "minimum_cash_balance": 500_000,
                    "average_savings_rate": 0.1,
                    "cash_depletion_month": None,
                    "improvement_vs_baseline": 0,
                },
                {
                    "scenario_name": "variable_expense_cut_15",
                    "ending_cash_balance": 1_500_000,
                    "minimum_cash_balance": 700_000,
                    "average_savings_rate": 0.15,
                    "cash_depletion_month": None,
                    "improvement_vs_baseline": 500_000,
                },
            ]
        }
    )

    assert table.loc[0, "대응 방법"] == "아무 조치 없음"
    assert table.loc[0, "현금 고갈 시점"] == "발생하지 않음"
    assert table.loc[1, "기준 대비 개선액(만원)"] == 50.0
    assert table.loc[1, "평균 저축률"] == "15.0%"


def test_build_breakpoint_display_data_for_found_and_not_found() -> None:
    found = build_breakpoint_display_data(
        {
            "status": "found",
            "breakpoint_month": 14,
            "months_from_current": 2,
            "primary_factor": "dsr",
            "risk_group_mean": 0.4,
            "avoidance_group_mean": 0.2,
            "standardized_difference": 0.8,
        }
    )
    not_found = build_breakpoint_display_data({"status": "not_found"})

    assert found["breakpoint_month"] == "2개월 후 · 14개월 차"
    assert found["months_from_current"] == "2개월"
    assert found["primary_factor"] == "dsr"
    assert "발견되지 않았습니다" in not_found["message"]


def test_missing_demo_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_demo_customers(tmp_path / "missing.csv")


def test_wrong_customer_id_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown customer_id"):
        build_customer_summary(_monthly_df(), "C999999")


def test_run_customer_analysis_calls_each_analysis_step_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {
        "match": 0,
        "outcome_lookup": 0,
        "outcome_summary": 0,
        "breakpoint": 0,
        "breakpoint_comparison": 0,
        "whatif": 0,
    }

    class FakeMatcher:
        def match(self, customer_id: str, top_k: int) -> pd.DataFrame:
            calls["match"] += 1
            return pd.DataFrame(
                {
                    "matched_customer_id": ["C000002", "C000003"],
                    "similarity_score": [0.9, 0.8],
                }
            )

    def fake_outcome_lookup(monthly_df: pd.DataFrame) -> dict:
        calls["outcome_lookup"] += 1
        return {}

    def fake_outcome_summary(
        customer_id: str,
        matched_ids: list[str],
        monthly_df: pd.DataFrame,
        outcome_lookup: dict,
    ) -> dict:
        calls["outcome_summary"] += 1
        return {
            "matched_count": len(matched_ids),
            "outcomes": {
                "healthy": {"count": 1, "ratio": 0.5},
                "recovered": {"count": 0, "ratio": 0.0},
                "stress": {"count": 1, "ratio": 0.5},
                "delinquent": {"count": 0, "ratio": 0.0},
            },
        }

    def fake_breakpoint(matched_ids: list[str], monthly_df: pd.DataFrame) -> dict:
        calls["breakpoint"] += 1
        return {"status": "not_found"}

    def fake_breakpoint_comparison(matched_ids: list[str], monthly_df: pd.DataFrame) -> pd.DataFrame:
        calls["breakpoint_comparison"] += 1
        return pd.DataFrame()

    def fake_whatif(customer_id: str, monthly_df: pd.DataFrame) -> dict:
        calls["whatif"] += 1
        return {"target_customer_id": customer_id, "simulation_months": 24, "scenarios": []}

    monkeypatch.setattr("src.ui_components.build_final_outcome_lookup", fake_outcome_lookup)
    monkeypatch.setattr("src.ui_components.summarize_matched_outcomes", fake_outcome_summary)
    monkeypatch.setattr("src.ui_components.find_breakpoint", fake_breakpoint)
    monkeypatch.setattr("src.ui_components.build_breakpoint_comparison", fake_breakpoint_comparison)
    monkeypatch.setattr("src.ui_components.build_whatif_results", fake_whatif)

    run_customer_analysis(
        "C000001",
        pd.DataFrame({"customer_id": ["C000001", "C000002", "C000003"]}),
        pd.DataFrame({"customer_id": ["C000001", "C000002", "C000003"]}),
        FakeMatcher(),  # type: ignore[arg-type]
        top_k=2,
    )

    assert calls == {
        "match": 1,
        "outcome_lookup": 1,
        "outcome_summary": 1,
        "breakpoint": 1,
        "breakpoint_comparison": 1,
        "whatif": 1,
    }
