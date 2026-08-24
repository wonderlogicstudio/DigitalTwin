"""Data preparation helpers used by the Streamlit MVP."""

from __future__ import annotations

import json
import html
import math
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from config import settings
from src.assets import load_css_asset
from src.breakpoint_analyzer import (
    AVOIDANCE_OUTCOMES,
    RISK_OUTCOMES,
    calculate_monthly_smd,
    find_breakpoint,
    prepare_breakpoint_data,
)
from src.copy import (
    BREAKPOINT_INSUFFICIENT_MESSAGE,
    BREAKPOINT_NOT_FOUND_MESSAGE,
    SECTION_COPY,
    UI_MESSAGES,
    WHATIF_TABLE_COLUMNS,
    cash_depletion_label,
)
from src.demo_selector import build_final_outcome_lookup, summarize_matched_outcomes
from src.formatters import (
    format_currency,
    format_krw_compact,
    format_metric_value,
    format_month_label,
    format_percent,
    to_million_krw,
    to_ten_thousand_won,
)
from src.i18n import t
from src.labels import (
    METRIC_LABELS,
    OUTCOME_ORDER,
    TERM_HELP_TEXT,
    label_metric,
    label_persona,
    label_scenario,
    label_status,
    term_help_text,
)
from src.matcher import TrajectoryMatcher
from src.theme import DESIGN_TOKENS
from src.whatif_simulator import build_whatif_results


DEMO_ROLE_LABELS = {
    "main": "메인 고객",
    "stable_comparison": "안정 비교 고객",
    "high_risk": "고위험 고객",
}
HERO_DEMO_ROLE_LABELS = {
    "main": "메인",
    "stable_comparison": "안정 비교",
    "high_risk": "고위험",
}
OUTCOME_LABELS = {
    key: label_status(key) for key in OUTCOME_ORDER
}
ANALYSIS_METRICS = {
    "savings_rate": METRIC_LABELS["savings_rate"],
    "cash_balance_ratio": METRIC_LABELS["cash_balance_ratio"],
    "fixed_expense_ratio": METRIC_LABELS["fixed_expense_ratio"],
    "dsr": METRIC_LABELS["dsr"],
}
CURRENT_METRICS = {
    "savings_rate": METRIC_LABELS["savings_rate"],
    "dsr": METRIC_LABELS["dsr"],
    "cash_balance": METRIC_LABELS["cash_balance"],
    "income": METRIC_LABELS["income"],
    "total_expense": METRIC_LABELS["total_expense"],
    "fixed_expense_ratio": METRIC_LABELS["fixed_expense_ratio"],
}
JUDGE_FLOW_SECTION_TITLES = (
    SECTION_COPY["current"]["title"],
    SECTION_COPY["peers"]["title"],
    SECTION_COPY["breakpoint"]["title"],
    SECTION_COPY["whatif"]["title"],
    SECTION_COPY["usage"]["title"],
)


def get_analysis_metric_options(language: str = "ko") -> dict[str, str]:
    """Return display labels for the metrics available in the future-path chart."""

    return {metric: label_metric(metric, language) for metric in ANALYSIS_METRICS}


def get_section_copy(section: str, language: str = "ko") -> dict[str, str]:
    """Return translated section label, title, and short description."""

    key = "briefing" if section == "usage" else section
    return {
        "label": t(f"section.{key}.label", language),
        "title": t(f"section.{key}.title", language),
        "caption": t(f"section.{key}.description", language),
    }


def load_css(path: Path | None = None) -> str:
    """Read the app CSS file without blocking the UI when it is unavailable."""

    css = load_css_asset(path) if path is not None else load_css_asset()
    if not css:
        return ""
    return f"{_design_token_css()}\n{css}"


def escape_html(value: Any) -> str:
    """Escape user-controlled values before inserting them into HTML."""

    return html.escape("" if value is None else str(value), quote=True)


def build_first_screen_view_model(
    *,
    customer_id: str,
    summary: Mapping[str, Any],
    demo_df: pd.DataFrame | None = None,
    analysis: Mapping[str, Any] | None = None,
    matched_count: int = settings.TOP_K_MATCHES,
    language: str = "ko",
) -> dict[str, Any]:
    """Build display-only data for the hero-adjacent customer summary."""

    resolved_matched_count = _resolve_matched_count(customer_id, demo_df, analysis, matched_count)
    breakpoint_result = _resolve_breakpoint_result(customer_id, demo_df, analysis)
    return {
        "customer_identity": build_customer_identity(
            customer_id=customer_id,
            summary=summary,
            demo_df=demo_df,
            matched_count=resolved_matched_count,
            language=language,
        ),
        "kpi_cards": build_kpi_cards(summary, breakpoint_result, language=language),
        "status_sentence": build_current_status_sentence(summary, breakpoint_result, language=language),
    }


def build_customer_identity(
    *,
    customer_id: str,
    summary: Mapping[str, Any],
    demo_df: pd.DataFrame | None = None,
    matched_count: int = settings.TOP_K_MATCHES,
    current_month: int = settings.OBSERVATION_END_MONTH,
    language: str = "ko",
) -> list[dict[str, Any]]:
    """Return compact customer identity chips for the first screen."""

    status_badge = build_status_badge(summary.get("current_status"), language=language)
    items: list[dict[str, Any]] = [
        {"label": t("customer.id", language), "value": str(customer_id)},
        {"label": t("customer.current_status", language), "value": status_badge["label"], "badge": status_badge},
        {"label": t("customer.analysis_period", language), "value": t("customer.analysis_period_value", language)},
        {"label": t("customer.similar_count", language), "value": _format_count(int(matched_count), language)},
        {"label": t("customer.current_position", language), "value": _month_number_text(int(current_month), language)},
    ]
    role = _demo_role_for_customer(customer_id, demo_df)
    if role:
        items.append({"label": t("customer.demo_role", language), "value": _demo_role_label(role, language, short=True)})
    return items


def build_status_badge(status: Any, language: str = "ko") -> dict[str, str]:
    """Build a text badge model for a monthly status value."""

    status_key = "" if status is None else str(status)
    class_key = status_key if status_key in {"healthy", "recovered", "watch", "stress", "delinquent"} else "baseline"
    return {
        "label": label_status(status, language),
        "status": status_key,
        "class_name": f"fpt-badge status-{class_key}",
    }


