"""Regression tests for the five-tab presentation-mode layout."""

from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import app as app_module
from streamlit.testing.v1 import AppTest

from src.presentation import GENERAL_MODE, PRESENTATION_MODE, build_presentation_view_model, get_presentation_tab_labels
from src.rm_workspace import RM_WORKSPACE_MODE, get_rm_workspace_tab_labels
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
        "③ 유사 경로 근거",
        "④ 대응 시나리오",
        "⑤ 분석 요약",
    ]
    assert get_presentation_tab_labels("en") == [
        "① Current",
        "② Similar Paths",
        "③ Similar-path Evidence",
        "④ Action Scenarios",
        "⑤ Summary",
    ]


def test_presentation_tab_css_preserves_single_line_labels() -> None:
    css = load_css()

    assert 'div[data-testid="stTabs"] button' in css
    assert "white-space: nowrap;" in css
    assert '[role="tabpanel"]' in css


def test_rm_queue_table_uses_localized_reason_copy_not_raw_codes() -> None:
    table = app_module._rm_queue_table_rows(
        [
            {
                "customer_id": "C000001",
                "selection_rank": 1,
                "priority": "Priority Review",
                "case_state": "NO_OPEN_ALERT",
                "selection_reason_codes": ("PRIORITY_BAND_PRIORITY_REVIEW",),
                "why_now_reason_codes": ("CURRENT_STATUS_CONCERNING",),
                "timing_evidence_reference": {"source": "prospective_signal"},
                "due_at": None,
                "owner_reference": None,
                "updated_at": None,
            }
        ],
        language="en",
    )

    rendered_values = " ".join(str(value) for value in table.iloc[0].tolist())
    assert "PRIORITY_BAND_PRIORITY_REVIEW" not in rendered_values
    assert "CURRENT_STATUS_CONCERNING" not in rendered_values
    assert "Priority Review tier" in rendered_values
    assert "Current status condition" in rendered_values
    assert "Customer ID" in table.columns


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


def test_presentation_app_shows_population_strip_without_adding_a_sixth_tab() -> None:
    at = AppTest.from_file(Path(app_module.__file__))
    at.run(timeout=45)

    assert not at.exception
    assert [tab.label for tab in at.tabs] == get_presentation_tab_labels("ko")
    assert len(at.tabs) == 5
    assert any("5,000" in markdown.value for markdown in at.markdown)

    at.selectbox(key="ui_language").set_value("en").run(timeout=45)
    assert not at.exception
    assert [tab.label for tab in at.tabs] == get_presentation_tab_labels("en")
    assert any(caption.value == "Population evidence" for caption in at.caption)


def test_app_test_all_modes_keep_their_own_tab_and_language_contracts() -> None:
    at = AppTest.from_file(Path(app_module.__file__))
    at.run(timeout=45)

    assert not at.exception
    assert [tab.label for tab in at.tabs] == get_presentation_tab_labels("ko")

    at.sidebar.selectbox(key="app_mode").set_value(GENERAL_MODE).run(timeout=45)
    assert not at.exception
    assert list(at.tabs) == []

    at.selectbox(key="ui_language").set_value("en").run(timeout=45)
    at.sidebar.selectbox(key="app_mode").set_value(PRESENTATION_MODE).run(timeout=45)
    assert not at.exception
    assert [tab.label for tab in at.tabs] == get_presentation_tab_labels("en")

    at.sidebar.selectbox(key="app_mode").set_value(RM_WORKSPACE_MODE).run(timeout=45)
    assert not at.exception
    assert [tab.label for tab in at.tabs] == get_rm_workspace_tab_labels("en")
