"""Streamlit app for the Financial Path Twin demo."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings  # noqa: E402
from src.advisor import build_brief_with_fallback  # noqa: E402
from src.copy import APP_MODE_OPTIONS, BUTTON_LABELS, SECTION_COPY, UI_MESSAGES  # noqa: E402
from src.demo_cache import (  # noqa: E402
    MODE_CACHED,
    MODE_FALLBACK,
    MODE_LIVE,
    build_fallback_customer_summary,
    load_precomputed_demo_analysis,
    missing_demo_cache_files,
)
from src.assets import load_hero_svg, load_logo_svg  # noqa: E402
from src.i18n import DEFAULT_LANGUAGE, get_supported_languages, t  # noqa: E402
from src.labels import label_metric  # noqa: E402
from src.ui_components import (  # noqa: E402
    ANALYSIS_METRICS,
    add_balance_ratios,
    build_breakpoint_summary_cards,
    build_best_whatif_card,
    build_customer_summary,
    build_demo_options,
    build_first_screen_view_model,
    build_judge_flow_view_model,
    build_missing_data_guidance,
    build_whatif_comparison_table,
    fit_matcher,
    get_analysis_metric_options,
    get_section_copy,
    load_css,
    load_demo_customers,
    render_brief_panel_html,
    render_customer_identity_html,
    render_hero_html,
    render_info_cards_html,
    render_kpi_cards_html,
    render_rm_customer_detail_header_html,
    render_rm_review_brief_html,
    render_presentation_notice_html,
    render_presentation_scene_heading_html,
    render_status_summary_html,
    run_customer_analysis,
)
from src.presentation import (  # noqa: E402
    GENERAL_MODE,
    PRESENTATION_MODE,
    build_presentation_metric_cards,
    build_presentation_view_model,
    get_presentation_tab_labels,
    load_presentation_payload,
    resolve_presentation_customer_id,
)
from src.daily_worklist import build_daily_worklist, previous_business_day  # noqa: E402
from src.rm_daily_review_view import (  # noqa: E402
    build_rm_customer_detail_view,
    build_rm_daily_review_view,
)
from src.rm_daily_review_loader import load_saved_rm_daily_review  # noqa: E402
from src.rm_review_store import (  # noqa: E402
    REVIEW_COMPLETED,
    REVIEW_FOLLOW_UP,
    REVIEW_MONITOR,
    append_review_event,
    cancel_customer_review,
    create_review_event,
    find_latest_review_event,
    load_review_events,
    replace_customer_review,
)
from src.theme import DESIGN_TOKENS  # noqa: E402
from src.visualizations import (  # noqa: E402
    create_breakpoint_comparison_chart,
    create_current_trajectory_chart,
    create_income_expense_chart,
    create_outcome_bar_chart,
    create_twin_trajectory_chart,
    create_whatif_balance_chart,
    create_whatif_improvement_chart,
)


APP_CONCEPT_SUMMARY = "당신의 미래를 예측하지 않습니다"


RM_DAILY_REVIEW_MODE = "RM 오늘의 업무"
RM_DAILY_REVIEW_SNAPSHOT_DIR = PROJECT_ROOT / "artifacts" / "rm_daily_review" / "monthly"
RM_DAILY_REVIEW_PRESENTATION_OVERLAY_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "rm_daily_review"
    / "presentation"
    / "rm_presentation_overlay.json"
)
RM_DAILY_PANEL_TODAY = "today"
RM_DAILY_PANEL_UPCOMING = "upcoming"
RM_DAILY_PANEL_MONITOR = "monitor"
RM_DAILY_PANEL_COMPLETED = "completed"
RM_DAILY_PANEL_NONE = "none"
RM_DAILY_PANEL_STATE_KEY = "rm_daily_active_panel"
RM_DAILY_HELP_STATE_KEY = "rm_daily_help_visible"
RM_DAILY_SELECTED_COMPLETED_CUSTOMER_STATE_KEY = "rm_selected_completed_customer_id"
RM_DAILY_RECORD_EDIT_STATE_KEY = "rm_daily_record_edit_customer_id"
RM_DAILY_RECORD_CANCEL_CONFIRM_STATE_KEY = "rm_daily_record_cancel_customer_id"
RM_DAILY_VISIBLE_SNAPSHOT_STATE_KEY = "rm_daily_visible_snapshot_id"
RM_DAILY_REVIEW_QUERY_LANGUAGE_STATE_KEY = "rm_daily_review_query_language"
# A display-only work rhythm: Daily timing and ordering stay untouched while
# an RM sees a manageable batch before explicitly expanding the list.
RM_DAILY_ROW_BATCH_SIZE = 5


st.set_page_config(
    page_title="Financial Path Twin",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="collapsed",
)


@dataclass(frozen=True)
class SidebarSelection:
    """User-facing sidebar choices for the presentation dashboard."""

    customer_id: str
    selected_metric: str
    app_mode: str
    presentation_mode: bool
    show_raw_samples: bool
    rm_daily_review_mode: bool = False


@st.cache_data(show_spinner=False)
def load_monthly_data() -> pd.DataFrame:
    """Load monthly data once per file state."""

    return pd.read_csv(settings.CUSTOMER_MONTHLY_PATH)


@st.cache_data(show_spinner=False)
def load_feature_data() -> pd.DataFrame:
    """Load trajectory features once per file state."""

    return pd.read_csv(settings.TRAJECTORY_FEATURES_PATH)


@st.cache_data(show_spinner=False)
def load_demo_data() -> pd.DataFrame:
    """Load demo customer rows once per file state."""

    return load_demo_customers()


@st.cache_data(show_spinner=False)
def load_precomputed_demo_data() -> Any:
    """Load fixed demo artifacts for cached/fallback operation."""

    return load_precomputed_demo_analysis()


@st.cache_resource(show_spinner=False)
def load_matcher(features_df: pd.DataFrame) -> Any:
    """Build the matcher once and reuse it across customer changes."""

    return fit_matcher(features_df)


def main() -> None:
    """Render the one-page presentation flow."""

    language = render_header()
    if st.session_state.get("app_mode") == RM_DAILY_REVIEW_MODE:
        cache_payload = None
        demo_df = pd.DataFrame(columns=settings.DEMO_CUSTOMER_COLUMNS)
    else:
        cache_payload = load_precomputed_demo_safely()
        demo_df = load_demo_data_safely(language)
    selection = render_sidebar(demo_df, cache_payload, language)
    if selection.rm_daily_review_mode:
        render_rm_daily_review_mode(language=language)
        return
    missing_files = [
        path
        for path in (settings.CUSTOMER_MONTHLY_PATH, settings.TRAJECTORY_FEATURES_PATH)
        if not path.exists()
    ]

    runtime_mode = MODE_LIVE
    if missing_files:
        runtime_mode = MODE_FALLBACK
    monthly_df = load_monthly_data() if settings.CUSTOMER_MONTHLY_PATH.exists() else pd.DataFrame()
    features_df = load_feature_data() if settings.TRAJECTORY_FEATURES_PATH.exists() else pd.DataFrame()
    matcher = load_matcher(features_df) if not features_df.empty else None

    if selection.presentation_mode:
        presentation_payload = load_presentation_payload_for_customer(
            demo_dir=settings.DATA_DEMO_DIR,
            processed_dir=settings.DATA_PROCESSED_DIR,
            monthly_df=monthly_df,
            features_df=features_df,
            matcher=matcher,
            customer_id=selection.customer_id,
            language=language,
        )
        if not presentation_payload.is_ready:
            st.warning(presentation_payload.error_message or t("ui.presentation_error", language))
            return
        render_presentation_mode(
            monthly_df,
            demo_df,
            presentation_payload,
            selection,
            language,
        )
        return

    if missing_files and cache_payload is None:
        st.warning(build_missing_data_guidance(missing_files, language=language))
        return

    selected_customer_id = selection.customer_id
    if not selected_customer_id:
        st.info(t("ui.select_customer", language))
        return
    if runtime_mode == MODE_FALLBACK and cache_payload is not None:
        selected_customer_id = cache_payload.customer_id
        selection = SidebarSelection(
            customer_id=selected_customer_id,
            selected_metric=selection.selected_metric,
            app_mode=selection.app_mode,
            presentation_mode=selection.presentation_mode,
            show_raw_samples=selection.show_raw_samples,
        )

    reset_analysis_on_customer_change(selected_customer_id)
    summary = build_summary_safely(monthly_df, selected_customer_id, cache_payload)
    if summary is None:
        st.warning(t("ui.summary_not_ready", language))
        return

    hydrate_cached_analysis(selected_customer_id, cache_payload, runtime_mode)
    analysis = st.session_state.get("analysis")
    render_section_current_flow(
        monthly_df,
        selected_customer_id,
        summary,
        demo_df,
        analysis,
        presentation_mode=selection.presentation_mode,
        language=language,
    )
    render_analysis_action(
        monthly_df,
        features_df,
        matcher,
        selected_customer_id,
        cache_payload,
        language,
    )
    analysis = st.session_state.get("analysis")
    render_section_peer_outcomes(
        monthly_df,
        selected_customer_id,
        summary,
        demo_df,
        analysis,
        selection,
        language,
    )
    render_section_breakpoint(
        analysis,
        presentation_mode=selection.presentation_mode,
        language=language,
    )
    render_section_whatif(
        analysis,
        presentation_mode=selection.presentation_mode,
        language=language,
    )
    render_section_usage(summary, analysis, language=language)


def render_header() -> str:
    """Render the compact product introduction."""

    initialize_language_state()
    css = load_css()
    if css:
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    language = str(st.session_state.get("ui_language", DEFAULT_LANGUAGE))
    header_cols = st.columns([4.6, 1.4])
    with header_cols[1]:
        st.selectbox(
            t("language.label", language),
            options=list(get_supported_languages()),
            format_func=lambda code: get_supported_languages()[code],
            key="ui_language",
        )
        language = str(st.session_state.get("ui_language", DEFAULT_LANGUAGE))
    with header_cols[0]:
        st.markdown(
            render_hero_html(
                logo_svg=load_logo_svg(),
                hero_svg=load_hero_svg(),
                language=language,
            ),
            unsafe_allow_html=True,
        )
    return language


def initialize_language_state() -> None:
    """Initialize UI language without touching customer or analysis state."""

    if "ui_language" not in st.session_state:
        st.session_state["ui_language"] = DEFAULT_LANGUAGE


def load_demo_data_safely(language: str = "ko") -> pd.DataFrame:
    """Load demo data and show a non-blocking message if it is missing."""

    try:
        return load_demo_data()
    except FileNotFoundError:
        st.sidebar.warning(t("ui.demo_list_missing", language))
        return pd.DataFrame(columns=settings.DEMO_CUSTOMER_COLUMNS)
    except Exception:  # noqa: BLE001
        st.sidebar.warning(t("ui.demo_list_unreadable", language))
        return pd.DataFrame(columns=settings.DEMO_CUSTOMER_COLUMNS)


def load_precomputed_demo_safely() -> Any | None:
    """Load precomputed demo files without exposing technical details."""

    if missing_demo_cache_files():
        return None
    try:
        return load_precomputed_demo_data()
    except Exception:  # noqa: BLE001
        return None


def load_presentation_payload_for_customer(
    *,
    demo_dir: Path,
    processed_dir: Path,
    monthly_df: pd.DataFrame,
    features_df: pd.DataFrame,
    matcher: Any,
    customer_id: str,
    language: str,
) -> Any:
    """Cache each prepared presentation payload across tab and language reruns."""

    payloads = st.session_state.setdefault("presentation_payloads", {})
    cached = payloads.get(str(customer_id))
    if cached is not None:
        return cached
    payload = load_presentation_payload(
        demo_dir=demo_dir,
        processed_dir=processed_dir,
        monthly_df=monthly_df,
        features_df=features_df,
        matcher=matcher,
        customer_id=customer_id,
        language=language,
    )
    if payload.is_ready:
        payloads[str(customer_id)] = payload
    return payload


def build_summary_safely(
    monthly_df: pd.DataFrame,
    customer_id: str,
    cache_payload: Any | None,
) -> dict[str, Any] | None:
    """Build current summary, falling back to fixed demo metrics."""

    try:
        if not monthly_df.empty:
            return build_customer_summary(monthly_df, customer_id)
    except Exception:  # noqa: BLE001
        pass
    if cache_payload is not None and str(customer_id) == str(cache_payload.customer_id):
        return build_fallback_customer_summary(cache_payload.main_demo_customer)
    return None


def reset_analysis_on_customer_change(customer_id: str) -> None:
    """Clear stale analysis when the selected customer changes."""

    if st.session_state.get("selected_customer_id") != customer_id:
        st.session_state["selected_customer_id"] = customer_id
        st.session_state.pop("analysis", None)
        st.session_state.pop("analysis_mode", None)


def hydrate_cached_analysis(customer_id: str, cache_payload: Any | None, runtime_mode: str) -> None:
    """Use the fixed main demo analysis when it matches the selected customer."""

    if cache_payload is None or str(customer_id) != str(cache_payload.customer_id):
        return
    if "analysis" not in st.session_state:
        st.session_state["analysis"] = cache_payload.analysis
        st.session_state["analysis_mode"] = MODE_FALLBACK if runtime_mode == MODE_FALLBACK else MODE_CACHED


def render_sidebar(demo_df: pd.DataFrame, cache_payload: Any | None, language: str = "ko") -> SidebarSelection:
    """Render only presenter-facing controls needed for the main story."""

    st.sidebar.header(t("mode.settings", language))
    app_mode_options = (*APP_MODE_OPTIONS, RM_DAILY_REVIEW_MODE)
    app_mode = st.sidebar.selectbox(
        t("mode.selector", language),
        list(app_mode_options),
        index=list(app_mode_options).index(PRESENTATION_MODE),
        format_func=lambda mode: (
            t("mode.rm_daily", language)
            if mode == RM_DAILY_REVIEW_MODE
            else t("mode.presentation" if mode == PRESENTATION_MODE else "mode.normal", language)
        ),
        key="app_mode",
    )
    presentation_mode = app_mode == PRESENTATION_MODE
    rm_daily_review_mode = app_mode == RM_DAILY_REVIEW_MODE
    if rm_daily_review_mode:
        st.sidebar.caption(t("rm.subtitle", language))
        return SidebarSelection(
            customer_id="",
            selected_metric="",
            app_mode=app_mode,
            presentation_mode=False,
            show_raw_samples=False,
            rm_daily_review_mode=True,
        )
    demo_options = build_demo_options(demo_df, language=language)
    if cache_payload is not None and not any(option["customer_id"] == cache_payload.customer_id for option in demo_options):
        demo_options.insert(
            0,
            {
                "label": f"{t('demo_role.main', language)} ({cache_payload.customer_id})",
                "role": "main",
                "customer_id": cache_payload.customer_id,
            },
        )

    if presentation_mode:
        default_customer_id = resolve_presentation_customer_id(
            demo_df=demo_df,
            main_demo_customer=cache_payload.main_demo_customer if cache_payload is not None else None,
        )
        customer_options = [option["customer_id"] for option in demo_options]
        option_by_id = {option["customer_id"]: option for option in demo_options}
        st.sidebar.caption(t("ui.presentation_main_default", language))
        if customer_options:
            default_index = customer_options.index(default_customer_id) if default_customer_id in customer_options else 0
            customer_id = st.sidebar.selectbox(
                t("customer.selector", language),
                customer_options,
                index=default_index,
                format_func=lambda option_id: option_by_id.get(option_id, {"label": option_id})["label"],
                key="presentation_customer_selector",
            )
            selected_option = option_by_id[customer_id]
            st.session_state["selected_demo_role"] = selected_option["role"]
            st.sidebar.caption(t("customer.demo_role_caption", language, role=selected_option["label"].split(" (")[0]))
        else:
            customer_id = default_customer_id
    else:
        manual_option = "__manual_customer_id__"
        customer_options = [option["customer_id"] for option in demo_options]
        customer_options.append(manual_option)
        option_by_id = {option["customer_id"]: option for option in demo_options}
        selected_customer_option = st.sidebar.selectbox(
            t("customer.selector", language),
            customer_options,
            index=0,
            format_func=lambda option_id: (
                t("customer.direct_input", language)
                if option_id == manual_option
                else option_by_id.get(option_id, {"label": option_id})["label"]
            ),
            key="customer_selector",
        )

        if selected_customer_option == manual_option:
            customer_id = st.sidebar.text_input(t("customer.id", language), value="", key="customer_id_input")
        else:
            selected_option = option_by_id[selected_customer_option]
            customer_id = selected_option["customer_id"]
            st.session_state["selected_demo_role"] = selected_option["role"]
            st.sidebar.caption(t("customer.demo_role_caption", language, role=selected_option["label"].split(" (")[0]))

    analysis_metric_options = get_analysis_metric_options(language)
    selected_metric = st.sidebar.selectbox(
        t(
            "sidebar.presentation_metric_selector"
            if presentation_mode
            else "sidebar.metric_selector",
            language,
        ),
        list(analysis_metric_options),
        index=0,
        format_func=lambda metric: analysis_metric_options[metric],
        key="selected_metric",
    )
    if presentation_mode:
        show_raw_samples = False
        st.sidebar.caption(t("ui.raw_hidden", language))
    else:
        show_raw_samples = st.sidebar.checkbox(
            t("sidebar.raw_samples", language),
            value=False,
            help=t("sidebar.raw_samples_help", language),
            key="show_raw_samples",
        )
    return SidebarSelection(
        customer_id=str(customer_id).strip(),
        selected_metric=selected_metric,
        app_mode=app_mode,
        presentation_mode=bool(presentation_mode),
        show_raw_samples=bool(show_raw_samples),
        rm_daily_review_mode=False,
    )


def load_latest_rm_snapshot_artifact(
    snapshot_dir: Path = RM_DAILY_REVIEW_SNAPSHOT_DIR,
) -> tuple[Path, dict[str, object]] | None:
    """Read the most recently written standalone monthly Snapshot artifact."""

    if not snapshot_dir.exists():
        return None
    snapshot_paths = [
        path
        for path in snapshot_dir.glob("*.json")
        if not path.name.endswith("_workload_report.json")
    ]
    if not snapshot_paths:
        return None
    latest_path = max(snapshot_paths, key=lambda path: (path.stat().st_mtime_ns, path.name))
    payload = json.loads(latest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Monthly Snapshot artifact must contain a JSON object.")
    return latest_path, payload


def build_rm_daily_review_worklist(
    snapshot_artifact: dict[str, object],
    *,
    snapshot_path: Path,
    daily_date: date,
) -> Any:
    """Build Daily work solely from a saved Snapshot and manual review events."""

    review_events = load_review_events()
    snapshot_id = str(snapshot_artifact.get("snapshot_id") or "")
    completed_customer_ids = {
        event.customer_id
        for event in review_events
        if event.snapshot_id == snapshot_id
    }
    completed_today_customer_ids = {
        event.customer_id
        for event in review_events
        if event.snapshot_id == snapshot_id
        and event.reviewed_at.astimezone().date() == daily_date
    }
    previous_workday_completed_count = sum(
        1
        for event in review_events
        if event.snapshot_id == snapshot_id
        and event.reviewed_at.astimezone().date() == previous_business_day(daily_date)
    )
    return build_daily_worklist(
        snapshot_artifact,
        daily_date=daily_date,
        completed_customer_ids=completed_customer_ids,
        completed_today_customer_ids=completed_today_customer_ids,
        previous_workday_completed_count=previous_workday_completed_count,
        snapshot_published_on=datetime.fromtimestamp(snapshot_path.stat().st_mtime).date(),
    )


def _build_rm_daily_kpi_cards(
    dashboard: Any,
    *,
    language: str,
) -> list[dict[str, str]]:
    """Build four operational cards using only the saved Daily view model."""

    card_specs = (
        (
            t("rm.metric.today", language),
            dashboard.today_count,
            t("rm.summary.today", language),
            "watch",
        ),
        (
            t("rm.metric.upcoming", language),
            dashboard.upcoming_count,
            t("rm.summary.upcoming", language),
            "watch",
        ),
        (
            t("rm.metric.monitor", language),
            dashboard.monitor_count,
            t("rm.summary.monitor", language),
            "neutral",
        ),
        (
            t("rm.metric.completed", language),
            dashboard.completed_today_count,
            t(
                "rm.summary.completed_on",
                language,
                date=_format_rm_plan_date(dashboard.freshness.daily_date, language),
            ),
            "stable",
        ),
    )
    return [
        {
            "title": label,
            "value": t("rm.people", language, count=count),
            "description": description,
            "detail": t("rm.kpi.snapshot_source", language),
            "tone": tone,
        }
        for label, count, description, tone in card_specs
    ]


def _render_rm_daily_kpi_cards(
    dashboard: Any,
    *,
    language: str,
) -> str:
    """Render one operational KPI row and its directly associated actions.

    The cards deliberately use the shared General/Presentation KPI treatment.
    Their controls open the related list below, instead of repeating the same
    counts in a second selector-card row.
    """

    cards = _build_rm_daily_kpi_cards(dashboard, language=language)
    st.markdown(
        render_kpi_cards_html(cards, language=language, grid_columns=4),
        unsafe_allow_html=True,
    )
    active_panel = str(
        st.session_state.get(RM_DAILY_PANEL_STATE_KEY, RM_DAILY_PANEL_NONE)
    )
    action_specs = (
        (RM_DAILY_PANEL_TODAY, t("rm.metric.today", language)),
        (RM_DAILY_PANEL_UPCOMING, t("rm.metric.upcoming", language)),
        (RM_DAILY_PANEL_MONITOR, t("rm.metric.monitor", language)),
        (RM_DAILY_PANEL_COMPLETED, t("rm.metric.completed", language)),
    )
    for column, (panel_key, panel_label) in zip(st.columns(4), action_specs):
        with column:
            is_active = active_panel == panel_key
            if st.button(
                t("rm.panel.close", language)
                if is_active
                else t("rm.panel.open", language),
                key=f"rm_daily_kpi_action_{panel_key}",
                use_container_width=True,
                help=panel_label,
            ):
                st.session_state[RM_DAILY_PANEL_STATE_KEY] = (
                    RM_DAILY_PANEL_NONE if is_active else panel_key
                )
                st.session_state.pop("rm_selected_customer_id", None)
                st.session_state.pop(RM_DAILY_SELECTED_COMPLETED_CUSTOMER_STATE_KEY, None)
                active_panel = RM_DAILY_PANEL_NONE if is_active else panel_key
    return active_panel


def _render_rm_daily_planning_summary(
    dashboard: Any,
    *,
    language: str,
) -> None:
    """Show a saved-work horizon without changing any timing bucket."""

    plan = dashboard.planning
    next_workday_label = _format_rm_plan_date(plan.next_workday, language)
    previous_workday_label = _format_rm_plan_date(plan.previous_workday, language)
    cards = [
        {
            "title": t("rm.planning.today", language),
            "value": t("rm.people", language, count=len(plan.today_items)),
            "detail": t(
                "rm.planning.today.detail",
                language,
                date=_format_rm_plan_date(plan.effective_workday, language),
            ),
            "tone": "watch",
        },
        {
            "title": t("rm.planning.next_workday", language),
            "value": t("rm.people", language, count=len(plan.next_workday_items)),
            "detail": t("rm.planning.next_workday.detail", language, date=next_workday_label),
            "tone": "watch",
        },
        {
            "title": t("rm.planning.this_month", language),
            "value": t("rm.people", language, count=len(plan.this_month_items)),
            "detail": t("rm.planning.this_month.detail", language),
            "tone": "neutral",
        },
        {
            "title": t("rm.planning.next_month", language),
            "value": t("rm.people", language, count=len(plan.next_month_items)),
            "detail": t("rm.planning.next_month.detail", language),
            "tone": "stable",
        },
        {
            "title": t("rm.planning.previous_completed", language),
            "value": t(
                "rm.people",
                language,
                count=plan.previous_workday_completed_count,
            ),
            "detail": t(
                "rm.planning.previous_completed.detail",
                language,
                date=previous_workday_label,
            ),
            "tone": "neutral",
        },
    ]
    heading_column, help_column = st.columns([6.0, 1.0])
    with heading_column:
        st.markdown(f"##### {t('rm.planning.title', language)}")
    with help_column:
        help_visible = bool(st.session_state.get(RM_DAILY_HELP_STATE_KEY, False))
        if st.button(
            f"ⓘ {t('rm.help.title', language)}",
            key="rm_daily_help_link",
            use_container_width=True,
        ):
            st.session_state[RM_DAILY_HELP_STATE_KEY] = not help_visible
            help_visible = not help_visible
    if help_visible:
        _render_rm_daily_help(language)
    if plan.effective_workday != dashboard.freshness.daily_date:
        st.caption(
            t(
                "rm.planning.non_business_day_notice",
                language,
                workday=_format_rm_plan_date(plan.effective_workday, language),
                record_date=_format_rm_plan_date(
                    dashboard.freshness.daily_date,
                    language,
                ),
            )
        )
    else:
        st.caption(t("rm.planning.notice", language))
    st.markdown(
        render_info_cards_html(cards, t("rm.planning.title", language)),
        unsafe_allow_html=True,
    )


def _format_rm_plan_date(value: date, language: str) -> str:
    return value.strftime("%Y.%m.%d" if language == "ko" else "%Y-%m-%d")


def _render_rm_daily_selected_panel(
    active_panel: str,
    dashboard: Any,
    *,
    language: str,
) -> None:
    """Render only the panel chosen above the detail area."""

    if active_panel == RM_DAILY_PANEL_NONE:
        return

    if active_panel == RM_DAILY_PANEL_TODAY:
        st.subheader(t("rm.list.today.title", language))
        st.caption(
            t(
                "rm.planning.batch_notice",
                language,
                date=_format_rm_plan_date(
                    dashboard.planning.effective_workday,
                    language,
                ),
            )
        )
        _render_rm_customer_rows(
            dashboard.today_items,
            key_prefix="rm_today",
            language=language,
        )
        with st.expander(
            t(
                "rm.planning.next_workday.list",
                language,
                date=_format_rm_plan_date(dashboard.planning.next_workday, language),
                count=len(dashboard.planning.next_workday_items),
            ),
            expanded=False,
        ):
            _render_rm_customer_rows(
                dashboard.planning.next_workday_items,
                key_prefix="rm_next_workday",
                language=language,
            )
        with st.expander(
            t(
                "rm.planning.this_month.list",
                language,
                count=len(dashboard.planning.this_month_items),
            ),
            expanded=False,
        ):
            _render_rm_customer_rows(
                dashboard.planning.this_month_items,
                key_prefix="rm_this_month",
                language=language,
            )
        with st.expander(
            t(
                "rm.planning.next_month.list",
                language,
                count=len(dashboard.planning.next_month_items),
            ),
            expanded=False,
        ):
            _render_rm_customer_rows(
                dashboard.planning.next_month_items,
                key_prefix="rm_next_month",
                language=language,
            )
        return

    if active_panel == RM_DAILY_PANEL_UPCOMING:
        st.subheader(t("rm.list.upcoming.title", language))
        core_only = st.checkbox(t("rm.filter.core_only", language), key="rm_upcoming_core_only")
        upcoming_rows = dashboard.upcoming_items
        if core_only:
            upcoming_rows = tuple(
                row
                for row in upcoming_rows
                if row.relationship_badge == t("rm.relationship.core", language)
            )
        _render_rm_customer_rows(upcoming_rows, key_prefix="rm_upcoming", language=language)
        return

    if active_panel == RM_DAILY_PANEL_MONITOR:
        st.subheader(t("rm.list.monitor.title", language))
        st.caption(t("rm.monitor.summary", language, count=dashboard.monitor_count))
        monitor_search = st.text_input(t("rm.monitor.search", language), key="rm_monitor_search")
        if monitor_search.strip():
            matches = tuple(
                row
                for row in dashboard.customer_list
                if row.review_state_label == t("rm.state.monitor", language)
                if monitor_search.strip().upper() in row.customer_id.upper()
            )
            _render_rm_customer_rows(matches, key_prefix="rm_monitor", language=language)
        return

    if active_panel != RM_DAILY_PANEL_COMPLETED:
        return

    st.subheader(t("rm.completed.title", language, count=dashboard.completed_today_count))
    if not dashboard.completed_items:
        st.caption(t("rm.completed.empty", language))
        return
    _render_rm_completed_customer_rows(
        dashboard.completed_items,
        language=language,
    )


def _render_rm_daily_help(language: str) -> None:
    """Show the optional glossary beside the work-plan context."""

    st.caption(t("rm.panel.help.description", language))
    for help_key in (
        "rm.help.breakpoint",
        "rm.help.daily_review",
        "rm.help.relationship",
        "rm.help.upcoming",
    ):
        st.caption(t(help_key, language))


def render_rm_daily_review_mode(
    *,
    daily_date: date | None = None,
    language: str = DEFAULT_LANGUAGE,
) -> None:
    """Render the saved-work first screen without loading live analytics."""

    st.title(t("rm.dashboard.title", language))
    st.caption(t("rm.dashboard.subtitle", language))
    result_state_key = "rm_daily_review_query_result"
    loaded_at_state_key = "rm_daily_review_last_loaded_at"
    query_language_state_key = RM_DAILY_REVIEW_QUERY_LANGUAGE_STATE_KEY
    query_result = st.session_state.get(result_state_key)
    loaded_query_language = str(st.session_state.get(query_language_state_key) or "")
    refresh_after_review = bool(
        st.session_state.pop("rm_daily_review_refresh_after_review", False)
    )
    current_date = daily_date or date.today()

    if query_result is None:
        if not st.button(t("rm.query.button", language), key="rm_daily_review_query"):
            return
        st.session_state.pop(RM_DAILY_PANEL_STATE_KEY, None)
        st.session_state.pop("rm_selected_customer_id", None)
        st.session_state.pop(RM_DAILY_SELECTED_COMPLETED_CUSTOMER_STATE_KEY, None)
    if query_result is None or loaded_query_language != language:
        with st.spinner(t("rm.query.loading", language)):
            query_result = load_saved_rm_daily_review(
                daily_date=current_date,
                snapshot_directory=RM_DAILY_REVIEW_SNAPSHOT_DIR,
                presentation_overlay_path=RM_DAILY_REVIEW_PRESENTATION_OVERLAY_PATH,
                language=language,
            )
        st.session_state[result_state_key] = query_result
        st.session_state[loaded_at_state_key] = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
        st.session_state[query_language_state_key] = language
    if getattr(query_result, "status", None) == "READY":
        header_action, header_status = st.columns([1.2, 4.8])
        with header_action:
            refresh_requested = st.button(t("rm.refresh", language), key="rm_daily_review_refresh")
        with header_status:
            last_loaded_at = str(st.session_state.get(loaded_at_state_key) or "-")
            st.caption(t("rm.loaded_at", language, time=last_loaded_at))
        if refresh_requested or refresh_after_review:
            with st.spinner(t("rm.query.loading", language)):
                query_result = load_saved_rm_daily_review(
                    daily_date=current_date,
                    snapshot_directory=RM_DAILY_REVIEW_SNAPSHOT_DIR,
                    presentation_overlay_path=RM_DAILY_REVIEW_PRESENTATION_OVERLAY_PATH,
                    language=language,
            )
            st.session_state[result_state_key] = query_result
            st.session_state[loaded_at_state_key] = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
            st.session_state[query_language_state_key] = language

    assert query_result is not None
    if query_result.status != "READY":
        if query_result.status == "MISSING_SNAPSHOT":
            st.info(query_result.message)
        else:
            st.warning(query_result.message)
        st.code(query_result.cli_command, language="bash")
        return

    assert query_result.worklist is not None
    assert query_result.dashboard is not None
    worklist = query_result.worklist
    dashboard = query_result.dashboard
    _reset_rm_daily_row_batches_for_snapshot(dashboard.snapshot_id)

    completion_message = st.session_state.pop("rm_daily_review_completion_message", None)
    if completion_message:
        st.success(t("rm.done.title", language))
        st.caption(str(completion_message))
        st.caption(t("rm.done.remaining", language, count=dashboard.today_count))
        if st.button(t("rm.done.back", language), key="rm_daily_review_done_back"):
            st.session_state.pop("rm_selected_customer_id", None)
    st.caption(f"{dashboard.analysis_as_of_label} · {dashboard.snapshot_freshness_label}")
    st.caption(
        t(
            "rm.date_context",
            language,
            record_date=_format_rm_plan_date(dashboard.freshness.daily_date, language),
            work_date=_format_rm_plan_date(
                dashboard.planning.effective_workday,
                language,
            ),
        )
    )
    st.caption(t("rm.today_review_criterion", language))
    st.markdown(f"##### {t('rm.status.title', language)}")
    active_panel = _render_rm_daily_kpi_cards(dashboard, language=language)

    selected_customer_id = st.session_state.get("rm_selected_customer_id")
    if selected_customer_id and active_panel in {
        RM_DAILY_PANEL_TODAY,
        RM_DAILY_PANEL_UPCOMING,
        RM_DAILY_PANEL_MONITOR,
    }:
        _render_rm_customer_detail(
            worklist,
            dashboard,
            str(selected_customer_id),
            language=language,
        )
    if active_panel != RM_DAILY_PANEL_NONE:
        st.divider()
        _render_rm_daily_selected_panel(active_panel, dashboard, language=language)
    selected_completed_customer_id = st.session_state.get(
        RM_DAILY_SELECTED_COMPLETED_CUSTOMER_STATE_KEY
    )
    if selected_completed_customer_id and active_panel == RM_DAILY_PANEL_COMPLETED:
        _render_rm_completed_record(
            dashboard,
            str(selected_completed_customer_id),
            language=language,
        )

    st.divider()
    _render_rm_daily_planning_summary(dashboard, language=language)



def _render_rm_snapshot_cli_guidance() -> None:
    st.code("python scripts/build_rm_monthly_snapshot.py --snapshot-id YYYY-MM", language="bash")


def _render_rm_customer_rows(
    rows: tuple[Any, ...],
    *,
    key_prefix: str,
    language: str = DEFAULT_LANGUAGE,
) -> None:
    if not rows:
        st.info(t("rm.list.empty", language))
        return
    visible_count_key = f"{key_prefix}_visible_count"
    visible_count = _rm_daily_visible_row_count(
        st.session_state.get(visible_count_key),
        total_rows=len(rows),
    )
    visible_rows = _visible_rm_daily_rows(rows, visible_count=visible_count)
    column_widths = [1.65, 1.15, 2.4, 1.05, 1.55, 0.8]
    header_columns = st.columns(column_widths)
    for column, label in zip(
        header_columns,
        (
            t("rm.row.customer", language),
            t("rm.row.relationship", language),
            t("rm.row.reason", language),
            t("rm.row.timing", language),
            t("rm.row.change", language),
            t("rm.row.action", language),
        ),
    ):
        with column:
            st.caption(label)
    for row in visible_rows:
        columns = st.columns(column_widths)
        with columns[0]:
            st.markdown(f"**{row.display_name}**")
            st.caption(row.customer_id)
        with columns[1]:
            st.caption(row.relationship_badge)
            st.caption(t("rm.relationship.overlay_notice", language))
        with columns[2]:
            st.write(row.why_today)
        with columns[3]:
            st.caption(_format_rm_timing(row.timing_months, language))
        with columns[4]:
            st.caption(" · ".join(row.current_change_summary))
        with columns[5]:
            if st.button(t("rm.customer.open", language), key=f"{key_prefix}_{row.customer_id}"):
                st.session_state["rm_selected_customer_id"] = row.customer_id
                st.rerun()
    st.caption(
        t(
            "rm.list.visible_count",
            language,
            shown=len(visible_rows),
            total=len(rows),
        )
    )
    if len(visible_rows) < len(rows):
        next_batch_count = min(RM_DAILY_ROW_BATCH_SIZE, len(rows) - len(visible_rows))
        if st.button(
            t("rm.list.show_more", language, count=next_batch_count),
            key=f"{key_prefix}_show_more",
        ):
            st.session_state[visible_count_key] = len(visible_rows) + RM_DAILY_ROW_BATCH_SIZE
            st.rerun()
    elif len(rows) > RM_DAILY_ROW_BATCH_SIZE:
        if st.button(
            t("rm.list.collapse", language, count=RM_DAILY_ROW_BATCH_SIZE),
            key=f"{key_prefix}_collapse",
        ):
            st.session_state[visible_count_key] = RM_DAILY_ROW_BATCH_SIZE
            st.rerun()


def _rm_daily_visible_row_count(value: object, *, total_rows: int) -> int:
    """Normalize the session-only display count without changing the worklist."""

    try:
        requested_count = int(value) if value is not None else RM_DAILY_ROW_BATCH_SIZE
    except (TypeError, ValueError):
        requested_count = RM_DAILY_ROW_BATCH_SIZE
    return min(total_rows, max(RM_DAILY_ROW_BATCH_SIZE, requested_count))


def _reset_rm_daily_row_batches_for_snapshot(snapshot_id: str) -> None:
    """Return a new saved Snapshot to the first five-customer display batch."""

    if st.session_state.get(RM_DAILY_VISIBLE_SNAPSHOT_STATE_KEY) == snapshot_id:
        return
    st.session_state[RM_DAILY_VISIBLE_SNAPSHOT_STATE_KEY] = snapshot_id
    for key_prefix in (
        "rm_today",
        "rm_next_workday",
        "rm_this_month",
        "rm_next_month",
        "rm_upcoming",
    ):
        st.session_state.pop(f"{key_prefix}_visible_count", None)


def _visible_rm_daily_rows(rows: tuple[Any, ...], *, visible_count: int) -> tuple[Any, ...]:
    """Return the deterministic display slice; it never filters or ranks work."""

    return rows[:max(0, int(visible_count))]


def _format_rm_timing(timing_months: int | None, language: str) -> str:
    """Format the saved breakpoint timing without adjusting it by calendar day."""

    if timing_months == 1:
        return t("rm.timing.within_month", language)
    if isinstance(timing_months, int) and timing_months > 1:
        return t("rm.timing.within_months", language, months=timing_months)
    return t("rm.timing.check_needed", language)


def _render_rm_completed_customer_rows(
    rows: tuple[Any, ...],
    *,
    language: str = DEFAULT_LANGUAGE,
) -> None:
    if not rows:
        st.info(t("rm.completed.empty", language))
        return
    for row in rows:
        columns = st.columns([1.2, 1.2, 3.8, 1.0])
        with columns[0]:
            st.markdown(f"**{row.display_name}**")
            st.caption(row.customer_id)
        with columns[1]:
            st.caption(row.relationship_badge)
        with columns[2]:
            st.caption(t("rm.completed.row", language))
        with columns[3]:
            if st.button(t("rm.completed.open", language), key=f"rm_completed_{row.customer_id}"):
                st.session_state[RM_DAILY_SELECTED_COMPLETED_CUSTOMER_STATE_KEY] = row.customer_id


def _render_rm_completed_record(
    dashboard: Any,
    customer_id: str,
    *,
    language: str = DEFAULT_LANGUAGE,
) -> None:
    """Show and maintain one saved RM review record without analytics or Cases."""

    completed_item = next(
        (
            item
            for item in dashboard.completed_items
            if item.customer_id == customer_id
        ),
        None,
    )
    if completed_item is None:
        st.session_state.pop(RM_DAILY_SELECTED_COMPLETED_CUSTOMER_STATE_KEY, None)
        st.warning(t("rm.record.not_found", language))
        return
    try:
        review_event = find_latest_review_event(
            load_review_events(),
            customer_id=customer_id,
            snapshot_id=dashboard.snapshot_id,
        )
    except (OSError, ValueError):
        review_event = None
    if review_event is None:
        st.warning(t("rm.record.not_found", language))
        return

    st.divider()
    st.subheader(t("rm.record.title", language))
    st.markdown(f"**{completed_item.display_name}** ({completed_item.customer_id})")
    st.caption(completed_item.relationship_badge)
    st.caption(
        t(
            "rm.record.saved_at",
            language,
            time=_format_rm_recorded_at(review_event.reviewed_at, language),
        )
    )
    result_labels = _rm_review_result_labels(language)
    st.markdown(f"**{t('rm.record.result', language)}**")
    st.write(result_labels[review_event.result])
    st.markdown(f"**{t('rm.record.note', language)}**")
    st.write(review_event.note or t("rm.record.no_note", language))

    is_editing = (
        st.session_state.get(RM_DAILY_RECORD_EDIT_STATE_KEY) == customer_id
    )
    is_confirming_cancel = (
        st.session_state.get(RM_DAILY_RECORD_CANCEL_CONFIRM_STATE_KEY) == customer_id
    )
    if is_editing:
        _render_rm_review_record_editor(
            review_event,
            result_labels=result_labels,
            language=language,
        )
        return
    if is_confirming_cancel:
        st.warning(t("rm.record.cancel_confirm", language))
        confirm_column, back_column = st.columns(2)
        with confirm_column:
            if st.button(
                t("rm.record.cancel_confirm_button", language),
                key=f"rm_record_confirm_cancel_{customer_id}",
                type="primary",
            ):
                try:
                    cancelled_count = cancel_customer_review(
                        customer_id=customer_id,
                        snapshot_id=dashboard.snapshot_id,
                    )
                except (OSError, ValueError):
                    st.warning(t("rm.record.save_error", language))
                    return
                if cancelled_count:
                    _finish_rm_review_record_change(
                        customer_id,
                        message=t("rm.record.cancelled", language),
                    )
                else:
                    st.warning(t("rm.record.not_found", language))
        with back_column:
            if st.button(t("rm.record.back", language), key=f"rm_record_cancel_back_{customer_id}"):
                st.session_state.pop(RM_DAILY_RECORD_CANCEL_CONFIRM_STATE_KEY, None)
                st.rerun()
        return

    edit_column, cancel_column, back_column = st.columns(3)
    with edit_column:
        if st.button(t("rm.record.edit", language), key=f"rm_record_edit_{customer_id}"):
            st.session_state[RM_DAILY_RECORD_EDIT_STATE_KEY] = customer_id
            st.rerun()
    with cancel_column:
        if st.button(t("rm.record.cancel", language), key=f"rm_record_cancel_{customer_id}"):
            st.session_state[RM_DAILY_RECORD_CANCEL_CONFIRM_STATE_KEY] = customer_id
            st.rerun()
    with back_column:
        if st.button(t("rm.record.back", language), key=f"rm_record_back_{customer_id}"):
            st.session_state.pop(RM_DAILY_SELECTED_COMPLETED_CUSTOMER_STATE_KEY, None)
            st.rerun()


def _render_rm_review_record_editor(
    review_event: Any,
    *,
    result_labels: dict[str, str],
    language: str,
) -> None:
    """Edit the selected standalone RM record in place before saving once."""

    result_values = tuple(result_labels)
    current_index = result_values.index(review_event.result)
    selected_result = st.selectbox(
        t("rm.record.edit_result", language),
        result_values,
        index=current_index,
        format_func=lambda value: result_labels[value],
        key=f"rm_record_edit_result_{review_event.customer_id}",
    )
    updated_note = st.text_area(
        t("rm.record.edit_note", language),
        value=review_event.note or "",
        key=f"rm_record_edit_note_{review_event.customer_id}",
    )
    save_column, close_column = st.columns(2)
    with save_column:
        if st.button(
            t("rm.record.update_save", language),
            key=f"rm_record_update_{review_event.customer_id}",
            type="primary",
        ):
            updated_event = create_review_event(
                customer_id=review_event.customer_id,
                snapshot_id=review_event.snapshot_id,
                reviewed_at=datetime.now().astimezone(),
                result=selected_result,
                note=updated_note,
            )
            try:
                replace_customer_review(updated_event)
            except (OSError, ValueError):
                st.warning(t("rm.record.save_error", language))
                return
            _finish_rm_review_record_change(
                review_event.customer_id,
                message=t("rm.record.updated", language),
            )
    with close_column:
        if st.button(
            t("rm.record.close_edit", language),
            key=f"rm_record_close_edit_{review_event.customer_id}",
        ):
            st.session_state.pop(RM_DAILY_RECORD_EDIT_STATE_KEY, None)
            st.rerun()


def _rm_review_result_labels(language: str) -> dict[str, str]:
    return {
        REVIEW_COMPLETED: t("rm.result.completed", language),
        REVIEW_FOLLOW_UP: t("rm.result.follow_up", language),
        REVIEW_MONITOR: t("rm.result.monitor", language),
    }


def _format_rm_recorded_at(value: datetime, language: str) -> str:
    localized = value.astimezone()
    return localized.strftime("%Y.%m.%d %H:%M" if language == "ko" else "%Y-%m-%d %H:%M")


def _finish_rm_review_record_change(customer_id: str, *, message: str) -> None:
    """Clear record-editor state and reload only the saved Daily projection."""

    st.session_state.pop(RM_DAILY_SELECTED_COMPLETED_CUSTOMER_STATE_KEY, None)
    st.session_state.pop(RM_DAILY_RECORD_EDIT_STATE_KEY, None)
    st.session_state.pop(RM_DAILY_RECORD_CANCEL_CONFIRM_STATE_KEY, None)
    st.session_state.pop(f"rm_record_edit_result_{customer_id}", None)
    st.session_state.pop(f"rm_record_edit_note_{customer_id}", None)
    st.session_state["rm_daily_review_completion_message"] = message
    st.session_state["rm_daily_review_refresh_after_review"] = True
    st.rerun()


def _render_rm_customer_detail(
    worklist: Any,
    dashboard: Any,
    customer_id: str,
    *,
    language: str = DEFAULT_LANGUAGE,
) -> None:
    try:
        detail = build_rm_customer_detail_view(
            worklist,
            customer_id,
            presentation_metadata_by_customer=_presentation_metadata_from_dashboard(dashboard),
            language=language,
        )
    except ValueError:
        st.session_state.pop("rm_selected_customer_id", None)
        return
    st.divider()
    header_column, action_column = st.columns([5.0, 0.9])
    with header_column:
        st.markdown(
            render_rm_customer_detail_header_html(
                display_name=detail.display_name,
                customer_id=detail.customer_id,
                presentation_label=detail.presentation_label or t("rm.detail.identity", language),
                relationship_label=t("rm.detail.relationship_badge", language),
                relationship_value=detail.relationship_badge,
                relationship_note=t("rm.detail.relationship_badge_notice", language),
            ),
            unsafe_allow_html=True,
        )
    with action_column:
        st.caption(t("rm.detail.flow", language))
        if st.button(
            t("rm.detail.back_to_list", language),
            key=f"rm_detail_back_{detail.customer_id}",
            use_container_width=True,
        ):
            st.session_state.pop("rm_selected_customer_id", None)
            st.rerun()
    _render_rm_detail_evidence_at_a_glance(detail, language=language)
    st.markdown(f"#### {t('rm.detail.relationship', language)}")
    st.write(detail.relationship_badge)
    st.caption(detail.relationship_context)
    st.caption(t("rm.detail.relationship_separate", language))
    st.markdown(f"#### {t('rm.detail.conversation', language)}")
    _render_rm_conversation_steps(detail, language=language)
    with st.expander(t("rm.detail.analysis", language), expanded=False):
        st.caption(detail.supporting_analysis.evidence_status_message)
        for summary in detail.supporting_analysis.current_summary:
            st.caption(summary)
        for outcome in detail.supporting_analysis.matched_outcome_summary:
            st.caption(outcome)
        st.caption(detail.supporting_analysis.breakpoint_summary)
        _render_rm_outcome_distribution_chart(detail, language=language)
        _render_rm_whatif_summary(detail, language=language)
        st.caption(detail.supporting_analysis.additional_analysis_notice)
    st.markdown(f"#### {t('rm.detail.result', language)}")
    if detail.completed_today:
        st.success(t("rm.completed.already", language))
        return
    option_by_label = {option.label: option.result for option in detail.result_recording.result_options}
    selected_label = st.selectbox(
        t("rm.result.label", language),
        list(option_by_label),
        key=f"rm_result_{detail.customer_id}",
    )
    st.caption(t("rm.follow_up.note", language))
    note = st.text_area(
        t("rm.note.label", language),
        key=f"rm_note_{detail.customer_id}",
    )
    if st.button(t("rm.result.save", language), key=f"rm_save_{detail.customer_id}"):
        event = create_review_event(
            customer_id=detail.result_recording.customer_id,
            snapshot_id=detail.result_recording.snapshot_id,
            reviewed_at=datetime.now().astimezone(),
            result=option_by_label[selected_label],
            note=note,
        )
        append_review_event(event)
        st.session_state.pop("rm_selected_customer_id", None)
        st.session_state["rm_daily_review_completion_message"] = t("rm.completed.message", language)
        st.session_state["rm_daily_review_refresh_after_review"] = True
        st.rerun()


def _presentation_metadata_from_dashboard(dashboard: Any) -> dict[str, dict[str, object]]:
    """Reuse the loaded synthetic display overlay; never derive it from finance data."""

    return {
        row.customer_id: {
            "display_name": row.display_name,
            "display_owner_or_team": row.display_owner_or_team,
            "presentation_label": row.presentation_label,
        }
        for row in (*dashboard.customer_list, *dashboard.completed_items)
    }


def _render_rm_conversation_steps(detail: Any, *, language: str) -> None:
    """Reveal optional neutral prompts without predicting a customer response."""

    st.caption(t("rm.conversation.optional_intro", language))
    for step in detail.conversation_steps:
        with st.expander(f"{step.number}. {step.title}", expanded=False):
            st.caption(step.context)
            st.markdown(f"**{t('rm.conversation.question', language)}**")
            st.write(step.question)
            if step.saved_observations:
                st.markdown(f"**{t('rm.conversation.observations', language)}**")
                for observation in step.saved_observations:
                    st.caption(f"• {observation}")


def _render_rm_detail_evidence_at_a_glance(detail: Any, *, language: str) -> None:
    """Render a compact, saved-evidence briefing before the full review flow."""

    st.markdown(f"#### {t('rm.detail.brief.title', language)}")
    st.caption(t("rm.detail.brief.subtitle", language))
    why_column, chart_column = st.columns([0.9, 1.1])
    with why_column:
        evidence_summary = (
            detail.supporting_analysis_evidence[0]
            if detail.supporting_analysis_evidence
            else detail.why_today
        )
        st.markdown(
            render_rm_review_brief_html(
                label=t("rm.detail.why", language),
                summary=evidence_summary,
                supporting_text=detail.why_today,
                timing_title=t("rm.detail.brief.timing", language),
                timing_value=_format_rm_timing(detail.timing_months, language),
                timing_detail=t("rm.detail.brief.timing_detail", language),
                focus_title=t("rm.detail.brief.change", language),
                focus_value=detail.primary_change,
                focus_detail=t("rm.detail.brief.change_detail", language),
            ),
            unsafe_allow_html=True,
        )
    with chart_column:
        _render_rm_historical_cohort_chart(
            detail,
            language=language,
            show_heading=True,
            chart_height=330,
        )

    changes_column, prompt_column = st.columns([1.35, 0.85])
    with changes_column:
        with st.container(border=True):
            _render_rm_current_change_cards(detail, language=language)
    with prompt_column:
        with st.container(border=True):
            st.markdown(f"**{t('rm.detail.brief.prompts', language)}**")
            if not detail.conversation_steps:
                st.caption(t("rm.detail.brief.prompts_empty", language))
            else:
                for step in detail.conversation_steps[:3]:
                    st.caption(f"{step.number}. {step.question}")


def _render_rm_current_change_cards(detail: Any, *, language: str) -> None:
    """Present saved current observations with text and semantic display tones."""

    change_cards = detail.supporting_analysis.current_change_card_views[:3]
    st.markdown(f"**{t('rm.detail.change_cards', language)}**")
    if not change_cards:
        st.caption(detail.supporting_analysis.evidence_status_message)
        return
    cards = [
        {
            "title": change_card.label,
            "value": change_card.value,
            "detail": t("rm.detail.saved_change", language),
            "status": change_card.status_label,
            "tone": change_card.tone,
        }
        for change_card in change_cards
    ]
    st.markdown(
        render_info_cards_html(cards, t("rm.detail.change_cards", language)),
        unsafe_allow_html=True,
    )


def _render_rm_historical_cohort_chart(
    detail: Any,
    *,
    language: str,
    show_heading: bool = True,
    chart_height: int = 300,
) -> None:
    """Render only historical aggregates saved in the Monthly Snapshot."""

    chart = detail.supporting_analysis.historical_cohort_chart
    if show_heading:
        st.markdown(f"**{t('rm.detail.cohort_chart', language)}**")
    if not chart.available:
        st.info(chart.unavailable_message or t("rm.evidence.chart_unavailable", language))
        return

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=[point.month for point in chart.risk_path],
            y=[point.mean for point in chart.risk_path],
            mode="lines+markers",
            name=t("chart.risk_path_mean", language),
            line={"color": DESIGN_TOKENS["stress"], "width": 2.5},
            marker={"symbol": "circle", "size": 6},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[point.month for point in chart.avoidance_path],
            y=[point.mean for point in chart.avoidance_path],
            mode="lines+markers",
            name=t("chart.avoidance_path_mean", language),
            line={"color": DESIGN_TOKENS["stable"], "width": 2.5, "dash": "dash"},
            marker={"symbol": "diamond", "size": 6},
        )
    )
    # The full Breakpoint help text belongs below the chart, not inside its
    # plotting area. A dotted line is sufficient context here; the saved
    # month and historical-comparison explanation are rendered nearby.
    figure.add_vline(
        x=chart.breakpoint_month,
        line_dash="dot",
        line_color=DESIGN_TOKENS["primary_dark"],
    )
    figure.update_layout(
        height=chart_height,
        margin={"l": 72, "r": 48, "t": 84, "b": 64},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.08,
            "xanchor": "left",
            "x": 0,
            "font": {"size": 10},
        },
        legend_title_text=None,
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font={"family": DESIGN_TOKENS["font_family"], "color": DESIGN_TOKENS["text"]},
        xaxis_title=t("chart.month_axis", language),
        yaxis_title=label_metric(chart.metric_key, language),
    )
    figure.update_xaxes(
        gridcolor="#e2eaf2",
        zerolinecolor="#e2eaf2",
        automargin=True,
        title_standoff=10,
    )
    figure.update_yaxes(
        gridcolor="#e2eaf2",
        zerolinecolor="#e2eaf2",
        automargin=True,
        title_standoff=12,
    )
    _render_framed_plotly_chart(
        figure,
        chart_key=f"rm_cohort_{detail.customer_id}",
    )
    st.caption(t("rm.detail.cohort_caption", language))
    st.caption(
        t(
            "rm.detail.cohort_groups",
            language,
            risk_count=chart.risk_group_size if chart.risk_group_size is not None else "-",
            avoidance_count=(
                chart.avoidance_group_size if chart.avoidance_group_size is not None else "-"
            ),
            month=chart.breakpoint_month if chart.breakpoint_month is not None else "-",
        )
    )


def _render_rm_outcome_distribution_chart(detail: Any, *, language: str) -> None:
    """Render saved similar-customer counts, never a prediction or new outcome."""

    bars = detail.supporting_analysis.outcome_distribution
    st.markdown(f"**{t('rm.detail.outcome_chart', language)}**")
    if not bars:
        st.caption(t("rm.outcome.unavailable", language))
        return
    color_by_tone = {
        "stable": DESIGN_TOKENS["stable"],
        "recovered": DESIGN_TOKENS["recovered"],
        "stress": DESIGN_TOKENS["stress"],
        "delinquent": DESIGN_TOKENS["delinquent"],
    }
    figure = go.Figure(
        go.Bar(
            x=[bar.count for bar in bars],
            y=[bar.label for bar in bars],
            orientation="h",
            marker_color=[color_by_tone.get(bar.tone, DESIGN_TOKENS["baseline"]) for bar in bars],
            text=[f"{bar.count:,}" for bar in bars],
            textposition="outside",
            cliponaxis=False,
        )
    )
    figure.update_layout(
        height=300,
        margin={"l": 72, "r": 54, "t": 56, "b": 56},
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font={"family": DESIGN_TOKENS["font_family"], "color": DESIGN_TOKENS["text"]},
        showlegend=False,
    )
    figure.update_xaxes(
        showgrid=True,
        gridcolor="#e2eaf2",
        title=None,
        rangemode="tozero",
        automargin=True,
    )
    figure.update_yaxes(autorange="reversed", title=None, automargin=True)
    _render_framed_plotly_chart(
        figure,
        chart_key=f"rm_outcome_{detail.customer_id}",
    )
    st.caption(t("rm.detail.outcome_caption", language))


def _render_rm_whatif_summary(detail: Any, *, language: str) -> None:
    """Show only names of saved scenario summaries, never a full time series."""

    whatif_summary = detail.supporting_analysis.whatif_summary
    st.markdown(f"**{t('rm.detail.whatif', language)}**")
    if not whatif_summary.available:
        st.caption(whatif_summary.unavailable_message or t("rm.evidence.whatif_unavailable", language))
        return
    for scenario_label in whatif_summary.scenario_labels:
        st.caption(f"- {scenario_label}")
    st.caption(t("rm.detail.whatif_general", language))


def render_presentation_mode(
    monthly_df: pd.DataFrame,
    demo_df: pd.DataFrame,
    payload: Any,
    selection: SidebarSelection,
    language: str = "ko",
) -> None:
    """Render prepared presentation results in five non-calculating tabs."""

    customer_id = payload.customer_id
    summary = payload.summary
    analysis = payload.analysis
    view_model = build_presentation_view_model(
        customer_id=customer_id,
        summary=summary,
        analysis=analysis,
        source=payload.source,
        language=language,
    )
    scenes = {scene["id"]: scene for scene in view_model["scenes"]}
    presentation_cards = build_presentation_metric_cards(
        breakpoint_result=analysis.get("breakpoint_result"),
        whatif_results=analysis.get("whatif_results"),
        language=language,
    )
    first_screen = build_first_screen_view_model(
        customer_id=customer_id,
        summary=summary,
        demo_df=demo_df,
        analysis=analysis,
        language=language,
    )
    peer_view_model = build_judge_flow_view_model(
        customer_id=customer_id,
        summary=summary,
        demo_df=demo_df,
        analysis=analysis,
        selected_metric=selection.selected_metric,
        language=language,
    )
    current_history = build_target_history(monthly_df, customer_id)
    twin_history, twin_trajectory = build_twin_trajectory_frames(
        monthly_df,
        customer_id,
        selection.selected_metric,
        analysis,
    )
    customer_brief = build_brief_with_fallback(
        "customer",
        summary,
        analysis["outcome_summary"],
        analysis["breakpoint_result"],
        analysis["whatif_results"],
        language=language,
    )
    staff_brief = build_brief_with_fallback(
        "staff",
        summary,
        analysis["outcome_summary"],
        analysis["breakpoint_result"],
        analysis["whatif_results"],
        language=language,
    )
    tabs = st.tabs(get_presentation_tab_labels(language))

    with tabs[0]:
        render_presentation_current_scene(
            first_screen=first_screen,
            target_history=current_history,
            scene=scenes["current"],
            language=language,
        )
    with tabs[1]:
        render_presentation_peer_scene(
            analysis=analysis,
            scene=scenes["peers"],
            view_model=peer_view_model,
            target_history=twin_history,
            twin_trajectory=twin_trajectory,
            selected_metric=selection.selected_metric,
            language=language,
        )
    with tabs[2]:
        render_presentation_breakpoint_scene(
            analysis=analysis,
            scene=scenes["breakpoint"],
            breakpoint_cards=presentation_cards["breakpoint"],
            language=language,
        )
    with tabs[3]:
        render_presentation_whatif_scene(
            analysis=analysis,
            scene=scenes["whatif"],
            whatif_cards=presentation_cards["whatif"],
            language=language,
        )
    with tabs[4]:
        render_presentation_summary_scene(
            scene=scenes["summary"],
            customer_brief=customer_brief,
            staff_brief=staff_brief,
            notices=view_model["notices"],
            language=language,
        )


def render_presentation_current_scene(
    *,
    first_screen: dict[str, Any],
    target_history: pd.DataFrame,
    scene: dict[str, str],
    language: str = "ko",
) -> None:
    """Render presentation tab 1 from prepared display values."""

    st.markdown(render_presentation_scene_heading_html(scene), unsafe_allow_html=True)
    st.markdown(render_customer_identity_html(first_screen["customer_identity"], language=language), unsafe_allow_html=True)
    st.markdown(render_kpi_cards_html(first_screen["kpi_cards"], language=language), unsafe_allow_html=True)
    st.markdown(render_status_summary_html(first_screen["status_sentence"]), unsafe_allow_html=True)

    if target_history.empty:
        st.info(t("ui.current_data_missing", language))
        return

    render_chart_or_table(
        lambda: create_income_expense_chart(target_history, language=language),
        target_history.loc[:, ["month", "income", "total_expense"]],
        presentation_mode=True,
        language=language,
    )
    chart_cols = st.columns(2)
    with chart_cols[0]:
        render_chart_or_table(
            lambda: create_current_trajectory_chart(target_history, "savings_rate", language=language),
            target_history.loc[:, ["month", "savings_rate"]],
            presentation_mode=True,
            language=language,
        )
    with chart_cols[1]:
        render_chart_or_table(
            lambda: create_current_trajectory_chart(target_history, "dsr", language=language),
            target_history.loc[:, ["month", "dsr"]],
            presentation_mode=True,
            language=language,
        )


def render_presentation_peer_scene(
    *,
    analysis: dict[str, Any],
    scene: dict[str, str],
    view_model: dict[str, Any],
    target_history: pd.DataFrame,
    twin_trajectory: pd.DataFrame,
    selected_metric: str,
    language: str = "ko",
) -> None:
    """Render presentation tab 2 from prepared display values."""

    st.markdown(render_presentation_scene_heading_html(scene), unsafe_allow_html=True)
    st.markdown(render_info_cards_html(view_model["similarity_cards"], t("card.similar_summary", language)), unsafe_allow_html=True)
    metric_label = get_analysis_metric_options(language).get(selected_metric, selected_metric)
    st.caption(t("presentation.metric.active", language, metric=metric_label))
    chart_cols = st.columns([1.35, 1.0])
    with chart_cols[0]:
        render_chart_or_table(
            lambda: create_twin_trajectory_chart(
                target_history,
                twin_trajectory,
                metric=selected_metric,
                breakpoint_result=analysis.get("breakpoint_result"),
                show_raw_samples=False,
                language=language,
            ),
            twin_trajectory.head(30),
            presentation_mode=True,
            language=language,
            chart_key=f"presentation_future_trajectory_{selected_metric}",
        )
    with chart_cols[1]:
        render_chart_or_table(
            lambda: create_outcome_bar_chart(analysis["outcome_summary"], language=language),
            pd.DataFrame([analysis["outcome_summary"]]),
            presentation_mode=True,
            language=language,
        )


def render_presentation_breakpoint_scene(
    *,
    analysis: dict[str, Any],
    scene: dict[str, str],
    breakpoint_cards: list[dict[str, str]],
    language: str = "ko",
) -> None:
    """Render presentation scene 3."""

    st.markdown(render_presentation_scene_heading_html(scene), unsafe_allow_html=True)
    cards = breakpoint_cards or build_breakpoint_summary_cards(analysis.get("breakpoint_result"), language=language)
    st.markdown(render_info_cards_html(cards, t("card.breakpoint_summary", language)), unsafe_allow_html=True)
    st.caption(t("caption.non_causal", language))
    render_chart_or_table(
        lambda: create_breakpoint_comparison_chart(
            analysis["breakpoint_result"],
            analysis.get("breakpoint_comparison"),
            language=language,
        ),
        pd.DataFrame([analysis["breakpoint_result"]]),
        presentation_mode=True,
        language=language,
    )


def render_presentation_whatif_scene(
    *,
    analysis: dict[str, Any],
    scene: dict[str, str],
    whatif_cards: list[dict[str, str]],
    language: str = "ko",
) -> None:
    """Render presentation scene 4."""

    st.markdown(render_presentation_scene_heading_html(scene), unsafe_allow_html=True)
    cards = whatif_cards or [build_best_whatif_card(analysis.get("whatif_results"), language=language)]
    st.markdown(render_info_cards_html(cards, t("card.best_action", language)), unsafe_allow_html=True)
    whatif_results = analysis.get("whatif_results", {})
    table = build_whatif_comparison_table(whatif_results, language=language)
    if table.empty:
        st.info(t("ui.whatif_no_results", language))
        return

    st.dataframe(table, hide_index=True, width="stretch")
    chart_cols = st.columns([1.25, 1.0])
    with chart_cols[0]:
        render_chart_or_table(
            lambda: create_whatif_balance_chart(whatif_results, language=language),
            table,
            presentation_mode=True,
            language=language,
        )
    with chart_cols[1]:
        render_chart_or_table(
            lambda: create_whatif_improvement_chart(whatif_results, language=language),
            table,
            presentation_mode=True,
            language=language,
        )
    st.caption(t("ui.loan_scenario_notice", language))


def render_presentation_summary_scene(
    *,
    scene: dict[str, str],
    customer_brief: str,
    staff_brief: str,
    notices: list[str],
    language: str = "ko",
) -> None:
    """Render presentation tab 5 from prepared briefing text."""

    st.markdown(render_presentation_scene_heading_html(scene), unsafe_allow_html=True)
    brief_cols = st.columns(2)
    with brief_cols[0]:
        st.markdown(render_brief_panel_html(t("brief.customer.title", language), customer_brief), unsafe_allow_html=True)
    with brief_cols[1]:
        st.markdown(render_brief_panel_html(t("brief.staff.title", language), staff_brief), unsafe_allow_html=True)
    st.markdown(render_presentation_notice_html(notices), unsafe_allow_html=True)


def render_section_current_flow(
    monthly_df: pd.DataFrame,
    customer_id: str,
    summary: dict[str, Any],
    demo_df: pd.DataFrame,
    analysis: dict[str, Any] | None,
    *,
    presentation_mode: bool,
    language: str = "ko",
) -> None:
    """Render Section 1: current financial flow."""

    section = get_section_copy("current", language)
    render_section_heading(section["label"], section["title"], section["caption"])
    view_model = build_first_screen_view_model(
        customer_id=customer_id,
        summary=summary,
        demo_df=demo_df,
        analysis=analysis,
        language=language,
    )
    st.markdown(render_customer_identity_html(view_model["customer_identity"], language=language), unsafe_allow_html=True)
    st.markdown(render_kpi_cards_html(view_model["kpi_cards"], language=language), unsafe_allow_html=True)
    st.markdown(render_status_summary_html(view_model["status_sentence"]), unsafe_allow_html=True)

    target_history = build_target_history(monthly_df, customer_id)
    if target_history.empty:
        st.info(t("ui.current_data_missing", language))
        return

    render_chart_or_table(
        lambda: create_income_expense_chart(target_history, language=language),
        target_history.loc[:, ["month", "income", "total_expense"]],
        presentation_mode=presentation_mode,
        language=language,
    )
    lower_cols = st.columns(2)
    with lower_cols[0]:
        render_chart_or_table(
            lambda: create_current_trajectory_chart(target_history, "savings_rate", language=language),
            target_history.loc[:, ["month", "savings_rate"]],
            presentation_mode=presentation_mode,
            language=language,
        )
    with lower_cols[1]:
        render_chart_or_table(
            lambda: create_current_trajectory_chart(target_history, "dsr", language=language),
            target_history.loc[:, ["month", "dsr"]],
            presentation_mode=presentation_mode,
            language=language,
        )


def render_analysis_action(
    monthly_df: pd.DataFrame,
    features_df: pd.DataFrame,
    matcher: Any,
    customer_id: str,
    cache_payload: Any | None,
    language: str = "ko",
) -> None:
    """Run analysis once when it is not already available."""

    if st.session_state.get("analysis"):
        return

    st.info(t("ui.analysis_cta", language))
    if st.button(t("button.find_twins", language), type="primary", disabled=matcher is None):
        step = st.empty()
        try:
            step.info(t("ui.analysis_step_compare", language))
            with st.spinner(t("ui.analysis_step_outcomes", language)):
                analysis = run_customer_analysis(customer_id, monthly_df, features_df, matcher)
            step.info(t("ui.analysis_step_done", language))
            st.session_state["analysis"] = analysis
            st.session_state["analysis_mode"] = MODE_LIVE
            step.empty()
        except Exception:  # noqa: BLE001
            step.empty()
            if cache_payload is not None and str(customer_id) == str(cache_payload.customer_id):
                st.session_state["analysis"] = cache_payload.analysis
                st.session_state["analysis_mode"] = MODE_FALLBACK
                st.warning(t("ui.analysis_fallback", language))
            else:
                st.warning(t("ui.analysis_failed", language))


def render_section_peer_outcomes(
    monthly_df: pd.DataFrame,
    customer_id: str,
    summary: dict[str, Any],
    demo_df: pd.DataFrame,
    analysis: dict[str, Any] | None,
    selection: SidebarSelection,
    language: str = "ko",
) -> None:
    """Render Section 2: peer outcomes."""

    section = get_section_copy("peers", language)
    render_section_heading(section["label"], section["title"], section["caption"])
    view_model = build_judge_flow_view_model(
        customer_id=customer_id,
        summary=summary,
        demo_df=demo_df,
        analysis=analysis,
        selected_metric=selection.selected_metric,
        language=language,
    )
    st.markdown(render_info_cards_html(view_model["similarity_cards"], t("card.similar_summary", language)), unsafe_allow_html=True)

    if not analysis:
        st.info(t("ui.peers_empty", language))
        return

    target_history, twin_trajectory = build_twin_trajectory_frames(
        monthly_df,
        customer_id,
        selection.selected_metric,
        analysis,
    )
    chart_cols = st.columns([1.35, 1.0])
    with chart_cols[0]:
        render_chart_or_table(
            lambda: create_twin_trajectory_chart(
                target_history,
                twin_trajectory,
                metric=selection.selected_metric,
                breakpoint_result=analysis["breakpoint_result"],
                show_raw_samples=selection.show_raw_samples,
                language=language,
            ),
            twin_trajectory.head(30),
            presentation_mode=selection.presentation_mode,
            language=language,
        )
    with chart_cols[1]:
        render_chart_or_table(
            lambda: create_outcome_bar_chart(analysis["outcome_summary"], language=language),
            pd.DataFrame([analysis["outcome_summary"]]),
            presentation_mode=selection.presentation_mode,
            language=language,
        )


def render_section_breakpoint(
    analysis: dict[str, Any] | None,
    *,
    presentation_mode: bool,
    language: str = "ko",
) -> None:
    """Render Section 3: breakpoint explanation."""

    section = get_section_copy("breakpoint", language)
    render_section_heading(section["label"], section["title"], section["caption"])
    if not analysis:
        st.info(t("ui.breakpoint_empty", language))
        return

    view_cards = build_breakpoint_summary_cards(analysis.get("breakpoint_result"), language=language)
    st.markdown(render_info_cards_html(view_cards, t("card.breakpoint_summary", language)), unsafe_allow_html=True)
    st.caption(t("caption.non_causal", language))
    render_chart_or_table(
        lambda: create_breakpoint_comparison_chart(
            analysis["breakpoint_result"],
            analysis.get("breakpoint_comparison"),
            language=language,
        ),
        pd.DataFrame([analysis["breakpoint_result"]]),
        presentation_mode=presentation_mode,
        language=language,
    )


def render_section_whatif(
    analysis: dict[str, Any] | None,
    *,
    presentation_mode: bool,
    language: str = "ko",
) -> None:
    """Render Section 4: What-if response options."""

    section = get_section_copy("whatif", language)
    render_section_heading(section["label"], section["title"], section["caption"])
    if not analysis:
        st.info(t("ui.whatif_empty", language))
        return

    whatif_results = analysis["whatif_results"]
    best_card = build_best_whatif_card(whatif_results, language=language)
    st.markdown(render_info_cards_html([best_card], t("card.best_action", language)), unsafe_allow_html=True)
    table = build_whatif_comparison_table(whatif_results, language=language)
    if table.empty:
        st.info(t("ui.whatif_no_results", language))
        return

    st.dataframe(table, hide_index=True, width="stretch")
    chart_cols = st.columns([1.25, 1.0])
    with chart_cols[0]:
        render_chart_or_table(
            lambda: create_whatif_balance_chart(whatif_results, language=language),
            table,
            presentation_mode=presentation_mode,
            language=language,
        )
    with chart_cols[1]:
        render_chart_or_table(
            lambda: create_whatif_improvement_chart(whatif_results, language=language),
            table,
            presentation_mode=presentation_mode,
            language=language,
        )
    st.caption(t("ui.loan_scenario_notice", language))


def render_section_usage(summary: dict[str, Any], analysis: dict[str, Any] | None, language: str = "ko") -> None:
    """Render Section 5: usage briefings and bottom notice."""

    section = get_section_copy("usage", language)
    render_section_heading(section["label"], section["title"], section["caption"])
    if analysis:
        customer_brief = build_brief_with_fallback(
            "customer",
            summary,
            analysis["outcome_summary"],
            analysis["breakpoint_result"],
            analysis["whatif_results"],
            language=language,
        )
        staff_brief = build_brief_with_fallback(
            "staff",
            summary,
            analysis["outcome_summary"],
            analysis["breakpoint_result"],
            analysis["whatif_results"],
            language=language,
        )
    else:
        view_model = build_judge_flow_view_model(customer_id=str(summary.get("customer_id", "")), summary=summary, language=language)
        customer_brief = view_model["brief_empty_message"]
        staff_brief = view_model["brief_empty_message"]

    brief_cols = st.columns(2)
    with brief_cols[0]:
        st.markdown(render_brief_panel_html(t("brief.customer.title", language), customer_brief), unsafe_allow_html=True)
    with brief_cols[1]:
        st.markdown(render_brief_panel_html(t("brief.staff.title", language), staff_brief), unsafe_allow_html=True)
    st.info(t("ui.poc_notice", language))


def render_section_heading(section_label: str, title: str, caption: str) -> None:
    """Render a consistent section heading."""

    st.markdown(
        (
            '<div class="fpt-section-heading">'
            f'<span class="fpt-section-label">{section_label}</span>'
            f"<h2>{title}</h2>"
            f"<p>{caption}</p>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def build_target_history(monthly_df: pd.DataFrame, customer_id: str) -> pd.DataFrame:
    """Return the selected customer's observed 12-month history."""

    if monthly_df.empty or "customer_id" not in monthly_df.columns:
        return pd.DataFrame()
    target_history = monthly_df[
        (monthly_df["customer_id"].astype(str) == str(customer_id))
        & (monthly_df["month"] <= settings.OBSERVATION_END_MONTH)
    ].copy()
    return target_history.sort_values("month")


