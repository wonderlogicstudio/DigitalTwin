"""Tests for Plotly visualization helpers."""

from __future__ import annotations

import json
from copy import deepcopy

import pandas as pd
import plotly.graph_objects as go
import pytest

from src.labels import OUTCOME_ORDER
from src.visualizations import (
    build_breakpoint_title,
    build_dsr_title,
    build_income_expense_title,
    build_outcome_title,
    build_savings_rate_title,
    build_whatif_title,
    create_breakpoint_comparison_chart,
    create_current_trajectory_chart,
    create_feature_similarity_chart,
    create_income_expense_chart,
    create_outcome_bar_chart,
    create_twin_trajectory_chart,
    create_whatif_balance_chart,
    create_whatif_improvement_chart,
)


def _target_monthly() -> pd.DataFrame:
    months = list(range(1, 13))
    return pd.DataFrame(
        {
            "customer_id": ["C000001"] * 12,
            "month": months,
            "income": [5_000_000 + month * 10_000 for month in months],
            "total_expense": [4_000_000 + month * 5_000 for month in months],
            "cash_balance": [10_000_000 + month * 100_000 for month in months],
            "savings_rate": [0.18 - month * 0.002 for month in months],
            "dsr": [0.30 + month * 0.001 for month in months],
            "fixed_expense_ratio": [0.40 + month * 0.001 for month in months],
            "cash_balance_ratio": [2.0 + month * 0.02 for month in months],
            "monthly_status": ["healthy"] * 12,
        }
    )


def _twin_monthly() -> pd.DataFrame:
    rows = []
    outcomes = ["healthy", "recovered", "stress", "delinquent"]
    for index, outcome in enumerate(outcomes, start=1):
        for month in range(1, 37):
            rows.append(
                {
                    "customer_id": f"C00000{index + 1}",
                    "month": month,
                    "savings_rate": 0.20 - index * 0.01 - month * 0.001,
                    "cash_balance": 90_000_000 + index * 3_000_000 + month * 1_000_000,
                    "cash_balance_ratio": 2.5 - index * 0.1 - month * 0.01,
                    "fixed_expense_ratio": 0.35 + index * 0.01 + month * 0.001,
                    "dsr": 0.25 + index * 0.01 + month * 0.001,
                    "final_outcome": outcome,
                }
            )
    return pd.DataFrame(rows)


def _outcome_summary() -> dict:
    return {
        "matched_count": 200,
        "outcomes": {
            "healthy": {"count": 90, "ratio": 0.45},
            "recovered": {"count": 40, "ratio": 0.20},
            "stress": {"count": 60, "ratio": 0.30},
            "delinquent": {"count": 10, "ratio": 0.05},
        },
    }


def _breakpoint_result(status: str = "found") -> dict:
    if status != "found":
        return {
            "status": status,
            "breakpoint_month": None,
            "primary_factor": None,
            "risk_group_mean": None,
            "avoidance_group_mean": None,
        }
    return {
        "status": "found",
        "breakpoint_month": 14,
        "primary_factor": "dsr",
        "risk_group_mean": 0.42,
        "avoidance_group_mean": 0.28,
        "standardized_difference": 0.8,
    }


def _breakpoint_comparison() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "month": [13, 14, 15],
            "metric": ["dsr", "dsr", "dsr"],
            "risk_group_mean": [0.38, 0.42, 0.44],
            "avoidance_group_mean": [0.27, 0.28, 0.29],
        }
    )


def _whatif_results() -> dict:
    scenarios = []
    names = [
        "baseline",
        "variable_expense_cut_15",
        "fixed_expense_cut_300k",
        "debt_payment_cut_20",
    ]
    improvements = {
        "baseline": 0,
        "variable_expense_cut_15": 800_000,
        "fixed_expense_cut_300k": 1_500_000,
        "debt_payment_cut_20": 1_200_000,
    }
    for index, name in enumerate(names, start=1):
        rows = [
            {
                "scenario_id": index,
                "scenario_name": name,
                "month": month,
                "cash_balance": 1_000_000 + index * 100_000 + month * 50_000,
            }
            for month in range(1, 5)
        ]
        scenarios.append(
            {
                "scenario_id": index,
                "scenario_name": name,
                "ending_cash_balance": rows[-1]["cash_balance"],
                "minimum_cash_balance": min(row["cash_balance"] for row in rows),
                "cash_depletion_month": None,
                "improvement_vs_baseline": improvements[name],
                "monthly_data": rows,
            }
        )
    return {"scenarios": scenarios}