def build_kpi_cards(
    summary: Mapping[str, Any],
    breakpoint_result: Mapping[str, Any] | None = None,
    language: str = "ko",
) -> list[dict[str, Any]]:
    """Return the five first-screen KPI cards without mutating source data."""

    cash_balance = summary.get("current_cash_balance")
    savings_rate = summary.get("recent_savings_rate")
    dsr = summary.get("recent_dsr")
    fixed_expense_ratio = summary.get("recent_fixed_expense_ratio")
    return [
        {
            "id": "current_cash_balance",
            "title": t("kpi.cash_balance", language),
            "value": format_currency(cash_balance, language=language),
            "unit": "",
            "description": t("kpi.cash_balance.description", language),
            "detail": _cash_balance_note(cash_balance, language),
            "tone": classify_kpi_tone("cash_balance", cash_balance),
            "badge": _kpi_tone_badge(classify_kpi_tone("cash_balance", cash_balance), language),
        },
        {
            "id": "recent_savings_rate",
            "title": t("kpi.savings_rate", language),
            "value": format_percent(savings_rate),
            "unit": "",
            "description": t("kpi.recent_3m_average", language),
            "detail": _savings_rate_note(savings_rate, language),
            "tone": classify_kpi_tone("savings_rate", savings_rate),
            "badge": _kpi_tone_badge(classify_kpi_tone("savings_rate", savings_rate), language),
            "help": term_help_text("savings_rate", language),
        },
        {
            "id": "recent_dsr",
            "title": t("kpi.dsr", language),
            "value": format_percent(dsr),
            "unit": "",
            "description": t("kpi.recent_3m_average", language),
            "detail": _dsr_note(dsr, language),
            "tone": classify_kpi_tone("dsr", dsr),
            "badge": _kpi_tone_badge(classify_kpi_tone("dsr", dsr), language),
            "help": term_help_text("dsr", language),
        },
        {
            "id": "recent_fixed_expense_ratio",
            "title": t("kpi.fixed_expense_ratio", language),
            "value": format_percent(fixed_expense_ratio),
            "unit": "",
            "description": t("kpi.recent_3m_average", language),
            "detail": _fixed_expense_ratio_note(fixed_expense_ratio, language),
            "tone": classify_kpi_tone("fixed_expense_ratio", fixed_expense_ratio),
            "badge": _kpi_tone_badge(classify_kpi_tone("fixed_expense_ratio", fixed_expense_ratio), language),
            "help": term_help_text("fixed_expense_ratio", language),
        },
        _breakpoint_kpi_card(breakpoint_result, language),
    ]


def classify_kpi_tone(metric: str, value: Any) -> str:
    """Classify display tone from documented business thresholds only."""

    number = _safe_float(value)
    if number is None:
        return "neutral"
    if metric == "cash_balance":
        return "danger" if number < 0 else "neutral"
    if metric == "dsr":
        if number >= 0.45:
            return "danger"
        if number >= 0.35:
            return "watch"
        return "stable"
    if metric == "savings_rate":
        return "watch" if number < 0.05 else "neutral"
    if metric == "fixed_expense_ratio":
        if number >= 0.55:
            return "danger"
        if number >= 0.45:
            return "watch"
    return "neutral"


def build_current_status_sentence(
    summary: Mapping[str, Any],
    breakpoint_result: Mapping[str, Any] | None = None,
    language: str = "ko",
) -> str:
    """Build one concise first-screen interpretation sentence from existing results."""

    status_key = "" if summary.get("current_status") is None else str(summary.get("current_status"))
    status_label = label_status(status_key, language)
    if status_label == "-":
        status_label = t("brief.unavailable", language)
    if language == "en":
        prefix = (
            "The customer is currently delinquent."
            if status_key == "delinquent"
            else f"The customer is currently {status_label}."
        )
    else:
        prefix = "현재는 연체 상태입니다." if status_label == "연체" else f"현재는 {status_label} 상태입니다."
    if breakpoint_result is None:
        suffix = (
            "Run similar-customer analysis to review whether a historical landmark appears in the similar-path cohort."
            if language == "en"
            else "유사 고객 분석을 실행하면 유사 경로 집단에 과거 landmark가 있는지 함께 확인할 수 있습니다."
        )
        return f"{prefix} {suffix}"

    status = str(breakpoint_result.get("status", "not_found"))
    if status == "found":
        breakpoint_month = _to_int_or_none(breakpoint_result.get("breakpoint_month"))
        primary_factor = label_metric(breakpoint_result.get("primary_factor"), language)
        timing_text = _historical_breakpoint_sentence(breakpoint_month, language)
        if language == "en":
            return f"{prefix} {timing_text} The key difference is {primary_factor}."
        return f"{prefix} {timing_text} 주요 차이 지표는 {primary_factor}입니다."
    if status == "insufficient_group_size":
        return f"{prefix} {t('breakpoint.insufficient_group_size', language)}"
    if status == "error":
        return f"{prefix} {t('breakpoint.display_error', language)}"
    return f"{prefix} {t('breakpoint.not_found', language)}"


def render_hero_html(
    logo_svg: str | None = None,
    hero_svg: str | None = None,
    language: str = "ko",
) -> str:
    """Return the static product hero block."""

    logo_html = f'<div class="fpt-hero-logo">{logo_svg}</div>' if logo_svg else ""
    hero_visual_html = f'<div class="fpt-hero-visual">{hero_svg}</div>' if hero_svg else ""
    return f"""
<section class="fpt-hero" aria-label="{escape_html(t("app.hero_aria", language))}">
  <div class="fpt-hero-main">
    {logo_html}
    <div class="fpt-hero-copy">
      <h1>{escape_html(t("app.title", language))}</h1>
      <p class="fpt-subtitle">{escape_html(t("app.subtitle", language))}</p>
      <p class="fpt-message">{escape_html(t("app.message", language))}</p>
      <p class="fpt-notice">{escape_html(t("app.disclaimer", language))}</p>
    </div>
  </div>
  {hero_visual_html}
</section>
""".strip()


