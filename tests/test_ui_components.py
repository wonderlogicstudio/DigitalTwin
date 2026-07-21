"""Tests for first-screen Streamlit display helpers."""

from __future__ import annotations

from copy import deepcopy

import pandas as pd

from config import settings
from src.theme import DESIGN_TOKENS
from src.ui_components import (
    build_best_whatif_card,
    build_breakpoint_summary_cards,
    build_brief_empty_message,
    build_customer_identity,
    build_current_status_sentence,
    build_first_screen_view_model,
    build_judge_flow_view_model,
    build_kpi_cards,
    build_missing_data_guidance,
    build_outcome_risk_sentence,
    build_status_badge,
    classify_kpi_tone,
    load_css,
    render_hero_html,
    render_customer_identity_html,
    render_info_cards_html,
    render_kpi_cards_html,
    render_status_summary_html,
)


def _summary() -> dict:
    return {
        "customer_id": "C000001",
        "current_status": "watch",
        "current_cash_balance": 850_000,
        "recent_savings_rate": 0.082,
        "recent_dsr": 0.38,
        "recent_fixed_expense_ratio": 0.46,
    }


def _breakpoint(status: str = "found") -> dict:
    if status == "found":
        return {
            "status": "found",
            "breakpoint_month": 14,
            "months_from_current": 2,
            "primary_factor": "fixed_expense_ratio",
        }
    return {"status": status}


def test_first_screen_kpi_data_generation() -> None:
    cards = build_kpi_cards(_summary(), _breakpoint())

    assert len(cards) == 5
    assert [card["id"] for card in cards] == [
        "current_cash_balance",
        "recent_savings_rate",
        "recent_dsr",
        "recent_fixed_expense_ratio",
        "breakpoint",
    ]


def test_kpi_money_and_ratio_formatting() -> None:
    cards = build_kpi_cards(_summary(), _breakpoint())
    by_id = {card["id"]: card for card in cards}

    assert by_id["current_cash_balance"]["value"] == "85만원"
    assert by_id["recent_savings_rate"]["value"] == "8.2%"
    assert by_id["recent_dsr"]["value"] == "38.0%"
    assert by_id["recent_fixed_expense_ratio"]["value"] == "46.0%"


def test_hero_contains_required_copy_without_brand_repetition() -> None:
    hero = render_hero_html()

    assert "<h1>Financial Path Twin</h1>" in hero
    assert "비슷한 금융 궤적을 먼저 경험한 고객들의 결과를 통해 위험 분기점과 대응 시점을 확인합니다." in hero
    assert "당신의 미래를 단정적으로 예측하지 않습니다. 같은 길을 먼저 걸은 고객들의 결과를 보여줍니다." in hero
    assert "합성 데이터 기반 PoC이며 실제 신용평가 또는 미래 확정 예측이 아닙니다." in hero
    assert hero.count("Financial Path Twin") == 1
    assert "fpt-product-mark" not in hero
    assert "fpt-eyebrow" not in hero
    assert "최근 12개월 흐름이 비슷했던 합성 고객" not in hero


def test_kpi_help_tooltips_are_rendered_and_escaped() -> None:
    rendered = render_kpi_cards_html(
        [
            {
                "title": "DSR",
                "value": "38.0%",
                "description": "최근 3개월 평균",
                "detail": "주의 구간 35~45%",
                "tone": "watch",
                "help": "월소득 < 대출상환 부담",
            }
        ]
    )

    assert 'class="fpt-kpi-help"' in rendered
    assert "월소득 < 대출상환 부담" not in rendered
    assert "월소득 &lt; 대출상환 부담" in rendered


def test_dsr_status_bands() -> None:
    assert classify_kpi_tone("dsr", 0.34) == "stable"
    assert classify_kpi_tone("dsr", 0.35) == "watch"
    assert classify_kpi_tone("dsr", 0.45) == "danger"


def test_savings_rate_status_band() -> None:
    assert classify_kpi_tone("savings_rate", 0.049) == "watch"
    assert classify_kpi_tone("savings_rate", 0.05) == "neutral"


def test_fixed_expense_status_bands() -> None:
    assert classify_kpi_tone("fixed_expense_ratio", 0.449) == "neutral"
    assert classify_kpi_tone("fixed_expense_ratio", 0.45) == "watch"
    assert classify_kpi_tone("fixed_expense_ratio", 0.55) == "danger"


def test_negative_cash_balance_is_danger() -> None:
    assert classify_kpi_tone("cash_balance", -1) == "danger"
    assert classify_kpi_tone("cash_balance", 0) == "neutral"


def test_breakpoint_found_card() -> None:
    breakpoint_card = build_kpi_cards(_summary(), _breakpoint())[-1]

    assert breakpoint_card["value"] == "2개월 후"
    assert breakpoint_card["unit"] == "14개월 차"
    assert "고정지출 비중" in breakpoint_card["detail"]


def test_current_status_sentence_uses_natural_remaining_month_text() -> None:
    sentence = build_current_status_sentence(_summary(), _breakpoint())

    assert "약 2개월이 남아" in sentence
    assert "2개월 후 남아" not in sentence


def test_breakpoint_not_found_and_insufficient_cards() -> None:
    not_found = build_kpi_cards(_summary(), _breakpoint("not_found"))[-1]
    insufficient = build_kpi_cards(_summary(), _breakpoint("insufficient_group_size"))[-1]

    assert not_found["value"] == "미발견"
    assert insufficient["value"] == "분석 제한"


def test_status_badge_label() -> None:
    badge = build_status_badge("stress")

    assert badge["label"] == "재무 스트레스"
    assert badge["class_name"] == "fpt-badge status-stress"


