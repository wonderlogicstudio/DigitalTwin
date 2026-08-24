"""Shared user-facing copy for the Streamlit dashboard.

This module contains display text only. It must not perform business
calculation or change persisted data values.
"""

from __future__ import annotations

from typing import Any

from src.i18n import t


TERM_LABELS = {
    "Trajectory Matching": "유사 재무 흐름 찾기",
    "Outcome Distribution": "유사 고객의 이후 결과",
    "Breakpoint": "위험 분기점",
    "Risk Group": "위험 경로 고객",
    "Avoidance Group": "위험 회피 고객",
    "What-if": "대응 시나리오",
    "Similarity Score": "재무 흐름 유사도",
    "Cash Depletion": "현금 고갈",
    "Baseline": "아무 조치 없음",
    "Current Trajectory": "현재 재무 흐름",
    "Future Trajectory": "유사 고객의 이후 흐름",
    "Financial Stress": "재무 스트레스",
}

TERM_EXPLANATIONS = {
    "dsr": "월소득 중 대출 원리금 상환에 사용하는 비율입니다.",
    "savings_rate": "월소득에서 모든 지출을 제외하고 남은 비율입니다.",
    "fixed_expense_ratio": "월소득 중 매월 반복적으로 지출되는 금액의 비율입니다.",
    "stress": "현금흐름과 부채 부담이 함께 악화된 상태를 의미합니다.",
    "outcome_ratio": "비슷한 재무 흐름을 보였던 고객 집단에서 실제로 나타난 결과의 비율입니다.",
    "breakpoint": "위험 경로 고객과 위험을 피한 고객의 재무 흐름이 처음으로 뚜렷하게 달라진 시점입니다.",
    "response_scenario": "현재 재무 조건에 특정 행동을 적용했을 때 현금흐름이 어떻게 달라지는지 계산한 결과입니다.",
}

SECTION_COPY = {
    "current": {
        "label": "1단계",
        "title": "현재 재무 흐름은 어떤가요?",
        "caption": "현재 상태와 최근 12개월 현금흐름을 먼저 확인합니다. 저축 여력과 대출상환 부담을 함께 봅니다.",
    },
    "peers": {
        "label": "2단계",
        "title": "비슷한 고객들은 이후 어떻게 되었나요?",
        "caption": "현재 고객과 비슷한 흐름을 보였던 고객들의 이후 범위와 결과 분포를 봅니다.",
    },
    "breakpoint": {
        "label": "3단계",
        "title": "위험 경로는 언제 갈라졌나요?",
        "caption": "위험 경로 고객과 위험 회피 고객의 흐름이 처음 달라진 시점을 확인합니다.",
    },
    "whatif": {
        "label": "4단계",
        "title": "지금 어떤 선택이 가장 효과적인가요?",
        "caption": "아무 조치 없음과 대응 시나리오를 비교해 현금흐름 개선 폭이 큰 선택을 봅니다.",
    },
    "usage": {
        "label": "5단계",
        "title": "이 결과를 상담에 어떻게 활용할 수 있나요?",
        "caption": "고객에게는 쉬운 설명을, 은행 직원에게는 상담 포인트를 분리해 제공합니다.",
    },
}

APP_MODE_OPTIONS = ("일반 모드", "발표 모드", "RM 업무 모드")

PRESENTATION_SCENE_COPY = {
    "current": {
        "label": "장면 1",
        "title": "현재 고객은 어떤 상태인가",
    },
    "peers": {
        "label": "장면 2",
        "title": "같은 길을 걸었던 고객들은 어떻게 되었는가",
    },
    "breakpoint": {
        "label": "장면 3",
        "title": "위험 경로는 언제 갈라졌는가",
    },
    "whatif": {
        "label": "장면 4",
        "title": "지금 무엇을 바꾸면 되는가",
    },
}

PRESENTATION_NOTICES = (
    "합성 데이터 기반 PoC입니다.",
    "실제 고객 신용평가가 아닙니다.",
    "미래를 확정적으로 예측하는 모델이 아닙니다.",
    "유사 고객 집단의 과거 결과와 규칙 기반 시뮬레이션을 결합한 결과입니다.",
)

BUTTON_LABELS = {
    "run_analysis": "유사 재무 흐름 찾기",
}

