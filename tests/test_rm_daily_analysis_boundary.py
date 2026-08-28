"""Regression guards for the boundary between monthly analysis and Daily Review."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
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


def test_missing_snapshot_shows_cli_guidance_without_automatic_reanalysis(monkeypatch) -> None:
    _block_live_analytics(monkeypatch)
    fake_st = _NoSnapshotStreamlit()
    monkeypatch.setattr(app_module, "st", fake_st)
    monkeypatch.setattr(app_module, "load_latest_rm_snapshot_artifact", lambda: None)

    app_module.render_rm_daily_review_mode(daily_date=date(2026, 8, 29))

    assert fake_st.calls == ["title", "caption", "info", "code"]


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
