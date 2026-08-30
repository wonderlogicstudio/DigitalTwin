"""Tests for display-only formatting and label helpers."""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd

from src.formatters import (
    format_krw_compact,
    format_month_label,
    format_percent,
    select_krw_unit,
    to_ten_thousand_won,
)
from src.labels import (
    METRIC_LABELS,
    PERSONA_LABELS,
    SCENARIO_LABELS,
    STATUS_LABELS,
    label_metric,
    label_persona,
    label_scenario,
    label_status,
)
from src.ui_components import build_match_display_table, build_whatif_comparison_table
from src.visualizations import create_current_trajectory_chart, create_whatif_balance_chart


def test_format_krw_compact_positive_amounts() -> None:
    assert format_krw_compact(850_000) == "85만원"
    assert format_krw_compact(12_500_000) == "1,250만원"


def test_format_krw_compact_negative_and_zero_amounts() -> None:
    assert format_krw_compact(-3_500_000) == "-350만원"
    assert format_krw_compact(0) == "0원"


def test_format_krw_compact_ten_thousand_and_hundred_million_units() -> None:
    assert format_krw_compact(10_000) == "1만원"
    assert format_krw_compact(123_000_000) == "1억 2,300만원"


def test_format_krw_compact_missing_values() -> None:
    assert format_krw_compact(None) == "-"
    assert format_krw_compact(math.nan) == "-"
    assert format_krw_compact(np.nan) == "-"


def test_to_ten_thousand_won_and_unit_selection() -> None:
    assert to_ten_thousand_won(12_345_678) == 1234.6
    assert to_ten_thousand_won(-3_500_000) == -350.0
    assert math.isnan(to_ten_thousand_won(None))
    assert math.isnan(to_ten_thousand_won(math.nan))
    assert select_krw_unit([1_000_000, 99_999_999]) == "만원"
    assert select_krw_unit([1_000_000, 100_000_000]) == "억원"
    assert select_krw_unit(pd.DataFrame({"금액": [99_999_999, 100_000_000]})) == "억원"


def test_format_percent_positive_negative_and_over_100_percent() -> None:
    assert format_percent(0.352) == "35.2%"
    assert format_percent(-0.041) == "-4.1%"
    assert format_percent(1.0) == "100.0%"
    assert format_percent(1.234) == "123.4%"
    assert format_percent(None) == "-"
    assert format_percent(math.nan) == "-"


def test_format_month_label_current_future_and_past() -> None:
    assert format_month_label(12) == "현재 · 12개월 차"
    assert format_month_label(14) == "2개월 후 · 14개월 차"
    assert format_month_label(24) == "12개월 후 · 24개월 차"
    assert format_month_label(10) == "2개월 전 · 10개월 차"


def test_shared_labels_cover_required_mappings() -> None:
    expected_status = {
        "healthy": "안정",
        "recovered": "회복",
        "watch": "주의",
        "stress": "재무 스트레스",
        "delinquent": "연체",
    }
    expected_personas = {
        "stable": "안정형",
        "gradual_deterioration": "점진적 악화형",
        "event_shock": "이벤트 충격형",
        "recovery": "회복형",
        "overspending": "과소비형",
        "self_employed": "사업 소득 변동형(합성)",
        "asset_resilient": "여유자금 보유형(합성)",
        "financially_constrained": "재무 여력 제약형(합성)",
    }
    expected_metrics = {
        "income": "월 소득",
        "total_expense": "월 총지출",
        "cash_balance": "현금 잔액",
        "savings_rate": "저축률",
        "dsr": "DSR",
        "fixed_expense_ratio": "고정지출 비중",
        "variable_expense_ratio": "변동지출 비중",
        "loan_balance": "대출 잔액",
        "cash_balance_ratio": "소득 대비 현금 보유 수준",
        "loan_balance_ratio": "소득 대비 대출 수준",
    }
    expected_scenarios = {
        "baseline": "아무 조치 없음",
        "variable_expense_cut_15": "변동지출 15% 절감",
        "fixed_expense_cut_300k": "고정지출 월 30만원 절감",
        "debt_payment_cut_20": "대출상환액 20% 감소",
    }

    for key, label in expected_status.items():
        assert STATUS_LABELS[key] == label
        assert label_status(key) == label
    for key, label in expected_personas.items():
        assert PERSONA_LABELS[key] == label
        assert label_persona(key) == label
    for key, label in expected_metrics.items():
        assert METRIC_LABELS[key] == label
        assert label_metric(key) == label
    for key, label in expected_scenarios.items():
        assert SCENARIO_LABELS[key] == label
        assert label_scenario(key) == label

    assert label_status("unknown_status") == "unknown_status"
    assert label_status(None) == "-"


