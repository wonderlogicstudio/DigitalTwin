"""Tests for Korean/English display internationalization."""

from __future__ import annotations

import json
from copy import deepcopy

import pandas as pd

from src.advisor import build_customer_brief, build_staff_brief
from src.formatters import (
    format_currency,
    format_month_label,
    format_percent,
    select_currency_unit,
)
from src.i18n import DEFAULT_LANGUAGE, get_supported_languages, t, validate_translation_keys
from src.labels import label_persona, label_scenario, label_status
from src.presentation import build_presentation_view_model
from src.visualizations import (
    build_income_expense_title,
    build_outcome_title,
    create_current_trajectory_chart,
    create_income_expense_chart,
    create_outcome_bar_chart,
)


FORBIDDEN_KO = (
    "확실히",
    "반드시",
    "정확한 확률",
    "연체하게 됩니다",
    "위험이 사라집니다",
    "미래가 이렇게 됩니다",
    "SMD",
)
FORBIDDEN_EN = (
    "The customer will become delinquent",
    "exact probability",
    "eliminates the risk",
    "must purchase",
    "future is certain",
    "caused the delinquency",
    "Guaranteed",
    "100% safe",
)


def _target_monthly() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "month": [10, 11, 12],
            "income": [4_000_000, 4_100_000, 4_200_000],
            "total_expense": [3_000_000, 3_300_000, 3_600_000],
            "cash_balance": [12_000_000, 12_500_000, 13_000_000],
            "savings_rate": [0.25, 0.195, 0.143],
            "dsr": [0.30, 0.34, 0.36],
            "monthly_status": ["healthy", "watch", "watch"],
        }
    )


def _outcome_summary() -> dict:
    return {
        "matched_count": 200,
        "outcomes": {
            "healthy": {"count": 87, "ratio": 0.435},
            "recovered": {"count": 41, "ratio": 0.205},
            "stress": {"count": 66, "ratio": 0.33},
            "delinquent": {"count": 6, "ratio": 0.03},
        },
    }


def _breakpoint() -> dict:
    return {
        "status": "found",
        "breakpoint_month": 13,
        "months_from_current": 1,
        "primary_factor": "cash_balance_ratio",
        "risk_group_mean": 3.43,
        "avoidance_group_mean": 5.49,
    }


def _whatif_results() -> dict:
    return {
        "scenarios": [
            {
                "scenario_name": "baseline",
                "ending_cash_balance": 50_000_000,
                "minimum_cash_balance": 30_000_000,
                "average_savings_rate": 0.12,
                "cash_depletion_month": None,
                "improvement_vs_baseline": 0,
            },
            {
                "scenario_name": "variable_expense_cut_15",
                "ending_cash_balance": 59_000_000,
                "minimum_cash_balance": 31_000_000,
                "average_savings_rate": 0.17,
                "cash_depletion_month": None,
                "improvement_vs_baseline": 9_000_000,
            },
        ]
    }


def _current_metrics() -> dict:
    return {
        "current_status": "watch",
        "recent_savings_rate": 0.1234,
        "recent_dsr": 0.3456,
        "recent_fixed_expense_ratio": 0.4567,
        "current_cash_balance": 12_345_678,
        "savings_rate_slope_6m": -0.0123,
        "balance_decline_run_6m": 3,
    }


def test_supported_languages_and_translation_fallbacks() -> None:
    assert DEFAULT_LANGUAGE == "ko"
    assert get_supported_languages() == {"ko": "한국어", "en": "English"}
    assert t("section.current.title", "ko") == "현재 재무 흐름은 어떤가요?"
    assert t("section.current.title", "en") == "What does the customer's current financial path look like?"
    assert t("section.current.title", "bad") == "현재 재무 흐름은 어떤가요?"
    assert t("missing.translation.key", "en") == "missing.translation.key"
    assert t("customer.main_id", "en", customer_id="C000001") == "Main customer: C000001"
    assert "{customer_id}" in t("customer.main_id", "en")
    assert validate_translation_keys() == []