def _feature_rows() -> tuple[pd.DataFrame, pd.DataFrame]:
    target = pd.DataFrame(
        {
            "customer_id": ["C000001"],
            "avg_savings_rate_3m": [0.12],
            "avg_dsr_3m": [0.31],
            "avg_fixed_expense_ratio_3m": [0.41],
            "savings_rate_slope_12m": [-0.01],
            "expense_growth_12m": [0.08],
            "dsr_change_12m": [0.03],
        }
    )
    matched = pd.DataFrame(
        {
            "customer_id": ["C000002", "C000003"],
            "avg_savings_rate_3m": [0.11, 0.13],
            "avg_dsr_3m": [0.32, 0.30],
            "avg_fixed_expense_ratio_3m": [0.40, 0.42],
            "savings_rate_slope_12m": [-0.02, -0.005],
            "expense_growth_12m": [0.07, 0.09],
            "dsr_change_12m": [0.04, 0.02],
        }
    )
    return target, matched


def test_all_visualization_functions_return_figures() -> None:
    target_features, matched_features = _feature_rows()
    figures = [
        create_current_trajectory_chart(_target_monthly(), "savings_rate"),
        create_income_expense_chart(_target_monthly()),
        create_twin_trajectory_chart(_target_monthly(), _twin_monthly(), "dsr", _breakpoint_result()),
        create_outcome_bar_chart(_outcome_summary()),
        create_breakpoint_comparison_chart(_breakpoint_result(), _breakpoint_comparison()),
        create_whatif_balance_chart(_whatif_results()),
        create_whatif_improvement_chart(_whatif_results()),
        create_feature_similarity_chart(target_features, matched_features),
    ]

    assert all(isinstance(figure, go.Figure) for figure in figures)


def test_visualization_functions_do_not_mutate_inputs() -> None:
    target = _target_monthly()
    twins = _twin_monthly()
    whatif = _whatif_results()
    target_before = target.copy(deep=True)
    twins_before = twins.copy(deep=True)
    whatif_before = deepcopy(whatif)

    create_current_trajectory_chart(target, "cash_balance")
    create_income_expense_chart(target)
    create_twin_trajectory_chart(target, twins, "savings_rate", _breakpoint_result())
    create_whatif_balance_chart(whatif)
    create_whatif_improvement_chart(whatif)

    pd.testing.assert_frame_equal(target, target_before)
    pd.testing.assert_frame_equal(twins, twins_before)
    assert whatif == whatif_before


def test_empty_data_returns_guide_figure() -> None:
    empty_target = _target_monthly().iloc[0:0]
    empty_twins = _twin_monthly().iloc[0:0]

    current_fig = create_current_trajectory_chart(empty_target, "savings_rate")
    income_expense_fig = create_income_expense_chart(empty_target)
    twin_fig = create_twin_trajectory_chart(empty_target, empty_twins, "savings_rate")
    whatif_fig = create_whatif_balance_chart({})
    improvement_fig = create_whatif_improvement_chart({})

    assert isinstance(current_fig, go.Figure)
    assert isinstance(income_expense_fig, go.Figure)
    assert isinstance(twin_fig, go.Figure)
    assert isinstance(whatif_fig, go.Figure)
    assert isinstance(improvement_fig, go.Figure)
    assert current_fig.layout.annotations
    assert income_expense_fig.layout.annotations
    assert twin_fig.layout.annotations
    assert whatif_fig.layout.annotations
    assert improvement_fig.layout.annotations


def test_missing_required_columns_raise_value_error() -> None:
    with pytest.raises(ValueError, match="Missing required columns"):
        create_current_trajectory_chart(pd.DataFrame({"month": [1]}), "savings_rate")

    with pytest.raises(ValueError, match="Missing required columns"):
        create_income_expense_chart(pd.DataFrame({"month": [1]}))

    with pytest.raises(ValueError, match="Missing required columns"):
        create_twin_trajectory_chart(_target_monthly(), pd.DataFrame({"month": [1]}), "savings_rate")

    broken_whatif = {
        "scenarios": [
            {
                "scenario_name": "baseline",
                "monthly_data": [{"month": 1, "scenario_name": "baseline"}],
            }
        ]
    }
    with pytest.raises(ValueError, match="Missing required columns"):
        create_whatif_balance_chart(broken_whatif)


def test_money_axis_units_are_included() -> None:
    current_fig = create_current_trajectory_chart(_target_monthly(), "cash_balance")
    twin_fig = create_twin_trajectory_chart(_target_monthly(), _twin_monthly(), "cash_balance")
    whatif_fig = create_whatif_balance_chart(_whatif_results())
    improvement_fig = create_whatif_improvement_chart(_whatif_results())

    assert "현금 잔액(" in current_fig.layout.yaxis.title.text
    assert "현금 잔액(" in twin_fig.layout.yaxis.title.text
    assert "현금 잔액(" in whatif_fig.layout.yaxis.title.text
    assert "기준 대비 개선액(" in improvement_fig.layout.xaxis.title.text