def test_display_helpers_do_not_mutate_source_data() -> None:
    matches = pd.DataFrame(
        {
            "target_customer_id": ["C000001"],
            "matched_customer_id": ["C000002"],
            "rank": [1],
            "distance": [0.12345],
            "similarity_score": [0.89123],
            "matched_final_outcome": ["stress"],
            "matched_persona": ["stable"],
        }
    )
    before = matches.copy(deep=True)

    display_table = build_match_display_table(matches)

    pd.testing.assert_frame_equal(matches, before)
    assert display_table.loc[0, "이후 결과"] == "재무 스트레스"
    assert display_table.loc[0, "고객 유형"] == "안정형"


def test_whatif_table_uses_display_units_without_internal_names() -> None:
    table = build_whatif_comparison_table(
        {
            "scenarios": [
                {
                    "scenario_name": "variable_expense_cut_15",
                    "ending_cash_balance": 12_500_000,
                    "minimum_cash_balance": -3_500_000,
                    "average_savings_rate": 0.352,
                    "cash_depletion_month": 4,
                    "improvement_vs_baseline": 850_000,
                }
            ]
        }
    )

    assert table.columns.tolist() == [
        "대응 방법",
        "24개월 후 잔액(만원)",
        "최소 잔액(만원)",
        "평균 저축률",
        "현금 고갈 시점",
        "기준 대비 개선액(만원)",
    ]
    assert table.loc[0, "대응 방법"] == "변동지출 15% 절감"
    assert table.loc[0, "24개월 후 잔액(만원)"] == 1250.0
    assert table.loc[0, "최소 잔액(만원)"] == -350.0
    assert table.loc[0, "평균 저축률"] == "35.2%"
    assert table.loc[0, "현금 고갈 시점"] == "4개월 후"
    assert "variable_expense_cut_15" not in table.to_string()


def test_plotly_figures_are_json_serializable_with_display_units() -> None:
    current_df = pd.DataFrame(
        {
            "month": [10, 11, 12],
            "cash_balance": [12_000_000, 12_500_000, 13_000_000],
            "savings_rate": [0.1, 0.12, 0.13],
            "monthly_status": ["healthy", "watch", "healthy"],
        }
    )
    whatif = {
        "scenarios": [
            {
                "scenario_name": "fixed_expense_cut_300k",
                "cash_depletion_month": None,
                "monthly_data": [
                    {"month": 1, "scenario_name": "fixed_expense_cut_300k", "cash_balance": 120_000_000},
                    {"month": 2, "scenario_name": "fixed_expense_cut_300k", "cash_balance": 123_000_000},
                ],
            }
        ]
    }

    current_fig = create_current_trajectory_chart(current_df, "cash_balance")
    whatif_fig = create_whatif_balance_chart(whatif)
    current_payload = json.loads(current_fig.to_json())
    whatif_json = whatif_fig.to_json()
    whatif_payload = json.loads(whatif_json)

    assert current_payload
    assert whatif_payload
    assert current_payload["layout"]["yaxis"]["title"]["text"] == "현금 잔액(만원)"
    assert whatif_payload["layout"]["yaxis"]["title"]["text"] == "현금 잔액(억원)"
    assert "fixed_expense_cut_300k" not in whatif_json


def test_plotly_hover_values_use_display_units_without_internal_metric_names() -> None:
    current_df = pd.DataFrame(
        {
            "month": [10, 12, 14],
            "cash_balance": [12_000_000, 12_500_000, 13_000_000],
            "savings_rate": [0.1, 0.12, 0.13],
            "monthly_status": ["healthy", "watch", "healthy"],
        }
    )

    money_fig = create_current_trajectory_chart(current_df, "cash_balance")
    ratio_fig = create_current_trajectory_chart(current_df, "savings_rate")
    money_json = money_fig.to_json()
    ratio_json = ratio_fig.to_json()

    assert "현금 잔액" in money_fig.data[0].hovertemplate
    assert "원 단위" in money_fig.data[0].hovertemplate
    assert "1,200만원" in str(money_fig.data[0].customdata.tolist())
    assert "12,000,000원" in str(money_fig.data[0].customdata.tolist())
    assert "저축률" in ratio_fig.data[0].hovertemplate
    assert "12.0%" in str(ratio_fig.data[0].customdata.tolist())
    assert "cash_balance" not in money_json
    assert "savings_rate" not in ratio_json
