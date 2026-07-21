"""Tests for deterministic template advisor explanations."""

from __future__ import annotations

import re

from src.advisor import build_brief_with_fallback, build_customer_brief, build_staff_brief


def _sentence_count(text: str) -> int:
    return len(re.findall(r"(?<!\d)\.(?!\d)", text))


FORBIDDEN_PHRASES = (
    "확실히",
    "반드시",
    "정확한 확률",
    "연체하게 됩니다",
    "가입해야 합니다",
    "위험이 사라집니다",
    "미래가 이렇게 됩니다",
    "100% 안전합니다",
    "원인으로 증명되었습니다",
    "고객은 곧 연체합니다",
    "예측 확률",
    "SMD",
)


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


def _outcome_summary() -> dict:
    return {
        "matched_count": 200,
        "outcomes": {
            "healthy": {"count": 100, "ratio": 0.50},
            "recovered": {"count": 38, "ratio": 0.19},
            "stress": {"count": 50, "ratio": 0.25},
            "delinquent": {"count": 12, "ratio": 0.06},
        },
    }


def _breakpoint(status: str = "found") -> dict:
    if status == "found":
        return {
            "status": "found",
            "breakpoint_month": 14,
            "months_from_current": 2,
            "primary_factor": "fixed_expense_ratio",
            "risk_group_mean": 0.4712,
            "avoidance_group_mean": 0.3612,
            "standardized_difference": 0.7249,
        }
    return {
        "status": status,
        "breakpoint_month": None,
        "months_from_current": None,
        "primary_factor": None,
        "risk_group_mean": None,
        "avoidance_group_mean": None,
        "standardized_difference": None,
    }


def _whatif_results(cash_depletion_month: int | None = None, minimum_cash_balance: float = 7_500_000) -> dict:
    return {
        "scenarios": [
            {
                "scenario_name": "baseline",
                "ending_cash_balance": 20_000_000,
                "minimum_cash_balance": 5_000_000,
                "average_savings_rate": 0.10,
                "cash_depletion_month": None,
                "improvement_vs_baseline": 0,
            },
            {
                "scenario_name": "variable_expense_cut_15",
                "ending_cash_balance": 29_000_000,
                "minimum_cash_balance": minimum_cash_balance,
                "average_savings_rate": 0.18,
                "cash_depletion_month": cash_depletion_month,
                "improvement_vs_baseline": 9_000_000,
            },
            {
                "scenario_name": "fixed_expense_cut_300k",
                "ending_cash_balance": 25_000_000,
                "minimum_cash_balance": 6_000_000,
                "average_savings_rate": 0.14,
                "cash_depletion_month": None,
                "improvement_vs_baseline": 5_000_000,
            },
        ]
    }


def test_customer_brief_reflects_input_numbers() -> None:
    brief = build_customer_brief(_current_metrics(), _outcome_summary(), _breakpoint(), _whatif_results())

    assert "200명" in brief
    assert "31.0%" in brief
    assert "14개월" in brief
    assert "약 2개월" in brief
    assert "900만원" in brief
    assert "1,235만원" in brief
    assert _sentence_count(brief) == 7


def test_customer_brief_does_not_create_unprovided_example_numbers() -> None:
    brief = build_customer_brief(_current_metrics(), _outcome_summary(), _breakpoint(), _whatif_results())

    assert "9,999,999원" not in brief
    assert "45.0%" not in brief
    assert "18개월" not in brief


def test_breakpoint_found_handling() -> None:
    brief = build_customer_brief(_current_metrics(), _outcome_summary(), _breakpoint("found"), _whatif_results())

    assert "fixed_expense_ratio" not in brief
    assert "고정지출 비중" in brief
    assert "위험 경로 고객 평균은 47.1%" in brief
    assert "위험 회피 고객 평균은 36.1%" in brief
    assert "SMD" not in brief


def test_breakpoint_not_found_handling() -> None:
    brief = build_customer_brief(_current_metrics(), _outcome_summary(), _breakpoint("not_found"), _whatif_results())

    assert "위험 경로와 회피 경로가 뚜렷하게 갈라지는 시점이 발견되지 않았습니다" in brief
    assert "남은 기간은 표시하지 않습니다" in brief


def test_insufficient_group_size_handling() -> None:
    staff = build_staff_brief(
        _current_metrics(),
        _outcome_summary(),
        _breakpoint("insufficient_group_size"),
        _whatif_results(),
    )

    assert "위험 경로 또는 위험 회피 고객 수가 충분하지 않습니다" in staff
    assert "분기점 기준 상담 시점은 표시하지 않습니다" in staff


def test_null_cash_depletion_month_handling() -> None:
    brief = build_customer_brief(_current_metrics(), _outcome_summary(), _breakpoint(), _whatif_results(None))

    assert "현금 고갈 시점은 발생하지 않음" in brief


def test_cash_depletion_month_handling() -> None:
    brief = build_customer_brief(_current_metrics(), _outcome_summary(), _breakpoint(), _whatif_results(4))

    assert "현금 고갈 시점은 4개월 후" in brief


def test_negative_balance_display() -> None:
    staff = build_staff_brief(
        _current_metrics(),
        _outcome_summary(),
        _breakpoint(),
        _whatif_results(minimum_cash_balance=-1_200_000),
    )

    assert "-120만원" in staff


def test_money_and_ratio_formatting() -> None:
    brief = build_customer_brief(_current_metrics(), _outcome_summary(), _breakpoint(), _whatif_results())

    assert "12.3%" in brief
    assert "34.6%" in brief
    assert "45.7%" in brief
    assert "2,900만원" in brief


def test_forbidden_phrases_are_not_included() -> None:
    customer = build_customer_brief(_current_metrics(), _outcome_summary(), _breakpoint(), _whatif_results())
    staff = build_staff_brief(_current_metrics(), _outcome_summary(), _breakpoint(), _whatif_results())
    combined = customer + staff

    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in combined


def test_brief_lengths_are_limited_for_default_screen() -> None:
    customer = build_customer_brief(_current_metrics(), _outcome_summary(), _breakpoint(), _whatif_results())
    staff = build_staff_brief(_current_metrics(), _outcome_summary(), _breakpoint(), _whatif_results())

    assert 5 <= _sentence_count(customer) <= 7
    assert 6 <= _sentence_count(staff) <= 9


def test_llm_failure_falls_back_to_template() -> None:
    def failing_llm(*args: object, **kwargs: object) -> str:
        raise TimeoutError("simulated timeout")

    brief = build_brief_with_fallback(
        "customer",
        _current_metrics(),
        _outcome_summary(),
        _breakpoint(),
        _whatif_results(),
        llm_builder=failing_llm,
    )

    assert "200" in brief
    assert "900만원" in brief