def test_ratio_axes_use_percent_display() -> None:
    savings_fig = create_current_trajectory_chart(_target_monthly(), "savings_rate")
    dsr_fig = create_current_trajectory_chart(_target_monthly(), "dsr")
    twin_fig = create_twin_trajectory_chart(_target_monthly(), _twin_monthly(), "fixed_expense_ratio")

    assert savings_fig.layout.yaxis.title.text == "저축률(%)"
    assert dsr_fig.layout.yaxis.title.text == "DSR(%)"
    assert twin_fig.layout.yaxis.title.text == "고정지출 비중(%)"
    assert savings_fig.layout.yaxis.tickformat == ".0%"
    assert dsr_fig.layout.yaxis.tickformat == ".0%"


def test_current_metric_chart_highlights_current_position() -> None:
    fig = create_current_trajectory_chart(_target_monthly(), "dsr")
    current_trace = next(trace for trace in fig.data if trace.name == "현재 위치")

    assert current_trace.mode == "markers+text"
    assert current_trace.marker.symbol == "diamond"
    assert current_trace.text[0].endswith("%")
    assert "현재" not in current_trace.text[0]
    assert current_trace.textposition == "middle left"


def test_hover_and_titles_do_not_expose_internal_variable_names() -> None:
    breakpoint = {**_breakpoint_result(), "primary_factor": "fixed_expense_ratio"}
    comparison = pd.DataFrame(
        {
            "month": [14],
            "metric": ["fixed_expense_ratio"],
            "risk_group_mean": [0.58],
            "avoidance_group_mean": [0.41],
        }
    )
    breakpoint_json = create_breakpoint_comparison_chart(breakpoint, comparison).to_json()
    whatif_json = create_whatif_balance_chart(_whatif_results()).to_json()

    assert "fixed_expense_ratio" not in breakpoint_json
    assert "variable_expense_cut_15" not in whatif_json
    assert "trace " not in breakpoint_json.lower()
    assert "SMD" not in breakpoint_json


def test_current_month_line_and_future_background_exist() -> None:
    current_fig = create_current_trajectory_chart(_target_monthly(), "savings_rate")
    income_expense_fig = create_income_expense_chart(_target_monthly())
    twin_fig = create_twin_trajectory_chart(_target_monthly(), _twin_monthly(), "savings_rate")

    assert any(shape.x0 == 12 and shape.x1 == 12 for shape in current_fig.layout.shapes)
    assert any(shape.x0 == 12 and shape.x1 == 12 for shape in income_expense_fig.layout.shapes)
    assert any(shape.x0 == 12 and shape.x1 == 12 for shape in twin_fig.layout.shapes)
    assert any(shape.type == "rect" and shape.x0 == 13 and shape.x1 == 36 for shape in twin_fig.layout.shapes)


def test_breakpoint_found_not_found_and_insufficient_are_handled() -> None:
    found_fig = create_breakpoint_comparison_chart(_breakpoint_result(), _breakpoint_comparison())
    not_found_fig = create_breakpoint_comparison_chart(_breakpoint_result("not_found"))
    insufficient_fig = create_breakpoint_comparison_chart(_breakpoint_result("insufficient_group_size"))

    assert isinstance(found_fig, go.Figure)
    assert isinstance(not_found_fig, go.Figure)
    assert isinstance(insufficient_fig, go.Figure)
    assert any(shape.x0 == 14 for shape in found_fig.layout.shapes)
    assert "뚜렷하게" in not_found_fig.layout.title.text
    assert "갈라지는 시점이 발견되지 않았습니다" in not_found_fig.layout.title.text
    assert "위험 경로 또는 위험 회피 고객" in insufficient_fig.layout.title.text
    assert "충분하지 않습니다" in insufficient_fig.layout.title.text


def test_breakpoint_found_uses_result_values_when_comparison_frame_is_empty() -> None:
    fig = create_breakpoint_comparison_chart(_breakpoint_result(), pd.DataFrame())

    assert isinstance(fig, go.Figure)
    assert any(trace.name == "위험 경로 고객 평균" for trace in fig.data)
    assert any(trace.name == "위험 회피 고객 평균" for trace in fig.data)
    assert any(shape.x0 == 14 for shape in fig.layout.shapes)


def test_outcome_order_is_fixed_and_bar_text_has_count_and_ratio() -> None:
    fig = create_outcome_bar_chart(_outcome_summary())
    expected_labels = ("안정", "회복", "재무 스트레스", "연체")

    assert tuple(fig.data[0].y) == expected_labels
    assert fig.layout.yaxis.categoryarray == expected_labels
    assert fig.data[0].orientation == "h"
    assert "90명 · 45.0%" in fig.data[0].text


