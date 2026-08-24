"""Contracts for the separate, display-only RM Workspace shell."""

from __future__ import annotations

import ast
import json
import inspect
from contextlib import nullcontext
from pathlib import Path

import app as app_module
from streamlit.testing.v1 import AppTest

from src.copy import APP_MODE_OPTIONS
from src.i18n import t
from src.presentation import GENERAL_MODE, PRESENTATION_MODE, get_presentation_tab_labels
from src.rm_workspace import (
    RM_WORKSPACE_MODE,
    build_rm_workspace_view_model,
    get_rm_workspace_tab_labels,
    load_rm_workspace_artifacts,
)


def _cohort() -> dict[str, object]:
    return {
        "records": [
            {"category_id": "priority_review", "customer_id": "C000001", "status": "selected"},
            {"category_id": "early_signal_review", "customer_id": "C000007", "status": "selected"},
            {"category_id": "monitor_no_alert_comparison", "customer_id": "C000003", "status": "selected"},
            {
                "category_id": "insufficient_or_landmark_not_found",
                "customer_id": None,
                "status": "unavailable",
            },
        ]
    }


def test_mode_contract_keeps_general_presentation_and_separate_rm_workspace() -> None:
    assert APP_MODE_OPTIONS == ("일반 모드", "발표 모드", "RM 업무 모드")
    assert GENERAL_MODE == APP_MODE_OPTIONS[0]
    assert PRESENTATION_MODE == APP_MODE_OPTIONS[1]
    assert RM_WORKSPACE_MODE == APP_MODE_OPTIONS[2]
    assert get_presentation_tab_labels("ko") == [
        "① 현재 상태",
        "② 유사 경로",
        "③ 유사 경로 근거",
        "④ 대응 시나리오",
        "⑤ 분석 요약",
    ]
    assert get_rm_workspace_tab_labels("ko") == [
        "포트폴리오",
        "검토 큐",
        "고객 검토",
        "활동/감사",
    ]
    assert get_rm_workspace_tab_labels("en") == [
        "Portfolio",
        "Review Queue",
        "Customer Review",
        "Activity / Audit",
    ]


def test_workspace_view_model_displays_exported_funnel_and_honest_representative_availability() -> None:
    model = build_rm_workspace_view_model(
        language="en",
        funnel={"monitored_total": 5000, "eligible_total": 1522, "selected_queue_ready": 1522},
        representative_cohort=_cohort(),
        customer_context="C000007",
    )

    assert [stage["count"] for stage in model["funnel"]] == [5000, 1522, 1522]
    assert model["tabs"] == get_rm_workspace_tab_labels("en")
    assert model["customer_review_target"] == "C000007"
    assert [item["customer_id"] for item in model["representative_quick_selects"]] == [
        "C000001",
        "C000007",
        "C000003",
        None,
    ]
    assert model["representative_quick_selects"][-1]["status"] == "unavailable"
    assert model["scope"] == {
        "analytics_recomputed": False,
        "triage_selection_changed": False,
        "case_mutated": False,
        "notification_sent": False,
    }


def test_workspace_shell_does_not_substitute_a_default_population_for_missing_artifacts() -> None:
    model = build_rm_workspace_view_model(language="en", funnel=None, representative_cohort=None)

    assert [stage["count"] for stage in model["funnel"]] == [None, None, None]


def test_workspace_artifact_loader_is_read_only_and_handles_missing_or_corrupt_files(tmp_path: Path) -> None:
    missing = load_rm_workspace_artifacts(tmp_path)
    assert missing.funnel is None
    assert missing.representative_cohort is None

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    incomplete_manifest = {"funnel": {"monitored_total": 5000, "eligible_total": 2, "selected_queue_ready": 1}}
    (run_dir / "rm_selection_manifest.json").write_text(
        json.dumps(incomplete_manifest),
        encoding="utf-8",
    )
    (run_dir / "rm_representative_cohort.json").write_text(json.dumps(_cohort()), encoding="utf-8")
    partial = load_rm_workspace_artifacts(tmp_path)
    assert partial.funnel is None
    assert partial.load_error == "artifact_unavailable"

    complete_funnel = {
        "monitored_total": 5000,
        "eligible_priority": 1,
        "eligible_review": 1,
        "eligible_total": 2,
        "selected_queue_ready": 1,
        "deferred_capacity": 1,
        "monitor_only": 1,
        "no_actionable_signal": 4995,
        "insufficient_evidence": 0,
        "data_unavailable": 0,
    }
    (run_dir / "rm_selection_manifest.json").write_text(
        json.dumps({"funnel": complete_funnel, "records": []}),
        encoding="utf-8",
    )
    loaded = load_rm_workspace_artifacts(tmp_path)
    assert loaded.funnel == complete_funnel
    assert loaded.representative_cohort == _cohort()

    (run_dir / "rm_selection_manifest.json").write_text("{bad", encoding="utf-8")
    corrupt = load_rm_workspace_artifacts(tmp_path)
    assert corrupt.load_error == "artifact_unavailable"


