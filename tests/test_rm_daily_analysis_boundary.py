"""Regression guards for the boundary between monthly analysis and Daily Review."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import inspect
import json
import os
from contextlib import nullcontext
from datetime import date, datetime
from pathlib import Path

import pandas as pd

import app as app_module
import src.breakpoint_analyzer as breakpoint_analyzer
import src.customer_analysis as customer_analysis
import src.demo_selector as demo_selector
import src.feature_engineering as feature_engineering
import src.monthly_review_snapshot as monthly_review_snapshot
import src.pipeline as pipeline
import src.whatif_simulator as whatif_simulator
from src.daily_worklist import FRESHNESS_PRIOR_MONTH
from src.matcher import TrajectoryMatcher
from src.monthly_review_snapshot import build_monthly_review_snapshot
from src.rm_daily_review_view import (
    build_rm_customer_detail_view,
    build_rm_daily_review_view,
)
from src.rm_portfolio import (
    RELATIONSHIP_LABELS,
    RmPortfolio,
    RmPortfolioCustomer,
)
from src.rm_daily_review_loader import (
    ControlledLoadingAdapter,
    SavedDailyReviewLoadResult,
    load_saved_rm_daily_review,
)
from src.rm_review_store import (
    REVIEW_FOLLOW_UP,
    append_review_event,
    create_review_event,
    load_review_events,
)


def _snapshot_artifact() -> dict[str, object]:
    return {
        "snapshot_id": "monthly-2026-07",
        "analysis_as_of_month": 12,
        "rm_portfolio_id": "RM-POC-001",
        "universe_customer_count": 5_000,
        "portfolio_size": 2,
        "records": [
            {
                "customer_id": "C000001",
                "snapshot_id": "monthly-2026-07",
                "current_summary": {"current_status": "watch"},
                "matched_count": 200,
                "breakpoint": {
                    "status": "found",
                    "breakpoint_month": 13,
                    "months_from_current": 1,
                    "primary_factor": "cash_balance_ratio",
                },
                "evidence": {"available": True, "status": "available", "errors": {}},
                "relationship_metadata": {
                    "source": "synthetic_crm_overlay",
                    "rm_portfolio_id": "RM-POC-001",
                    "relationship_priority": "CORE",
                    "relationship_label": "핵심관리",
                },
                "outcome_summary": {"matched_count": 200, "outcomes": {}},
            },
            {
                "customer_id": "C000002",
                "snapshot_id": "monthly-2026-07",
                "current_summary": {"current_status": "healthy"},
                "matched_count": 200,
                "breakpoint": {
                    "status": "found",
                    "breakpoint_month": 15,
                    "months_from_current": 3,
                    "primary_factor": "dsr",
                },
                "evidence": {"available": True, "status": "available", "errors": {}},
                "relationship_metadata": {
                    "source": "synthetic_crm_overlay",
                    "rm_portfolio_id": "RM-POC-001",
                    "relationship_priority": "STANDARD",
                    "relationship_label": "일반관리",
                },
                "outcome_summary": {"matched_count": 200, "outcomes": {}},
            },
        ],
    }


def _e2e_snapshot_artifact() -> dict[str, object]:
    """Saved-only fixture covering today, upcoming, monitor, and detail evidence."""

    snapshot = deepcopy(_snapshot_artifact())
    records = snapshot["records"]
    assert isinstance(records, list)
    first = records[0]
    second = records[1]
    assert isinstance(first, dict)
    assert isinstance(second, dict)
    first["supporting_evidence"] = {
        "available": True,
        "evidence_status": "available",
        "why_now": {
            "breakpoint_status": "found",
            "months_from_current": 1,
            "primary_factor": "cash_balance_ratio",
        },
        "current_change_cards": [
            {
                "key": "cash_availability",
                "value": 2,
                "value_type": "consecutive_months",
            }
        ],
        "cohort_path_chart": {
            "available": True,
            "metric": "cash_balance_ratio",
            "risk_path": [{"month": 1, "mean": 0.61}, {"month": 13, "mean": 0.38}],
            "avoidance_path": [{"month": 1, "mean": 0.60}, {"month": 13, "mean": 0.70}],
            "group_sizes": {"risk_path": 50, "avoidance_path": 150},
            "breakpoint_marker": {"month": 13},
        },
        "outcome_summary": {"matched_count": 200, "outcomes": {}},
        "whatif_summary": {
            "available": True,
            "scenarios": [{"scenario_name": "baseline"}],
        },
    }
    second["relationship_metadata"] = {
        **second["relationship_metadata"],  # type: ignore[arg-type]
        "relationship_priority": "CORE",
        "relationship_label": "CORE",
    }
    records.append(
        {
            "customer_id": "C000003",
            "snapshot_id": "monthly-2026-07",
            "current_summary": {"current_status": "healthy"},
            "matched_count": 200,
            "breakpoint": {
                "status": "insufficient_group_size",
                "breakpoint_month": None,
                "months_from_current": None,
                "primary_factor": None,
            },
            "evidence": {
                "available": False,
                "status": "insufficient_group_size",
                "errors": {},
            },
            "relationship_metadata": {
                "source": "synthetic_crm_overlay",
                "rm_portfolio_id": "RM-POC-001",
                "relationship_priority": "STANDARD",
                "relationship_label": "STANDARD",
            },
            "outcome_summary": {"matched_count": 200, "outcomes": {}},
            "supporting_evidence": {
                "available": False,
                "evidence_status": "insufficient_group_size",
            },
        }
    )
    return snapshot


def _fail_if_called(name: str):
    def _blocked(*_args: object, **_kwargs: object) -> object:
        raise AssertionError(f"Daily Review must not call {name}.")

    return _blocked


def _block_live_analytics(monkeypatch) -> None:
    """Make every prohibited Daily analytics operation fail loudly."""

    monkeypatch.setattr(
        feature_engineering,
        "build_trajectory_features",
        _fail_if_called("feature engineering"),
    )
    monkeypatch.setattr(TrajectoryMatcher, "fit", _fail_if_called("matcher.fit"))
    monkeypatch.setattr(TrajectoryMatcher, "match", _fail_if_called("matcher.match"))
    monkeypatch.setattr(
        demo_selector,
        "build_final_outcome_lookup",
        _fail_if_called("outcome aggregation"),
    )
    monkeypatch.setattr(
        demo_selector,
        "summarize_matched_outcomes",
        _fail_if_called("outcome aggregation"),
    )
    monkeypatch.setattr(
        breakpoint_analyzer,
        "find_breakpoint",
        _fail_if_called("breakpoint analyzer"),
    )
    monkeypatch.setattr(
        breakpoint_analyzer,
        "prepare_breakpoint_data",
        _fail_if_called("breakpoint analyzer"),
    )
    monkeypatch.setattr(
        whatif_simulator,
        "build_whatif_results",
        _fail_if_called("What-if simulator"),
    )
    monkeypatch.setattr(pipeline, "run_pipeline", _fail_if_called("pipeline"))
    monkeypatch.setattr(
        customer_analysis,
        "run_customer_analysis",
        _fail_if_called("customer analysis service"),
    )
    monkeypatch.setattr(
        app_module,
        "run_customer_analysis",
        _fail_if_called("app customer analysis service"),
    )
    monkeypatch.setattr(app_module, "fit_matcher", _fail_if_called("app matcher"))
    monkeypatch.setattr(app_module, "load_monthly_data", _fail_if_called("monthly data loading"))
    monkeypatch.setattr(app_module, "load_feature_data", _fail_if_called("feature data loading"))
    monkeypatch.setattr(app_module, "load_matcher", _fail_if_called("app matcher loading"))


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_monthly_snapshot_default_remains_existing_customer_analysis_service() -> None:
    """The monthly boundary retains the existing analytics composition by default."""

    analysis_runner = inspect.signature(build_monthly_review_snapshot).parameters[
        "analysis_runner"
    ]
    assert analysis_runner.default is customer_analysis.run_customer_analysis


def test_monthly_snapshot_keeps_relationship_metadata_out_of_analysis_inputs_and_5000_universe(
    monkeypatch,
) -> None:
    """Portfolio metadata is joined after analysis; it never narrows matching."""

    customer_ids = [f"C{index:06d}" for index in range(1, 5_001)]
    features_df = pd.DataFrame({"customer_id": customer_ids})
    monthly_df = pd.DataFrame({"customer_id": ["C000001"], "month": [12]})

    class _FullUniverseMatcher:
        _customer_ids = pd.Series(customer_ids)

    matcher = _FullUniverseMatcher()
    monkeypatch.setattr(
        monthly_review_snapshot,
        "build_current_metrics",
        lambda _monthly_df: pd.DataFrame(
            [{"customer_id": "C000001", "current_status": "healthy"}]
        ),
    )
    observed_arguments: list[tuple[object, ...]] = []

    def analysis_runner(
        customer_id: str,
        received_monthly_df: pd.DataFrame,
        received_features_df: pd.DataFrame,
        received_matcher: object,
        *,
        top_k: int,
    ) -> dict[str, object]:
        observed_arguments.append(
            (
                customer_id,
                received_monthly_df,
                received_features_df,
                received_matcher,
                top_k,
            )
        )
        return {
            "outcome_summary": {"matched_count": top_k, "outcomes": {}},
            "breakpoint_result": {
                "status": "found",
                "breakpoint_month": 13,
                "months_from_current": 1,
                "primary_factor": "cash_balance_ratio",
            },
            "errors": {},
        }

    def build_portfolio(relationship_priority: str) -> RmPortfolio:
        return RmPortfolio(
            rm_portfolio_id="RM-POC-001",
            universe_customer_count=5_000,
            portfolio_selection_seed=20260828,
            relationship_assignment_seed=42,
            customers=(
                RmPortfolioCustomer(
                    customer_id="C000001",
                    rm_portfolio_id="RM-POC-001",
                    relationship_priority=relationship_priority,
                    relationship_label=RELATIONSHIP_LABELS[relationship_priority],
                ),
            ),
        )

    core_snapshot = build_monthly_review_snapshot(
        build_portfolio("CORE"),
        monthly_df,
        features_df,
        matcher,  # type: ignore[arg-type]
        snapshot_id="monthly-12-core",
        top_k=5,
        analysis_runner=analysis_runner,
    )
    standard_snapshot = build_monthly_review_snapshot(
        build_portfolio("STANDARD"),
        monthly_df,
        features_df,
        matcher,  # type: ignore[arg-type]
        snapshot_id="monthly-12-standard",
        top_k=5,
        analysis_runner=analysis_runner,
    )

    assert len(observed_arguments) == 2
    assert all(arguments[0] == "C000001" for arguments in observed_arguments)
    assert all(arguments[1] is monthly_df for arguments in observed_arguments)
    assert all(arguments[2] is features_df for arguments in observed_arguments)
    assert all(len(arguments[2]) == 5_000 for arguments in observed_arguments)
    assert all(arguments[3] is matcher for arguments in observed_arguments)
    assert all(arguments[4] == 5 for arguments in observed_arguments)
    assert core_snapshot.records[0].breakpoint == standard_snapshot.records[0].breakpoint
    assert core_snapshot.records[0].outcome_summary == standard_snapshot.records[0].outcome_summary
    assert (
        core_snapshot.records[0].relationship_metadata
        != standard_snapshot.records[0].relationship_metadata
    )


def test_daily_worklist_and_views_use_saved_artifact_without_analytics_or_financial_writes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Daily work is a read-only projection of saved Snapshot data and review events."""

    _block_live_analytics(monkeypatch)
    snapshot_path = tmp_path / "monthly-2026-07.json"
    snapshot_path.write_text(json.dumps(_snapshot_artifact()), encoding="utf-8")
    os.utime(snapshot_path, (datetime(2026, 7, 31).timestamp(),) * 2)
    financial_data_path = tmp_path / "customer_monthly.csv"
    financial_data_path.write_text("customer_id,month,cash_balance\nC000001,12,100\n", encoding="utf-8")
    customer_master_path = tmp_path / "customer_master.csv"
    customer_master_path.write_text("customer_id\nC000001\n", encoding="utf-8")
    before_digest = _file_digest(financial_data_path)
    before_master_digest = _file_digest(customer_master_path)
    monkeypatch.setattr(app_module.settings, "CUSTOMER_MONTHLY_PATH", financial_data_path)
    monkeypatch.setattr(app_module.settings, "CUSTOMER_MASTER_PATH", customer_master_path)
    monkeypatch.setattr(app_module, "load_review_events", lambda: ())

    worklist = app_module.build_rm_daily_review_worklist(
        _snapshot_artifact(),
        snapshot_path=snapshot_path,
        daily_date=date(2026, 8, 29),
    )
    dashboard = build_rm_daily_review_view(worklist)
    detail = build_rm_customer_detail_view(worklist, "C000001")

    assert [item.customer_id for item in worklist.today_items] == ["C000001"]
    assert worklist.snapshot_freshness.status == FRESHNESS_PRIOR_MONTH
    assert dashboard.today_count == 1
    assert detail.customer_id == "C000001"
    assert _file_digest(financial_data_path) == before_digest
    assert _file_digest(customer_master_path) == before_master_digest


