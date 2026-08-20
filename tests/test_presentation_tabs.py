"""Regression tests for the five-tab presentation-mode layout."""

from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import app as app_module

from src.presentation import build_presentation_view_model, get_presentation_tab_labels
from src.ui_components import load_css


def _summary(customer_id: str = "C000001") -> dict[str, Any]:
    return {
        "customer_id": customer_id,
        "current_status": "watch",
        "recent_savings_rate": 0.08,
        "recent_dsr": 0.38,
        "recent_fixed_expense_ratio": 0.46,
        "current_cash_balance": 12_500_000,
        "savings_rate_slope_6m": -0.01,
    }


def _analysis() -> dict[str, Any]:
    return {
        "outcome_summary": {
            "matched_count": 200,
            "outcomes": {
                "healthy": {"count": 87, "ratio": 0.435},
                "recovered": {"count": 41, "ratio": 0.205},
                "stress": {"count": 66, "ratio": 0.33},
                "delinquent": {"count": 6, "ratio": 0.03},
            },
        },
        "breakpoint_result": {
            "status": "found",
            "breakpoint_month": 14,
            "months_from_current": 2,
            "primary_factor": "fixed_expense_ratio",
            "risk_group_mean": 0.51,
            "avoidance_group_mean": 0.39,
        },
        "whatif_results": {
            "scenarios": [
                {
                    "scenario_name": "baseline",
                    "ending_cash_balance": 50_000_000,
                    "minimum_cash_balance": 30_000_000,
                    "improvement_vs_baseline": 0,
                },
                {
                    "scenario_name": "variable_expense_cut_15",
                    "ending_cash_balance": 59_000_000,
                    "minimum_cash_balance": 31_000_000,
                    "improvement_vs_baseline": 9_000_000,
                },
            ]
        },
    }


def test_presentation_tabs_are_short_and_localized() -> None:
    assert get_presentation_tab_labels("ko") == [
        "① 현재 상태",
        "② 유사 경로",
        "③ 위험 분기점",
        "④ 대응 시나리오",
        "⑤ 분석 요약",
    ]
    assert get_presentation_tab_labels("en") == [
        "① Current",
        "② Similar Paths",
        "③ Turning Point",
        "④ Action Scenarios",
        "⑤ Summary",
    ]


def test_presentation_tab_css_preserves_single_line_labels() -> None:
    css = load_css()

    assert 'div[data-testid="stTabs"] button' in css
    assert "white-space: nowrap;" in css
    assert '[role="tabpanel"]' in css


def test_presentation_view_model_includes_summary_scene_for_all_breakpoint_states() -> None:
    for status in ("found", "not_found", "insufficient_group_size"):
        analysis = _analysis()
        analysis["breakpoint_result"] = {"status": status}
        if status == "found":
            analysis["breakpoint_result"] = _analysis()["breakpoint_result"]

        view_model = build_presentation_view_model(
            customer_id="C000001",
            summary=_summary(),
            analysis=analysis,
            source="test",
            language="en",
        )

        assert [scene["id"] for scene in view_model["scenes"]] == [
            "current",
            "peers",
            "breakpoint",
            "whatif",
            "summary",
        ]
        assert view_model["scenes"][-1]["title"] == "How can these results support customer engagement?"


def test_tab_renderer_uses_prepared_values_without_repeating_analysis(monkeypatch) -> None:
    summary = _summary()
    analysis = _analysis()
    before_summary = deepcopy(summary)
    before_analysis = deepcopy(analysis)
    payload = SimpleNamespace(customer_id="C000001", summary=summary, analysis=analysis, source="test")
    selection = app_module.SidebarSelection(
        customer_id="C000001",
        selected_metric="savings_rate",
        app_mode=app_module.PRESENTATION_MODE,
        presentation_mode=True,
        show_raw_samples=False,
    )
    calls: list[str] = []
    labels_seen: list[str] = []

    monkeypatch.setattr(app_module.st, "tabs", lambda labels: (labels_seen.extend(labels) or [nullcontext() for _ in labels]))
    monkeypatch.setattr(app_module, "build_first_screen_view_model", lambda **kwargs: {"customer_identity": {}, "kpi_cards": [], "status_sentence": ""})
    monkeypatch.setattr(app_module, "build_judge_flow_view_model", lambda **kwargs: {"similarity_cards": [], "outcome_sentence": ""})
    monkeypatch.setattr(app_module, "build_target_history", lambda *args: "current-history")
    monkeypatch.setattr(app_module, "build_twin_trajectory_frames", lambda *args: ("twin-history", "future-trajectory"))
    monkeypatch.setattr(app_module, "build_brief_with_fallback", lambda brief_type, *args, **kwargs: f"{brief_type}-brief")
    monkeypatch.setattr(app_module, "run_customer_analysis", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("analysis rerun")))

    for name in (
        "render_presentation_current_scene",
        "render_presentation_peer_scene",
        "render_presentation_breakpoint_scene",
        "render_presentation_whatif_scene",
        "render_presentation_summary_scene",
    ):
        monkeypatch.setattr(app_module, name, lambda _name=name, **kwargs: calls.append(_name))

    app_module.render_presentation_mode(
        monthly_df=object(),
        demo_df=object(),
        payload=payload,
        selection=selection,
        language="ko",
    )

    assert labels_seen == get_presentation_tab_labels("ko")
    assert calls == [
        "render_presentation_current_scene",
        "render_presentation_peer_scene",
        "render_presentation_breakpoint_scene",
        "render_presentation_whatif_scene",
        "render_presentation_summary_scene",
    ]
    assert summary == before_summary
    assert analysis == before_analysis
