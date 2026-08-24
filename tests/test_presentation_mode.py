"""Tests for hackathon presentation-mode view models."""

from __future__ import annotations

import json
import inspect
from copy import deepcopy
from pathlib import Path
from typing import Any

import pandas as pd

from config import settings
from src.copy import (
    APP_MODE_OPTIONS,
    BREAKPOINT_INSUFFICIENT_MESSAGE,
    BREAKPOINT_NOT_FOUND_MESSAGE,
    UI_MESSAGES,
    find_internal_screen_terms,
)
from src.presentation import (
    GENERAL_MODE,
    PRESENTATION_MODE,
    PRESENTATION_SOURCE_LIVE,
    PRESENTATION_SOURCE_MAIN_DEMO,
    PRESENTATION_SOURCE_PROCESSED,
    build_breakpoint_scene_message,
    build_presentation_current_review_signal,
    build_presentation_customer_options,
    build_peer_scene_message,
    build_presentation_metric_cards,
    build_presentation_population_strip,
    build_presentation_view_model,
    build_whatif_scene_message,
    load_presentation_population_evidence,
    load_presentation_payload,
    resolve_presentation_customer_id,
)
from src.ui_components import render_presentation_notice_html, render_presentation_scene_heading_html


def _outcome_summary() -> dict[str, Any]:
    return {
        "target_customer_id": "C000001",
        "matched_count": 200,
        "outcomes": {
            "healthy": {"count": 87, "ratio": 0.435},
            "recovered": {"count": 41, "ratio": 0.205},
            "stress": {"count": 66, "ratio": 0.33},
            "delinquent": {"count": 6, "ratio": 0.03},
        },
    }


def _breakpoint(status: str = "found") -> dict[str, Any]:
    if status == "found":
        return {
            "status": "found",
            "breakpoint_month": 13,
            "months_from_current": 1,
            "primary_factor": "cash_balance_ratio",
            "risk_group_mean": 3.43,
            "avoidance_group_mean": 5.49,
            "standardized_difference": -1.26,
        }
    return {"status": status}


def _whatif_results(with_scenarios: bool = True) -> dict[str, Any]:
    if not with_scenarios:
        return {"target_customer_id": "C000001", "simulation_months": 24, "scenarios": []}
    return {
        "target_customer_id": "C000001",
        "simulation_months": 24,
        "starting_profile": {
            "customer_id": "C000001",
            "cash_balance": 28_833_050.0,
        },
        "scenarios": [
            {
                "scenario_name": "baseline",
                "ending_cash_balance": 50_622_709.84,
                "minimum_cash_balance": 29_828_040.33,
                "average_savings_rate": 0.124767,
                "cash_depletion_month": None,
                "improvement_vs_baseline": 0.0,
            },
            {
                "scenario_name": "debt_payment_cut_20",
                "ending_cash_balance": 59_617_377.04,
                "minimum_cash_balance": 30_202_818.13,
                "average_savings_rate": 0.17627,
                "cash_depletion_month": None,
                "improvement_vs_baseline": 8_994_667.2,
            },
        ],
    }


def _analysis(status: str = "found", with_whatif: bool = True) -> dict[str, Any]:
    return {
        "customer_id": "C000001",
        "matches": pd.DataFrame(),
        "matched_ids": [],
        "outcome_summary": _outcome_summary(),
        "breakpoint_result": _breakpoint(status),
        "whatif_results": _whatif_results(with_whatif),
        "breakpoint_comparison": pd.DataFrame(),
        "matched_future_trajectory": pd.DataFrame(),
        "errors": {},
    }


def _summary() -> dict[str, Any]:
    return {
        "customer_id": "C000001",
        "current_status": "healthy",
        "recent_savings_rate": 0.136633,
        "recent_dsr": 0.2576,
        "recent_fixed_expense_ratio": 0.368136,
        "current_cash_balance": 28_833_050.0,
        "savings_rate_slope_6m": -0.002945,
    }


def _main_demo_customer() -> dict[str, Any]:
    return {
        "customer_id": "C000001",
        "current_metrics": {
            "current_status": "healthy",
            "recent_savings_rate": 0.136633,
            "recent_dsr": 0.2576,
            "recent_fixed_expense_ratio": 0.368136,
            "savings_rate_slope_6m": -0.002945,
        },
        "match_summary": {
            "matched_count": 200,
            "top_10": [
                {
                    "target_customer_id": "C000001",
                    "matched_customer_id": "C000002",
                    "rank": 1,
                    "distance": 0.3,
                    "similarity_score": 0.76,
                }
            ],
        },
        "outcome_summary": _outcome_summary(),
        "breakpoint_result": _breakpoint(),
        "whatif_results": _whatif_results(),
    }