UI_MESSAGES = {
    "select_customer": "고객을 선택하거나 고객 ID를 입력해 주세요.",
    "summary_not_ready": "선택한 고객의 분석 결과를 찾을 수 없습니다. 다른 고객을 선택하거나 파이프라인을 다시 실행해 주세요.",
    "demo_list_missing": "데모 고객 목록을 찾지 못했습니다. 고객 ID를 직접 입력해 주세요.",
    "demo_list_unreadable": "데모 고객 목록을 읽지 못했습니다. 고객 ID 직접 입력으로 계속합니다.",
    "current_data_missing": "현재 고객의 월별 데이터가 없어 KPI 요약만 표시합니다.",
    "analysis_cta": "유사 재무 흐름 찾기를 실행하면 이후 결과, 위험 분기점, 대응 시나리오가 한 흐름으로 이어집니다.",
    "analysis_step_compare": "재무 흐름을 비교하고 있습니다.",
    "analysis_step_outcomes": "유사 고객의 이후 결과를 집계하고 있습니다.",
    "analysis_step_done": "위험 분기점과 대응 시나리오 비교를 준비했습니다.",
    "analysis_fallback": "실시간 분석 대신 준비된 메인 데모 결과를 표시합니다.",
    "analysis_failed": "선택한 고객의 분석 결과를 찾을 수 없습니다. 다른 고객을 선택하거나 파이프라인을 다시 실행해 주세요.",
    "peers_empty": "유사 재무 흐름 찾기를 실행하면 이 섹션에 이후 흐름과 결과 분포가 표시됩니다.",
    "breakpoint_empty": "유사 재무 흐름 찾기 후 위험 분기점 요약과 비교 그래프가 표시됩니다.",
    "whatif_empty": "유사 재무 흐름 찾기 후 대응 시나리오 비교표와 잔액 그래프가 표시됩니다.",
    "whatif_no_results": "표시할 대응 시나리오 결과가 없습니다.",
    "loan_scenario_notice": "대출상환액 감소 시나리오는 실제 승인 여부나 계약 변경 가능성을 반영하지 않은 현금흐름 가정입니다.",
    "chart_fallback": "차트를 표시하지 못해 요약 표로 대체합니다.",
    "chart_fallback_empty": "표시할 대체 데이터가 없습니다.",
    "poc_notice": "이 결과는 합성 데이터 기반 PoC이며, 공식 신용평가나 확정된 미래 판단으로 사용하지 않습니다.",
    "presentation_main_customer": "발표 모드는 메인 데모 고객을 자동으로 사용합니다.",
    "presentation_error": "발표 모드 데이터를 준비하지 못했습니다. python scripts/run_pipeline.py를 실행한 뒤 앱을 다시 시작해 주세요.",
}

BREAKPOINT_NOT_FOUND_MESSAGE = (
    "현재 유사 고객 집단에서는 위험 경로와 회피 경로가 뚜렷하게 갈라지는 시점이 발견되지 않았습니다."
)
BREAKPOINT_INSUFFICIENT_MESSAGE = (
    "위험 분기점을 비교하기에 위험 경로 또는 위험 회피 고객 수가 충분하지 않습니다."
)
CASH_DEPLETION_NONE = "발생하지 않음"

WHATIF_TABLE_COLUMNS = (
    "대응 방법",
    "24개월 후 잔액(만원)",
    "최소 잔액(만원)",
    "평균 저축률",
    "현금 고갈 시점",
    "기준 대비 개선액(만원)",
)

FORBIDDEN_PHRASES = (
    "확실히",
    "반드시",
    "정확한 확률",
    "연체하게 됩니다",
    "위험이 사라집니다",
    "이 상품에 가입해야 합니다",
    "미래가 이렇게 됩니다",
    "100% 안전합니다",
    "원인으로 증명되었습니다",
    "고객은 곧 연체합니다",
)

INTERNAL_SCREEN_TERMS = (
    "fixed_expense_ratio",
    "cash_balance_ratio",
    "variable_expense_cut_15",
    "fixed_expense_cut_300k",
    "debt_payment_cut_20",
    "Outcome Summary",
    "Breakpoint Analysis",
    "What-if Result",
    "Similarity Matching",
    "Trajectory Matching",
    "Feature Engineering",
    "SMD",
    "top_k",
    "random_seed",
)


def label_term(term: Any, language: str = "ko") -> str:
    """Return the plain Korean term for a UI concept."""

    if term is None or term == "":
        return "-"
    key = str(term)
    if language == "en":
        translation_keys = {
            "Trajectory Matching": "button.find_twins",
            "Outcome Distribution": "section.similar.title",
            "Breakpoint": "kpi.breakpoint",
            "Risk Group": "chart.risk_path",
            "Avoidance Group": "chart.avoidance_path",
            "What-if": "section.whatif.title",
            "Similarity Score": "table.similarity_score",
            "Cash Depletion": "chart.whatif.cash_depletion",
            "Baseline": "scenario.baseline",
            "Current Trajectory": "chart.current_customer",
            "Future Trajectory": "chart.future_period",
            "Financial Stress": "status.stress",
        }
        if key in translation_keys:
            return t(translation_keys[key], language)
    return TERM_LABELS.get(key, key)


def cash_depletion_label(month: Any, language: str = "ko") -> str:
    """Format a cash-depletion month for display tables and briefings."""

    if month is None or month == "":
        return t("cash_depletion.none", language)
    return t("cash_depletion.after", language, month=int(month))


def breakpoint_status_message(status: Any, language: str = "ko") -> str:
    """Return a friendly breakpoint empty-state message."""

    if status == "insufficient_group_size":
        return t("breakpoint.insufficient_group_size", language)
    if status == "not_found":
        return t("breakpoint.not_found", language)
    return t("breakpoint.display_error", language)


def find_forbidden_phrases(text: str) -> list[str]:
    """Return prohibited phrases included in user-facing copy."""

    return [phrase for phrase in FORBIDDEN_PHRASES if phrase in text]


def find_internal_screen_terms(text: str) -> list[str]:
    """Return internal terms that should not appear in default UI copy."""

    return [term for term in INTERNAL_SCREEN_TERMS if term in text]