def render_customer_identity_html(items: list[dict[str, Any]], language: str = "ko") -> str:
    """Render customer identity chips with escaped values."""

    chips = []
    for item in items:
        label = escape_html(item.get("label", ""))
        badge = item.get("badge")
        if badge:
            value_html = (
                f'<span class="{escape_html(badge.get("class_name", "fpt-badge status-baseline"))}">'
                f'{escape_html(badge.get("label", ""))}</span>'
            )
        else:
            value_html = escape_html(item.get("value", ""))
        chips.append(
            '<div class="fpt-meta-chip">'
            f'<span class="fpt-meta-label">{label}</span>'
            f'<span class="fpt-meta-value">{value_html}</span>'
            "</div>"
        )
    aria_label = escape_html(t("app.customer_identity_aria", language))
    return f'<section class="fpt-customer-strip" aria-label="{aria_label}">' + "".join(chips) + "</section>"


def render_kpi_cards_html(cards: list[dict[str, Any]], language: str = "ko") -> str:
    """Render the first-screen KPI card grid."""

    rendered_cards = []
    for card in cards:
        tone = escape_html(card.get("tone", "neutral"))
        badge = card.get("badge")
        badge_html = ""
        if badge:
            badge_html = (
                f'<span class="fpt-kpi-badge tone-{escape_html(badge.get("tone", "neutral"))}">'
                f'{escape_html(badge.get("label", ""))}</span>'
            )
        help_html = ""
        help_text = card.get("help")
        if help_text:
            escaped_help = escape_html(help_text)
            help_html = (
                '<span class="fpt-kpi-help" '
                f'title="{escaped_help}" aria-label="{escaped_help}">?</span>'
            )
        unit = card.get("unit")
        unit_html = f' <span class="fpt-kpi-unit">{escape_html(unit)}</span>' if unit else ""
        rendered_cards.append(
            f'<article class="fpt-kpi-card tone-{tone}">'
            '<div class="fpt-kpi-topline">'
            '<span class="fpt-kpi-title-wrap">'
            f'<span class="fpt-kpi-title">{escape_html(card.get("title", ""))}</span>'
            f"{help_html}"
            "</span>"
            f"{badge_html}"
            "</div>"
            f'<div class="fpt-kpi-value">{escape_html(card.get("value", ""))}{unit_html}</div>'
            f'<div class="fpt-kpi-description">{escape_html(card.get("description", ""))}</div>'
            f'<div class="fpt-kpi-detail">{escape_html(card.get("detail", ""))}</div>'
            "</article>"
        )
    aria_label = escape_html(t("kpi.grid_aria", language))
    return f'<section class="fpt-kpi-grid" aria-label="{aria_label}">' + "".join(rendered_cards) + "</section>"


def render_status_summary_html(sentence: str) -> str:
    """Render the one-line current state interpretation."""

    return f'<p class="fpt-status-summary">{escape_html(sentence)}</p>'


def render_presentation_scene_heading_html(scene: Mapping[str, Any]) -> str:
    """Render a numbered presentation scene heading."""

    return (
        '<section class="fpt-presentation-scene-heading">'
        f'<span class="fpt-presentation-step">{escape_html(scene.get("label", ""))}</span>'
        f'<h2>{escape_html(scene.get("title", ""))}</h2>'
        f'<p>{escape_html(scene.get("message", ""))}</p>'
        "</section>"
    )


def render_presentation_notice_html(notices: list[str]) -> str:
    """Render the presentation-mode bottom notice list."""

    items = "".join(f"<li>{escape_html(notice)}</li>" for notice in notices)
    return f'<section class="fpt-presentation-notice"><ul>{items}</ul></section>'


def build_judge_flow_view_model(
    *,
    customer_id: str,
    summary: Mapping[str, Any],
    demo_df: pd.DataFrame | None = None,
    analysis: Mapping[str, Any] | None = None,
    selected_metric: str = "savings_rate",
    language: str = "ko",
) -> dict[str, Any]:
    """Build display-only content for the five-section judge flow."""

    first_screen = build_first_screen_view_model(
        customer_id=customer_id,
        summary=summary,
        demo_df=demo_df,
        analysis=analysis,
        language=language,
    )
    outcome_summary = analysis.get("outcome_summary") if analysis else None
    matches = analysis.get("matches") if analysis else None
    breakpoint_result = analysis.get("breakpoint_result") if analysis else None
    whatif_results = analysis.get("whatif_results") if analysis else None
    return {
        "section_titles": [
            get_section_copy("current", language)["title"],
            get_section_copy("peers", language)["title"],
            get_section_copy("breakpoint", language)["title"],
            get_section_copy("whatif", language)["title"],
            get_section_copy("usage", language)["title"],
        ],
        "customer_identity": first_screen["customer_identity"],
        "kpi_cards": first_screen["kpi_cards"],
        "status_sentence": first_screen["status_sentence"],
        "similarity_cards": build_similarity_summary_cards(
            matches,
            outcome_summary=outcome_summary,
            selected_metric=selected_metric,
            language=language,
        ),
        "outcome_sentence": build_outcome_risk_sentence(outcome_summary, language=language),
        "breakpoint_cards": build_breakpoint_summary_cards(breakpoint_result, language=language),
        "whatif_card": build_best_whatif_card(whatif_results, language=language),
        "brief_empty_message": build_brief_empty_message(language=language),
    }


def build_similarity_summary_cards(
    matches: Any,
    *,
    outcome_summary: Mapping[str, Any] | None = None,
    selected_metric: str = "savings_rate",
    language: str = "ko",
) -> list[dict[str, Any]]:
    """Build compact peer-group cards without exposing match internals."""

    matched_count = _outcome_matched_count(outcome_summary)
    average_similarity: float | None = None
    if isinstance(matches, pd.DataFrame):
        try:
            summary = build_match_summary(matches)
            matched_count = summary["matched_count"] if matched_count is None else matched_count
            average_similarity = summary["average_similarity"]
        except ValueError:
            average_similarity = None

    count_text = "-" if matched_count is None else _format_count(int(matched_count), language)
    similarity_text = "-" if average_similarity is None else f"{average_similarity:.3f}"
    return [
        {
            "title": t("customer.similar_count", language),
            "value": count_text,
            "detail": t("customer.analysis_period_value", language),
            "tone": "neutral",
        },
        {
            "title": t("table.similarity_score", language),
            "value": similarity_text,
            "detail": (
                "Closer to 1 means more similar"
                if language == "en"
                else "1에 가까울수록 현재 흐름이 유사"
            ),
            "tone": "neutral",
        },
        {
            "title": "Display Metric" if language == "en" else "표시 지표",
            "value": label_metric(selected_metric, language),
            "detail": "Future path chart metric" if language == "en" else "미래 궤적 그래프 기준",
            "tone": "neutral",
        },
    ]