def test_twin_chart_uses_quantile_band_and_group_medians_by_default() -> None:
    fig = create_twin_trajectory_chart(_target_monthly(), _twin_monthly(), "savings_rate")
    trace_names = [trace.name for trace in fig.data]

    assert "전체 유사 고객 10~90% 범위" in trace_names
    assert "전체 유사 고객 중앙값" in trace_names
    assert "위험 경로 고객 중앙값" in trace_names
    assert "위험 회피 고객 중앙값" in trace_names
    assert "현재 고객" in trace_names
    assert not any("대표 궤적" in str(name) for name in trace_names)


def test_raw_trajectory_samples_are_opt_in() -> None:
    fig = create_twin_trajectory_chart(
        _target_monthly(),
        _twin_monthly(),
        "savings_rate",
        show_raw_samples=True,
    )

    assert any("대표 궤적" in str(trace.name) for trace in fig.data)


def test_twin_quantile_values_are_correct() -> None:
    target = _target_monthly()
    rows = [
        {
            "customer_id": f"C{i:06d}",
            "month": 13,
            "savings_rate": float(i),
            "final_outcome": "healthy",
        }
        for i in range(10)
    ]
    twins = pd.DataFrame(rows)

    fig = create_twin_trajectory_chart(target, twins, "savings_rate")
    q10_trace = fig.data[0]
    q90_trace = fig.data[1]
    median_trace = next(trace for trace in fig.data if trace.name == "전체 유사 고객 중앙값")

    assert list(q10_trace.y) == pytest.approx([0.9])
    assert list(q90_trace.y) == pytest.approx([8.1])
    assert list(median_trace.y) == pytest.approx([4.5])


def test_empty_risk_or_avoidance_group_is_handled() -> None:
    twins = _twin_monthly()
    healthy_only = twins[twins["final_outcome"].isin(["healthy", "recovered"])].copy()

    fig = create_twin_trajectory_chart(_target_monthly(), healthy_only, "savings_rate")

    assert isinstance(fig, go.Figure)
    assert not any(trace.name == "위험 경로 고객 중앙값" for trace in fig.data)
    assert fig.layout.annotations


def test_whatif_baseline_and_best_scenario_are_distinct() -> None:
    balance_fig = create_whatif_balance_chart(_whatif_results())
    improvement_fig = create_whatif_improvement_chart(_whatif_results())
    baseline_trace = next(trace for trace in balance_fig.data if trace.name == "아무 조치 없음")
    best_trace = next(trace for trace in balance_fig.data if trace.name == "고정지출 -30만원/월")

    assert baseline_trace.line.dash == "dash"
    assert baseline_trace.line.color != best_trace.line.color
    assert best_trace.line.width > baseline_trace.line.width
    assert improvement_fig.data[0].marker.color[0] != improvement_fig.data[0].marker.color[-1]


def test_zero_balance_reference_lines_exist() -> None:
    balance_fig = create_whatif_balance_chart(_whatif_results())
    improvement_fig = create_whatif_improvement_chart(_whatif_results())

    assert any(shape.y0 == 0 and shape.y1 == 0 for shape in balance_fig.layout.shapes)
    assert any(shape.x0 == 0 and shape.x1 == 0 for shape in improvement_fig.layout.shapes)


def test_title_helpers_return_conclusion_style_labels() -> None:
    target = _target_monthly()

    assert "소득" in build_income_expense_title(target)
    assert "저축률" in build_savings_rate_title(target)
    assert "DSR" in build_dsr_title(target)
    assert "위험 경로" in build_outcome_title(_outcome_summary())
    assert "유사 과거 경로 landmark" in build_breakpoint_title(_breakpoint_result())
    assert "고정지출 -30만원/월" in build_whatif_title(_whatif_results())


def test_figures_are_json_serializable() -> None:
    target_features, matched_features = _feature_rows()
    figures = [
        create_current_trajectory_chart(_target_monthly(), "fixed_expense_ratio"),
        create_income_expense_chart(_target_monthly()),
        create_twin_trajectory_chart(_target_monthly(), _twin_monthly(), "cash_balance_ratio"),
        create_outcome_bar_chart(_outcome_summary()),
        create_breakpoint_comparison_chart(_breakpoint_result(), _breakpoint_comparison()),
        create_whatif_balance_chart(_whatif_results()),
        create_whatif_improvement_chart(_whatif_results()),
        create_feature_similarity_chart(target_features, matched_features),
    ]

    for figure in figures:
        assert json.loads(figure.to_json())
