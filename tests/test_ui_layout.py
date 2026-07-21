"""Layout regression tests for presentation-friendly UI spacing."""

from __future__ import annotations

import re

import pandas as pd

from src.ui_components import build_kpi_cards, load_css, render_kpi_cards_html
from src.i18n import t
from src.visualizations import (
    create_breakpoint_comparison_chart,
    create_current_trajectory_chart,
    create_twin_trajectory_chart,
    create_whatif_balance_chart,
)


def _plain_title(title: str | None) -> str:
    if title is None:
        return ""
    return re.sub(r"<br\s*/?>", " ", str(title))


def _target_monthly() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "customer_id": ["C000001"] * 12,
            "month": list(range(1, 13)),
            "savings_rate": [0.18 - month * 0.004 for month in range(1, 13)],
            "cash_balance_ratio": [4.8 + month * 0.02 for month in range(1, 13)],
            "monthly_status": ["healthy"] * 12,
        }
    )


def _twin_monthly() -> pd.DataFrame:
    rows = []
    for index, outcome in enumerate(("healthy", "recovered", "stress", "delinquent"), start=1):
        for month in range(13, 37):
            rows.append(
                {
                    "customer_id": f"C00000{index}",
                    "month": month,
                    "savings_rate": 0.16 - index * 0.02 - month * 0.002,
                    "cash_balance_ratio": 5.8 - index * 0.35 - month * 0.01,
                    "final_outcome": outcome,
                }
            )
    return pd.DataFrame(rows)


def _breakpoint_result() -> dict:
    return {
        "status": "found",
        "breakpoint_month": 13,
        "primary_factor": "cash_balance_ratio",
        "risk_group_mean": 3.4329,
        "avoidance_group_mean": 5.4944,
        "standardized_difference": -1.267,
    }


def _breakpoint_comparison() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "month": [13],
            "metric": ["cash_balance_ratio"],
            "risk_group_mean": [3.4329],
            "avoidance_group_mean": [5.4944],
        }
    )


def _whatif_results() -> dict:
    scenarios = []
    improvements = {
        "baseline": 0,
        "variable_expense_cut_15": 5_000_000,
        "fixed_expense_cut_300k": 7_000_000,
        "debt_payment_cut_20": 9_000_000,
    }
    ending = {
        "baseline": 50_000_000,
        "variable_expense_cut_15": 55_000_000,
        "fixed_expense_cut_300k": 57_000_000,
        "debt_payment_cut_20": 59_000_000,
    }
    for name, improvement in improvements.items():
        scenarios.append(
            {
                "scenario_name": name,
                "ending_cash_balance": ending[name],
                "minimum_cash_balance": 30_000_000,
                "cash_depletion_month": None,
                "improvement_vs_baseline": improvement,
                "monthly_data": [
                    {"month": month, "scenario_name": name, "cash_balance": 30_000_000 + month * 1_200_000}
                    for month in range(1, 25)
                ],
            }
        )
    return {"scenarios": scenarios}


def test_english_charts_use_safe_title_and_legend_spacing() -> None:
    figures = [
        create_twin_trajectory_chart(
            _target_monthly(),
            _twin_monthly(),
            metric="savings_rate",
            breakpoint_result=_breakpoint_result(),
            language="en",
        ),
        create_breakpoint_comparison_chart(
            _breakpoint_result(),
            _breakpoint_comparison(),
            language="en",
        ),
        create_whatif_balance_chart(_whatif_results(), language="en"),
    ]

    for figure in figures:
        assert figure.layout.margin.t >= 156
        assert figure.layout.legend.yanchor == "bottom"
        assert figure.layout.legend.y >= 1.03
        assert figure.layout.legend.title.text in ("", None)
        assert len(_plain_title(figure.layout.title.text)) <= 74
        assert figure.layout.title.y <= 0.93


def test_chart_annotations_use_short_non_overlapping_labels() -> None:
    twin = create_twin_trajectory_chart(
        _target_monthly(),
        _twin_monthly(),
        metric="savings_rate",
        breakpoint_result=_breakpoint_result(),
        language="en",
    )
    breakpoint = create_breakpoint_comparison_chart(
        _breakpoint_result(),
        _breakpoint_comparison(),
        language="en",
    )
    annotation_text = " ".join(str(annotation.text) for annotation in [*twin.layout.annotations, *breakpoint.layout.annotations])

    assert t("chart.current_point_annotation", "en", month=12) in annotation_text
    assert t("chart.breakpoint_annotation", "en", month=13) in annotation_text
    assert t("chart.observed_period", "en") in annotation_text
    assert t("chart.future_period", "en") in annotation_text
    assert "In 1 months · Month 13" not in annotation_text
    assert all((annotation.font.size or 0) <= 11 for annotation in [*twin.layout.annotations, *breakpoint.layout.annotations])


def test_whatif_chart_uses_compact_legend_labels_in_english() -> None:
    figure = create_whatif_balance_chart(_whatif_results(), language="en")
    trace_names = [str(trace.name) for trace in figure.data]

    assert "Debt Payment -20%" in trace_names
    assert "Fixed Expense -KRW 300K/mo" in trace_names
    assert "Reduce Monthly Debt Payments by 20%" not in trace_names
    assert "Reduce Fixed Expenses by KRW 300K per Month" not in trace_names
    assert figure.layout.title.text == "Debt Payment -20%: +KRW 9.0M vs no action"


def test_single_current_metric_chart_avoids_redundant_legend_and_current_text() -> None:
    figure = create_current_trajectory_chart(_target_monthly(), "savings_rate", language="en")
    trace_names = [str(trace.name) for trace in figure.data]
    current_marker = next(trace for trace in figure.data if str(trace.name) == t("chart.current_position", "en"))

    assert t("chart.current_customer", "en") in trace_names
    assert figure.data[0].showlegend is False
    assert all(annotation.text != t("chart.current_point_annotation", "en", month=12) for annotation in figure.layout.annotations)
    assert current_marker.text[0].endswith("%")
    assert "Current" not in current_marker.text[0]
    assert current_marker.textposition == "middle left"


def test_kpi_cards_have_wrapping_and_height_guards_for_english_copy() -> None:
    cards = build_kpi_cards(
        {
            "current_cash_balance": 12_500_000,
            "recent_savings_rate": 0.082,
            "recent_dsr": 0.38,
            "recent_fixed_expense_ratio": 0.46,
            "current_status": "watch",
        },
        {
            "status": "found",
            "breakpoint_month": 14,
            "months_from_current": 2,
            "primary_factor": "fixed_expense_ratio",
        },
        language="en",
    )
    rendered = render_kpi_cards_html(cards, language="en")
    css = load_css()

    assert 'aria-label="Key KPIs"' in rendered
    assert "grid-template-columns: repeat(5, minmax(190px, 1fr));" in css
    assert "overflow-wrap: anywhere;" in css
    assert "min-height: 132px;" in css
    assert "padding: 10px 6px 2px;" in css
