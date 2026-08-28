"""Tests for plain-language RM timing explanations."""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

import src.rm_review_explainability as explainability
from src.daily_review import MONITOR, REVIEW_NOW, UPCOMING
from src.daily_worklist import DailyWorklistItem
from src.rm_review_explainability import (
    FACTOR_LABELS,
    HISTORICAL_COMPARISON_NOTICE,
    build_rm_review_explanation,
    build_rm_review_explanations,
)


def _item(**overrides: object) -> DailyWorklistItem:
    values: dict[str, object] = {
        "customer_id": "C000001",
        "snapshot_id": "monthly-2026-08",
        "review_state": REVIEW_NOW,
        "timing_months": 1,
        "reason_code": "NEAR_TIMING_WITH_CURRENT_OBSERVATION",
        "primary_factor": "cash_balance_ratio",
        "current_status": "watch",
        "relationship_priority": "CORE",
        "relationship_label": "핵심관리",
        "completed_today": False,
    }
    values.update(overrides)
    return DailyWorklistItem(**values)


def test_review_now_explains_historical_timing_and_primary_change() -> None:
    explanation = build_rm_review_explanation(_item())

    assert explanation.review_reason == "오늘 확인 근거: 분기 시점 1개월 이내 · 주요 변화: 현금 여력"
    assert "유사 고객의 위험 경로와 위험 회피 경로" in explanation.timing_evidence
    assert "역사적으로" in explanation.timing_evidence
    assert explanation.primary_change == "주요 변화: 현금 여력"
    assert explanation.historical_comparison_notice == HISTORICAL_COMPARISON_NOTICE
    assert "새로운 예측이 아닙니다" in explanation.historical_comparison_notice
    assert explanation.relationship_context == "고객관계: 핵심관리 고객 · 합성 CRM 메타데이터"
    assert "핵심관리" not in explanation.review_reason


@pytest.mark.parametrize("factor, label", FACTOR_LABELS.items())
def test_factor_mapping_uses_easy_term(factor: str, label: str) -> None:
    explanation = build_rm_review_explanation(_item(primary_factor=factor))

    assert explanation.primary_change == f"주요 변화: {label}"
    assert factor not in explanation.primary_change


def test_upcoming_and_monitor_use_saved_reason_without_prediction_language() -> None:
    upcoming = build_rm_review_explanation(
        _item(
            review_state=UPCOMING,
            timing_months=3,
            reason_code="TIMING_IN_3_TO_4_MONTHS",
            primary_factor="dsr",
            relationship_priority="PRIORITY",
            relationship_label="우선관리",
        )
    )
    monitor = build_rm_review_explanation(
        _item(
            review_state=MONITOR,
            timing_months=None,
            reason_code="INSUFFICIENT_GROUP_SIZE",
            primary_factor=None,
            relationship_priority="STANDARD",
            relationship_label="일반관리",
        )
    )

    assert upcoming.review_reason == "곧 확인 예정 근거: 분기 시점 3개월 이내 · 주요 변화: 대출 상환 부담"
    assert monitor.review_reason == "모니터링 근거: 유사 고객 그룹의 비교 근거가 충분하지 않습니다."
    assert monitor.primary_change == "주요 변화: 주요 변화 정보 확인 필요"
    assert "INSUFFICIENT_GROUP_SIZE" not in monitor.review_reason
    assert monitor.timing_evidence == "분기 시점의 timing 근거가 충분하지 않아 현재는 모니터링합니다."
    assert "예측" not in upcoming.review_reason


def test_relationship_priority_never_changes_timing_explanation() -> None:
    core_item = _item()
    standard_item = replace(
        core_item,
        relationship_priority="STANDARD",
        relationship_label="일반관리",
    )

    core = build_rm_review_explanation(core_item)
    standard = build_rm_review_explanation(standard_item)

    assert core.review_reason == standard.review_reason
    assert core.timing_evidence == standard.timing_evidence
    assert core.primary_change == standard.primary_change
    assert core.relationship_context != standard.relationship_context


def test_batch_explanations_keep_existing_worklist_order() -> None:
    items = (_item(customer_id="C000002"), _item(customer_id="C000001"))

    explanations = build_rm_review_explanations(items)

    assert [explanation.customer_id for explanation in explanations] == ["C000002", "C000001"]


def test_module_has_no_analysis_imports_or_score_fields() -> None:
    module_path = Path(explainability.__file__)
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert imported_modules.issubset(
        {
            "__future__",
            "collections.abc",
            "dataclasses",
            "src.daily_review",
            "src.daily_worklist",
        }
    )
    fields = set(explainability.RmReviewExplanation.__dataclass_fields__)
    assert not {"score", "risk_score", "probability", "prediction_probability"}.intersection(fields)