def test_labels_translate_without_changing_unknown_fallbacks() -> None:
    assert label_status("stress", "ko") == "재무 스트레스"
    assert label_status("stress", "en") == "Financial Stress"
    assert label_persona("event_shock", "en") == "Event Shock"
    assert label_scenario("variable_expense_cut_15", "en") == "Reduce Variable Expenses by 15%"
    assert label_status("unknown_status", "en") == "unknown_status"


def test_currency_percent_and_month_formatting_by_language() -> None:
    assert format_currency(850_000, "ko") == "85만원"
    assert format_currency(850_000, "en") == "KRW 850K"
    assert format_currency(12_500_000, "en") == "KRW 12.5M"
    assert format_currency(123_000_000, "en") == "KRW 123.0M"
    assert format_currency(-3_500_000, "en") == "-KRW 3.5M"
    assert format_percent(1.234) == "123.4%"
    assert format_month_label(12, language="en") == "Current · Month 12"
    assert format_month_label(14, language="en") == "In 2 months · Month 14"
    assert format_month_label(10, language="en") == "2 months ago · Month 10"
    assert select_currency_unit([12_500_000], "ko") == "만원"
    assert select_currency_unit([12_500_000], "en") == "KRW million"


def test_chart_titles_axes_hover_and_json_are_language_aware() -> None:
    original = _target_monthly()
    before = original.copy(deep=True)

    ko_fig = create_current_trajectory_chart(original, "cash_balance", language="ko")
    en_fig = create_current_trajectory_chart(original, "cash_balance", language="en")
    income_fig = create_income_expense_chart(original, language="en")
    outcome_fig = create_outcome_bar_chart(_outcome_summary(), language="en")

    pd.testing.assert_frame_equal(original, before)
    assert "현금 잔액(만원)" == ko_fig.layout.yaxis.title.text
    assert "Cash Balance(KRW million)" == en_fig.layout.yaxis.title.text
    assert "Cash Balance" in en_fig.data[0].hovertemplate
    assert "cash_balance" not in en_fig.to_json()
    assert "Monthly Income" in income_fig.data[0].name
    assert "customers" in str(outcome_fig.data[0].text)
    json.loads(en_fig.to_json())
    assert build_income_expense_title(original, "en")
    assert build_outcome_title(_outcome_summary(), "en") == "Risk path 36.0% · 200 similar customers"


def test_briefings_translate_without_forbidden_phrases_or_number_changes() -> None:
    current = _current_metrics()
    outcome = _outcome_summary()
    breakpoint = _breakpoint()
    whatif = _whatif_results()
    before = deepcopy((current, outcome, breakpoint, whatif))

    ko_customer = build_customer_brief(current, outcome, breakpoint, whatif, language="ko")
    en_customer = build_customer_brief(current, outcome, breakpoint, whatif, language="en")
    en_staff = build_staff_brief(current, outcome, breakpoint, whatif, language="en")

    assert before == (current, outcome, breakpoint, whatif)
    assert "200명" in ko_customer
    assert "200 customers" in en_customer
    assert "36.0%" in ko_customer and "36.0%" in en_customer and "36.0%" in en_staff
    assert "KRW 9.0M" in en_customer
    for phrase in FORBIDDEN_KO:
        assert phrase not in ko_customer
    for phrase in FORBIDDEN_EN:
        assert phrase not in en_customer + en_staff


def test_presentation_view_model_translates_scenes_with_same_core_values() -> None:
    summary = _current_metrics()
    analysis = {
        "outcome_summary": _outcome_summary(),
        "breakpoint_result": _breakpoint(),
        "whatif_results": _whatif_results(),
    }
    ko = build_presentation_view_model(customer_id="C000001", summary=summary, analysis=analysis, source="test", language="ko")
    en = build_presentation_view_model(customer_id="C000001", summary=summary, analysis=analysis, source="test", language="en")

    assert ko["customer_id"] == en["customer_id"] == "C000001"
    assert "장면 1" == ko["scenes"][0]["label"]
    assert "Scene 1" == en["scenes"][0]["label"]
    assert "36.0%" in ko["scenes"][1]["message"]
    assert "36.0%" in en["scenes"][1]["message"]
    assert "13" in ko["scenes"][2]["message"]
    assert "13" in en["scenes"][2]["message"]