def _monthly_df(customer_id: str = "C000001") -> pd.DataFrame:
    rows = []
    for month in range(1, 13):
        rows.append(
            {
                "customer_id": customer_id,
                "month": month,
                "savings_rate": 0.15 - month * 0.002,
                "dsr": 0.24 + month * 0.001,
                "fixed_expense_ratio": 0.35 + month * 0.001,
                "cash_balance": 20_000_000 + month * 100_000,
                "monthly_status": "healthy",
            }
        )
    return pd.DataFrame(rows)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _write_population_artifacts(run_dir: Path) -> None:
    records = [
        {
            "customer_id": "C000001",
            "eligibility_label": "Priority Review",
            "timing_evidence_reference": {"source": "prospective_signal"},
        },
        {
            "customer_id": "C000003",
            "eligibility_label": "Monitor",
            "timing_evidence_reference": {"source": "prospective_signal"},
        },
    ]
    _write_json(
        run_dir / "rm_selection_manifest.json",
        {
            "funnel": {"monitored_total": 5000, "eligible_total": 1522, "selected_queue_ready": 1522},
            "reconciliation": {"is_exact": True},
            "records": records,
        },
    )
    _write_json(
        run_dir / "rm_representative_cohort.json",
        {
            "records": [
                {"category_id": "priority_review", "customer_id": "C000001", "status": "selected", "source_as_of_month": 12},
                {"category_id": "early_signal_review", "customer_id": "C000007", "status": "selected", "source_as_of_month": 12},
                {"category_id": "monitor_no_alert_comparison", "customer_id": "C000003", "status": "selected", "source_as_of_month": 12},
                {"category_id": "insufficient_or_landmark_not_found", "customer_id": None, "status": "unavailable", "source_as_of_month": 12},
            ]
        },
    )


def test_mode_options_keep_general_and_presentation_modes() -> None:
    assert APP_MODE_OPTIONS == ("일반 모드", "발표 모드", "RM 업무 모드")
    assert GENERAL_MODE == "일반 모드"
    assert PRESENTATION_MODE == "발표 모드"


def test_main_customer_is_default_for_presentation_mode() -> None:
    demo_df = pd.DataFrame(
        [
            {"demo_role": "stable_comparison", "customer_id": "C000002"},
            {"demo_role": "main", "customer_id": "C000001"},
        ]
    )

    assert resolve_presentation_customer_id(demo_df=demo_df) == "C000001"
    assert resolve_presentation_customer_id(main_demo_customer={"customer_id": "C000099"}) == "C000099"


def test_presentation_view_model_has_four_scenes_with_actual_values() -> None:
    model = build_presentation_view_model(
        customer_id="C000001",
        summary=_summary(),
        analysis=_analysis(),
        source=PRESENTATION_SOURCE_MAIN_DEMO,
    )

    assert [scene["label"] for scene in model["scenes"]] == ["장면 1", "장면 2", "장면 3", "장면 4", "장면 5"]
    assert "최근 저축 여력이 감소" in model["scenes"][0]["message"]
    assert "200명 중 36.0%" in model["scenes"][1]["message"]
    assert "13개월 차" in model["scenes"][2]["message"]
    assert "대출상환액 20% 감소" in model["scenes"][3]["message"]
    assert "899만원" in model["scenes"][3]["message"]
    assert "고객용 설명" in model["scenes"][4]["message"]


def test_scene_messages_handle_breakpoint_states_and_empty_whatif() -> None:
    assert "소득 대비 현금 보유 수준" in build_breakpoint_scene_message(_breakpoint())
    assert build_breakpoint_scene_message({"status": "not_found"}) != BREAKPOINT_NOT_FOUND_MESSAGE
    assert build_breakpoint_scene_message({"status": "insufficient_group_size"}) != BREAKPOINT_INSUFFICIENT_MESSAGE
    assert "아직 준비되지 않았습니다" in build_whatif_scene_message({"scenarios": []})


def test_peer_message_uses_observed_ratio_not_prediction_language() -> None:
    message = build_peer_scene_message(_outcome_summary())

    assert "36.0%" in message
    assert "예측 확률" not in message


