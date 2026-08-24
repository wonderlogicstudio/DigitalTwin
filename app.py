"""Streamlit app for the Financial Path Twin demo."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd
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
from src.presentation_population import (  # noqa: E402
    build_presentation_current_review_signal,
    build_presentation_customer_options,
    build_presentation_population_strip,
    load_presentation_population_evidence,
)
from src.rm_workspace import (  # noqa: E402
    RM_WORKSPACE_MODE,
    build_rm_portfolio_queue_view_model,
    build_rm_workspace_view_model,
    customer_context_from_queue_row,
    load_rm_alert_cases,
    load_rm_workspace_artifacts,
)
from src.rm_customer_review import (  # noqa: E402
    build_rm_customer_review_view_model,
    load_customer_observation,
    load_population_result_index,
)
from src.rm_workflow_ui import (  # noqa: E402
    RMWorkflowUIService,
    build_offline_notification_preview,
    build_rm_activity_history,
    create_file_backed_rm_workflow_ui_service,
    load_rm_workflow_case,
    make_submission_token,
    perform_rm_workflow_operation,
    utc_now,
)
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
    rm_workspace_mode: bool = False
    rm_queue_scope: str = "all"
    rm_priority_scope: str = "all"
    rm_owner_scope: str = "all"
    rm_due_scope: str = "all"
    rm_customer_context: str = ""
    presentation_population_evidence: Mapping[str, Any] | None = None


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
    cache_payload = load_precomputed_demo_safely()
    demo_df = load_demo_data_safely(language)
    selection = render_sidebar(demo_df, cache_payload, language)
    if selection.rm_workspace_mode:
        render_rm_workspace_mode(selection=selection, language=language)
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
        if st.session_state.get("app_mode") == RM_WORKSPACE_MODE:
            st.markdown(f"#### {t('rm.header.title', language)}")
            st.caption(t("rm.header.subtitle", language))
        else:
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
    """Render mode-specific controls without sharing RM and customer-story state."""

    st.sidebar.header(t("mode.settings", language))
    app_mode = st.sidebar.selectbox(
        t("mode.selector", language),
        list(APP_MODE_OPTIONS),
        index=list(APP_MODE_OPTIONS).index(PRESENTATION_MODE),
        format_func=lambda mode: t(_app_mode_translation_key(mode), language),
        key="app_mode",
    )
    presentation_mode = app_mode == PRESENTATION_MODE
    if app_mode == RM_WORKSPACE_MODE:
        return render_rm_workspace_sidebar(app_mode=app_mode, language=language)
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

    population_evidence: Mapping[str, Any] | None = None
    if presentation_mode:
        population_evidence = load_presentation_population_evidence()
        default_customer_id = resolve_presentation_customer_id(
            demo_df=demo_df,
            main_demo_customer=cache_payload.main_demo_customer if cache_payload is not None else None,
        )
        presentation_options = build_presentation_customer_options(
            demo_options=demo_options,
            population_evidence=population_evidence,
            language=language,
        )
        customer_options = [option["option_id"] for option in presentation_options]
        option_by_id = {option["option_id"]: option for option in presentation_options}
        st.sidebar.caption(t("ui.presentation_main_default", language))
        if customer_options:
            default_index = next(
                (
                    index
                    for index, option in enumerate(presentation_options)
                    if option["source"] == "demo" and option["customer_id"] == default_customer_id
                ),
                0,
            )
            selected_option_id = st.sidebar.selectbox(
                t("customer.selector", language),
                customer_options,
                index=default_index,
                format_func=lambda option_id: option_by_id.get(option_id, {"label": option_id})["label"],
                key="presentation_customer_selector",
            )
            selected_option = option_by_id[selected_option_id]
            customer_id = selected_option["customer_id"]
            st.session_state["selected_demo_role"] = selected_option["role"]
            st.sidebar.caption(t("customer.demo_role_caption", language, role=selected_option["label"]))
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
        t("sidebar.metric_selector", language),
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
        presentation_population_evidence=population_evidence,
    )


def _app_mode_translation_key(app_mode: str) -> str:
    """Map one stable display-mode value to its localized label key."""

    if app_mode == PRESENTATION_MODE:
        return "mode.presentation"
    if app_mode == RM_WORKSPACE_MODE:
        return "mode.rm_workspace"
    return "mode.normal"


def render_rm_workspace_sidebar(*, app_mode: str, language: str) -> SidebarSelection:
    """Render RM-only shell filters with distinct session-state keys."""

    st.sidebar.caption(t("rm.sidebar.caption", language))
    queue_scope = st.sidebar.selectbox(
        t("rm.sidebar.queue", language),
        ("all", "selected"),
        format_func=lambda value: t(f"rm.filter.{value}", language),
        key="rm_queue_scope",
    )
    priority_scope = st.sidebar.selectbox(
        t("rm.sidebar.priority", language),
        ("all", "priority", "review"),
        format_func=lambda value: t(f"rm.filter.{value}", language),
        key="rm_priority_scope",
    )
    owner_scope = st.sidebar.selectbox(
        t("rm.sidebar.owner", language),
        ("all", "unassigned"),
        format_func=lambda value: t(f"rm.filter.{value}", language),
        key="rm_owner_scope",
    )
    due_scope = st.sidebar.selectbox(
        t("rm.sidebar.due", language),
        ("all", "due_soon"),
        format_func=lambda value: t(f"rm.filter.{value}", language),
        key="rm_due_scope",
    )
    return SidebarSelection(
        customer_id="",
        selected_metric="",
        app_mode=app_mode,
        presentation_mode=False,
        show_raw_samples=False,
        rm_workspace_mode=True,
        rm_queue_scope=str(queue_scope),
        rm_priority_scope=str(priority_scope),
        rm_owner_scope=str(owner_scope),
        rm_due_scope=str(due_scope),
        rm_customer_context=str(st.session_state.get("rm_customer_context", "")),
    )


def render_rm_workspace_mode(*, selection: SidebarSelection, language: str = "ko") -> None:
    """Render the read-only RM portfolio and selected-only review queue."""

    artifacts = load_rm_workspace_artifacts()
    alert_snapshot = load_rm_alert_cases()
    workflow_service = _get_rm_workflow_ui_service()
    view_model = build_rm_workspace_view_model(
        language=language,
        funnel=artifacts.funnel,
        representative_cohort=artifacts.representative_cohort,
        customer_context=selection.rm_customer_context,
    )
    portfolio_model = build_rm_portfolio_queue_view_model(
        selection_manifest=getattr(artifacts, "selection_manifest", None),
        representative_cohort=artifacts.representative_cohort,
        alert_cases=alert_snapshot.cases,
        language=language,
        priority_scope=selection.rm_priority_scope,
        owner_scope=selection.rm_owner_scope,
        due_scope=selection.rm_due_scope,
        search_query=str(st.session_state.get("rm_queue_search", "")),
        sort_by=str(st.session_state.get("rm_queue_sort", "rank")),
    )
    customer_target = view_model["customer_review_target"]
    customer_review_model: dict[str, Any] | None = None
    if customer_target:
        population_results = load_population_result_index()
        initial_customer_review = build_rm_customer_review_view_model(
            customer_id=customer_target,
            selection_manifest=getattr(artifacts, "selection_manifest", None),
            representative_cohort=artifacts.representative_cohort,
            population_results=population_results,
            observation=None,
            alert_cases=alert_snapshot.cases,
            language=language,
        )
        as_of_value = initial_customer_review.get("provenance", {}).get(
            "selection_as_of_month", settings.OBSERVATION_END_MONTH
        )
        as_of_month = (
            as_of_value
            if isinstance(as_of_value, int)
            and not isinstance(as_of_value, bool)
            and settings.OBSERVATION_START_MONTH <= as_of_value <= settings.OBSERVATION_END_MONTH
            else settings.OBSERVATION_END_MONTH
        )
        observation = load_customer_observation(
            customer_target,
            as_of_month=as_of_month,
        )
        customer_review_model = build_rm_customer_review_view_model(
            customer_id=customer_target,
            selection_manifest=getattr(artifacts, "selection_manifest", None),
            representative_cohort=artifacts.representative_cohort,
            population_results=population_results,
            observation=observation,
            alert_cases=alert_snapshot.cases,
            language=language,
        )
    tabs = st.tabs(view_model["tabs"])
    with tabs[0]:
        st.caption(t("rm.synthetic.notice", language))
        if artifacts.load_error or artifacts.source_reference is None:
            st.info(t("rm.artifact.unavailable", language))
        if portfolio_model["available"]:
            funnel_stages = portfolio_model["portfolio"]["funnel"]
        else:
            funnel_stages = view_model["funnel"]
        funnel_columns = st.columns(3)
        for index, stage in enumerate(funnel_stages):
            column = funnel_columns[index % len(funnel_columns)]
            with column:
                st.metric(str(stage["label"]), str(stage["display_value"]))
        alert_summary = portfolio_model["portfolio"]
        alert_columns = st.columns(4)
        for column, key, label_key in zip(
            alert_columns,
            ("new_alert_count", "open_alert_count", "due_alert_count", "overdue_alert_count"),
            ("rm.alert.new", "rm.alert.open", "rm.alert.due", "rm.alert.overdue"),
        ):
            count = alert_summary[key]
            with column:
                st.metric(
                    t(label_key, language),
                    t("rm.value.unavailable", language) if count is None else f"{count:,}",
                )
        reconciliation = alert_summary["reconciliation"]
        if reconciliation["is_exact"]:
            st.success(t("rm.portfolio.reconciliation_exact", language))
        else:
            st.warning(t("rm.portfolio.reconciliation_failed", language))
        if alert_snapshot.load_error:
            st.warning(t("rm.repository.unavailable", language))

        quick_selects = portfolio_model["representative_comparisons"] or view_model[
            "representative_quick_selects"
        ]
        st.caption(t("rm.representative.comparison", language))
        option_ids = [str(item["category_id"]) for item in quick_selects]
        labels_by_id = {
            str(item["category_id"]): (
                f"{item['label']} · {item['customer_id']}"
                if item["available"]
                else f"{item['label']} · {t('rm.representative.unavailable', language)}"
            )
            for item in quick_selects
        }
        selected_category = st.selectbox(
            t("rm.representative.label", language),
            option_ids,
            format_func=lambda category_id: labels_by_id[category_id],
            key="rm_representative_quick_select",
        )
        selected_quick_select = next(
            item for item in quick_selects if item["category_id"] == selected_category
        )
        last_representative_category = st.session_state.get("rm_representative_context_category")
        if selected_quick_select["available"] and last_representative_category != selected_category:
            st.session_state["rm_customer_context"] = str(selected_quick_select["customer_id"])
            st.session_state["rm_workspace_requested_tab"] = "customer_review"
            st.session_state["rm_representative_context_category"] = selected_category
    with tabs[1]:
        if not portfolio_model["available"]:
            st.info(t("rm.artifact.unavailable", language))
        else:
            search_query = st.text_input(
                t("rm.queue.search", language),
                key="rm_queue_search",
            )
            sort_by = st.selectbox(
                t("rm.queue.sort", language),
                ("rank", "due", "updated"),
                format_func=lambda value: t(f"rm.queue.sort.{value}", language),
                key="rm_queue_sort",
            )
            if search_query != portfolio_model["queue"]["filters"]["search_query"] or sort_by != portfolio_model["queue"]["filters"]["sort_by"]:
                st.rerun()
            st.caption(
                t(
                    "rm.queue.source_count",
                    language,
                    visible=portfolio_model["queue"]["filtered_count"],
                    selected=portfolio_model["queue"]["unfiltered_count"],
                )
            )
            queue_rows = portfolio_model["queue"]["rows"]
            if not queue_rows:
                st.info(t("rm.queue.empty", language))
            else:
                event = st.dataframe(
                    _rm_queue_table_rows(queue_rows, language=language),
                    hide_index=True,
                    width="stretch",
                    on_select="rerun",
                    selection_mode="single-row",
                    key="rm_review_queue_table",
                )
                selected_indexes = getattr(getattr(event, "selection", None), "rows", [])
                if selected_indexes:
                    selected_index = selected_indexes[0]
                    if isinstance(selected_index, int) and 0 <= selected_index < len(queue_rows):
                        target = customer_context_from_queue_row(
                            portfolio_model,
                            str(queue_rows[selected_index]["customer_id"]),
                        )
                        if target:
                            st.session_state["rm_customer_context"] = target
                            st.session_state["rm_workspace_requested_tab"] = "customer_review"
    with tabs[2]:
        if customer_review_model is None:
            st.info(t("rm.placeholder.customer_review", language))
        elif not customer_review_model["available"]:
            st.info(str(customer_review_model["message"]))
        else:
            _render_rm_customer_review(
                customer_review_model,
                language=language,
                workflow_service=workflow_service,
            )
    with tabs[3]:
        _render_rm_activity_audit(
            customer_review_model,
            language=language,
            workflow_service=workflow_service,
        )


def _rm_queue_table_rows(queue_rows: Any, *, language: str = "ko") -> pd.DataFrame:
    """Prepare readable display fields without changing triage or case state."""

    return pd.DataFrame(
        [
            {
                t("rm.queue.column.customer", language): row["customer_id"],
                t("rm.queue.column.rank", language): row["selection_rank"],
                t("rm.queue.column.priority", language): _rm_queue_priority_label(
                    row["priority"], language
                ),
                t("rm.queue.column.case_state", language): _rm_queue_case_state_label(
                    row["case_state"], language
                ),
                t("rm.queue.column.selection_reason", language): _rm_queue_reason_label(
                    row["selection_reason_codes"], language
                ),
                t("rm.queue.column.why_now", language): _rm_queue_reason_label(
                    row["why_now_reason_codes"], language
                ),
                t("rm.queue.column.timing", language): _rm_queue_timing_label(
                    row["timing_evidence_reference"], language
                ),
                t("rm.queue.column.due", language): row["due_at"]
                or t("rm.queue.value.not_scheduled", language),
                t("rm.queue.column.owner", language): row["owner_reference"]
                or t("rm.queue.value.unassigned", language),
                t("rm.queue.column.updated", language): row["updated_at"]
                or t("rm.value.unavailable", language),
            }
            for row in queue_rows
        ]
    )


def _rm_queue_reason_label(reason_codes: Any, language: str) -> str:
    """Show a compact localized reason, while raw codes stay in the manifest."""

    if isinstance(reason_codes, (tuple, list)):
        for code in reason_codes:
            if not isinstance(code, str) or not code:
                continue
            translation_key = f"rm.queue.reason.{code}"
            translated = t(translation_key, language)
            if translated != translation_key:
                return translated
    return t("rm.queue.reason.declared", language)


def _rm_queue_priority_label(priority: Any, language: str) -> str:
    priority_key = {
        "Priority Review": "priority_review",
        "Review": "review",
    }.get(str(priority), "unavailable")
    return t(f"rm.queue.priority.{priority_key}", language)


def _rm_queue_case_state_label(case_state: Any, language: str) -> str:
    state_key = {
        "NO_OPEN_ALERT": "no_open_alert",
        "NEW": "new",
        "ACKNOWLEDGED": "acknowledged",
        "IN_REVIEW": "in_review",
        "FOLLOW_UP": "follow_up",
        "SNOOZED": "snoozed",
        "ESCALATED": "escalated",
        "CLOSED": "closed",
    }.get(str(case_state), "unavailable")
    return t(f"rm.queue.case_state.{state_key}", language)


def _rm_queue_timing_label(reference: Any, language: str) -> str:
    source = reference.get("source") if isinstance(reference, Mapping) else None
    key = "prospective" if source == "prospective_signal" else "unavailable"
    return t(f"rm.queue.timing.{key}", language)


def _render_rm_customer_review(
    review: Mapping[str, Any],
    *,
    language: str,
    workflow_service: RMWorkflowUIService | None = None,
) -> None:
    """Render persisted RM evidence without recalculating triage or analytics."""

    header = review["header"]
    st.subheader(f"{review['customer_id']} · {header['operational_label']}")
    header_columns = st.columns(3)
    header_columns[0].metric(t("rm.review.header.context", language), str(header["context_label"]))
    header_columns[1].metric(t("rm.review.header.state", language), str(header["case_state"]))
    header_columns[2].metric(
        t("rm.review.header.due", language),
        t("rm.value.unavailable", language) if header["due_at"] is None else str(header["due_at"]),
    )
    st.markdown(f"**{t('rm.review.header.selection_reason', language)}**  {header['selection_reason']}")
    st.markdown(f"**{t('rm.review.header.why_now', language)}**  {header['why_now']}")
    provenance = review["provenance"]
    st.caption(
        t(
            "rm.review.header.provenance",
            language,
            policy=f"{provenance['policy_id']} v{provenance['policy_version']}",
            as_of=provenance["selection_as_of_month"],
        )
    )

    st.markdown(f"#### {t('rm.review.section.current', language)}")
    current = review["current_signals"]
    if not current["available"]:
        st.info(str(current["message"]))
    else:
        current_columns = st.columns(len(current["items"]))
        for column, item in zip(current_columns, current["items"]):
            with column:
                st.metric(str(item["label"]), str(item["value"]))
        trajectory = review["chart_trajectory"]
        if isinstance(trajectory, pd.DataFrame) and not trajectory.empty:
            st.plotly_chart(
                create_current_trajectory_chart(trajectory, metric="savings_rate", language=language),
                width="stretch",
                key=f"rm_current_signals_chart_{review['customer_id']}",
            )

    st.markdown(f"#### {t('rm.review.section.timing', language)}")
    timing = review["prospective_timing"]
    if timing["available"]:
        st.info(str(timing["message"]))
        st.caption(str(timing["lead_time_message"]))
    else:
        st.info(str(timing["message"]))

    st.markdown(f"#### {t('rm.review.section.twin', language)}")
    twin = review["twin_evidence"]
    if not twin["available"]:
        st.info(str(twin["message"]))
    else:
        twin_columns = st.columns(4)
        twin_columns[0].metric(t("rm.review.twin.matched_count", language), str(twin["matched_count"]))
        twin_columns[1].metric(
            t("rm.review.twin.distance_mean", language),
            _rm_display_decimal(twin["distance_mean"], language=language),
        )
        twin_columns[2].metric(t("rm.review.twin.stability", language), str(twin["neighbor_stability"]))
        twin_columns[3].metric(t("rm.review.twin.persistence", language), str(twin["signal_persistence"]))
        st.caption(str(twin["description"]))
        st.dataframe(
            pd.DataFrame(twin["historical_outcome_distribution"]),
            hide_index=True,
            width="stretch",
        )

    st.markdown(f"#### {t('rm.review.section.landmark', language)}")
    landmark = review["historical_landmark"]
    if landmark["status"] == "found":
        st.info(
            t(
                "rm.review.landmark.detail",
                language,
                month=landmark["month"],
                factor=landmark["factor"],
            )
        )
    else:
        st.info(str(landmark["message"]))
    if landmark.get("caption"):
        st.caption(str(landmark["caption"]))

    st.markdown(f"#### {t('rm.review.section.follow_up', language)}")
    follow_up = review["recommended_follow_up"]
    st.info(str(follow_up["message"]))
    if follow_up["available"]:
        st.caption(
            t(
                "rm.review.follow_up.actions",
                language,
                actions=", ".join(str(action) for action in follow_up["actions"]),
            )
        )
    whatif = follow_up.get("whatif_supporting_evidence", {})
    if isinstance(whatif, Mapping):
        st.caption(str(whatif.get("message", t("rm.review.whatif.unavailable", language))))
        st.caption(t("rm.review.whatif.disclaimer", language))

    _render_rm_action_controls(
        review,
        language=language,
        workflow_service=workflow_service,
    )


def _get_rm_workflow_ui_service() -> RMWorkflowUIService | None:
    """Retain the service instance so a browser retry has one idempotency ledger."""

    key = "rm_workflow_ui_service"
    existing = st.session_state.get(key)
    if isinstance(existing, RMWorkflowUIService):
        return existing
    try:
        service = create_file_backed_rm_workflow_ui_service()
    except (OSError, ValueError):
        return None
    st.session_state[key] = service
    return service


def _render_rm_action_controls(
    review: Mapping[str, Any],
    *,
    language: str,
    workflow_service: RMWorkflowUIService | None,
) -> None:
    """Render human RM operations without opening repository/audit files in the UI."""

    st.markdown(f"#### {t('rm.review.section.actions', language)}")
    workflow_case = review.get("workflow_case")
    if not isinstance(workflow_case, Mapping) or not workflow_case.get("available"):
        st.info(t("rm.action.no_case", language))
        return
    if workflow_service is None:
        st.warning(t("rm.action.service_unavailable", language))
        return
    alert_id = str(workflow_case["alert_id"])
    case_state = str(workflow_case["state"])
    feedback = st.session_state.get("rm_workflow_feedback")
    if isinstance(feedback, Mapping) and feedback.get("alert_id") == alert_id:
        st.success(str(feedback.get("message", t("rm.action.completed", language))))
    st.caption(t("rm.action.service_boundary", language))

    state_buttons: dict[str, tuple[str, str]] = {
        "NEW": ("ACKNOWLEDGE", "rm.action.acknowledge"),
        "ACKNOWLEDGED": ("START_REVIEW", "rm.action.start_review"),
        "IN_REVIEW": ("SET_FOLLOW_UP", "rm.action.follow_up"),
        "CLOSED": ("REOPEN", "rm.action.reopen"),
    }
    state_button = state_buttons.get(case_state)
    if state_button is not None:
        operation, label_key = state_button
        if st.button(
            t(label_key, language),
            key=f"rm_action_{operation.lower()}_{alert_id}_{case_state}",
            type="primary" if operation in {"ACKNOWLEDGE", "START_REVIEW"} else "secondary",
        ):
            _submit_rm_action(
                workflow_service,
                alert_id=alert_id,
                expected_state=case_state,
                operation=operation,
                language=language,
            )

    if case_state != "CLOSED":
        action = st.selectbox(
            t("rm.action.record_label", language),
            (
                "REVIEW_COMPLETED",
                "CONTACT_PLANNED",
                "CONTACT_COMPLETED",
                "MONITOR_ONLY",
                "NO_ACTION_REQUIRED",
                "REFERRED",
                "FOLLOW_UP_CREATED",
            ),
            format_func=lambda code: t(f"rm.action.code.{code}", language),
            key=f"rm_action_record_choice_{alert_id}_{case_state}",
        )
        if st.button(
            t("rm.action.record", language),
            key=f"rm_action_record_{alert_id}_{case_state}_{action}",
        ):
            _submit_rm_action(
                workflow_service,
                alert_id=alert_id,
                expected_state=case_state,
                operation="RECORD_ACTION",
                action=str(action),
                language=language,
            )
        close_options: dict[str, str] = {
            "REVIEW_DOCUMENTED": "REVIEW_COMPLETE_NO_FURTHER_ACTION",
            "CONTACT_DOCUMENTED": "CONTACT_COMPLETED",
            "NO_ACTION_REQUIRED": "REVIEW_COMPLETE_NO_FURTHER_ACTION",
            "REFERRED": "REFERRED_TO_SPECIALIST",
            "CLOSED_UNRESOLVED": "UNRESOLVED",
        }
        close_outcome = st.selectbox(
            t("rm.action.close_label", language),
            tuple(close_options),
            format_func=lambda code: t(f"rm.action.outcome.{code}", language),
            key=f"rm_action_close_choice_{alert_id}_{case_state}",
        )
        if st.button(
            t("rm.action.close", language),
            key=f"rm_action_close_{alert_id}_{case_state}_{close_outcome}",
        ):
            _submit_rm_action(
                workflow_service,
                alert_id=alert_id,
                expected_state=case_state,
                operation="CLOSE",
                close_outcome=str(close_outcome),
                closure_reason=close_options[str(close_outcome)],
                language=language,
            )

    with st.expander(t("rm.notification.preview_heading", language), expanded=False):
        st.caption(t("rm.notification.preview_not_sent", language))
        if st.button(
            t("rm.notification.preview_generate", language),
            key=f"rm_notification_preview_{alert_id}_{case_state}",
        ):
            try:
                case = load_rm_workflow_case(workflow_service, alert_id=alert_id)
                if case is None:
                    raise KeyError(alert_id)
                st.session_state[f"rm_notification_preview_result:{alert_id}"] = (
                    build_offline_notification_preview(workflow_service, alert_case=case)
                )
            except (KeyError, OSError, ValueError, RuntimeError):
                st.warning(t("rm.notification.preview_unavailable", language))
        preview = st.session_state.get(f"rm_notification_preview_result:{alert_id}")
        if isinstance(preview, Mapping):
            st.markdown(f"**{preview.get('title', '')}**")
            st.write(str(preview.get("body", "")))
            st.code(str(preview.get("deep_link", "")), language=None)
            st.caption(t("rm.notification.preview_not_sent", language))


def _submit_rm_action(
    workflow_service: RMWorkflowUIService,
    *,
    alert_id: str,
    expected_state: str,
    operation: str,
    language: str,
    action: str | None = None,
    close_outcome: str | None = None,
    closure_reason: str | None = None,
) -> None:
    """Call the Banker service once; retries reuse identical token and timestamp."""

    submission_key = ":".join(("rm_submission", alert_id, expected_state, operation, action or close_outcome or ""))
    submission = st.session_state.get(submission_key)
    if not isinstance(submission, Mapping):
        submission = {
            "token": make_submission_token(
                alert_id=alert_id,
                expected_state=expected_state,  # type: ignore[arg-type]
                operation=operation,  # type: ignore[arg-type]
                action=action or close_outcome,
            ),
            "occurred_at": utc_now(),
        }
        st.session_state[submission_key] = submission
    try:
        response = perform_rm_workflow_operation(
            workflow_service,
            operation=operation,  # type: ignore[arg-type]
            alert_id=alert_id,
            expected_state=expected_state,  # type: ignore[arg-type]
            occurred_at=submission["occurred_at"],
            actor_reference="rm-demo",
            idempotency_token=str(submission["token"]),
            action=action,  # type: ignore[arg-type]
            close_outcome=close_outcome,  # type: ignore[arg-type]
            closure_reason=closure_reason,  # type: ignore[arg-type]
        )
    except (KeyError, OSError, ValueError, RuntimeError) as error:
        st.error(t("rm.action.failed", language, detail=str(error)))
        return
    st.session_state["rm_workflow_feedback"] = {
        "alert_id": response.alert_case.alert_id,
        "message": t(
            "rm.action.completed_replay" if response.idempotent_replay else "rm.action.completed",
            language,
        ),
    }
    st.rerun()


def _render_rm_activity_audit(
    review: Mapping[str, Any] | None,
    *,
    language: str,
    workflow_service: RMWorkflowUIService | None,
) -> None:
    """Show read-only time-ordered audit evidence for the current RM context."""

    if workflow_service is None:
        st.warning(t("rm.action.service_unavailable", language))
        return
    workflow_case = review.get("workflow_case") if isinstance(review, Mapping) else None
    alert_id = workflow_case.get("alert_id") if isinstance(workflow_case, Mapping) else None
    customer_id = review.get("customer_id") if isinstance(review, Mapping) else None
    history = build_rm_activity_history(
        workflow_service,
        alert_id=str(alert_id) if alert_id else None,
        customer_id=str(customer_id) if customer_id else None,
    )
    if not history["available"]:
        st.warning(t("rm.audit.unavailable", language))
        return
    events = history["events"]
    if not events:
        st.info(t("rm.audit.empty", language))
        return
    st.caption(t("rm.audit.caption", language))
    st.dataframe(pd.DataFrame(events), hide_index=True, width="stretch")


def _rm_display_decimal(value: object, *, language: str = "ko") -> str:
    return t("rm.value.unavailable", language) if not isinstance(value, (int, float)) else f"{float(value):.3f}"


def render_presentation_population_evidence_strip(strip: Mapping[str, Any]) -> None:
    """Render the prepared population context without performing UI-side analysis."""

    if not strip.get("available"):
        st.caption(str(strip.get("message", "")))
        return
    items = tuple(strip.get("items", ()))
    if not items:
        return
    st.caption(str(strip.get("message", "")))
    st.markdown(
        " | ".join(f"**{label}** {value}" for label, value in items),
        unsafe_allow_html=False,
    )


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
    # Presentation scene 1 is a current-state view.  Keep the established
    # customer identity and current KPIs, but reserve historical landmark
    # evidence for scene 3 instead of presenting it as a current-date claim.
    first_screen = {
        **first_screen,
        "kpi_cards": list(first_screen["kpi_cards"][:4]),
        "status_sentence": scenes["current"]["message"],
    }
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
    population_strip = build_presentation_population_strip(
        customer_id=customer_id,
        population_evidence=selection.presentation_population_evidence,
        language=language,
    )
    current_review_signal = build_presentation_current_review_signal(
        customer_id=customer_id,
        population_evidence=selection.presentation_population_evidence,
        language=language,
    )
    render_presentation_population_evidence_strip(population_strip)
    tabs = st.tabs(get_presentation_tab_labels(language))

    with tabs[0]:
        render_presentation_current_scene(
            first_screen=first_screen,
            target_history=current_history,
            scene=scenes["current"],
            current_review_signal=current_review_signal,
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
    current_review_signal: Mapping[str, str] | None = None,
    language: str = "ko",
) -> None:
    """Render presentation tab 1 from prepared display values."""

    st.markdown(render_presentation_scene_heading_html(scene), unsafe_allow_html=True)
    st.markdown(render_customer_identity_html(first_screen["customer_identity"], language=language), unsafe_allow_html=True)
    st.markdown(render_kpi_cards_html(first_screen["kpi_cards"], language=language), unsafe_allow_html=True)
    st.markdown(render_status_summary_html(first_screen["status_sentence"]), unsafe_allow_html=True)
    if current_review_signal is not None:
        st.caption(
            f"{current_review_signal['label']}: {current_review_signal['value']} · "
            f"{current_review_signal['detail']}"
        )

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
        )
    with chart_cols[1]:
        st.markdown(f'<p class="fpt-inline-summary">{view_model["outcome_sentence"]}</p>', unsafe_allow_html=True)
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
    st.caption(t("presentation.breakpoint.caption", language))
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
    st.caption(t("presentation.whatif.disclaimer", language))
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
        st.markdown(f'<p class="fpt-inline-summary">{view_model["outcome_sentence"]}</p>', unsafe_allow_html=True)
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


def render_chart_or_table(
    figure_factory: Callable[[], Any],
    fallback_df: pd.DataFrame | None = None,
    *,
    presentation_mode: bool = False,
    language: str = "ko",
) -> None:
    """Render a Plotly figure, falling back to a compact table."""

    try:
        st.plotly_chart(
            figure_factory(),
            width="stretch",
            config={"displayModeBar": not presentation_mode, "responsive": True},
        )
    except Exception:  # noqa: BLE001
        st.warning(t("ui.chart_fallback", language))
        if fallback_df is not None and not fallback_df.empty:
            st.dataframe(fallback_df, hide_index=True, width="stretch")
        else:
            st.info(t("ui.chart_fallback_empty", language))


if __name__ == "__main__":
    main()
