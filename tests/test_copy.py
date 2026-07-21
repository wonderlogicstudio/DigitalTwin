"""Tests for shared user-facing copy."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.copy import (
    APP_MODE_OPTIONS,
    BREAKPOINT_INSUFFICIENT_MESSAGE,
    BREAKPOINT_NOT_FOUND_MESSAGE,
    BUTTON_LABELS,
    CASH_DEPLETION_NONE,
    FORBIDDEN_PHRASES,
    PRESENTATION_NOTICES,
    PRESENTATION_SCENE_COPY,
    SECTION_COPY,
    TERM_EXPLANATIONS,
    TERM_LABELS,
    UI_MESSAGES,
    WHATIF_TABLE_COLUMNS,
    breakpoint_status_message,
    cash_depletion_label,
    find_forbidden_phrases,
    find_internal_screen_terms,
    label_term,
)
from src.ui_components import build_missing_data_guidance


def _flatten_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        flattened: list[str] = []
        for item in value.values():
            flattened.extend(_flatten_values(item))
        return flattened
    if isinstance(value, (list, tuple)):
        flattened = []
        for item in value:
            flattened.extend(_flatten_values(item))
        return flattened
    return [str(value)]


def test_required_term_labels_are_korean() -> None:
    assert label_term("Trajectory Matching") == "유사 재무 흐름 찾기"
    assert label_term("Outcome Distribution") == "유사 고객의 이후 결과"
    assert label_term("Breakpoint") == "위험 분기점"
    assert label_term("Risk Group") == "위험 경로 고객"
    assert label_term("Avoidance Group") == "위험 회피 고객"
    assert label_term("What-if") == "대응 시나리오"
    assert label_term("Similarity Score") == "재무 흐름 유사도"
    assert label_term("Cash Depletion") == "현금 고갈"
    assert label_term("Baseline") == "아무 조치 없음"
    assert label_term("Financial Stress") == "재무 스트레스"
    assert label_term("unknown") == "unknown"


def test_term_explanations_are_short_and_plain() -> None:
    assert TERM_EXPLANATIONS["dsr"] == "월소득 중 대출 원리금 상환에 사용하는 비율입니다."
    assert TERM_EXPLANATIONS["savings_rate"] == "월소득에서 모든 지출을 제외하고 남은 비율입니다."
    assert "예측 확률" not in TERM_EXPLANATIONS["outcome_ratio"]


def test_breakpoint_empty_messages_are_friendly() -> None:
    assert breakpoint_status_message("not_found") == BREAKPOINT_NOT_FOUND_MESSAGE
    assert breakpoint_status_message("insufficient_group_size") == BREAKPOINT_INSUFFICIENT_MESSAGE
    assert "status" not in breakpoint_status_message("unexpected")


def test_cash_depletion_display_text() -> None:
    assert cash_depletion_label(None) == CASH_DEPLETION_NONE
    assert cash_depletion_label(4) == "4개월 후"


def test_whatif_table_columns_include_units() -> None:
    assert WHATIF_TABLE_COLUMNS == (
        "대응 방법",
        "24개월 후 잔액(만원)",
        "최소 잔액(만원)",
        "평균 저축률",
        "현금 고갈 시점",
        "기준 대비 개선액(만원)",
    )


def test_default_copy_has_no_forbidden_phrases_or_internal_terms() -> None:
    text = "\n".join(
        _flatten_values(SECTION_COPY)
        + _flatten_values(PRESENTATION_SCENE_COPY)
        + _flatten_values(APP_MODE_OPTIONS)
        + _flatten_values(PRESENTATION_NOTICES)
        + _flatten_values(BUTTON_LABELS)
        + _flatten_values(UI_MESSAGES)
        + _flatten_values(TERM_EXPLANATIONS)
        + _flatten_values(WHATIF_TABLE_COLUMNS)
        + [BREAKPOINT_NOT_FOUND_MESSAGE, BREAKPOINT_INSUFFICIENT_MESSAGE, CASH_DEPLETION_NONE]
        + list(TERM_LABELS.values())
    )

    assert find_forbidden_phrases(text) == []
    assert find_internal_screen_terms(text) == []


def test_forbidden_phrase_detector_finds_requested_phrases() -> None:
    assert "확실히" in find_forbidden_phrases("확실히 좋아집니다.")
    assert set(FORBIDDEN_PHRASES) >= {"반드시", "정확한 확률", "고객은 곧 연체합니다"}


def test_internal_term_detector_finds_variable_names() -> None:
    assert "fixed_expense_ratio" in find_internal_screen_terms("fixed_expense_ratio")


def test_error_guidance_includes_user_action_without_paths() -> None:
    guidance = build_missing_data_guidance([Path("data/raw/missing.csv")])

    assert "python scripts/run_pipeline.py" in guidance
    assert "missing.csv" not in guidance