def test_presentation_metric_cards_include_breakpoint_and_whatif_numbers() -> None:
    cards = build_presentation_metric_cards(
        breakpoint_result=_breakpoint(),
        whatif_results=_whatif_results(),
    )

    assert "13개월 차" in cards["breakpoint"][0]["value"]
    assert "1개월" not in cards["breakpoint"][0]["value"]
    assert cards["breakpoint"][1]["value"] == "소득 대비 현금 보유 수준"
    assert cards["whatif"][0]["value"] == "대출상환액 20% 감소"
    assert cards["whatif"][1]["value"] == "899만원"


def test_population_evidence_strip_and_representative_options_use_saved_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / "triage-run"
    _write_population_artifacts(run_dir)

    evidence = load_presentation_population_evidence(run_dir)
    strip = build_presentation_population_strip(
        customer_id="C000001",
        population_evidence=evidence,
        language="en",
    )
    options = build_presentation_customer_options(
        demo_options=[{"customer_id": "C000001", "role": "main", "label": "Main (C000001)"}],
        population_evidence=evidence,
        language="en",
    )

    assert evidence["available"]
    assert evidence["population_count"] == 5000
    assert evidence["eligible_count"] == 1522
    assert evidence["selected_count"] == 1522
    assert strip["items"][0] == ("Population analyzed", "5,000")
    assert "deterministic representative" in strip["items"][-1][1].lower()
    assert [option["customer_id"] for option in options] == ["C000001", "C000001", "C000007", "C000003"]
    assert not any("insufficient_or_landmark_not_found" in option["option_id"] for option in options)
    current_signal = build_presentation_current_review_signal(
        customer_id="C000001",
        population_evidence=evidence,
        language="en",
    )
    assert current_signal is not None
    assert current_signal["value"] == "Priority Review"


def test_population_evidence_fallback_and_selection_helpers_do_not_read_future_labels(tmp_path: Path) -> None:
    unavailable = load_presentation_population_evidence(tmp_path / "missing")

    assert not unavailable["available"]
    assert build_presentation_population_strip(customer_id="C000001", population_evidence=unavailable, language="en")["available"] is False
    selection_source = inspect.getsource(load_presentation_population_evidence) + inspect.getsource(build_presentation_customer_options)
    assert "final_outcome" not in selection_source
    assert "persona" not in selection_source


def test_presentation_breakpoint_copy_is_historical_not_a_current_forecast() -> None:
    message = build_breakpoint_scene_message(_breakpoint(), language="en")
    cards = build_presentation_metric_cards(
        breakpoint_result=_breakpoint(),
        whatif_results=_whatif_results(),
        language="en",
    )

    assert "historical landmark" in message.lower()
    assert "forecast" not in cards["breakpoint"][0]["value"].lower()
    assert "In 1 month" not in cards["breakpoint"][0]["value"]


def test_rendered_presentation_copy_hides_internal_terms_and_escapes_html() -> None:
    model = build_presentation_view_model(
        customer_id="<C&001>",
        summary=_summary(),
        analysis=_analysis(),
        source=PRESENTATION_SOURCE_MAIN_DEMO,
    )
    rendered = "".join(render_presentation_scene_heading_html(scene) for scene in model["scenes"])
    rendered += render_presentation_notice_html(model["notices"])

    assert "<C&001>" not in rendered
    assert find_internal_screen_terms(rendered) == []


def test_load_presentation_payload_uses_main_demo_customer_first(tmp_path: Path) -> None:
    demo_dir = tmp_path / "demo"
    processed_dir = tmp_path / "processed"
    _write_json(demo_dir / settings.MAIN_DEMO_CUSTOMER_FILENAME, _main_demo_customer())

    payload = load_presentation_payload(demo_dir=demo_dir, processed_dir=processed_dir)

    assert payload.is_ready
    assert payload.source == PRESENTATION_SOURCE_MAIN_DEMO
    assert payload.customer_id == "C000001"
    assert payload.summary["current_cash_balance"] == 28_833_050.0
    assert payload.analysis["outcome_summary"]["matched_count"] == 200