def test_saved_snapshot_e2e_daily_flow_never_calls_analytics_or_snapshot_build(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Daily query, detail, review save, and rerun operate only on saved artifacts."""

    _block_live_analytics(monkeypatch)
    monkeypatch.setattr(
        monthly_review_snapshot,
        "build_monthly_review_snapshot",
        _fail_if_called("monthly snapshot builder"),
    )
    snapshot_directory = tmp_path / "monthly"
    snapshot_directory.mkdir()
    snapshot_path = snapshot_directory / "monthly-2026-07.json"
    snapshot_path.write_text(json.dumps(_e2e_snapshot_artifact()), encoding="utf-8")
    os.utime(snapshot_path, (datetime(2026, 7, 31).timestamp(),) * 2)
    overlay_path = tmp_path / "presentation.json"
    overlay_path.write_text(
        json.dumps(
            {
                "customers": [
                    {
                        "customer_id": "C000001",
                        "display_name": "Synthetic customer 01",
                        "presentation_label": "Synthetic customer display information for this PoC",
                    },
                    {
                        "customer_id": "C000002",
                        "display_name": "Synthetic customer 02",
                    },
                    {
                        "customer_id": "C000003",
                        "display_name": "Synthetic customer 03",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    financial_data_path = tmp_path / "customer_monthly.csv"
    financial_data_path.write_text("customer_id,month,cash_balance\nC000001,12,100\n", encoding="utf-8")
    raw_digest_before = _file_digest(financial_data_path)
    event_path = tmp_path / "review_events.jsonl"
    adapter = ControlledLoadingAdapter(sleep=lambda _seconds: None, monotonic=lambda: 0.0)

    initial = load_saved_rm_daily_review(
        daily_date=date(2026, 8, 29),
        snapshot_directory=snapshot_directory,
        presentation_overlay_path=overlay_path,
        review_events_loader=lambda: load_review_events(event_path),
        loading_adapter=adapter,
        language="en",
    )
    next_day = load_saved_rm_daily_review(
        daily_date=date(2026, 8, 30),
        snapshot_directory=snapshot_directory,
        presentation_overlay_path=overlay_path,
        review_events_loader=lambda: load_review_events(event_path),
        loading_adapter=adapter,
        language="en",
    )

    assert initial.status == "READY"
    assert initial.worklist is not None
    assert initial.dashboard is not None
    assert (initial.dashboard.today_count, initial.dashboard.upcoming_count, initial.dashboard.monitor_count) == (1, 1, 1)
    assert initial.dashboard.today_items[0].display_name == "Synthetic customer 01"
    assert initial.dashboard.upcoming_items[0].relationship_badge == "Core"
    assert next_day.dashboard is not None
    assert [item.timing_months for item in initial.dashboard.customer_list] == [
        item.timing_months for item in next_day.dashboard.customer_list
    ]

    presentation_by_customer = {
        row.customer_id: {
            "display_name": row.display_name,
            "display_owner_or_team": row.display_owner_or_team,
            "presentation_label": row.presentation_label,
        }
        for row in initial.dashboard.customer_list
    }
    detail = build_rm_customer_detail_view(
        initial.worklist,
        "C000001",
        presentation_metadata_by_customer=presentation_by_customer,
        language="en",
    )
    assert detail.display_name == "Synthetic customer 01"
    assert detail.relationship_badge == "Core"
    assert len(detail.conversation_preparation) == 3
    assert detail.supporting_analysis.historical_cohort_chart.available is True

    event = create_review_event(
        review_id="e2e-follow-up",
        customer_id="C000001",
        snapshot_id="monthly-2026-07",
        reviewed_at=datetime(2026, 8, 29, 9, tzinfo=datetime.now().astimezone().tzinfo),
        result=REVIEW_FOLLOW_UP,
        note="Optional RM note",
    )
    append_review_event(event, event_path)
    rerun = load_saved_rm_daily_review(
        daily_date=date(2026, 8, 29),
        snapshot_directory=snapshot_directory,
        presentation_overlay_path=overlay_path,
        review_events_loader=lambda: load_review_events(event_path),
        loading_adapter=adapter,
        language="en",
    )

    assert rerun.dashboard is not None
    assert rerun.worklist is not None
    assert rerun.dashboard.today_count == 0
    assert rerun.dashboard.completed_today_count == 1
    assert [item.customer_id for item in rerun.worklist.completed_today] == ["C000001"]
    assert load_review_events(event_path) == (event,)
    assert _file_digest(financial_data_path) == raw_digest_before


class _NoSnapshotStreamlit:
    def __init__(self) -> None:
        self.session_state: dict[str, object] = {}
        self.calls: list[str] = []

    def title(self, _value: str) -> None:
        self.calls.append("title")

    def caption(self, _value: str) -> None:
        self.calls.append("caption")

    def info(self, _value: str) -> None:
        self.calls.append("info")

    def warning(self, _value: str) -> None:
        self.calls.append("warning")

    def code(self, _value: str, *, language: str) -> None:
        self.calls.append("code")

    def button(self, _value: str, *, key: str) -> bool:
        self.calls.append("button")
        return True

    def spinner(self, _value: str):
        self.calls.append("spinner")
        return nullcontext()


def test_missing_snapshot_shows_cli_guidance_without_automatic_reanalysis(monkeypatch) -> None:
    _block_live_analytics(monkeypatch)
    fake_st = _NoSnapshotStreamlit()
    monkeypatch.setattr(app_module, "st", fake_st)
    monkeypatch.setattr(
        app_module,
        "load_saved_rm_daily_review",
        lambda **_kwargs: SavedDailyReviewLoadResult(
            status="MISSING_SNAPSHOT",
            message="저장된 월별 Snapshot이 없습니다.",
            cli_command="python scripts/build_rm_monthly_snapshot.py --snapshot-id YYYY-MM",
        ),
    )

    app_module.render_rm_daily_review_mode(daily_date=date(2026, 8, 29))

    assert fake_st.calls == ["title", "caption", "button", "spinner", "info", "code"]


def test_rm_main_short_circuits_all_live_analytics_before_daily_ui(monkeypatch) -> None:
    """The RM application entry path never reaches live analytics loaders."""

    _block_live_analytics(monkeypatch)
    calls: list[str] = []

    class _MainStreamlit:
        session_state = {"app_mode": app_module.RM_DAILY_REVIEW_MODE}

    monkeypatch.setattr(app_module, "st", _MainStreamlit())
    monkeypatch.setattr(app_module, "render_header", lambda: "ko")
    monkeypatch.setattr(
        app_module,
        "render_sidebar",
        lambda *_args, **_kwargs: app_module.SidebarSelection(
            customer_id="",
            selected_metric="",
            app_mode=app_module.RM_DAILY_REVIEW_MODE,
            presentation_mode=False,
            show_raw_samples=False,
            rm_daily_review_mode=True,
        ),
    )
    monkeypatch.setattr(
        app_module,
        "render_rm_daily_review_mode",
        lambda *_args, **_kwargs: calls.append("daily_ui"),
    )

    app_module.main()

    assert calls == ["daily_ui"]