def test_rm_renderer_uses_four_tabs_and_never_recalculates_analysis(monkeypatch) -> None:
    labels_seen: list[str] = []
    metrics_seen: list[tuple[str, str]] = []
    initial_customer = app_module.st.session_state.get("selected_customer_id")
    monkeypatch.setattr(
        app_module,
        "load_rm_workspace_artifacts",
        lambda: type("Artifacts", (), {"funnel": {"monitored_total": 5000}, "representative_cohort": _cohort(), "source_reference": "test", "load_error": None})(),
    )
    monkeypatch.setattr(
        app_module,
        "load_rm_alert_cases",
        lambda: type("AlertSnapshot", (), {"cases": (), "load_error": None})(),
    )
    monkeypatch.setattr(
        app_module,
        "build_rm_workspace_view_model",
        lambda **kwargs: build_rm_workspace_view_model(
            language=kwargs["language"],
            funnel=kwargs["funnel"],
            representative_cohort=kwargs["representative_cohort"],
            customer_context=kwargs["customer_context"],
        ),
    )
    monkeypatch.setattr(
        app_module.st,
        "tabs",
        lambda labels: (labels_seen.extend(labels) or [nullcontext() for _ in labels]),
    )
    monkeypatch.setattr(app_module.st, "columns", lambda count: [nullcontext() for _ in range(count)])
    monkeypatch.setattr(app_module.st, "metric", lambda label, value: metrics_seen.append((label, value)))
    monkeypatch.setattr(app_module.st, "selectbox", lambda _label, options, **_kwargs: options[0])
    monkeypatch.setattr(app_module.st, "info", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_module.st, "caption", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_module.st, "success", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_module.st, "warning", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        app_module,
        "run_customer_analysis",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("analysis must not run")),
    )

    app_module.render_rm_workspace_mode(
        selection=app_module.SidebarSelection(
            customer_id="",
            selected_metric="",
            app_mode=RM_WORKSPACE_MODE,
            presentation_mode=False,
            show_raw_samples=False,
            rm_workspace_mode=True,
        ),
        language="en",
    )

    assert labels_seen == get_rm_workspace_tab_labels("en")
    assert metrics_seen[0] == ("All Customers", "5,000")
    assert app_module.st.session_state.get("selected_customer_id") == initial_customer


def test_rm_view_model_module_has_no_streamlit_or_analytics_dependency() -> None:
    import src.rm_workspace as rm_workspace

    source = Path(rm_workspace.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    ]

    assert "streamlit" not in source.lower()
    assert "run_customer_analysis" not in source
    assert "final_outcome" not in source
    assert "persona" not in source
    assert not any("matcher" in module or "evaluator" in module for module in imported_modules)