def test_html_special_characters_are_escaped() -> None:
    items = build_customer_identity(
        customer_id="<C&001>",
        summary={**_summary(), "current_status": "watch"},
        matched_count=200,
    )
    rendered = render_customer_identity_html(items)

    assert "<C&001>" not in rendered
    assert "&lt;C&amp;001&gt;" in rendered


def test_first_screen_helpers_do_not_mutate_source_data() -> None:
    summary = _summary()
    analysis = {"breakpoint_result": _breakpoint()}
    before_summary = deepcopy(summary)
    before_analysis = deepcopy(analysis)

    build_first_screen_view_model(
        customer_id="C000001",
        summary=summary,
        analysis=analysis,
        demo_df=pd.DataFrame(),
    )

    assert summary == before_summary
    assert analysis == before_analysis


def test_css_file_exists_and_missing_css_is_non_blocking(tmp_path) -> None:
    assert (settings.BASE_DIR / "assets" / "styles.css").exists()
    assert load_css(tmp_path / "missing.css") == ""


def test_design_tokens_include_required_keys() -> None:
    required = {
        "page_background",
        "card_background",
        "primary",
        "primary_dark",
        "text",
        "muted_text",
        "border",
        "stable",
        "recovered",
        "watch",
        "stress",
        "delinquent",
        "baseline",
        "card_radius",
        "section_gap",
        "card_padding",
    }

    assert required.issubset(DESIGN_TOKENS)


def _demo_roles_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"customer_id": "C000001", "demo_role": "main"},
            {"customer_id": "C000002", "demo_role": "stable_comparison"},
            {"customer_id": "C000003", "demo_role": "high_risk"},
        ]
    )


def _analysis(status: str = "found") -> dict:
    breakpoint = _breakpoint(status)
    if status == "insufficient_group_size":
        breakpoint = {"status": "insufficient_group_size"}
    if status == "not_found":
        breakpoint = {"status": "not_found"}
    return {
        "matches": pd.DataFrame(
            {
                "matched_customer_id": ["C000101", "C000102"],
                "similarity_score": [0.91, 0.87],
            }
        ),
        "outcome_summary": {
            "matched_count": 200,
            "outcomes": {
                "healthy": {"count": 90, "ratio": 0.45},
                "recovered": {"count": 30, "ratio": 0.15},
                "stress": {"count": 60, "ratio": 0.30},
                "delinquent": {"count": 20, "ratio": 0.10},
            },
        },
        "breakpoint_result": breakpoint,
        "whatif_results": {
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
                    "ending_cash_balance": 2_500_000,
                    "minimum_cash_balance": 700_000,
                    "average_savings_rate": 0.15,
                    "cash_depletion_month": None,
                    "improvement_vs_baseline": 1_500_000,
                },
            ]
        },
    }


def test_judge_flow_view_model_prepares_three_demo_customer_roles() -> None:
    demo_df = _demo_roles_df()

    for customer_id in ("C000001", "C000002", "C000003"):
        model = build_judge_flow_view_model(
            customer_id=customer_id,
            summary={**_summary(), "customer_id": customer_id},
            demo_df=demo_df,
            analysis=_analysis(),
        )

        assert len(model["section_titles"]) == 5
        assert any(item["value"] == customer_id for item in model["customer_identity"])
        assert len(model["kpi_cards"]) == 5


def test_judge_flow_handles_breakpoint_states() -> None:
    found = build_breakpoint_summary_cards(_analysis("found")["breakpoint_result"])
    not_found = build_breakpoint_summary_cards(_analysis("not_found")["breakpoint_result"])
    insufficient = build_breakpoint_summary_cards(_analysis("insufficient_group_size")["breakpoint_result"])

    assert found[0]["title"] == "분기점"
    assert any(card["title"] == "주요 차이 지표" for card in found)
    assert not_found[0]["value"] == "미발견"
    assert insufficient[0]["value"] == "분석 제한"


def test_judge_flow_handles_missing_whatif_and_briefing() -> None:
    empty_card = build_best_whatif_card({"scenarios": []})

    assert empty_card["value"] == "비교 가능한 대응안 없음"
    assert "브리핑" in build_brief_empty_message()


def test_outcome_sentence_uses_observed_peer_ratio_language() -> None:
    sentence = build_outcome_risk_sentence(_analysis()["outcome_summary"])

    assert "유사 고객 200명 중 80명" in sentence
    assert "예측 확률" not in sentence


def test_missing_data_guidance_hides_file_paths() -> None:
    guidance = build_missing_data_guidance([settings.DATA_RAW_DIR / "missing.csv"])

    assert "missing.csv" not in guidance
    assert "python scripts/run_pipeline.py" in guidance


def test_default_screen_rendered_text_hides_internal_names_and_technical_settings() -> None:
    model = build_judge_flow_view_model(
        customer_id="C000001",
        summary=_summary(),
        demo_df=_demo_roles_df(),
        analysis=_analysis(),
        selected_metric="savings_rate",
    )
    rendered = "".join(
        [
            render_customer_identity_html(model["customer_identity"]),
            render_kpi_cards_html(model["kpi_cards"]),
            render_status_summary_html(model["status_sentence"]),
            render_info_cards_html(model["similarity_cards"]),
            render_info_cards_html(model["breakpoint_cards"]),
            render_info_cards_html([model["whatif_card"]]),
        ]
    )
    forbidden_terms = (
        "fixed_expense_ratio",
        "cash_balance_ratio",
        "variable_expense_cut_15",
        "Feature Engineering",
        "Similarity Matching",
        "top_k",
        "random_seed",
        "SMD",
    )

    assert not any(term in rendered for term in forbidden_terms)
