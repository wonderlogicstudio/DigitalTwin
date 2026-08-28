"""Streamlit app for the Financial Path Twin demo."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

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
from src.daily_worklist import build_daily_worklist  # noqa: E402
from src.rm_daily_review_view import (  # noqa: E402
    build_rm_customer_detail_view,
    build_rm_daily_review_view,
)
from src.rm_review_store import (  # noqa: E402
    append_review_event,
    create_review_event,
    load_review_events,
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


RM_DAILY_REVIEW_MODE = "RM 오늘의 업무"
RM_DAILY_REVIEW_SNAPSHOT_DIR = PROJECT_ROOT / "artifacts" / "rm_daily_review" / "monthly"


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
        render_rm_daily_review_mode()
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
            "RM 오늘의 업무"
            if mode == RM_DAILY_REVIEW_MODE
            else t("mode.presentation" if mode == PRESENTATION_MODE else "mode.normal", language)
        ),
        key="app_mode",
    )
    presentation_mode = app_mode == PRESENTATION_MODE
    rm_daily_review_mode = app_mode == RM_DAILY_REVIEW_MODE
    if rm_daily_review_mode:
        st.sidebar.caption("저장된 월별 분석 Snapshot을 읽어 오늘의 RM 업무를 표시합니다.")
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
        and event.reviewed_at.astimezone().date() == daily_date
    }
    return build_daily_worklist(
        snapshot_artifact,
        daily_date=daily_date,
        completed_customer_ids=completed_customer_ids,
        snapshot_published_on=datetime.fromtimestamp(snapshot_path.stat().st_mtime).date(),
    )


def render_rm_daily_review_mode(*, daily_date: date | None = None) -> None:
    """Render the simple RM work screen without loading or running analytics."""

    st.title("RM 오늘의 업무")
    st.caption("저장된 월별 분석 Snapshot을 읽어 오늘의 확인 업무를 보여줍니다.")
    try:
        snapshot_result = load_latest_rm_snapshot_artifact()
    except (OSError, ValueError, json.JSONDecodeError):
        st.warning("월별 Snapshot을 읽을 수 없습니다. 아래 CLI로 Snapshot을 다시 생성해 주세요.")
        _render_rm_snapshot_cli_guidance()
        return
    if snapshot_result is None:
        st.info("저장된 월별 Snapshot이 없습니다. 아래 CLI로 먼저 Snapshot을 생성해 주세요.")
        _render_rm_snapshot_cli_guidance()
        return

    snapshot_path, snapshot_artifact = snapshot_result
    current_date = daily_date or date.today()
    try:
        worklist = build_rm_daily_review_worklist(
            snapshot_artifact,
            snapshot_path=snapshot_path,
            daily_date=current_date,
        )
        dashboard = build_rm_daily_review_view(worklist)
    except (OSError, ValueError, json.JSONDecodeError):
        st.warning("월별 Snapshot 업무 목록을 준비할 수 없습니다. CLI 생성 결과를 확인해 주세요.")
        _render_rm_snapshot_cli_guidance()
        return

    st.caption(f"{dashboard.analysis_as_of_label} · {dashboard.snapshot_freshness_label}")
    summary_columns = st.columns(4)
    for column, label, count in zip(
        summary_columns,
        ("오늘 먼저 확인", "곧 확인 예정", "모니터링", "오늘 완료"),
        (
            dashboard.today_count,
            dashboard.upcoming_count,
            dashboard.monitor_count,
            dashboard.completed_today_count,
        ),
    ):
        with column:
            st.metric(label, f"{count}명")

    rows_by_state: dict[str, list[Any]] = {
        "오늘 먼저 확인": [],
        "곧 확인 예정": [],
        "모니터링": [],
    }
    for row in dashboard.customer_list:
        rows_by_state.setdefault(row.review_state_label, []).append(row)
    today_tab, upcoming_tab, monitor_tab = st.tabs(
        [
            f"오늘 먼저 확인 ({dashboard.today_count})",
            f"곧 확인 예정 ({dashboard.upcoming_count})",
            f"모니터링 ({dashboard.monitor_count})",
        ]
    )
    with today_tab:
        _render_rm_customer_rows(rows_by_state["오늘 먼저 확인"], key_prefix="rm_today")
    with upcoming_tab:
        core_only = st.checkbox("핵심관리만 보기", key="rm_upcoming_core_only")
        upcoming_rows = rows_by_state["곧 확인 예정"]
        if core_only:
            upcoming_rows = [row for row in upcoming_rows if row.relationship_badge == "핵심관리"]
        _render_rm_customer_rows(upcoming_rows, key_prefix="rm_upcoming")
    with monitor_tab:
        st.caption(
            f"현재 모니터링 대상은 {dashboard.monitor_count}명입니다. 고객 ID로 필요한 고객만 찾아볼 수 있습니다."
        )
        monitor_search = st.text_input("모니터링 고객 ID 검색", key="rm_monitor_search")
        if monitor_search.strip():
            matches = [
                row
                for row in rows_by_state["모니터링"]
                if monitor_search.strip().upper() in row.customer_id.upper()
            ]
            _render_rm_customer_rows(matches, key_prefix="rm_monitor")

    selected_customer_id = st.session_state.get("rm_selected_customer_id")
    if selected_customer_id:
        _render_rm_customer_detail(worklist, str(selected_customer_id))


def _render_rm_snapshot_cli_guidance() -> None:
    st.code("python scripts/build_rm_monthly_snapshot.py --snapshot-id YYYY-MM", language="bash")


def _render_rm_customer_rows(rows: list[Any], *, key_prefix: str) -> None:
    if not rows:
        st.info("표시할 고객이 없습니다.")
        return
    for row in rows:
        columns = st.columns([1.0, 1.0, 4.3, 1.0])
        with columns[0]:
            st.markdown(f"**{row.customer_id}**")
        with columns[1]:
            st.caption(row.relationship_badge)
        with columns[2]:
            st.write(row.why_today)
        with columns[3]:
            if st.button("고객 보기", key=f"{key_prefix}_{row.customer_id}"):
                st.session_state["rm_selected_customer_id"] = row.customer_id


def _render_rm_customer_detail(worklist: Any, customer_id: str) -> None:
    try:
        detail = build_rm_customer_detail_view(worklist, customer_id)
    except ValueError:
        st.session_state.pop("rm_selected_customer_id", None)
        return
    st.divider()
    st.subheader(f"고객 검토 · {detail.customer_id}")
    st.caption("아래는 검토를 돕는 순서이며, 각 단계를 강제하지 않습니다.")
    st.markdown("#### 1. 왜 오늘 확인?")
    st.write(detail.why_today)
    st.markdown("#### 2. 고객관계 정보")
    st.caption(f"{detail.relationship_badge} · {detail.relationship_context}")
    st.caption("고객관계 중요도는 합성 CRM 메타데이터이며, 오늘 확인 timing 근거와 별도입니다.")
    st.markdown("#### 3. 대화 준비")
    for point in detail.conversation_preparation:
        st.markdown(f"- {point}")
    with st.expander("4. 분석 근거 (보조)", expanded=False):
        for summary in detail.supporting_analysis.current_summary:
            st.caption(summary)
        for outcome in detail.supporting_analysis.matched_outcome_summary:
            st.caption(outcome)
        st.caption(detail.supporting_analysis.breakpoint_summary)
        st.caption(detail.supporting_analysis.additional_analysis_notice)
    st.markdown("#### 5. 검토 결과 기록")
    if detail.completed_today:
        st.success("6. 완료 · 오늘 검토 결과가 이미 기록되었습니다.")
        return
    option_by_label = {option.label: option.result for option in detail.result_recording.result_options}
    selected_label = st.selectbox(
        "검토 결과",
        list(option_by_label),
        key=f"rm_result_{detail.customer_id}",
    )
    note = st.text_area(
        "메모 (선택)",
        key=f"rm_note_{detail.customer_id}",
    )
    if st.button("결과 기록", key=f"rm_save_{detail.customer_id}"):
        event = create_review_event(
            customer_id=detail.result_recording.customer_id,
            snapshot_id=detail.result_recording.snapshot_id,
            reviewed_at=datetime.now().astimezone(),
            result=option_by_label[selected_label],
            note=note,
        )
        append_review_event(event)
        st.success("6. 완료 · 검토 결과를 기록했습니다.")


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