def build_twin_trajectory_frames(
    monthly_df: pd.DataFrame,
    customer_id: str,
    selected_metric: str,
    analysis: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Prepare display DataFrames for the future trajectory chart."""

    if not monthly_df.empty:
        matched_ids = list(analysis.get("matched_ids", []))
        monthly_with_ratios = add_balance_ratios(monthly_df, [customer_id, *matched_ids])
        target_history = monthly_with_ratios[
            (monthly_with_ratios["customer_id"].astype(str) == str(customer_id))
            & (monthly_with_ratios["month"] <= settings.OBSERVATION_END_MONTH)
        ].copy()
        twin_trajectory = monthly_with_ratios[
            monthly_with_ratios["customer_id"].astype(str).isin(set(matched_ids))
        ].copy()
        return target_history, twin_trajectory

    target_history = pd.DataFrame(columns=["month", selected_metric])
    cached_future = analysis.get("matched_future_trajectory", pd.DataFrame())
    if isinstance(cached_future, pd.DataFrame) and not cached_future.empty:
        twin_trajectory = cached_future.rename(columns={"matched_customer_id": "customer_id"}).copy()
    else:
        twin_trajectory = pd.DataFrame(columns=["customer_id", "month", selected_metric, "final_outcome"])
    return target_history, twin_trajectory


def _render_framed_plotly_chart(
    figure: Any,
    *,
    presentation_mode: bool = False,
    chart_key: str | None = None,
) -> None:
    """Render every Plotly chart inside one consistent visual frame."""

    chart_arguments: dict[str, Any] = {
        "width": "stretch",
        "config": {"displayModeBar": not presentation_mode, "responsive": True},
    }
    if chart_key is not None:
        chart_arguments["key"] = chart_key
    with st.container(border=True):
        st.plotly_chart(figure, **chart_arguments)


def render_chart_or_table(
    figure_factory: Callable[[], Any],
    fallback_df: pd.DataFrame | None = None,
    *,
    presentation_mode: bool = False,
    language: str = "ko",
    chart_key: str | None = None,
) -> None:
    """Render a Plotly figure, falling back to a compact table."""

    try:
        _render_framed_plotly_chart(
            figure_factory(),
            presentation_mode=presentation_mode,
            chart_key=chart_key,
        )
    except Exception:  # noqa: BLE001
        st.warning(t("ui.chart_fallback", language))
        if fallback_df is not None and not fallback_df.empty:
            st.dataframe(fallback_df, hide_index=True, width="stretch")
        else:
            st.info(t("ui.chart_fallback_empty", language))


if __name__ == "__main__":
    main()