def build_outcome_risk_sentence(outcome_summary: Mapping[str, Any] | None, language: str = "ko") -> str:
    """Summarize stress and delinquent outcomes in user-facing language."""

    if not outcome_summary:
        return t("ui.peers_empty", language)
    outcomes = outcome_summary.get("outcomes", {})
    matched_count = _outcome_matched_count(outcome_summary)
    if matched_count is None:
        matched_count = sum(int(values.get("count", 0)) for values in outcomes.values())
    risk_count = int(outcomes.get("stress", {}).get("count", 0)) + int(
        outcomes.get("delinquent", {}).get("count", 0)
    )
    risk_ratio = calculate_risk_group_ratio(dict(outcome_summary))
    return (
        f"Among {_format_count(int(matched_count), language)}, {_format_count(risk_count, language)} "
        f"({format_percent(risk_ratio)}) moved into a financial stress or delinquency path."
        if language == "en"
        else f"유사 고객 {int(matched_count):,}명 중 {risk_count:,}명"
        f"({format_percent(risk_ratio)})이 재무 스트레스 또는 연체 경로로 이동했습니다."
    )


def build_breakpoint_summary_cards(
    breakpoint_result: Mapping[str, Any] | None,
    language: str = "ko",
) -> list[dict[str, Any]]:
    """Build breakpoint summary cards while keeping SMD details out of the default view."""

    if not breakpoint_result:
        return [
            {
                "title": t("card.breakpoint_short", language),
                "value": t("kpi.before_analysis", language),
                "detail": t("kpi.breakpoint.after_analysis", language),
                "tone": "neutral",
            }
        ]

    display = build_breakpoint_display_data(dict(breakpoint_result), language=language)
    status = display["status"]
    if status == "found":
        primary_factor = str(display["primary_factor"])
        return [
            {
                "title": t("card.breakpoint_short", language),
                "value": display["breakpoint_month"],
                "detail": "First clear divergence point" if language == "en" else "처음 차이가 뚜렷해진 시점",
                "tone": "neutral",
            },
            {
                "title": t("kpi.breakpoint.description", language),
                "value": t("kpi.breakpoint.historical_value", language),
                "detail": t("kpi.breakpoint.historical_detail", language),
                "tone": "neutral",
            },
            {
                "title": "Key Difference Metric" if language == "en" else "주요 차이 지표",
                "value": label_metric(primary_factor, language),
                "detail": (
                    "Largest group-average difference"
                    if language == "en"
                    else "두 집단 평균이 가장 크게 갈라진 지표"
                ),
                "tone": "watch",
            },
            {
                "title": t("chart.risk_path_mean", language),
                "value": format_breakpoint_metric_value(display["risk_group_mean"], primary_factor, language),
                "detail": "At the turning-point month" if language == "en" else "분기점 월 기준",
                "tone": "danger",
            },
            {
                "title": t("chart.avoidance_path_mean", language),
                "value": format_breakpoint_metric_value(display["avoidance_group_mean"], primary_factor, language),
                "detail": "At the turning-point month" if language == "en" else "분기점 월 기준",
                "tone": "stable",
            },
        ]

    if status == "insufficient_group_size":
        return [
            {
                "title": t("card.breakpoint_short", language),
                "value": t("kpi.analysis_limited", language),
                "detail": t("kpi.compare_customer_shortage", language),
                "tone": "neutral",
            },
            {
                "title": "Interpretation" if language == "en" else "화면 해석",
                "value": "Comparison Limited" if language == "en" else "비교 제한",
                "detail": (
                    "The comparison groups are smaller than the threshold."
                    if language == "en"
                    else "비교 가능한 집단 크기가 기준보다 작습니다."
                ),
                "tone": "neutral",
            },
        ]
    if status == "error":
        return [
            {
                "title": t("card.breakpoint_short", language),
                "value": t("kpi.display_limited", language),
                "detail": (
                    "Rerun the pipeline and check again."
                    if language == "en"
                    else "파이프라인 재실행 후 확인해 주세요."
                ),
                "tone": "neutral",
            }
        ]
    return [
        {
            "title": t("card.breakpoint_short", language),
            "value": t("kpi.not_found", language),
            "detail": t("kpi.no_clear_turning_point", language),
            "tone": "neutral",
        }
    ]


def build_best_whatif_card(whatif_results: Mapping[str, Any] | None, language: str = "ko") -> dict[str, Any]:
    """Return the most effective response option for the default screen."""

    if not whatif_results:
        return {
            "title": "Most Effective Action" if language == "en" else "가장 효과적인 대응안",
            "value": "No Results" if language == "en" else "비교 결과 없음",
            "detail": t("ui.whatif_no_results", language),
            "secondary": "-",
            "tone": "neutral",
        }
    best = best_whatif_scenario(dict(whatif_results))
    if best is None:
        return {
            "title": "Most Effective Action" if language == "en" else "가장 효과적인 대응안",
            "value": "No Comparable Action" if language == "en" else "비교 가능한 대응안 없음",
            "detail": (
                "Only no action is available, so improvement comparison is limited."
                if language == "en"
                else "아무 조치 없음만 표시되어 개선액 비교가 제한됩니다."
            ),
            "secondary": "-",
            "tone": "neutral",
        }
    improvement = best.get("improvement_vs_baseline")
    ending_balance = best.get("ending_cash_balance")
    return {
        "title": "Most Effective Action" if language == "en" else "가장 효과적인 대응안",
        "value": label_scenario(best.get("scenario_name"), language),
        "detail": (
            f"{format_currency(improvement, language=language)} improvement vs no action"
            if language == "en"
            else f"기준 대비 {format_krw_compact(improvement)} 개선"
        ),
        "secondary": (
            f"24-month ending balance {format_currency(ending_balance, language=language)}"
            if language == "en"
            else f"24개월 후 잔액 {format_krw_compact(ending_balance)}"
        ),
        "tone": "stable" if (_safe_float(improvement) or 0.0) > 0 else "neutral",
    }


