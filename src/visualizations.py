"""Plotly visualization helpers for the Financial Path Twin demo."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from config import settings
from src.breakpoint_analyzer import AVOIDANCE_OUTCOMES, RISK_OUTCOMES
from src.copy import (
    BREAKPOINT_INSUFFICIENT_MESSAGE,
    BREAKPOINT_NOT_FOUND_MESSAGE,
    breakpoint_status_message,
)
from src.formatters import (
    format_krw_compact,
    format_krw_full,
    format_metric_value,
    format_month_label,
    format_percent,
    scale_currency_value,
    scale_krw_value,
    select_currency_unit,
    select_krw_unit,
)
from src.i18n import t
from src.labels import (
    METRIC_LABELS,
    OUTCOME_ORDER,
    STATUS_COLORS,
    label_metric,
    label_scenario,
    label_status,
)
from src.theme import DESIGN_TOKENS


OUTCOME_LABELS = {key: label_status(key) for key in OUTCOME_ORDER}
METRIC_CONFIG = {
    "income": {"label": METRIC_LABELS["income"], "unit": "money"},
    "total_expense": {"label": METRIC_LABELS["total_expense"], "unit": "money"},
    "cash_balance": {"label": METRIC_LABELS["cash_balance"], "unit": "money"},
    "loan_balance": {"label": METRIC_LABELS["loan_balance"], "unit": "money"},
    "savings_rate": {"label": METRIC_LABELS["savings_rate"], "unit": "ratio"},
    "dsr": {"label": METRIC_LABELS["dsr"], "unit": "ratio"},
    "fixed_expense_ratio": {"label": METRIC_LABELS["fixed_expense_ratio"], "unit": "ratio"},
    "variable_expense_ratio": {"label": METRIC_LABELS["variable_expense_ratio"], "unit": "ratio"},
    "cash_balance_ratio": {"label": METRIC_LABELS["cash_balance_ratio"], "unit": "ratio_multiple"},
    "loan_balance_ratio": {"label": METRIC_LABELS["loan_balance_ratio"], "unit": "ratio_multiple"},
}
FEATURE_LABELS = {
    "avg_savings_rate_3m": METRIC_LABELS["avg_savings_rate_3m"],
    "avg_dsr_3m": METRIC_LABELS["avg_dsr_3m"],
    "avg_fixed_expense_ratio_3m": METRIC_LABELS["avg_fixed_expense_ratio_3m"],
    "savings_rate_slope_12m": METRIC_LABELS["savings_rate_slope_12m"],
    "expense_growth_12m": METRIC_LABELS["expense_growth_12m"],
    "dsr_change_12m": METRIC_LABELS["dsr_change_12m"],
    "balance_change_ratio_12m": METRIC_LABELS["balance_change_ratio_12m"],
    "income_cv_12m": METRIC_LABELS["income_cv_12m"],
    "expense_cv_12m": METRIC_LABELS["expense_cv_12m"],
    "max_consecutive_balance_decline_12m": METRIC_LABELS["max_consecutive_balance_decline_12m"],
}
COLORS = {
    "target": DESIGN_TOKENS["text"],
    "current_line": DESIGN_TOKENS["current_customer"],
    "income": DESIGN_TOKENS["primary"],
    "expense": STATUS_COLORS["watch"],
    "warning": DESIGN_TOKENS["breakpoint"],
    "healthy": STATUS_COLORS["healthy"],
    "recovered": STATUS_COLORS["recovered"],
    "stress": STATUS_COLORS["stress"],
    "delinquent": STATUS_COLORS["delinquent"],
    "risk": STATUS_COLORS["stress"],
    "avoidance": STATUS_COLORS["healthy"],
    "baseline": DESIGN_TOKENS["baseline"],
    "scenario_2": DESIGN_TOKENS["primary"],
    "scenario_3": "#7a3e8e",
    "scenario_4": "#007c91",
    "band": "rgba(0, 94, 184, 0.14)",
}
LINE_DASHES = {
    "healthy": "solid",
    "recovered": "dash",
    "stress": "dot",
    "delinquent": "dashdot",
}
CORE_FEATURE_COUNT = 6
GRID_COLOR = "rgba(148, 163, 184, 0.20)"
TITLE_MAX_CHARS = {"ko": 32, "en": 48}
ANNOTATION_FONT_SIZE = 11


def create_current_trajectory_chart(target_df: pd.DataFrame, metric: str, language: str = "ko") -> go.Figure:
    """Create a month 1..12 trajectory chart for one target customer."""

    _require_supported_metric(metric)
    _validate_required_columns(target_df, ("month", metric, "monthly_status"), "target_df")
    if target_df.empty:
        return _empty_figure(_current_metric_empty_title(metric, language), t("chart.current.empty", language), language=language)

    chart_df = target_df.loc[:, ["month", metric, "monthly_status"]].copy().sort_values("month")
    krw_unit = _krw_unit_for_metric(metric, chart_df[metric], language)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=chart_df["month"],
            y=_display_y(chart_df[metric], metric, krw_unit, language),
            mode="lines+markers",
            name=t("chart.current_customer", language),
            line={"color": COLORS["current_line"], "width": 4},
            marker={"size": 7},
            customdata=_metric_customdata(chart_df, metric, include_status=True, language=language),
            hovertemplate=_hover_template(metric, include_status=True, language=language),
            showlegend=False,
        )
    )
    _add_current_metric_context(fig, chart_df, metric, krw_unit, language)
    _add_current_value_marker(fig, chart_df, metric, krw_unit, language)
    _add_current_month_line(fig, language, show_annotation=False)
    _apply_metric_axis(fig, metric, krw_unit=krw_unit, language=language)
    fig.update_layout(
        title=_current_metric_title(chart_df, metric, language),
        xaxis_title=t("chart.month_axis", language),
        legend_title_text=t("chart.category", language),
        hovermode="x unified",
    )
    return _style_figure(fig, language=language)


def create_income_expense_chart(target_df: pd.DataFrame, language: str = "ko") -> go.Figure:
    """Create a combined income and total-expense chart for one target customer."""

    _validate_required_columns(
        target_df,
        ("month", "income", "total_expense", "monthly_status"),
        "target_df",
    )
    if target_df.empty:
        return _empty_figure(t("chart.income_expense.empty", language), t("chart.current.empty", language), language=language)

    chart_df = target_df.loc[:, ["month", "income", "total_expense", "monthly_status"]].copy()
    chart_df = chart_df.sort_values("month")
    krw_unit = select_currency_unit(chart_df[["income", "total_expense"]].to_numpy(), language)
    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=chart_df["month"],
            y=chart_df["income"].map(lambda value: scale_currency_value(value, krw_unit, language)),
            mode="lines+markers",
            name=label_metric("income", language),
            line={"color": COLORS["income"], "width": 4, "dash": "solid"},
            marker={"size": 7},
            customdata=_metric_customdata(chart_df, "income", include_status=True, language=language),
            hovertemplate=_hover_template("income", include_status=True, language=language),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=chart_df["month"],
            y=chart_df["total_expense"].map(lambda value: scale_currency_value(value, krw_unit, language)),
            mode="lines+markers",
            name=label_metric("total_expense", language),
            line={"color": COLORS["expense"], "width": 3, "dash": "solid"},
            marker={"size": 7},
            fill="tozeroy",
            fillcolor=_hex_to_rgba(COLORS["expense"], 0.08),
            customdata=_metric_customdata(chart_df, "total_expense", include_status=True, language=language),
            hovertemplate=_hover_template("total_expense", include_status=True, language=language),
        )
    )

    overspending_df = chart_df[chart_df["total_expense"] > chart_df["income"]].copy()
    if not overspending_df.empty:
        fig.add_trace(
            go.Scatter(
                x=overspending_df["month"],
                y=overspending_df["total_expense"].map(lambda value: scale_currency_value(value, krw_unit, language)),
                mode="markers",
                name="Expense Exceeds Income" if language == "en" else "지출 초과",
                marker={"color": COLORS["warning"], "size": 11, "symbol": "triangle-up"},
                customdata=np.array(
                    [
                        [
                            format_month_label(int(row.month), language=language),
                            format_krw_compact(row.income, language=language),
                            format_krw_compact(row.total_expense, language=language),
                            format_krw_full(row.total_expense - row.income, language=language),
                        ]
                        for row in overspending_df.itertuples(index=False)
                    ],
                    dtype=object,
                ),
                hovertemplate=(
                    f"{t('chart.period', language)}=%{{customdata[0]}}<br>"
                    f"{label_metric('income', language)}=%{{customdata[1]}}<br>"
                    f"{label_metric('total_expense', language)}=%{{customdata[2]}}<br>"
                    f"{'Excess Expense' if language == 'en' else '초과 지출'}=%{{customdata[3]}}<extra></extra>"
                ),
            )
        )

    _add_current_month_line(fig, language, show_annotation=False)
    fig.update_layout(
        title=build_income_expense_title(chart_df, language=language),
        xaxis_title=t("chart.month_axis", language),
        yaxis_title=t("chart.amount_axis", language, unit=krw_unit),
        legend_title_text=t("chart.category", language),
        hovermode="x unified",
    )
    fig.update_yaxes(tickformat=",")
    return _style_figure(fig, language=language)


def create_twin_trajectory_chart(
    target_df: pd.DataFrame,
    twin_df: pd.DataFrame,
    metric: str = "savings_rate",
    breakpoint_result: Mapping[str, Any] | None = None,
    max_sample_per_outcome: int = 12,
    show_raw_samples: bool = False,
    language: str = "ko",
) -> go.Figure:
    """Create a target-past and matched-twin future trajectory chart."""

    _require_supported_metric(metric)
    _validate_required_columns(target_df, ("month", metric), "target_df")
    _validate_required_columns(twin_df, ("customer_id", "month", metric, "final_outcome"), "twin_df")
    if target_df.empty and twin_df.empty:
        return _empty_figure(
            t("chart.twin.title", language, metric=_title_metric_label(metric, language)),
            t("chart.twin.empty", language),
            language=language,
        )

    target_chart_df = target_df.loc[:, ["month", metric]].copy().sort_values("month")
    twin_chart_df = twin_df.loc[:, ["customer_id", "month", metric, "final_outcome"]].copy()
    twin_chart_df = twin_chart_df[
        twin_chart_df["month"].between(settings.FUTURE_START_MONTH, settings.FUTURE_END_MONTH)
    ].copy()
    krw_unit = _krw_unit_for_metric(metric, _combined_metric_values(target_chart_df, twin_chart_df, metric), language)
    fig = go.Figure()
    _add_past_future_background(fig, language)

    overall_quantiles = pd.DataFrame()
    if not twin_chart_df.empty:
        if show_raw_samples:
            for outcome in OUTCOME_ORDER:
                group = twin_chart_df[twin_chart_df["final_outcome"] == outcome].copy()
                if not group.empty:
                    _add_sample_twin_lines(fig, group, metric, outcome, max_sample_per_outcome, krw_unit, language)

        overall_quantiles = _monthly_quantiles(twin_chart_df, metric)
        _add_quantile_band(
            fig,
            overall_quantiles,
            metric,
            krw_unit,
            name=t("chart.quantile_band", language),
            color=COLORS["current_line"],
            language=language,
        )
        _add_median_line(
            fig,
            overall_quantiles,
            metric,
            krw_unit,
            name=t("chart.overall_median", language),
            color=COLORS["current_line"],
            dash="solid",
            width=4,
            language=language,
        )

        risk_group = twin_chart_df[twin_chart_df["final_outcome"].isin(RISK_OUTCOMES)].copy()
        avoidance_group = twin_chart_df[twin_chart_df["final_outcome"].isin(AVOIDANCE_OUTCOMES)].copy()
        if risk_group.empty or avoidance_group.empty:
            _add_group_availability_note(fig, risk_group.empty, avoidance_group.empty, language)
        if not risk_group.empty:
            _add_median_line(
                fig,
                _monthly_quantiles(risk_group, metric),
                metric,
                krw_unit,
                name=t("chart.risk_median", language),
                color=COLORS["risk"],
                dash="dot",
                width=4,
                language=language,
            )
        if not avoidance_group.empty:
            _add_median_line(
                fig,
                _monthly_quantiles(avoidance_group, metric),
                metric,
                krw_unit,
                name=t("chart.avoidance_median", language),
                color=COLORS["avoidance"],
                dash="dash",
                width=4,
                language=language,
            )

    if not target_chart_df.empty:
        fig.add_trace(
            go.Scatter(
                x=target_chart_df["month"],
                y=_display_y(target_chart_df[metric], metric, krw_unit, language),
                mode="lines+markers",
                name=t("chart.current_customer", language),
                line={"color": COLORS["target"], "width": 5},
                marker={"size": 8, "symbol": "circle"},
                customdata=_metric_customdata(target_chart_df, metric, include_status=False, language=language),
                hovertemplate=_hover_template(metric, include_status=False, language=language),
            )
        )

    _add_current_month_line(fig, language)
    if breakpoint_result and breakpoint_result.get("status") == "found":
        breakpoint_month = breakpoint_result.get("breakpoint_month")
        if breakpoint_month is not None:
            _add_breakpoint_line(fig, int(breakpoint_month), language)
            _add_breakpoint_marker_on_quantile(fig, overall_quantiles, int(breakpoint_month), metric, krw_unit, language)
    _apply_metric_axis(fig, metric, krw_unit=krw_unit, language=language)
    fig.update_layout(
        title=t("chart.twin.title", language, metric=_title_metric_label(metric, language)),
        xaxis_title=t("chart.month_axis", language),
        legend_title_text=t("chart.category", language),
        hovermode="x unified",
    )
    fig.update_xaxes(range=[settings.OBSERVATION_START_MONTH, settings.FUTURE_END_MONTH])
    return _style_figure(fig, height=460, language=language)


def create_outcome_bar_chart(outcome_summary: Mapping[str, Any] | pd.DataFrame, language: str = "ko") -> go.Figure:
    """Create a fixed-order horizontal bar chart for matched-customer final outcomes."""

    summary = _coerce_outcome_summary(outcome_summary)
    counts = [summary["outcomes"][outcome]["count"] for outcome in OUTCOME_ORDER]
    ratios = [summary["outcomes"][outcome]["ratio"] for outcome in OUTCOME_ORDER]
    labels = [label_status(outcome, language) for outcome in OUTCOME_ORDER]
    text = [
        f"{count:,} customers · {format_percent(ratio)}" if language == "en" else f"{count:,}명 · {format_percent(ratio)}"
        for count, ratio in zip(counts, ratios, strict=True)
    ]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=counts,
            y=labels,
            orientation="h",
            text=text,
            textposition="outside",
            cliponaxis=False,
            marker_color=[COLORS[outcome] for outcome in OUTCOME_ORDER],
            customdata=np.array(
                [
                    [
                        label,
                        f"{count:,} customers" if language == "en" else f"{count:,}명",
                        format_percent(ratio),
                    ]
                    for label, count, ratio in zip(labels, counts, ratios, strict=True)
                ],
                dtype=object,
            ),
            hovertemplate=(
                f"{t('chart.result', language)}=%{{customdata[0]}}<br>"
                f"{t('chart.count', language)}=%{{customdata[1]}}<br>"
                f"{t('chart.ratio', language)}=%{{customdata[2]}}<extra></extra>"
            ),
        )
    )
    fig.update_xaxes(title_text=t("chart.similar_customer_count", language), tickformat=",")
    max_count = max(counts) if counts else 0
    fig.update_xaxes(range=[0, max_count * 1.18 if max_count else 1])
    fig.update_yaxes(
        title_text=t("chart.final_outcome", language),
        categoryorder="array",
        categoryarray=labels,
        autorange="reversed",
    )
    fig.add_annotation(
        x=1.0,
        y=1.08,
        xref="paper",
        yref="paper",
        text=_outcome_risk_summary(summary, language),
        showarrow=False,
        align="right",
        font={"color": DESIGN_TOKENS["muted_text"], "size": 13},
    )
    fig.update_layout(title=build_outcome_title(summary, language=language), showlegend=False)
    # This chart is paired with the 460px similar-path chart in both General
    # and Presentation mode. Its summary lives inside this chart, so matching
    # the paired chart height keeps the two framed panels level.
    return _style_figure(fig, height=460, language=language)


def _create_breakpoint_single_month_chart(
    breakpoint_result: Mapping[str, Any],
    chart_df: pd.DataFrame,
    *,
    primary_factor: str,
    krw_unit: str | None,
    language: str,
) -> go.Figure:
    """Show a saved one-month comparison without implying a full trajectory.

    Older cached demos can contain only the already-calculated means at the
    breakpoint month. Rendering those values as two points across a 36-month
    axis looks broken and suggests history that was not saved. This display is
    intentionally a comparison of the two stored historical group means only.
    """

    row = chart_df.iloc[0]
    month = int(row["month"])
    raw_values = [float(row["risk_group_mean"]), float(row["avoidance_group_mean"])]
    display_values = _display_y(raw_values, primary_factor, krw_unit, language)
    group_labels = [
        t("chart.risk_path_mean", language),
        t("chart.avoidance_path_mean", language),
    ]
    figure = go.Figure(
        go.Bar(
            x=display_values,
            y=group_labels,
            orientation="h",
            marker_color=[COLORS["risk"], COLORS["avoidance"]],
            text=[
                format_metric_value(value, primary_factor, language=language)
                for value in raw_values
            ],
            textposition="outside",
            cliponaxis=False,
            customdata=np.array(
                [
                    [
                        label,
                        format_month_label(month, language=language),
                        format_metric_value(value, primary_factor, language=language),
                    ]
                    for label, value in zip(group_labels, raw_values, strict=True)
                ],
                dtype=object,
            ),
            hovertemplate=(
                f"{t('chart.group', language)}=%{{customdata[0]}}<br>"
                f"{t('chart.period', language)}=%{{customdata[1]}}<br>"
                f"{_metric_label(primary_factor, language)}=%{{customdata[2]}}<extra></extra>"
            ),
        )
    )
    figure.update_layout(
        title=(
            f"{build_breakpoint_title(breakpoint_result, language=language)}<br>"
            f"<span style='font-size:12px;color:{DESIGN_TOKENS['muted_text']}'>"
            f"{t('chart.breakpoint.single_month_context', language, month=month)}"
            "</span>"
        ),
        showlegend=False,
        hovermode="y",
    )
    figure.update_xaxes(
        title_text=_metric_label(primary_factor, language),
        range=_bar_value_range(display_values),
    )
    figure.update_yaxes(title_text=t("chart.group", language), autorange="reversed")
    return _style_figure(figure, height=440, language=language)


def create_breakpoint_comparison_chart(
    breakpoint_result: Mapping[str, Any],
    comparison_df: pd.DataFrame | None = None,
    language: str = "ko",
) -> go.Figure:
    """Create a risk-vs-avoidance group comparison chart around the breakpoint."""

    status = str(breakpoint_result.get("status", "not_found"))
    if status != "found":
        return _empty_figure(
            build_breakpoint_title(breakpoint_result, language=language),
            _breakpoint_empty_message(status, language),
            language=language,
        )

    primary_factor = str(breakpoint_result.get("primary_factor"))
    breakpoint_month = breakpoint_result.get("breakpoint_month")
    if breakpoint_month is None or primary_factor in {"None", ""}:
        return _empty_figure(t("chart.breakpoint.no_info", language), t("chart.breakpoint.no_month_metric", language), language=language)
    _require_supported_metric(primary_factor)

    if comparison_df is None or comparison_df.empty:
        chart_df = _comparison_from_breakpoint_result(breakpoint_result)
    else:
        required_columns = {"month", "risk_group_mean", "avoidance_group_mean"}
        if not required_columns.issubset(comparison_df.columns):
            chart_df = _comparison_from_breakpoint_result(breakpoint_result)
        else:
            chart_df = comparison_df.copy()
            if "metric" in chart_df.columns:
                chart_df = chart_df[chart_df["metric"] == primary_factor].copy()
            if chart_df.empty:
                chart_df = _comparison_from_breakpoint_result(breakpoint_result)
    if chart_df.empty:
        return _empty_figure(
            build_breakpoint_title(breakpoint_result, language=language),
            t("chart.breakpoint.no_group_mean", language),
            language=language,
        )

    chart_df = chart_df.sort_values("month")
    if len(chart_df) == 1:
        return _create_breakpoint_single_month_chart(
            breakpoint_result,
            chart_df,
            primary_factor=primary_factor,
            krw_unit=_krw_unit_for_metric(
                primary_factor,
                chart_df[["risk_group_mean", "avoidance_group_mean"]].to_numpy(),
                language,
            ),
            language=language,
        )
    krw_unit = _krw_unit_for_metric(
        primary_factor,
        chart_df[["risk_group_mean", "avoidance_group_mean"]].to_numpy(),
        language,
    )
    fig = go.Figure()
    _add_past_future_background(fig, language)
    fig.add_trace(
        go.Scatter(
            x=chart_df["month"],
            y=_display_y(chart_df["risk_group_mean"], primary_factor, krw_unit, language),
            mode="lines+markers",
            name=t("chart.risk_path_mean", language),
            line={"color": COLORS["risk"], "width": 4, "dash": "solid"},
            marker={"size": 8, "symbol": "circle"},
            customdata=_breakpoint_customdata(chart_df, "risk_group_mean", primary_factor, language),
            hovertemplate=_hover_template(primary_factor, include_status=False, language=language),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=chart_df["month"],
            y=_display_y(chart_df["avoidance_group_mean"], primary_factor, krw_unit, language),
            mode="lines+markers",
            name=t("chart.avoidance_path_mean", language),
            line={"color": COLORS["avoidance"], "width": 4, "dash": "dash"},
            marker={"size": 8, "symbol": "diamond"},
            customdata=_breakpoint_customdata(chart_df, "avoidance_group_mean", primary_factor, language),
            hovertemplate=_hover_template(primary_factor, include_status=False, language=language),
        )
    )
    _add_breakpoint_line(fig, int(breakpoint_month), language)
    _add_breakpoint_markers(fig, chart_df, int(breakpoint_month), primary_factor, krw_unit, breakpoint_result, language)
    _add_current_month_line(fig, language)
    _apply_metric_axis(fig, primary_factor, krw_unit=krw_unit, language=language)
    fig.update_layout(
        title=build_breakpoint_title(breakpoint_result, language=language),
        xaxis_title=t("chart.month_axis", language),
        legend_title_text=t("chart.group", language),
        hovermode="x unified",
    )
    return _style_figure(fig, height=440, language=language)


def create_whatif_balance_chart(whatif_results: Mapping[str, Any], language: str = "ko") -> go.Figure:
    """Create a monthly cash-balance chart for all what-if scenarios."""

    scenarios = list(whatif_results.get("scenarios", []))
    if not scenarios:
        return _empty_figure(t("chart.whatif.balance.empty_title", language), t("chart.whatif.empty", language), language=language)

    balance_values = []
    for scenario in scenarios:
        balance_values.extend(row.get("cash_balance") for row in scenario.get("monthly_data", []))
        balance_values.append(scenario.get("ending_cash_balance"))
        balance_values.append(scenario.get("improvement_vs_baseline"))
    krw_unit = select_currency_unit(balance_values, language)
    best_scenario_name = _best_scenario_name(scenarios)
    fig = go.Figure()
    for scenario in scenarios:
        monthly_data = scenario.get("monthly_data", [])
        if not monthly_data:
            continue
        scenario_df = pd.DataFrame(monthly_data).copy()
        _validate_required_columns(scenario_df, ("month", "cash_balance", "scenario_name"), "monthly_data")
        scenario_name = str(scenario.get("scenario_name", scenario_df.iloc[0]["scenario_name"]))
        line_style = _scenario_line_style(scenario_name, is_best=scenario_name == best_scenario_name)
        ending_balance = _scenario_ending_balance(scenario, scenario_df)
        improvement = float(scenario.get("improvement_vs_baseline") or 0.0)
        fig.add_trace(
            go.Scatter(
                x=scenario_df["month"],
                y=scenario_df["cash_balance"].map(lambda value: scale_currency_value(value, krw_unit, language)),
                mode="lines",
                name=_legend_scenario_label(scenario_name, language),
                line=line_style,
                customdata=np.array(
                    [
                        [
                            label_scenario(scenario_name, language),
                            _relative_simulation_month(int(month), language),
                            format_krw_compact(cash_balance, language=language),
                            format_krw_full(cash_balance, language=language),
                            format_krw_compact(ending_balance, language=language),
                            format_krw_compact(improvement, language=language),
                        ]
                        for month, cash_balance in zip(
                            scenario_df["month"],
                            scenario_df["cash_balance"],
                            strict=True,
                        )
                    ],
                    dtype=object,
                ),
                hovertemplate=(
                    f"{t('chart.action', language)}=%{{customdata[0]}}<br>"
                    f"{t('chart.period', language)}=%{{customdata[1]}}<br>"
                    f"{t('chart.whatif.balance', language)}=%{{customdata[2]}}<br>"
                    f"{t('chart.full_krw', language)}=%{{customdata[3]}}<br>"
                    f"{t('chart.whatif.ending_balance', language)}=%{{customdata[4]}}<br>"
                    f"{t('chart.whatif.improvement', language)}=%{{customdata[5]}}<extra></extra>"
                ),
            )
        )
        _add_depletion_marker(fig, scenario, scenario_df, scenario_name, krw_unit, line_style, language)
    fig.add_hline(y=0, line_color=DESIGN_TOKENS["baseline"], line_dash="dash", annotation_text=t("chart.zero_won", language))
    fig.update_layout(
        title=build_whatif_title(whatif_results, language=language),
        xaxis_title=t("chart.simulation_period", language),
        legend_title_text=t("chart.action", language),
        hovermode="x unified",
    )
    fig.update_yaxes(title_text=f"{t('chart.whatif.balance', language)}({krw_unit})", tickformat=",")
    return _style_figure(fig, height=440, language=language)


def create_whatif_improvement_chart(whatif_results: Mapping[str, Any], language: str = "ko") -> go.Figure:
    """Create a ranked horizontal bar chart of scenario improvements vs baseline."""

    scenarios = list(whatif_results.get("scenarios", []))
    if not scenarios:
        return _empty_figure(t("chart.whatif.improvement.empty_title", language), t("chart.whatif.empty", language), language=language)

    rows = [
        {
            "scenario_name": str(scenario.get("scenario_name", "")),
            "label": label_scenario(scenario.get("scenario_name"), language),
            "improvement": float(scenario.get("improvement_vs_baseline") or 0.0),
        }
        for scenario in scenarios
    ]
    chart_df = pd.DataFrame(rows)
    chart_df = chart_df.sort_values("improvement", ascending=False).reset_index(drop=True)
    krw_unit = select_currency_unit(chart_df["improvement"], language)
    best_scenario_name = _best_scenario_name(scenarios)
    colors = [
        COLORS["baseline"]
        if row.scenario_name == "baseline"
        else COLORS["current_line"]
        if row.scenario_name == best_scenario_name
        else _scenario_color(row.scenario_name)
        for row in chart_df.itertuples(index=False)
    ]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=chart_df["improvement"].map(lambda value: scale_currency_value(value, krw_unit, language)),
            y=chart_df["label"],
            orientation="h",
            marker_color=colors,
            text=[format_krw_compact(value, language=language) for value in chart_df["improvement"]],
            textposition="outside",
            cliponaxis=False,
            customdata=np.array(
                [
                    [
                        row.label,
                        format_krw_compact(row.improvement, language=language),
                        format_krw_full(row.improvement, language=language),
                    ]
                    for row in chart_df.itertuples(index=False)
                ],
                dtype=object,
            ),
            hovertemplate=(
                f"{t('chart.action', language)}=%{{customdata[0]}}<br>"
                f"{t('chart.whatif.improvement', language)}=%{{customdata[1]}}<br>"
                f"{t('chart.full_krw', language)}=%{{customdata[2]}}<extra></extra>"
            ),
        )
    )
    fig.add_vline(x=0, line_color=DESIGN_TOKENS["baseline"], line_dash="dash", annotation_text=t("chart.zero_won", language))
    display_improvements = chart_df["improvement"].map(
        lambda value: scale_currency_value(value, krw_unit, language)
    )
    fig.update_xaxes(
        title_text=f"{t('chart.whatif.improvement', language)}({krw_unit})",
        tickformat=",",
        range=_bar_value_range(display_improvements),
    )
    fig.update_yaxes(title_text=t("chart.action", language), autorange="reversed")
    fig.update_layout(title=t("chart.whatif.improvement_title", language), showlegend=False)
    # Keep the paired What-if cards level while preserving enough vertical
    # space for outside bar labels in Korean and English.
    return _style_figure(fig, height=440, language=language)


def create_feature_similarity_chart(
    target_features: pd.DataFrame | pd.Series,
    matched_features: pd.DataFrame,
    feature_names: Sequence[str] | None = None,
    language: str = "ko",
) -> go.Figure:
    """Create a radar chart comparing target and matched-average feature scores."""

    target_df = _coerce_target_feature_row(target_features)
    selected_features = tuple(feature_names or settings.MATCH_FEATURES[:CORE_FEATURE_COUNT])
    selected_features = selected_features[:CORE_FEATURE_COUNT]
    _validate_required_columns(target_df, selected_features, "target_features")
    _validate_required_columns(matched_features, selected_features, "matched_features")
    if target_df.empty or matched_features.empty:
        return _empty_figure(
            t("chart.feature_similarity.title", language),
            "No metric data is available." if language == "en" else "표시할 지표 데이터가 없습니다.",
            language=language,
        )

    target_values = target_df.loc[:, selected_features].astype(float)
    matched_values = matched_features.loc[:, selected_features].astype(float).copy()
    if not np.isfinite(target_values.to_numpy()).all() or not np.isfinite(matched_values.to_numpy()).all():
        raise ValueError("Feature values must not contain NaN or inf.")

    combined = pd.concat([target_values, matched_values], ignore_index=True)
    means = combined.mean(axis=0)
    stds = combined.std(axis=0, ddof=0).replace(0, 1.0)
    target_scores = ((target_values.iloc[0] - means) / stds).to_numpy(dtype=float)
    matched_scores = ((matched_values.mean(axis=0) - means) / stds).to_numpy(dtype=float)
    labels = [label_metric(feature, language) for feature in selected_features]

    fig = go.Figure()
    fig.add_trace(
        go.Scatterpolar(
            r=np.r_[target_scores, target_scores[0]],
            theta=[*labels, labels[0]],
            fill="toself",
            name=t("chart.current_customer", language),
            line={"color": COLORS["target"], "width": 3},
        )
    )
    fig.add_trace(
        go.Scatterpolar(
            r=np.r_[matched_scores, matched_scores[0]],
            theta=[*labels, labels[0]],
            fill="toself",
            name=t("chart.feature_similarity.matched_average", language),
            line={"color": COLORS["current_line"], "width": 3, "dash": "dash"},
        )
    )
    fig.update_layout(
        title=t("chart.feature_similarity.title", language),
        polar={"radialaxis": {"title": t("chart.feature_similarity.score", language), "showline": True}},
        legend_title_text=t("chart.category", language),
    )
    return _style_figure(fig, language=language)


def build_income_expense_title(target_df: pd.DataFrame, language: str = "ko") -> str:
    """Build a conclusion-style title from the displayed income and expense rows."""

    if target_df.empty:
        return t("chart.income_expense.empty", language)
    chart_df = target_df.sort_values("month").tail(6)
    if (chart_df["total_expense"] > chart_df["income"]).any():
        return t("chart.income_expense.title.overspending", language)
    if len(chart_df) >= 2:
        income_change = float(chart_df["income"].iloc[-1]) - float(chart_df["income"].iloc[0])
        expense_change = float(chart_df["total_expense"].iloc[-1]) - float(chart_df["total_expense"].iloc[0])
        if expense_change > income_change:
            return t("chart.income_expense.title.expense_growth", language)
    return t("chart.income_expense.title.stable", language)


def build_savings_rate_title(target_df: pd.DataFrame, language: str = "ko") -> str:
    """Build a conclusion-style title for the current savings-rate chart."""

    if target_df.empty:
        return t("chart.metric_empty", language, metric=label_metric("savings_rate", language))
    chart_df = target_df.sort_values("month")
    current_value = float(chart_df["savings_rate"].iloc[-1])
    recent = chart_df.tail(6)
    trend = float(recent["savings_rate"].iloc[-1]) - float(recent["savings_rate"].iloc[0]) if len(recent) >= 2 else 0.0
    if current_value < 0:
        key = "chart.savings_rate.title.negative"
    elif current_value < 0.05:
        key = "chart.savings_rate.title.watch"
    elif trend < -0.01:
        key = "chart.savings_rate.title.decline"
    else:
        key = "chart.savings_rate.title.stable"
    return t(key, language, value=format_percent(current_value))


def build_dsr_title(target_df: pd.DataFrame, language: str = "ko") -> str:
    """Build a conclusion-style title for the current DSR chart."""

    if target_df.empty:
        return t("chart.metric_empty", language, metric=label_metric("dsr", language))
    current_value = float(target_df.sort_values("month")["dsr"].iloc[-1])
    if current_value >= 0.45:
        key = "chart.dsr.title.danger"
    elif current_value >= 0.35:
        key = "chart.dsr.title.watch"
    else:
        key = "chart.dsr.title.stable"
    return t(key, language, value=format_percent(current_value))


def build_outcome_title(outcome_summary: Mapping[str, Any] | pd.DataFrame, language: str = "ko") -> str:
    """Build a conclusion-style title for matched-customer outcomes."""

    summary = _coerce_outcome_summary(outcome_summary)
    risk_ratio = _risk_ratio(summary)
    return t(
        "chart.outcome.title",
        language,
        matched_count=f"{summary['matched_count']:,}",
        risk_ratio=format_percent(risk_ratio),
    )


def build_breakpoint_title(breakpoint_result: Mapping[str, Any], language: str = "ko") -> str:
    """Build a conclusion-style title for the breakpoint chart."""

    status = str(breakpoint_result.get("status", "not_found"))
    if status == "insufficient_group_size":
        return t("breakpoint.insufficient_group_size", language)
    if status != "found":
        return t("breakpoint.not_found", language)
    month = breakpoint_result.get("breakpoint_month")
    metric = breakpoint_result.get("primary_factor")
    if month is None or not metric:
        return t("chart.breakpoint.no_info", language)
    return t("chart.breakpoint.title", language, month=int(month), metric=_title_metric_label(str(metric), language))


def build_whatif_title(whatif_results: Mapping[str, Any], language: str = "ko") -> str:
    """Build a conclusion-style title for what-if scenario balance trends."""

    scenarios = list(whatif_results.get("scenarios", []))
    best = _best_scenario(scenarios)
    if not best:
        return t("chart.whatif.title.empty", language)
    return t(
        "chart.whatif.title",
        language,
        scenario=_legend_scenario_label(best.get("scenario_name"), language),
        improvement=format_krw_compact(best.get("improvement_vs_baseline"), language=language),
    )


def _current_metric_title(target_df: pd.DataFrame, metric: str, language: str = "ko") -> str:
    if metric == "savings_rate":
        return build_savings_rate_title(target_df, language)
    if metric == "dsr":
        return build_dsr_title(target_df, language)
    if metric == "cash_balance":
        current_value = float(target_df.sort_values("month")["cash_balance"].iloc[-1])
        if current_value < 0:
            return t("chart.cash_balance.title.negative", language, value=format_krw_compact(current_value, language=language))
        return t("chart.cash_balance.title.current", language, value=format_krw_compact(current_value, language=language))
    return t("chart.metric_flow", language, metric=_metric_label(metric, language))


def _current_metric_empty_title(metric: str, language: str = "ko") -> str:
    if metric == "savings_rate":
        return t("chart.metric_empty", language, metric=label_metric("savings_rate", language))
    if metric == "dsr":
        return t("chart.metric_empty", language, metric=label_metric("dsr", language))
    return t("chart.metric_empty", language, metric=_metric_label(metric, language))


def _add_current_metric_context(
    fig: go.Figure,
    chart_df: pd.DataFrame,
    metric: str,
    krw_unit: str | None,
    language: str = "ko",
) -> None:
    if metric == "savings_rate":
        fig.add_hline(
            y=0.05,
            line_color=STATUS_COLORS["watch"],
            line_dash="dash",
            annotation_text=t("chart.watch_threshold_5", language),
            annotation_position="top left",
        )
        fig.add_hline(y=0, line_color=DESIGN_TOKENS["baseline"], line_dash="dot")
        negative = chart_df[chart_df[metric] < 0]
        if not negative.empty:
            _add_alert_markers(fig, negative, metric, krw_unit, t("chart.negative_savings", language), language)
    elif metric == "dsr":
        fig.add_hline(
            y=0.35,
            line_color=STATUS_COLORS["watch"],
            line_dash="dash",
            annotation_text=t("chart.watch_threshold_35", language),
            annotation_position="top left",
        )
        fig.add_hline(
            y=0.45,
            line_color=STATUS_COLORS["stress"],
            line_dash="dash",
            annotation_text=t("chart.stress_threshold_45", language),
            annotation_position="top left",
        )
    elif metric == "cash_balance":
        fig.add_hline(y=0, line_color=DESIGN_TOKENS["baseline"], line_dash="dash", annotation_text=t("chart.zero_won", language))
        negative = chart_df[chart_df[metric] < 0]
        if not negative.empty:
            _add_alert_markers(fig, negative, metric, krw_unit, t("chart.negative_balance", language), language)


def _add_current_value_marker(
    fig: go.Figure,
    chart_df: pd.DataFrame,
    metric: str,
    krw_unit: str | None,
    language: str = "ko",
) -> None:
    if chart_df.empty:
        return
    current_row = chart_df.sort_values("month").iloc[-1]
    month = int(current_row["month"])
    value = current_row[metric]
    fig.add_trace(
        go.Scatter(
            x=[month],
            y=_display_y([value], metric, krw_unit, language),
            mode="markers+text",
            name=t("chart.current_position", language),
            marker={"color": COLORS["target"], "size": 12, "symbol": "diamond"},
            text=[format_metric_value(value, metric, language=language)],
            textposition="middle left",
            customdata=np.array(
                [
                    [
                        format_month_label(month, language=language),
                        format_metric_value(value, metric, language=language),
                        format_krw_full(value, language=language) if _metric_unit(metric) == "money" else "",
                    ]
                ],
                dtype=object,
            ),
            hovertemplate=_hover_template(metric, include_status=False, language=language),
            showlegend=False,
        )
    )


def _add_alert_markers(
    fig: go.Figure,
    points_df: pd.DataFrame,
    metric: str,
    krw_unit: str | None,
    name: str,
    language: str = "ko",
) -> None:
    fig.add_trace(
        go.Scatter(
            x=points_df["month"],
            y=_display_y(points_df[metric], metric, krw_unit, language),
            mode="markers",
            name=name,
            marker={"color": COLORS["warning"], "size": 11, "symbol": "x"},
            customdata=_metric_customdata(points_df, metric, include_status=True, language=language),
            hovertemplate=_hover_template(metric, include_status=True, language=language),
        )
    )


def _monthly_quantiles(group: pd.DataFrame, metric: str) -> pd.DataFrame:
    if group.empty:
        return pd.DataFrame(columns=["month", "q10", "median", "q90"])
    quantiles = (
        group.loc[:, ["month", metric]]
        .copy()
        .groupby("month", as_index=True)[metric]
        .quantile([0.1, 0.5, 0.9])
        .unstack()
        .rename(columns={0.1: "q10", 0.5: "median", 0.9: "q90"})
        .reset_index()
        .sort_values("month")
    )
    return quantiles


def _add_quantile_band(
    fig: go.Figure,
    quantiles: pd.DataFrame,
    metric: str,
    krw_unit: str | None,
    *,
    name: str,
    color: str,
    language: str = "ko",
) -> None:
    if quantiles.empty:
        return
    fig.add_trace(
        go.Scatter(
            x=quantiles["month"],
            y=_display_y(quantiles["q10"], metric, krw_unit, language),
            mode="lines",
            line={"color": "rgba(0,0,0,0)", "width": 0},
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=quantiles["month"],
            y=_display_y(quantiles["q90"], metric, krw_unit, language),
            mode="lines",
            line={"color": "rgba(0,0,0,0)", "width": 0},
            fill="tonexty",
            fillcolor=_hex_to_rgba(color, 0.14),
            name=name,
            hoverinfo="skip",
        )
    )


def _add_median_line(
    fig: go.Figure,
    quantiles: pd.DataFrame,
    metric: str,
    krw_unit: str | None,
    *,
    name: str,
    color: str,
    dash: str,
    width: int,
    language: str = "ko",
) -> None:
    if quantiles.empty:
        return
    fig.add_trace(
        go.Scatter(
            x=quantiles["month"],
            y=_display_y(quantiles["median"], metric, krw_unit, language),
            mode="lines",
            name=name,
            line={"color": color, "width": width, "dash": dash},
            customdata=_metric_customdata(
                quantiles.loc[:, ["month", "median"]].rename(columns={"median": metric}),
                metric,
                include_status=False,
                language=language,
            ),
            hovertemplate=_hover_template(metric, include_status=False, language=language),
        )
    )


def _add_sample_twin_lines(
    fig: go.Figure,
    group: pd.DataFrame,
    metric: str,
    outcome: str,
    max_sample_per_outcome: int,
    krw_unit: str | None,
    language: str = "ko",
) -> None:
    customer_ids = sorted(group["customer_id"].astype(str).unique())
    if len(customer_ids) > max_sample_per_outcome:
        sample = pd.Series(customer_ids).sample(
            n=max_sample_per_outcome,
            random_state=settings.RANDOM_SEED,
        )
        customer_ids = sorted(sample.astype(str).tolist())
    for customer_id in customer_ids:
        customer_df = group[group["customer_id"].astype(str) == customer_id].sort_values("month")
        fig.add_trace(
            go.Scatter(
                x=customer_df["month"],
                y=_display_y(customer_df[metric], metric, krw_unit, language),
                mode="lines",
                name=(
                    f"Representative {label_status(outcome, language)} Path"
                    if language == "en"
                    else f"{OUTCOME_LABELS[outcome]} 대표 궤적"
                ),
                line={"color": COLORS[outcome], "width": 1, "dash": LINE_DASHES[outcome]},
                opacity=0.18,
                showlegend=False,
                hoverinfo="skip",
            )
        )


def _add_group_availability_note(fig: go.Figure, risk_empty: bool, avoidance_empty: bool, language: str = "ko") -> None:
    if risk_empty and avoidance_empty:
        message = t("chart.group_missing.both", language)
    elif risk_empty:
        message = t("chart.group_missing.risk", language)
    else:
        message = t("chart.group_missing.avoidance", language)
    fig.add_annotation(
        x=0.02,
        y=0.02,
        xref="paper",
        yref="paper",
        text=message,
        showarrow=False,
        align="left",
        font={"size": 12, "color": DESIGN_TOKENS["muted_text"]},
    )


def _add_breakpoint_marker_on_quantile(
    fig: go.Figure,
    quantiles: pd.DataFrame,
    breakpoint_month: int,
    metric: str,
    krw_unit: str | None,
    language: str = "ko",
) -> None:
    if quantiles.empty:
        return
    row = quantiles[quantiles["month"] == breakpoint_month]
    if row.empty:
        return
    value = row.iloc[0]["median"]
    fig.add_trace(
        go.Scatter(
            x=[breakpoint_month],
            y=_display_y([value], metric, krw_unit, language),
            mode="markers",
            name=t("chart.breakpoint", language),
            marker={"color": COLORS["warning"], "size": 12, "symbol": "diamond"},
            customdata=np.array(
                [[format_month_label(breakpoint_month, language=language), format_metric_value(value, metric, language=language)]],
                dtype=object,
            ),
            hovertemplate=f"{t('chart.period', language)}=%{{customdata[0]}}<br>{t('chart.overall_median', language)}=%{{customdata[1]}}<extra></extra>",
        )
    )


def _comparison_from_breakpoint_result(breakpoint_result: Mapping[str, Any]) -> pd.DataFrame:
    required = ("breakpoint_month", "primary_factor", "risk_group_mean", "avoidance_group_mean")
    if any(breakpoint_result.get(key) is None for key in required):
        return pd.DataFrame(columns=["month", "metric", "risk_group_mean", "avoidance_group_mean"])
    return pd.DataFrame(
        [
            {
                "month": int(breakpoint_result["breakpoint_month"]),
                "metric": breakpoint_result["primary_factor"],
                "risk_group_mean": float(breakpoint_result["risk_group_mean"]),
                "avoidance_group_mean": float(breakpoint_result["avoidance_group_mean"]),
            }
        ]
    )


def _add_breakpoint_markers(
    fig: go.Figure,
    chart_df: pd.DataFrame,
    breakpoint_month: int,
    metric: str,
    krw_unit: str | None,
    breakpoint_result: Mapping[str, Any],
    language: str = "ko",
) -> None:
    point = chart_df[chart_df["month"] == breakpoint_month]
    if point.empty:
        return
    row = point.iloc[0]
    values = [row["risk_group_mean"], row["avoidance_group_mean"]]
    y_values = [scale_currency_value(value, krw_unit, language) if krw_unit else value for value in values]
    fig.add_trace(
        go.Scatter(
            x=[breakpoint_month, breakpoint_month],
            y=y_values,
            # Keep exact values in hover/summary rather than placing text on
            # top of the two series in the narrow breakpoint area.
            mode="markers",
            name=t("chart.breakpoint_mean", language),
            showlegend=False,
            marker={"size": 11, "color": [COLORS["risk"], COLORS["avoidance"]], "symbol": ["circle", "diamond"]},
            customdata=np.array(
                [
                    [
                        format_month_label(breakpoint_month, language=language),
                        t("chart.risk_path", language),
                        format_metric_value(values[0], metric, language=language),
                    ],
                    [
                        format_month_label(breakpoint_month, language=language),
                        t("chart.avoidance_path", language),
                        format_metric_value(values[1], metric, language=language),
                    ],
                ],
                dtype=object,
            ),
            hovertemplate=(
                f"{t('chart.period', language)}=%{{customdata[0]}}<br>"
                f"{t('chart.group', language)}=%{{customdata[1]}}<br>"
                f"{_metric_label(metric, language)}=%{{customdata[2]}}<extra></extra>"
            ),
        )
    )


def _add_depletion_marker(
    fig: go.Figure,
    scenario: Mapping[str, Any],
    scenario_df: pd.DataFrame,
    scenario_name: str,
    krw_unit: str,
    line_style: Mapping[str, Any],
    language: str = "ko",
) -> None:
    depletion_month = scenario.get("cash_depletion_month")
    if depletion_month is None:
        return
    depleted = scenario_df[scenario_df["month"] == int(depletion_month)]
    if depleted.empty:
        return
    fig.add_trace(
        go.Scatter(
            x=depleted["month"],
            y=depleted["cash_balance"].map(lambda value: scale_currency_value(value, krw_unit, language)),
            mode="markers",
            name=f"{_legend_scenario_label(scenario_name, language)} {t('chart.whatif.depletion_suffix', language)}",
            marker={"color": line_style["color"], "size": 11, "symbol": "x"},
            customdata=np.array(
                [
                    [
                        _relative_simulation_month(int(row.month), language),
                        format_krw_compact(row.cash_balance, language=language),
                        format_krw_full(row.cash_balance, language=language),
                    ]
                    for row in depleted.itertuples(index=False)
                ],
                dtype=object,
            ),
            hovertemplate=(
                f"{t('chart.whatif.cash_depletion', language)}<br>"
                f"{t('chart.period', language)}=%{{customdata[0]}}<br>"
                f"{t('chart.whatif.balance', language)}=%{{customdata[1]}}<br>"
                f"{t('chart.full_krw', language)}=%{{customdata[2]}}<extra></extra>"
            ),
        )
    )
    first = depleted.iloc[0]
    fig.add_annotation(
        x=int(first["month"]),
        y=scale_currency_value(first["cash_balance"], krw_unit, language),
        text=t("chart.whatif.cash_depletion", language),
        showarrow=True,
        arrowhead=2,
        ax=30,
        ay=-36,
        bgcolor=DESIGN_TOKENS["card_background"],
        bordercolor=DESIGN_TOKENS["border"],
        borderwidth=1,
        font={"size": 12, "color": DESIGN_TOKENS["text"]},
    )


def _coerce_outcome_summary(outcome_summary: Mapping[str, Any] | pd.DataFrame) -> dict[str, Any]:
    if isinstance(outcome_summary, pd.DataFrame):
        _validate_required_columns(outcome_summary, ("final_outcome", "count", "ratio"), "outcome_summary")
        outcomes = {}
        for outcome in OUTCOME_ORDER:
            row = outcome_summary[outcome_summary["final_outcome"] == outcome]
            if row.empty:
                outcomes[outcome] = {"count": 0, "ratio": 0.0}
            else:
                outcomes[outcome] = {
                    "count": int(row.iloc[0]["count"]),
                    "ratio": float(row.iloc[0]["ratio"]),
                }
        return {"matched_count": int(sum(item["count"] for item in outcomes.values())), "outcomes": outcomes}

    if "outcomes" not in outcome_summary:
        raise ValueError("outcome_summary must contain an 'outcomes' mapping.")
    outcomes = {}
    for outcome in OUTCOME_ORDER:
        if outcome not in outcome_summary["outcomes"]:
            raise ValueError(f"Missing outcome summary for: {outcome}")
        values = outcome_summary["outcomes"][outcome]
        outcomes[outcome] = {
            "count": int(values["count"]),
            "ratio": float(values["ratio"]),
        }
    matched_count = int(outcome_summary.get("matched_count", sum(item["count"] for item in outcomes.values())))
    return {"matched_count": matched_count, "outcomes": outcomes}


def _coerce_target_feature_row(target_features: pd.DataFrame | pd.Series) -> pd.DataFrame:
    if isinstance(target_features, pd.Series):
        return target_features.to_frame().T
    return target_features.copy()


def _scenario_line_style(scenario_name: str, *, is_best: bool = False) -> dict[str, Any]:
    if scenario_name == "baseline":
        return {"color": COLORS["baseline"], "width": 3, "dash": "dash"}
    style = {"color": _scenario_color(scenario_name), "width": 3, "dash": "solid"}
    if scenario_name == "variable_expense_cut_15":
        style["dash"] = "solid"
    elif scenario_name == "fixed_expense_cut_300k":
        style["dash"] = "dot"
    elif scenario_name == "debt_payment_cut_20":
        style["dash"] = "dashdot"
    if is_best:
        style["width"] = 5
        style["dash"] = "solid"
    return style


def _scenario_color(scenario_name: str) -> str:
    if scenario_name == "baseline":
        return COLORS["baseline"]
    if scenario_name == "variable_expense_cut_15":
        return COLORS["scenario_2"]
    if scenario_name == "fixed_expense_cut_300k":
        return COLORS["scenario_3"]
    if scenario_name == "debt_payment_cut_20":
        return COLORS["scenario_4"]
    return COLORS["current_line"]


def _best_scenario(scenarios: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    candidates = [
        scenario
        for scenario in scenarios
        if scenario.get("scenario_name") not in {None, "", "baseline"}
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda scenario: float(scenario.get("improvement_vs_baseline") or 0.0))


def _best_scenario_name(scenarios: Sequence[Mapping[str, Any]]) -> str | None:
    best = _best_scenario(scenarios)
    if best is None:
        return None
    return str(best.get("scenario_name"))


def _scenario_ending_balance(scenario: Mapping[str, Any], scenario_df: pd.DataFrame) -> float:
    if scenario.get("ending_cash_balance") is not None:
        return float(scenario["ending_cash_balance"])
    if scenario_df.empty:
        return 0.0
    sorted_df = scenario_df.sort_values("month")
    return float(sorted_df["cash_balance"].iloc[-1])


def _metric_customdata(df: pd.DataFrame, metric: str, include_status: bool, language: str = "ko") -> np.ndarray:
    rows: list[list[str]] = []
    for row in df.itertuples(index=False):
        row_data = row._asdict()
        value = row_data[metric]
        full_value = format_krw_full(value, language=language) if _metric_unit(metric) == "money" else ""
        status = label_status(row_data.get("monthly_status"), language) if include_status else ""
        rows.append(
            [
                format_month_label(int(row_data["month"]), language=language),
                format_metric_value(value, metric, language=language),
                full_value,
                status,
            ]
        )
    return np.array(rows, dtype=object)


def _breakpoint_customdata(df: pd.DataFrame, value_column: str, metric: str, language: str = "ko") -> np.ndarray:
    return np.array(
        [
            [
                format_month_label(int(row.month), language=language),
                format_metric_value(getattr(row, value_column), metric, language=language),
                format_krw_full(getattr(row, value_column), language=language) if _metric_unit(metric) == "money" else "",
            ]
            for row in df.itertuples(index=False)
        ],
        dtype=object,
    )


def _display_y(values: pd.Series | Sequence[Any], metric: str, krw_unit: str | None, language: str = "ko") -> pd.Series:
    series = pd.Series(values)
    if _metric_unit(metric) == "money":
        unit = krw_unit or select_currency_unit(series, language)
        return series.map(lambda value: scale_currency_value(value, unit, language))
    return series.astype(float)


def _bar_value_range(values: pd.Series | Sequence[Any]) -> list[float]:
    """Reserve room for outside bar labels while retaining a visible zero."""

    numeric = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    if numeric.empty:
        return [-1.0, 1.0]
    lower = min(0.0, float(numeric.min()))
    upper = max(0.0, float(numeric.max()))
    span = max(upper - lower, abs(lower), abs(upper), 1.0)
    return [lower - span * 0.08, upper + span * 0.20]


def _combined_metric_values(target_df: pd.DataFrame, twin_df: pd.DataFrame, metric: str) -> pd.Series:
    values = []
    if metric in target_df.columns:
        values.append(target_df[metric])
    if metric in twin_df.columns:
        values.append(twin_df[metric])
    if not values:
        return pd.Series(dtype=float)
    return pd.concat(values, ignore_index=True)


def _krw_unit_for_metric(metric: str, values: Any, language: str = "ko") -> str | None:
    if _metric_unit(metric) == "money":
        return select_currency_unit(values, language)
    return None


def _metric_label(metric: str, language: str = "ko") -> str:
    return label_metric(metric, language)


def _title_metric_label(metric: str, language: str = "ko") -> str:
    short_label = t(f"chart.title_metric.{metric}", language)
    if short_label != f"chart.title_metric.{metric}":
        return short_label
    return label_metric(metric, language)


def _legend_scenario_label(scenario_name: Any, language: str = "ko") -> str:
    key = "" if scenario_name is None else str(scenario_name)
    short_label = t(f"chart.legend.scenario.{key}", language)
    if short_label != f"chart.legend.scenario.{key}":
        return short_label
    return label_scenario(key, language)


def _hover_template(metric: str, include_status: bool, language: str = "ko") -> str:
    full_value_part = f"<br>{t('chart.full_krw', language)}=%{{customdata[2]}}" if _metric_unit(metric) == "money" else ""
    status_part = f"<br>{t('chart.status', language)}=%{{customdata[3]}}" if include_status else ""
    return (
        f"{t('chart.period', language)}=%{{customdata[0]}}<br>{_metric_label(metric, language)}=%{{customdata[1]}}"
        f"{full_value_part}{status_part}<extra></extra>"
    )


def _apply_metric_axis(fig: go.Figure, metric: str, krw_unit: str | None = None, language: str = "ko") -> None:
    unit = _metric_unit(metric)
    label = _metric_label(metric, language)
    if unit == "money":
        selected_unit = krw_unit or ("KRW million" if language == "en" else "만원")
        fig.update_yaxes(title_text=f"{label}({selected_unit})", tickformat=",")
    elif unit == "ratio":
        fig.update_yaxes(title_text=f"{label}(%)", tickformat=".0%")
    else:
        unit_label = "x" if language == "en" else "배"
        fig.update_yaxes(title_text=f"{label}({unit_label})", tickformat=".2f")


def _metric_unit(metric: str) -> str:
    return str(METRIC_CONFIG.get(metric, {"unit": "ratio"})["unit"])


def _require_supported_metric(metric: str) -> None:
    if metric not in METRIC_CONFIG:
        raise ValueError(f"Unsupported metric: {metric}")


def _validate_required_columns(df: pd.DataFrame, required_columns: Sequence[str], context: str) -> None:
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns in {context}: {missing_columns}")


def _add_current_month_line(fig: go.Figure, language: str = "ko", show_annotation: bool = True) -> None:
    line_kwargs: dict[str, Any] = {
        "x": settings.OBSERVATION_END_MONTH,
        "line_color": DESIGN_TOKENS["current_customer"],
        "line_dash": "dash",
    }
    if show_annotation:
        line_kwargs["annotation_text"] = t(
            "chart.current_point_annotation",
            language,
            month=settings.OBSERVATION_END_MONTH,
        )
        line_kwargs["annotation_position"] = "bottom left"
    fig.add_vline(**line_kwargs)


def _add_breakpoint_line(fig: go.Figure, breakpoint_month: int, language: str = "ko") -> None:
    fig.add_vline(
        x=breakpoint_month,
        line_color=COLORS["warning"],
        line_dash="dot",
        annotation_text=t("chart.breakpoint_annotation", language, month=breakpoint_month),
        annotation_position="top right",
    )


def _add_past_future_background(fig: go.Figure, language: str = "ko") -> None:
    fig.add_vrect(
        x0=settings.OBSERVATION_START_MONTH,
        x1=settings.OBSERVATION_END_MONTH,
        fillcolor=DESIGN_TOKENS["future_band"],
        opacity=0.18,
        line_width=0,
        annotation_text=t("chart.observed_period", language),
        annotation_position="bottom left",
    )
    fig.add_vrect(
        x0=settings.FUTURE_START_MONTH,
        x1=settings.FUTURE_END_MONTH,
        fillcolor="#f7f8fa",
        opacity=0.24,
        line_width=0,
        annotation_text=t("chart.future_period", language),
        annotation_position="bottom right",
    )


def _empty_figure(title: str, message: str, language: str = "ko") -> go.Figure:
    fig = go.Figure()
    fig.update_layout(title=title, xaxis={"visible": False}, yaxis={"visible": False})
    fig.add_annotation(
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        text=message,
        showarrow=False,
        font={"size": 15, "color": DESIGN_TOKENS["muted_text"]},
    )
    return _style_figure(fig, language=language)


def _style_figure(fig: go.Figure, *, height: int = 420, language: str = "ko") -> go.Figure:
    wrapped_title = _wrap_title_text(fig.layout.title.text, language)
    title_lines = max(1, wrapped_title.count("<br>") + 1) if wrapped_title else 1
    legend_rows = _estimated_legend_rows(fig)
    top_margin = 126 + 22 * (title_lines - 1) + (30 * legend_rows if legend_rows else 0)
    fig.update_layout(
        template="plotly_white",
        height=height,
        margin={"l": 72, "r": 70, "t": top_margin, "b": 72},
        font={"family": DESIGN_TOKENS["font_family"], "size": 13, "color": DESIGN_TOKENS["text"]},
        title={
            "text": wrapped_title,
            "font": {"size": 17, "color": DESIGN_TOKENS["text"]},
            "x": 0.0,
            "xanchor": "left",
            "y": 0.93,
            "yanchor": "top",
            "pad": {"t": 10, "b": 12},
        },
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.03,
            "xanchor": "left",
            "x": 0,
            "font": {"size": 11},
            "title": {"text": ""},
            "tracegroupgap": 6,
        },
        paper_bgcolor=DESIGN_TOKENS["card_background"],
        plot_bgcolor=DESIGN_TOKENS["card_background"],
        hoverlabel={"bgcolor": DESIGN_TOKENS["card_background"], "font_size": 12, "namelength": -1},
    )
    fig.update_xaxes(
        showgrid=True,
        gridcolor=GRID_COLOR,
        zeroline=False,
        showline=False,
        ticks="outside",
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=GRID_COLOR,
        zeroline=False,
        showline=False,
        ticks="outside",
        automargin=True,
        title_standoff=10,
    )
    fig.update_xaxes(automargin=True, title_standoff=10)
    _style_annotations(fig)
    return fig


def _wrap_title_text(title: Any, language: str = "ko") -> str | None:
    if title is None:
        return None
    text = str(title)
    if "<br>" in text:
        return text
    max_chars = TITLE_MAX_CHARS.get(language, TITLE_MAX_CHARS["ko"])
    if len(text) <= max_chars:
        return text
    split_at = text.rfind(" ", 0, max_chars + 1)
    if split_at < max_chars * 0.45:
        split_at = max_chars
    first = text[:split_at].strip()
    second = text[split_at:].strip()
    if len(second) > max_chars:
        second = second[: max_chars - 3].rstrip() + "..."
    return f"{first}<br>{second}"


def _estimated_legend_rows(fig: go.Figure) -> int:
    visible_names = [
        str(trace.name)
        for trace in fig.data
        if trace.name and getattr(trace, "showlegend", None) is not False
    ]
    if not visible_names:
        return 0
    budget = 58
    rows = 1
    current = 0
    for name in visible_names:
        size = min(max(len(name), 8), 26)
        if current and current + size > budget:
            rows += 1
            current = 0
        current += size + 4
    return rows


def _style_annotations(fig: go.Figure) -> None:
    for annotation in fig.layout.annotations or ():
        existing_font = annotation.font.to_plotly_json() if annotation.font else {}
        existing_font.setdefault("color", DESIGN_TOKENS["muted_text"])
        existing_font["size"] = min(int(existing_font.get("size", ANNOTATION_FONT_SIZE)), ANNOTATION_FONT_SIZE)
        annotation.font = existing_font
        annotation.align = annotation.align or "center"


def _risk_ratio(summary: Mapping[str, Any]) -> float:
    outcomes = summary["outcomes"]
    return float(outcomes["stress"]["ratio"]) + float(outcomes["delinquent"]["ratio"])


def _outcome_risk_summary(summary: Mapping[str, Any], language: str = "ko") -> str:
    risk_count = int(summary["outcomes"]["stress"]["count"]) + int(summary["outcomes"]["delinquent"]["count"])
    return t(
        "chart.outcome.risk_summary",
        language,
        risk_count=f"{risk_count:,}",
        risk_ratio=format_percent(_risk_ratio(summary)),
    )


def _breakpoint_empty_message(status: str, language: str = "ko") -> str:
    return breakpoint_status_message(status, language)


def _format_metric_difference(value: float, metric: str, language: str = "ko") -> str:
    unit = _metric_unit(metric)
    if unit == "money":
        return format_krw_compact(value, language=language)
    if unit == "ratio":
        return f"{value * 100:.1f}%p"
    if unit == "ratio_multiple":
        suffix = "x" if language == "en" else "배"
        return f"{value:.2f}{suffix}"
    return f"{value:,.2f}"


def _relative_simulation_month(month: int, language: str = "ko") -> str:
    if language == "en":
        return f"After {int(month)} months"
    return f"{int(month)}개월 후"


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    value = hex_color.lstrip("#")
    red, green, blue = tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))
    return f"rgba({red}, {green}, {blue}, {alpha})"