def test_load_presentation_payload_falls_back_to_processed_json(tmp_path: Path) -> None:
    processed_dir = tmp_path / "processed"
    _write_json(processed_dir / settings.OUTCOME_SUMMARY_FILENAME, _outcome_summary())
    _write_json(processed_dir / settings.BREAKPOINT_RESULT_FILENAME, _breakpoint("not_found"))
    _write_json(processed_dir / settings.WHATIF_RESULTS_FILENAME, _whatif_results())

    payload = load_presentation_payload(
        demo_dir=tmp_path / "demo",
        processed_dir=processed_dir,
        monthly_df=_monthly_df(),
        customer_id="C000001",
    )

    assert payload.is_ready
    assert payload.source == PRESENTATION_SOURCE_PROCESSED
    assert payload.analysis["breakpoint_result"]["status"] == "not_found"


def test_load_presentation_payload_falls_back_to_live_calculation(tmp_path: Path) -> None:
    def fake_live_runner(customer_id: str, monthly_df: pd.DataFrame, features_df: pd.DataFrame, matcher: Any) -> dict:
        return {**_analysis(), "customer_id": customer_id}

    payload = load_presentation_payload(
        demo_dir=tmp_path / "demo",
        processed_dir=tmp_path / "processed",
        monthly_df=_monthly_df(),
        features_df=pd.DataFrame({"customer_id": ["C000001"]}),
        matcher=object(),
        customer_id="C000001",
        live_runner=fake_live_runner,
    )

    assert payload.is_ready
    assert payload.source == PRESENTATION_SOURCE_LIVE
    assert payload.summary["customer_id"] == "C000001"


def test_non_main_presentation_customer_uses_live_result_without_reusing_main_cache(tmp_path: Path) -> None:
    demo_dir = tmp_path / "demo"
    _write_json(demo_dir / settings.MAIN_DEMO_CUSTOMER_FILENAME, _main_demo_customer())
    monthly = _monthly_df().copy()
    monthly["customer_id"] = "C000002"

    payload = load_presentation_payload(
        demo_dir=demo_dir,
        processed_dir=tmp_path / "processed",
        monthly_df=monthly,
        features_df=pd.DataFrame({"customer_id": ["C000002"]}),
        matcher=object(),
        customer_id="C000002",
        live_runner=lambda customer_id, *_: {**_analysis(), "customer_id": customer_id},
    )

    assert payload.is_ready
    assert payload.customer_id == "C000002"
    assert payload.source == PRESENTATION_SOURCE_LIVE


def test_load_presentation_payload_handles_bad_json_with_friendly_error(tmp_path: Path) -> None:
    demo_dir = tmp_path / "demo"
    demo_dir.mkdir()
    (demo_dir / settings.MAIN_DEMO_CUSTOMER_FILENAME).write_text("{bad json", encoding="utf-8")

    payload = load_presentation_payload(demo_dir=demo_dir, processed_dir=tmp_path / "processed")

    assert not payload.is_ready
    assert payload.error_message == UI_MESSAGES["presentation_error"]
    assert "Json" not in payload.error_message


def test_presentation_helpers_do_not_mutate_source_data() -> None:
    summary = _summary()
    analysis = _analysis()
    before_summary = deepcopy(summary)
    before_analysis = deepcopy(analysis)

    build_presentation_view_model(
        customer_id="C000001",
        summary=summary,
        analysis=analysis,
        source=PRESENTATION_SOURCE_MAIN_DEMO,
    )
    build_presentation_metric_cards(
        breakpoint_result=analysis["breakpoint_result"],
        whatif_results=analysis["whatif_results"],
    )

    assert summary == before_summary
    for key in ("matches", "breakpoint_comparison", "matched_future_trajectory"):
        pd.testing.assert_frame_equal(analysis[key], before_analysis[key])
    for key in set(analysis) - {"matches", "breakpoint_comparison", "matched_future_trajectory"}:
        assert analysis[key] == before_analysis[key]


def test_general_and_presentation_data_match_precomputed_main_json(tmp_path: Path) -> None:
    main_demo = _main_demo_customer()
    demo_dir = tmp_path / "demo"
    _write_json(demo_dir / settings.MAIN_DEMO_CUSTOMER_FILENAME, main_demo)

    payload = load_presentation_payload(demo_dir=demo_dir, processed_dir=tmp_path / "processed")

    assert payload.analysis["outcome_summary"] == main_demo["outcome_summary"]
    assert payload.analysis["breakpoint_result"] == main_demo["breakpoint_result"]
    assert payload.analysis["whatif_results"] == main_demo["whatif_results"]