def build_brief_empty_message(language: str = "ko") -> str:
    """Return a friendly placeholder when briefing text is not available yet."""

    return t("brief.empty", language)


def render_info_cards_html(cards: list[Mapping[str, Any]], aria_label: str = "요약 카드") -> str:
    """Render compact summary cards with escaped user-facing values."""

    rendered_cards = []
    for card in cards:
        tone = escape_html(card.get("tone", "neutral"))
        secondary = card.get("secondary")
        secondary_html = (
            f'<div class="fpt-info-card-secondary">{escape_html(secondary)}</div>' if secondary else ""
        )
        rendered_cards.append(
            f'<article class="fpt-info-card tone-{tone}">'
            f'<div class="fpt-info-card-title">{escape_html(card.get("title", ""))}</div>'
            f'<div class="fpt-info-card-value">{escape_html(card.get("value", ""))}</div>'
            f'<div class="fpt-info-card-detail">{escape_html(card.get("detail", ""))}</div>'
            f"{secondary_html}"
            "</article>"
        )
    return (
        f'<section class="fpt-info-card-grid" aria-label="{escape_html(aria_label)}">'
        + "".join(rendered_cards)
        + "</section>"
    )


def render_brief_panel_html(title: str, body: str) -> str:
    """Render a briefing panel with escaped multiline text."""

    return (
        '<section class="fpt-brief-panel">'
        f'<h3>{escape_html(title)}</h3>'
        f'<p>{escape_html(body)}</p>'
        "</section>"
    )


def load_demo_customers(path: Path = settings.DEMO_CUSTOMERS_PATH) -> pd.DataFrame:
    """Load fixed demo customer selections."""

    if not path.exists():
        raise FileNotFoundError(f"Demo customer file not found: {path}")
    demo_df = pd.read_csv(path)
    missing_columns = [column for column in settings.DEMO_CUSTOMER_COLUMNS if column not in demo_df.columns]
    if missing_columns:
        raise ValueError(f"Missing demo customer columns: {missing_columns}")
    return demo_df.loc[:, settings.DEMO_CUSTOMER_COLUMNS].copy()