def test_app_test_switches_to_rm_shell_without_changing_presentation_tab_contract() -> None:
    app_path = Path(app_module.__file__)
    at = AppTest.from_file(app_path)
    at.run(timeout=45)
    presentation_tabs = [tab.label for tab in at.tabs]
    assert presentation_tabs == get_presentation_tab_labels("ko")

    at.sidebar.selectbox(key="app_mode").set_value(RM_WORKSPACE_MODE).run(timeout=45)

    assert not at.exception
    assert [tab.label for tab in at.tabs] == get_rm_workspace_tab_labels("ko")
    assert [widget.key for widget in at.sidebar.selectbox] == [
        "app_mode",
        "rm_queue_scope",
        "rm_priority_scope",
        "rm_owner_scope",
        "rm_due_scope",
    ]
    # Portfolio shows the complete selection funnel plus Alert and in-app delivery counts.
    portfolio_metric_labels = {
        t("rm.portfolio.monitored_total", "ko"),
        t("rm.portfolio.eligible_priority", "ko"),
        t("rm.portfolio.eligible_review", "ko"),
        t("rm.portfolio.eligible_total", "ko"),
        t("rm.portfolio.selected_queue_ready", "ko"),
        t("rm.portfolio.deferred_capacity", "ko"),
        t("rm.portfolio.monitor_only", "ko"),
        t("rm.portfolio.no_actionable_signal", "ko"),
        t("rm.portfolio.insufficient_evidence", "ko"),
        t("rm.portfolio.data_unavailable", "ko"),
        t("rm.alert.new", "ko"),
        t("rm.alert.open", "ko"),
        t("rm.alert.due", "ko"),
        t("rm.alert.overdue", "ko"),
        t("rm.alert.in_rm_queue", "ko"),
        t("rm.alert.selected_pending", "ko"),
    }
    assert portfolio_metric_labels.issubset({metric.label for metric in at.metric})
    # The default representative is safely routed to Customer Review in the
    # same mode, so its observed-signal metrics may be present as well.
    assert [header.value.split()[0] for header in at.subheader] == ["C000001"]
    assert [widget.key for widget in at.text_input] == ["rm_queue_search"]
    assert any(widget.key == "rm_queue_sort" for widget in at.selectbox)
    assert [frame.key for frame in at.dataframe if frame.key == "rm_review_queue_table"] == [
        "rm_review_queue_table"
    ]
    assert len(at.dataframe) == 2


def test_app_test_rm_queue_keeps_english_mode_and_selected_queue_shell() -> None:
    at = AppTest.from_file(Path(app_module.__file__))
    at.run(timeout=45)
    at.selectbox(key="ui_language").set_value("en").run(timeout=45)
    at.sidebar.selectbox(key="app_mode").set_value(RM_WORKSPACE_MODE).run(timeout=45)

    assert not at.exception
    assert [tab.label for tab in at.tabs] == get_rm_workspace_tab_labels("en")
    assert [frame.key for frame in at.dataframe if frame.key == "rm_review_queue_table"] == [
        "rm_review_queue_table"
    ]
    assert len(at.dataframe) == 2


def test_app_test_rm_capacity_comparison_is_opt_in_and_keeps_saved_queue_unchanged() -> None:
    at = AppTest.from_file(Path(app_module.__file__))
    at.run(timeout=45)
    at.sidebar.selectbox(key="app_mode").set_value(RM_WORKSPACE_MODE).run(timeout=45)

    assert not at.exception
    assert len(at.dataframe) == 2
    at.checkbox(key="rm_capacity_comparison_enabled").set_value(True).run(timeout=45)
    at.number_input(key="rm_capacity_comparison_value").set_value(1).run(timeout=45)

    assert not at.exception
    assert len(at.dataframe) == 3
    assert [frame.key for frame in at.dataframe if frame.key == "rm_review_queue_table"] == [
        "rm_review_queue_table"
    ]


def test_app_test_rm_customer_review_renders_observed_evidence_without_changing_tabs() -> None:
    at = AppTest.from_file(Path(app_module.__file__))
    at.run(timeout=45)
    at.sidebar.selectbox(key="app_mode").set_value(RM_WORKSPACE_MODE).run(timeout=45)
    # The deterministic representative quick-select supplies the persisted customer context.
    at.run(timeout=45)

    assert not at.exception
    assert [tab.label for tab in at.tabs] == get_rm_workspace_tab_labels("ko")
    assert [header.value.split()[0] for header in at.subheader] == ["C000001"]
    # Queue and historical-outcome distribution are distinct display tables.
    assert len(at.dataframe) == 2


def test_app_test_representative_customer_switches_do_not_reuse_prior_context() -> None:
    at = AppTest.from_file(Path(app_module.__file__))
    at.run(timeout=45)
    at.sidebar.selectbox(key="app_mode").set_value(RM_WORKSPACE_MODE).run(timeout=45)

    at.selectbox(key="rm_representative_quick_select").set_value("early_signal_review").run(
        timeout=45
    )
    assert not at.exception
    assert [header.value.split()[0] for header in at.subheader] == ["C000007"]

    at.selectbox(key="rm_representative_quick_select").set_value("priority_review").run(
        timeout=45
    )
    assert not at.exception
    assert [header.value.split()[0] for header in at.subheader] == ["C000001"]


def test_customer_review_renderer_uses_only_display_chart_helpers() -> None:
    source = inspect.getsource(app_module._render_rm_customer_review)

    assert "create_current_trajectory_chart" in source
    assert "create_twin_trajectory_chart" not in source
    assert "run_customer_analysis" not in source
