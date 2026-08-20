"""Presentation-mode view models for the hackathon demo.

This module only selects existing results and converts them into display
messages. It does not change matching, aggregation, breakpoint, or What-if
calculation rules.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from config import settings
from src.copy import (
    APP_MODE_OPTIONS,
    BREAKPOINT_INSUFFICIENT_MESSAGE,
    BREAKPOINT_NOT_FOUND_MESSAGE,
    PRESENTATION_NOTICES,
    PRESENTATION_SCENE_COPY,
    UI_MESSAGES,
)
from src.demo_cache import build_fallback_customer_summary
from src.formatters import format_krw_compact, format_metric_value, format_month_label, format_percent
from src.i18n import t
from src.labels import label_metric, label_scenario, label_status
from src.ui_components import (
    best_whatif_scenario,
    build_customer_summary,
    calculate_risk_group_ratio,
    run_customer_analysis,
)


GENERAL_MODE = APP_MODE_OPTIONS[0]
PRESENTATION_MODE = APP_MODE_OPTIONS[1]
PRESENTATION_SOURCE_MAIN_DEMO = "main_demo_customer.json"
PRESENTATION_SOURCE_PROCESSED = "processed 결과 JSON"
PRESENTATION_SOURCE_LIVE = "실시간 계산"
PRESENTATION_SOURCE_FAILED = "표시 가능한 데이터 없음"
PRESENTATION_TAB_KEYS = (
    "presentation.tab.current",
    "presentation.tab.similar",
    "presentation.tab.breakpoint",
    "presentation.tab.actions",
    "presentation.tab.summary",
)


@dataclass(frozen=True)
class PresentationLoadResult:
    """Loaded presentation data and the fallback source that supplied it."""

    customer_id: str
    summary: dict[str, Any]
    analysis: dict[str, Any]
    source: str
    fallback_steps: tuple[str, ...]
    error_message: str | None = None

    @property
    def is_ready(self) -> bool:
        return self.error_message is None


LiveRunner = Callable[[str, pd.DataFrame, pd.DataFrame, Any], dict[str, Any]]


def resolve_presentation_customer_id(
    *,
    demo_df: pd.DataFrame | None = None,
    main_demo_customer: Mapping[str, Any] | None = None,
    fallback_customer_id: str | None = None,
) -> str:
    """Return the main demo customer id for presentation mode."""

    if main_demo_customer and main_demo_customer.get("customer_id"):
        return str(main_demo_customer["customer_id"])
    if demo_df is not None and not demo_df.empty and {"demo_role", "customer_id"}.issubset(demo_df.columns):
        main_rows = demo_df[demo_df["demo_role"].astype(str) == "main"]
        if not main_rows.empty:
            return str(main_rows.iloc[0]["customer_id"])
    return "" if fallback_customer_id is None else str(fallback_customer_id)


def load_presentation_payload(
    *,
    demo_dir: Path = settings.DATA_DEMO_DIR,
    processed_dir: Path = settings.DATA_PROCESSED_DIR,
    monthly_df: pd.DataFrame | None = None,
    features_df: pd.DataFrame | None = None,
    matcher: Any = None,
    customer_id: str | None = None,
    live_runner: LiveRunner | None = None,
    language: str = "ko",
) -> PresentationLoadResult:
    """Load presentation data using the documented fallback order."""

    fallback_steps: list[str] = []
    main_demo_customer: dict[str, Any] | None = None
    resolved_customer_id = "" if customer_id is None else str(customer_id)

    try:
        main_demo_customer = _read_json(demo_dir / settings.MAIN_DEMO_CUSTOMER_FILENAME)
        main_customer_id = resolve_presentation_customer_id(main_demo_customer=main_demo_customer)
        if not resolved_customer_id:
            resolved_customer_id = main_customer_id
        if resolved_customer_id == main_customer_id:
            analysis = _analysis_from_main_demo_customer(main_demo_customer)
            analysis = _merge_cached_chart_data(analysis, resolved_customer_id, demo_dir)
            return PresentationLoadResult(
                customer_id=resolved_customer_id,
                summary=_presentation_summary_from_main(main_demo_customer),
                analysis=analysis,
                source=PRESENTATION_SOURCE_MAIN_DEMO,
                fallback_steps=(PRESENTATION_SOURCE_MAIN_DEMO,),
            )
        fallback_steps.append(f"{PRESENTATION_SOURCE_MAIN_DEMO}: selected customer differs")
    except Exception as exc:  # noqa: BLE001
        fallback_steps.append(f"{PRESENTATION_SOURCE_MAIN_DEMO}: {exc.__class__.__name__}")

    try:
        if main_demo_customer is not None:
            raise ValueError("processed presentation artifacts are available only for the fixed main customer")
        processed_analysis = _analysis_from_processed_json(resolved_customer_id, processed_dir)
        summary = _summary_from_monthly_or_main(monthly_df, resolved_customer_id, main_demo_customer)
        return PresentationLoadResult(
            customer_id=resolved_customer_id,
            summary=summary,
            analysis=processed_analysis,
            source=PRESENTATION_SOURCE_PROCESSED,
            fallback_steps=(*fallback_steps, PRESENTATION_SOURCE_PROCESSED),
        )
    except Exception as exc:  # noqa: BLE001
        fallback_steps.append(f"{PRESENTATION_SOURCE_PROCESSED}: {exc.__class__.__name__}")

    try:
        if not resolved_customer_id:
            raise ValueError("presentation customer_id is empty")
        if monthly_df is None or features_df is None or matcher is None:
            raise ValueError("live inputs are unavailable")
        if monthly_df.empty or features_df.empty:
            raise ValueError("live inputs are empty")
        runner = live_runner or run_customer_analysis
        analysis = runner(resolved_customer_id, monthly_df, features_df, matcher)
        summary = build_customer_summary(monthly_df, resolved_customer_id)
        return PresentationLoadResult(
            customer_id=resolved_customer_id,
            summary=summary,
            analysis=analysis,
            source=PRESENTATION_SOURCE_LIVE,
            fallback_steps=(*fallback_steps, PRESENTATION_SOURCE_LIVE),
        )
    except Exception as exc:  # noqa: BLE001
        fallback_steps.append(f"{PRESENTATION_SOURCE_LIVE}: {exc.__class__.__name__}")

    return PresentationLoadResult(
        customer_id=resolved_customer_id,
        summary={},
        analysis={},
        source=PRESENTATION_SOURCE_FAILED,
        fallback_steps=tuple(fallback_steps),
        error_message=t("ui.presentation_error", language),
    )


def build_presentation_view_model(
    *,
    customer_id: str,
    summary: Mapping[str, Any],
    analysis: Mapping[str, Any],
    source: str,
    language: str = "ko",
) -> dict[str, Any]:
    """Build the five-scene presentation script from existing values."""

    scenes = [
        _scene("current", build_current_scene_message(summary, language=language), language),
        _scene("peers", build_peer_scene_message(analysis.get("outcome_summary"), language=language), language),
        _scene("breakpoint", build_breakpoint_scene_message(analysis.get("breakpoint_result"), language=language), language),
        _scene("whatif", build_whatif_scene_message(analysis.get("whatif_results"), language=language), language),
        _scene("summary", t("presentation.summary.message", language), language),
    ]
    return {
        "customer_id": str(customer_id),
        "source": source,
        "scenes": scenes,
        "notices": [
            t("presentation.notice.synthetic", language),
            t("presentation.notice.credit", language),
            t("presentation.notice.prediction", language),
            t("presentation.notice.method", language),
        ],
        "current_metric": select_current_focus_metric(summary),
    }


def get_presentation_tab_labels(language: str = "ko") -> list[str]:
    """Return the short, localized labels used by presentation-mode tabs."""

    return [t(key, language) for key in PRESENTATION_TAB_KEYS]


def build_current_scene_message(summary: Mapping[str, Any], language: str = "ko") -> str:
    """Describe the current customer state without forecasting."""

    status = label_status(summary.get("current_status"), language)
    savings_slope = _to_float_or_none(summary.get("savings_rate_slope_6m"))
    cash_balance = _to_float_or_none(summary.get("current_cash_balance"))
    dsr = _to_float_or_none(summary.get("recent_dsr"))
    savings_rate = _to_float_or_none(summary.get("recent_savings_rate"))

    if str(summary.get("current_status")) == "delinquent":
        return t("presentation.current.delinquent", language)
    if cash_balance is not None and cash_balance < 0:
        return t("presentation.current.negative_cash", language, status=status)
    if savings_slope is not None and savings_slope < 0:
        return t("presentation.current.savings_decline", language)
    if dsr is not None and dsr >= 0.35:
        return t("presentation.current.dsr_watch", language, status=status)
    if savings_rate is not None and savings_rate < 0.05:
        return t("presentation.current.low_savings", language, status=status)
    return t("presentation.current.stable", language, status=status)


def build_peer_scene_message(outcome_summary: Any, language: str = "ko") -> str:
    """Describe observed peer outcomes."""

    if not outcome_summary:
        return t("presentation.peers.empty", language)
    matched_count = _matched_count(outcome_summary)
    risk_ratio = calculate_risk_group_ratio(dict(outcome_summary))
    return t(
        "presentation.peers.message",
        language,
        matched_count=f"{matched_count:,}",
        risk_ratio=format_percent(risk_ratio),
    )


def build_breakpoint_scene_message(breakpoint_result: Any, language: str = "ko") -> str:
    """Describe breakpoint status for the presentation story."""

    if not breakpoint_result:
        return t("breakpoint.not_found", language)
    status = str(breakpoint_result.get("status", "not_found"))
    if status == "insufficient_group_size":
        return t("breakpoint.insufficient_group_size", language)
    if status != "found":
        return t("breakpoint.not_found", language)
    month = breakpoint_result.get("breakpoint_month")
    metric = breakpoint_result.get("primary_factor")
    if month is None or not metric:
        return t("breakpoint.not_found", language)
    return t("presentation.breakpoint.message", language, month=int(month), metric=label_metric(metric, language))


def build_whatif_scene_message(whatif_results: Any, language: str = "ko") -> str:
    """Describe the best existing response-scenario result."""

    if not whatif_results:
        return t("presentation.whatif.empty", language)
    if not whatif_results.get("scenarios"):
        return t("presentation.whatif.empty", language)
    best = best_whatif_scenario(dict(whatif_results))
    if best is None:
        return t("presentation.whatif.baseline_only", language)
    return t(
        "presentation.whatif.message",
        language,
        scenario=label_scenario(best.get("scenario_name"), language),
        improvement=format_krw_compact(best.get("improvement_vs_baseline"), language=language),
    )


def build_presentation_metric_cards(
    *,
    breakpoint_result: Mapping[str, Any] | None,
    whatif_results: Mapping[str, Any] | None,
    language: str = "ko",
) -> dict[str, list[dict[str, str]]]:
    """Return compact scene-specific cards for presentation mode."""

    breakpoint_cards: list[dict[str, str]] = []
    if breakpoint_result and breakpoint_result.get("status") == "found":
        metric = str(breakpoint_result.get("primary_factor"))
        breakpoint_cards = [
            {
                "title": "Turning-Point Month" if language == "en" else "분기점 월",
                "value": format_month_label(int(breakpoint_result["breakpoint_month"]), language=language),
                "detail": "Based on current Month 12" if language == "en" else "현재 12개월 차 기준",
                "tone": "neutral",
            },
            {
                "title": "Key Difference Metric" if language == "en" else "주요 차이 지표",
                "value": label_metric(metric, language),
                "detail": "Based on group-average difference" if language == "en" else "두 집단 평균 차이 기준",
                "tone": "watch",
            },
            {
                "title": t("chart.risk_path_mean", language),
                "value": format_metric_value(breakpoint_result.get("risk_group_mean"), metric, language=language),
                "detail": "At the turning-point month" if language == "en" else "분기점 월 기준",
                "tone": "danger",
            },
            {
                "title": t("chart.avoidance_path_mean", language),
                "value": format_metric_value(breakpoint_result.get("avoidance_group_mean"), metric, language=language),
                "detail": "At the turning-point month" if language == "en" else "분기점 월 기준",
                "tone": "stable",
            },
        ]

    best = best_whatif_scenario(dict(whatif_results or {}))
    whatif_cards: list[dict[str, str]] = []
    if best is not None:
        whatif_cards = [
            {
                "title": "Most Effective Action" if language == "en" else "가장 효과적인 대응안",
                "value": label_scenario(best.get("scenario_name"), language),
                "detail": "Based on improvement vs no action" if language == "en" else "기준 대비 개선액 기준",
                "tone": "stable",
            },
            {
                "title": t("chart.whatif.improvement", language),
                "value": format_krw_compact(best.get("improvement_vs_baseline"), language=language),
                "detail": "Based on 24-month ending balance" if language == "en" else "24개월 후 잔액 기준",
                "tone": "stable",
            },
            {
                "title": t("chart.whatif.ending_balance", language),
                "value": format_krw_compact(best.get("ending_cash_balance"), language=language),
                "detail": "Action-scenario result" if language == "en" else "대응 시나리오 계산 결과",
                "tone": "neutral",
            },
        ]
    return {"breakpoint": breakpoint_cards, "whatif": whatif_cards}


def select_current_focus_metric(summary: Mapping[str, Any]) -> str:
    """Pick the single current chart that best supports the presentation story."""

    savings_rate = _to_float_or_none(summary.get("recent_savings_rate"))
    savings_slope = _to_float_or_none(summary.get("savings_rate_slope_6m"))
    dsr = _to_float_or_none(summary.get("recent_dsr"))
    if savings_rate is not None and savings_rate < 0.05:
        return "savings_rate"
    if savings_slope is not None and savings_slope < 0:
        return "savings_rate"
    if dsr is not None and dsr >= 0.35:
        return "dsr"
    return "savings_rate"


def _scene(key: str, message: str, language: str = "ko") -> dict[str, str]:
    return {
        "id": key,
        "label": t(f"presentation.{key}.label", language),
        "title": t(f"presentation.{key}.title", language),
        "message": message,
    }


def _analysis_from_main_demo_customer(main_demo_customer: Mapping[str, Any]) -> dict[str, Any]:
    customer_id = str(main_demo_customer["customer_id"])
    match_summary = main_demo_customer.get("match_summary", {})
    top_matches = match_summary.get("top_10", [])
    matches = pd.DataFrame(top_matches)
    matched_ids = []
    if not matches.empty and "matched_customer_id" in matches.columns:
        matched_ids = matches["matched_customer_id"].astype(str).tolist()
    return {
        "customer_id": customer_id,
        "matches": matches,
        "matched_ids": matched_ids,
        "outcome_summary": dict(main_demo_customer["outcome_summary"]),
        "breakpoint_result": dict(main_demo_customer["breakpoint_result"]),
        "whatif_results": dict(main_demo_customer["whatif_results"]),
        "breakpoint_comparison": pd.DataFrame(),
        "matched_future_trajectory": pd.DataFrame(),
        "errors": {},
    }


def _merge_cached_chart_data(analysis: dict[str, Any], customer_id: str, demo_dir: Path) -> dict[str, Any]:
    """Add full cached frames when available while keeping main JSON numbers first."""

    try:
        from src.demo_cache import load_precomputed_demo_analysis

        cached = load_precomputed_demo_analysis(customer_id=customer_id, demo_dir=demo_dir)
    except Exception:  # noqa: BLE001
        return analysis
    merged = dict(cached.analysis)
    merged.update(
        {
            "outcome_summary": analysis["outcome_summary"],
            "breakpoint_result": analysis["breakpoint_result"],
            "whatif_results": analysis["whatif_results"],
            "errors": dict(analysis.get("errors", {})),
        }
    )
    return merged


def _analysis_from_processed_json(customer_id: str, processed_dir: Path) -> dict[str, Any]:
    if not customer_id:
        raise ValueError("customer_id is required for processed JSON fallback")
    outcome_summary = _read_json(processed_dir / settings.OUTCOME_SUMMARY_FILENAME)
    breakpoint_result = _read_json(processed_dir / settings.BREAKPOINT_RESULT_FILENAME)
    whatif_results = _read_json(processed_dir / settings.WHATIF_RESULTS_FILENAME)
    return {
        "customer_id": str(customer_id),
        "matches": pd.DataFrame(),
        "matched_ids": [],
        "outcome_summary": outcome_summary,
        "breakpoint_result": breakpoint_result,
        "whatif_results": whatif_results,
        "breakpoint_comparison": pd.DataFrame(),
        "matched_future_trajectory": pd.DataFrame(),
        "errors": {},
    }


def _summary_from_monthly_or_main(
    monthly_df: pd.DataFrame | None,
    customer_id: str,
    main_demo_customer: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if monthly_df is not None and not monthly_df.empty:
        return build_customer_summary(monthly_df, customer_id)
    if main_demo_customer is not None:
        return _presentation_summary_from_main(main_demo_customer)
    return {"customer_id": str(customer_id)}


def _presentation_summary_from_main(main_demo_customer: Mapping[str, Any]) -> dict[str, Any]:
    """Build a display summary from the main demo JSON without mutating it."""

    summary = build_fallback_customer_summary(dict(main_demo_customer))
    if _to_float_or_none(summary.get("current_cash_balance")) is not None:
        return summary
    starting_profile = main_demo_customer.get("whatif_results", {}).get("starting_profile", {})
    cash_balance = starting_profile.get("cash_balance") if isinstance(starting_profile, Mapping) else None
    if _to_float_or_none(cash_balance) is not None:
        summary["current_cash_balance"] = float(cash_balance)
    return summary


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return value


def _matched_count(outcome_summary: Mapping[str, Any]) -> int:
    if outcome_summary.get("matched_count") is not None:
        return int(outcome_summary["matched_count"])
    outcomes = outcome_summary.get("outcomes", {})
    return int(sum(int(values.get("count", 0)) for values in outcomes.values()))


def _to_float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number