def load_main_demo_customer(path: Path = settings.MAIN_DEMO_CUSTOMER_PATH) -> dict[str, Any]:
    """Load the saved main demo customer JSON."""

    if not path.exists():
        raise FileNotFoundError(f"Main demo customer file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def fit_matcher(features_df: pd.DataFrame) -> TrajectoryMatcher:
    """Fit and return the trajectory matcher for cached UI use."""

    return TrajectoryMatcher().fit(features_df)


def build_demo_options(demo_df: pd.DataFrame, language: str = "ko") -> list[dict[str, str]]:
    """Return sidebar options for fixed demo customers."""

    if demo_df.empty:
        return []
    options: list[dict[str, str]] = []
    for _, row in demo_df.iterrows():
        role = str(row["demo_role"])
        customer_id = str(row["customer_id"])
        role_label = _demo_role_label(role, language)
        options.append(
            {
                "label": f"{role_label} ({customer_id})",
                "role": role,
                "customer_id": customer_id,
            }
        )
    return options


def build_customer_summary(monthly_df: pd.DataFrame, customer_id: str) -> dict[str, Any]:
    """Build current metric cards for one customer using months 10..12 and month 12."""

    required_columns = (
        "customer_id",
        "month",
        "savings_rate",
        "dsr",
        "fixed_expense_ratio",
        "cash_balance",
        "monthly_status",
    )
    _validate_columns(monthly_df, required_columns, "monthly_df")
    customer_df = monthly_df[monthly_df["customer_id"].astype(str) == str(customer_id)].copy()
    if customer_df.empty:
        raise ValueError(f"Unknown customer_id: {customer_id}")

    recent_df = customer_df[customer_df["month"].between(10, settings.OBSERVATION_END_MONTH)]
    month_12 = customer_df[customer_df["month"] == settings.OBSERVATION_END_MONTH]
    if len(recent_df) != 3 or month_12.empty:
        raise ValueError(f"Customer {customer_id} must have months 10, 11, and 12.")

    latest = month_12.iloc[0]
    return {
        "customer_id": str(customer_id),
        "recent_savings_rate": float(recent_df["savings_rate"].mean()),
        "recent_dsr": float(recent_df["dsr"].mean()),
        "recent_fixed_expense_ratio": float(recent_df["fixed_expense_ratio"].mean()),
        "current_cash_balance": float(latest["cash_balance"]),
        "current_status": str(latest["monthly_status"]),
    }


def build_outcome_table(outcome_summary: dict[str, Any], language: str = "ko") -> pd.DataFrame:
    """Build a fixed-order matched outcome table."""

    outcomes = outcome_summary.get("outcomes", {})
    rows = []
    for outcome in settings.FINAL_OUTCOMES:
        values = outcomes.get(outcome, {"count": 0, "ratio": 0.0})
        rows.append(
            {
                t("table.result", language): label_status(outcome, language),
                t("table.count", language): int(values.get("count", 0)),
                t("table.ratio", language): format_percent(values.get("ratio", 0.0)),
            }
        )
    return pd.DataFrame(rows)


def build_match_summary(matches: pd.DataFrame) -> dict[str, Any]:
    """Build compact display metrics for a match result table."""

    _validate_columns(matches, ("matched_customer_id", "similarity_score"), "matches")
    if matches.empty:
        return {"matched_count": 0, "average_similarity": 0.0}
    return {
        "matched_count": int(len(matches)),
        "average_similarity": float(matches["similarity_score"].mean()),
    }


def build_match_display_table(matches: pd.DataFrame, language: str = "ko") -> pd.DataFrame:
    """Build a display-only top-match table with Korean labels."""

    if matches.empty:
        return matches.copy()
    display_df = matches.copy()
    if "matched_final_outcome" in display_df.columns:
        display_df["matched_final_outcome"] = display_df["matched_final_outcome"].map(
            lambda value: label_status(value, language)
        )
    if "matched_persona" in display_df.columns:
        display_df["matched_persona"] = display_df["matched_persona"].map(
            lambda value: label_persona(value, language)
        )
    column_labels = {
        "target_customer_id": t("table.target_customer_id", language),
        "matched_customer_id": t("table.matched_customer_id", language),
        "rank": t("table.rank", language),
        "distance": t("table.distance", language),
        "similarity_score": t("table.similarity_score", language),
        "matched_final_outcome": t("table.matched_final_outcome", language),
        "matched_persona": t("table.matched_persona", language),
    }
    ordered_columns = [column for column in column_labels if column in display_df.columns]
    display_df = display_df.loc[:, ordered_columns].rename(columns=column_labels)
    distance_col = column_labels["distance"]
    similarity_col = column_labels["similarity_score"]
    if distance_col in display_df.columns:
        display_df[distance_col] = display_df[distance_col].map(lambda value: round(float(value), 3))
    if similarity_col in display_df.columns:
        display_df[similarity_col] = display_df[similarity_col].map(lambda value: round(float(value), 3))
    return display_df


def calculate_risk_group_ratio(outcome_summary: dict[str, Any]) -> float:
    """Return stress + delinquent ratio from an outcome summary."""

    outcomes = outcome_summary.get("outcomes", {})
    return float(outcomes.get("stress", {}).get("ratio", 0.0)) + float(
        outcomes.get("delinquent", {}).get("ratio", 0.0)
    )


def build_whatif_comparison_table(whatif_results: dict[str, Any], language: str = "ko") -> pd.DataFrame:
    """Build a display table for response-scenario cash-flow results."""

    scenarios = whatif_results.get("scenarios", [])
    columns = _whatif_table_columns(language)
    amount_converter = to_million_krw if language == "en" else to_ten_thousand_won
    rows = []
    for scenario in scenarios:
        scenario_name = str(scenario["scenario_name"])
        cash_depletion_month = scenario["cash_depletion_month"]
        rows.append(
            {
                columns[0]: label_scenario(scenario_name, language),
                columns[1]: amount_converter(scenario["ending_cash_balance"]),
                columns[2]: amount_converter(scenario["minimum_cash_balance"]),
                columns[3]: format_percent(scenario["average_savings_rate"]),
                columns[4]: cash_depletion_label(cash_depletion_month, language),
                columns[5]: amount_converter(scenario["improvement_vs_baseline"]),
            }
        )
    return pd.DataFrame(rows)


def build_breakpoint_display_data(breakpoint_result: dict[str, Any], language: str = "ko") -> dict[str, Any]:
    """Normalize breakpoint result fields for UI display."""

    status = str(breakpoint_result.get("status", "not_found"))
    if status == "found":
        return {
            "status": status,
            "message": (
                "This is the first sustained group difference observed in the historical similar-path cohort, not a future date for the current customer."
                if language == "en"
                else "유사 과거 경로 집단에서 지속적인 차이가 처음 관찰된 시점이며, 현재 고객의 미래 시점이 아닙니다."
            ),
            "breakpoint_month": format_month_label(int(breakpoint_result["breakpoint_month"]), language=language),
            "months_from_current": _duration_month_text(breakpoint_result["months_from_current"], language),
            "primary_factor": breakpoint_result.get("primary_factor"),
            "risk_group_mean": breakpoint_result.get("risk_group_mean"),
            "avoidance_group_mean": breakpoint_result.get("avoidance_group_mean"),
            "standardized_difference": breakpoint_result.get("standardized_difference"),
        }
    if status == "insufficient_group_size":
        message = t("breakpoint.insufficient_group_size", language)
    elif status == "error":
        message = t("breakpoint.result_display_error", language)
    else:
        message = t("breakpoint.not_found", language)
    return {
        "status": status,
        "message": message,
        "breakpoint_month": None,
        "months_from_current": None,
        "primary_factor": None,
        "risk_group_mean": None,
        "avoidance_group_mean": None,
        "standardized_difference": None,
    }


def add_balance_ratios(monthly_df: pd.DataFrame, customer_ids: list[str]) -> pd.DataFrame:
    """Filter customers and add balance-to-recent-income ratios for display charts."""

    _validate_columns(monthly_df, ("customer_id", "month", "income", "cash_balance", "loan_balance"), "monthly_df")
    filtered_df = monthly_df[monthly_df["customer_id"].astype(str).isin(set(customer_ids))].copy()
    baseline_income = (
        filtered_df[filtered_df["month"].between(10, settings.OBSERVATION_END_MONTH)]
        .groupby("customer_id")["income"]
        .mean()
    )
    denominator = filtered_df["customer_id"].map(baseline_income).fillna(1).clip(lower=1)
    filtered_df["cash_balance_ratio"] = filtered_df["cash_balance"] / denominator
    filtered_df["loan_balance_ratio"] = filtered_df["loan_balance"] / denominator
    return filtered_df


def build_breakpoint_comparison(matched_ids: list[str], monthly_df: pd.DataFrame) -> pd.DataFrame:
    """Build monthly SMD comparison rows for matched risk and avoidance groups."""

    enriched_df = prepare_breakpoint_data(matched_ids, monthly_df)
    customer_outcomes = (
        enriched_df[["customer_id", "final_outcome"]]
        .drop_duplicates("customer_id")
        .set_index("customer_id")["final_outcome"]
    )
    risk_ids = customer_outcomes[customer_outcomes.isin(RISK_OUTCOMES)].index.tolist()
    avoidance_ids = customer_outcomes[customer_outcomes.isin(AVOIDANCE_OUTCOMES)].index.tolist()
    future_df = enriched_df[
        enriched_df["month"].between(settings.FUTURE_START_MONTH, settings.FUTURE_END_MONTH)
    ]
    return calculate_monthly_smd(future_df, risk_ids, avoidance_ids)


def run_customer_analysis(
    customer_id: str,
    monthly_df: pd.DataFrame,
    features_df: pd.DataFrame,
    matcher: TrajectoryMatcher,
    top_k: int = settings.TOP_K_MATCHES,
) -> dict[str, Any]:
    """Run matching, outcome summary, breakpoint, and What-if for one customer."""

    if str(customer_id) not in set(features_df["customer_id"].astype(str)):
        raise ValueError(f"Unknown customer_id: {customer_id}")

    matches = matcher.match(str(customer_id), top_k=top_k)
    matched_ids = matches["matched_customer_id"].astype(str).tolist()
    outcome_lookup = build_final_outcome_lookup(monthly_df)
    outcome_summary = summarize_matched_outcomes(str(customer_id), matched_ids, monthly_df, outcome_lookup)
    errors: dict[str, str] = {}
    try:
        breakpoint_result = find_breakpoint(matched_ids, monthly_df)
    except Exception as exc:  # noqa: BLE001
        errors["breakpoint"] = str(exc)
        breakpoint_result = _error_breakpoint_result(str(exc))
    try:
        comparison_df = build_breakpoint_comparison(matched_ids, monthly_df)
    except Exception as exc:  # noqa: BLE001
        errors["breakpoint_comparison"] = str(exc)
        comparison_df = pd.DataFrame()
    try:
        whatif_results = build_whatif_results(str(customer_id), monthly_df)
    except Exception as exc:  # noqa: BLE001
        errors["whatif"] = str(exc)
        whatif_results = {"target_customer_id": str(customer_id), "simulation_months": 0, "scenarios": []}

    return {
        "customer_id": str(customer_id),
        "matches": matches,
        "matched_ids": matched_ids,
        "outcome_summary": outcome_summary,
        "breakpoint_result": breakpoint_result,
        "whatif_results": whatif_results,
        "breakpoint_comparison": comparison_df,
        "errors": errors,
    }


def best_whatif_scenario(whatif_results: dict[str, Any]) -> dict[str, Any] | None:
    """Return the non-baseline scenario with the largest cash-balance improvement."""

    candidates = [
        scenario
        for scenario in whatif_results.get("scenarios", [])
        if scenario.get("scenario_name") != "baseline"
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda scenario: float(scenario.get("improvement_vs_baseline", 0.0)))


def build_missing_data_guidance(missing_files: list[Path], language: str = "ko") -> str:
    """Return a command guide for missing project data files."""

    if language == "en":
        return "Analysis data has not been generated yet. Run python scripts/run_pipeline.py and restart the application."
    return "분석 데이터가 아직 생성되지 않았습니다. python scripts/run_pipeline.py를 실행한 뒤 앱을 다시 시작해 주세요."


def format_money(value: Any, language: str = "ko") -> str:
    """Format a KRW amount for display."""

    return format_currency(value, language=language)


def format_ratio(value: Any) -> str:
    """Format a ratio stored as 0..1 for display."""

    return format_percent(value)


def format_breakpoint_metric_value(value: Any, metric: str, language: str = "ko") -> str:
    """Format a breakpoint group mean using the factor's display unit."""

    return format_metric_value(value, metric, language=language)


def display_metric_label(metric: Any, language: str = "ko") -> str:
    """Return a safe Korean label for a metric key."""

    return label_metric(metric, language)


def _format_count(count: int, language: str = "ko") -> str:
    if language == "en":
        noun = "customer" if int(count) == 1 else "customers"
        return f"{int(count):,} {noun}"
    return f"{int(count):,}명"


def _month_number_text(month: int, language: str = "ko") -> str:
    if language == "en":
        return f"Month {int(month)}"
    return f"{int(month)}개월 차"


def _duration_month_text(months: Any, language: str = "ko") -> str:
    value = _to_int_or_none(months)
    if value is None:
        return "-"
    absolute = abs(value)
    if language == "en":
        unit = "month" if absolute == 1 else "months"
        return f"{absolute} {unit}"
    return f"{absolute}개월"


def _demo_role_label(role: str, language: str = "ko", *, short: bool = False) -> str:
    suffix = "_short" if short else ""
    return t(f"demo_role.{role}{suffix}", language)


def _whatif_table_columns(language: str = "ko") -> tuple[str, str, str, str, str, str]:
    if language == "ko":
        return WHATIF_TABLE_COLUMNS
    return (
        t("table.action", language),
        t("table.ending_balance", language),
        t("table.minimum_balance", language),
        t("table.average_savings_rate", language),
        t("table.cash_depletion_month", language),
        t("table.improvement", language),
    )


def _validate_columns(df: pd.DataFrame, required_columns: tuple[str, ...], context: str) -> None:
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns in {context}: {missing_columns}")


def _outcome_matched_count(outcome_summary: Mapping[str, Any] | None) -> int | None:
    if not outcome_summary:
        return None
    value = outcome_summary.get("matched_count")
    if value is not None:
        return int(value)
    outcomes = outcome_summary.get("outcomes", {})
    if not outcomes:
        return None
    return sum(int(values.get("count", 0)) for values in outcomes.values())


def _design_token_css() -> str:
    lines = [":root {"]
    for key, value in DESIGN_TOKENS.items():
        css_key = key.replace("_", "-")
        lines.append(f"  --fpt-{css_key}: {value};")
    lines.append("}")
    return "\n".join(lines)


def _resolve_matched_count(
    customer_id: str,
    demo_df: pd.DataFrame | None,
    analysis: Mapping[str, Any] | None,
    default_count: int,
) -> int:
    outcome_summary = analysis.get("outcome_summary", {}) if analysis else {}
    if outcome_summary.get("matched_count") is not None:
        return int(outcome_summary["matched_count"])
    row = _demo_row_for_customer(customer_id, demo_df)
    if row and _has_value(row.get("matched_count")):
        return int(row["matched_count"])
    return int(default_count)


def _resolve_breakpoint_result(
    customer_id: str,
    demo_df: pd.DataFrame | None,
    analysis: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if analysis and isinstance(analysis.get("breakpoint_result"), Mapping):
        return dict(analysis["breakpoint_result"])
    row = _demo_row_for_customer(customer_id, demo_df)
    if not row or not _has_value(row.get("breakpoint_status")):
        return None
    return {
        "status": str(row.get("breakpoint_status")),
        "breakpoint_month": _to_int_or_none(row.get("breakpoint_month")),
        "months_from_current": _to_int_or_none(row.get("months_from_current")),
        "primary_factor": None if not _has_value(row.get("primary_factor")) else str(row.get("primary_factor")),
    }


def _demo_role_for_customer(customer_id: str, demo_df: pd.DataFrame | None) -> str | None:
    row = _demo_row_for_customer(customer_id, demo_df)
    if not row or not _has_value(row.get("demo_role")):
        return None
    return str(row["demo_role"])


def _demo_row_for_customer(customer_id: str, demo_df: pd.DataFrame | None) -> dict[str, Any] | None:
    if demo_df is None or demo_df.empty or "customer_id" not in demo_df.columns:
        return None
    matches = demo_df[demo_df["customer_id"].astype(str) == str(customer_id)]
    if matches.empty:
        return None
    return matches.iloc[0].to_dict()


def _breakpoint_kpi_card(breakpoint_result: Mapping[str, Any] | None, language: str = "ko") -> dict[str, Any]:
    if breakpoint_result is None:
        return {
            "id": "breakpoint",
            "title": t("kpi.breakpoint", language),
            "value": t("kpi.before_analysis", language),
            "unit": "",
            "description": t("kpi.breakpoint.after_analysis", language),
            "detail": t("kpi.breakpoint.detail", language),
            "tone": "neutral",
            "badge": None,
            "help": term_help_text("breakpoint", language),
        }

    status = str(breakpoint_result.get("status", "not_found"))
    if status == "found":
        breakpoint_month = _to_int_or_none(breakpoint_result.get("breakpoint_month"))
        primary_factor = label_metric(breakpoint_result.get("primary_factor"), language)
        return {
            "id": "breakpoint",
            "title": t("kpi.breakpoint", language),
            "value": t("kpi.breakpoint.historical_value", language),
            "unit": "" if breakpoint_month is None else _month_number_text(breakpoint_month, language),
            "description": t("kpi.breakpoint.description", language),
            "detail": (
                f"{t('kpi.breakpoint.primary_factor', language, metric=primary_factor)} · "
                f"{t('kpi.breakpoint.historical_detail', language)}"
            ),
            "tone": "neutral",
            "badge": {"label": t("kpi.breakpoint.found", language), "tone": "neutral"},
            "help": term_help_text("breakpoint", language),
        }
    if status == "insufficient_group_size":
        return {
            "id": "breakpoint",
            "title": t("kpi.breakpoint", language),
            "value": t("kpi.analysis_limited", language),
            "unit": "",
            "description": t("kpi.breakpoint.comparison", language),
            "detail": t("kpi.compare_customer_shortage", language),
            "tone": "neutral",
            "badge": None,
            "help": term_help_text("breakpoint", language),
        }
    if status == "error":
        return {
            "id": "breakpoint",
            "title": t("kpi.breakpoint", language),
            "value": t("kpi.display_limited", language),
            "unit": "",
            "description": t("kpi.breakpoint.comparison", language),
            "detail": t("kpi.pipeline_check_needed", language),
            "tone": "neutral",
            "badge": None,
            "help": term_help_text("breakpoint", language),
        }
    return {
        "id": "breakpoint",
        "title": t("kpi.breakpoint", language),
        "value": t("kpi.not_found", language),
        "unit": "",
        "description": t("kpi.breakpoint.comparison", language),
        "detail": t("kpi.no_clear_turning_point", language),
        "tone": "neutral",
        "badge": None,
        "help": term_help_text("breakpoint", language),
    }


def _cash_balance_note(value: Any, language: str = "ko") -> str:
    number = _safe_float(value)
    if number is None:
        return "-"
    if number < 0:
        return t("kpi.cash_negative", language)
    return t("kpi.cash_neutral", language)


def _savings_rate_note(value: Any, language: str = "ko") -> str:
    number = _safe_float(value)
    if number is None:
        return "-"
    if number < 0.05:
        return t("kpi.savings_watch", language)
    return t("kpi.savings_neutral", language)


def _dsr_note(value: Any, language: str = "ko") -> str:
    number = _safe_float(value)
    if number is None:
        return "-"
    if number >= 0.45:
        return t("kpi.dsr_danger", language)
    if number >= 0.35:
        return t("kpi.dsr_watch", language)
    return t("kpi.dsr_stable", language)


def _fixed_expense_ratio_note(value: Any, language: str = "ko") -> str:
    number = _safe_float(value)
    if number is None:
        return "-"
    if number >= 0.55:
        return t("kpi.fixed_danger", language)
    if number >= 0.45:
        return t("kpi.fixed_watch", language)
    return t("kpi.fixed_neutral", language)


def _kpi_tone_badge(tone: str, language: str = "ko") -> dict[str, str] | None:
    labels = {
        "stable": t("kpi.tone.stable", language),
        "watch": t("kpi.tone.watch", language),
        "danger": t("kpi.tone.danger", language),
    }
    if tone not in labels:
        return None
    return {"label": labels[tone], "tone": tone}


def _relative_month_text(months_from_current: Any, language: str = "ko") -> str:
    months = _to_int_or_none(months_from_current)
    if months is None:
        return "-"
    if months == 0:
        return t("kpi.current", language)
    if months > 0:
        return t("kpi.in_months", language, months=months)
    return t("kpi.months_ago", language, months=abs(months))


def _historical_breakpoint_sentence(breakpoint_month: Any, language: str = "ko") -> str:
    """Describe a peer-cohort landmark without implying a customer forecast date."""

    month = _to_int_or_none(breakpoint_month)
    if language == "en":
        if month is None:
            return "No historical landmark is available for the similar-customer group."
        return (
            f"In the historical similar-path cohort, a sustained difference was observed at Month {month}; "
            "this is not a future date for the current customer."
        )
    if month is None:
        return "유사 고객 집단의 위험 분기점 시점은 확인되지 않았으며,"
    return (
        f"유사 과거 경로 집단에서 {month}개월 차에 지속적인 차이가 관찰되었으며, "
        "이는 현재 고객의 미래 시점이 아닙니다."
    )


def _to_int_or_none(value: Any) -> int | None:
    number = _safe_float(value)
    if number is None:
        return None
    return int(number)


def _safe_float(value: Any) -> float | None:
    if not _has_value(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _has_value(value: Any) -> bool:
    if value is None or value == "":
        return False
    try:
        return not bool(pd.isna(value))
    except (TypeError, ValueError):
        return True


def _error_breakpoint_result(message: str) -> dict[str, Any]:
    return {
        "status": "error",
        "breakpoint_month": None,
        "months_from_current": None,
        "primary_factor": None,
        "risk_group_mean": None,
        "avoidance_group_mean": None,
        "standardized_difference": None,
        "persistence_months": 0,
        "secondary_factors": [],
        "interpretation": message,
    }
