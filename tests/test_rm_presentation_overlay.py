"""Tests for the deterministic RM Daily presentation overlay."""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import pytest

from src.rm_presentation_overlay import (
    DEFAULT_PORTFOLIO_CUSTOMER_COUNT,
    DEFAULT_PRESENTATION_SEED,
    PRESENTATION_CUSTOMER_FIELDS,
    PRESENTATION_METADATA_SOURCE,
    SYNTHETIC_PRESENTATION_DISCLAIMER,
    build_rm_presentation_overlay,
    presentation_for_customer,
    write_rm_presentation_overlay_artifact,
)


def _portfolio_ids(count: int = DEFAULT_PORTFOLIO_CUSTOMER_COUNT) -> list[str]:
    return [f"C{index:06d}" for index in range(1, count + 1)]


def _rows(overlay) -> list[dict[str, str]]:
    return [customer.as_dict() for customer in overlay.customers]


def test_same_seed_and_customer_ids_produce_identical_display_overlay() -> None:
    first = build_rm_presentation_overlay(_portfolio_ids())
    second = build_rm_presentation_overlay(_portfolio_ids())

    assert first.as_artifact() == second.as_artifact()
    assert first.presentation_seed == DEFAULT_PRESENTATION_SEED


def test_default_overlay_has_exactly_300_unique_portfolio_customers() -> None:
    portfolio_ids = _portfolio_ids()
    overlay = build_rm_presentation_overlay(portfolio_ids)
    overlay_ids = [customer.customer_id for customer in overlay.customers]

    assert overlay.portfolio_customer_count == 300
    assert len(overlay_ids) == len(set(overlay_ids)) == 300
    assert set(overlay_ids) == set(portfolio_ids)
    assert all(
        customer.presentation_label == "PoC용 합성 고객 표시 정보"
        for customer in overlay.customers
    )


def test_builder_accepts_only_customer_ids_and_presentation_seed() -> None:
    parameter_names = set(inspect.signature(build_rm_presentation_overlay).parameters)
    forbidden_inputs = {
        "persona",
        "final_outcome",
        "outcome",
        "breakpoint",
        "months_from_current",
        "feature",
        "relationship_priority",
    }

    assert {"customer_ids", "presentation_seed", "expected_customer_count"}.issubset(
        parameter_names
    )
    assert not parameter_names.intersection(forbidden_inputs)


def test_financial_and_relationship_values_cannot_change_display_metadata() -> None:
    customer_ids = _portfolio_ids()
    unrelated_financial_and_crm_values = {
        customer_id: {
            "cash_balance": index * 1_000_000,
            "income": (300 - index) * 9_999,
            "relationship_priority": "CORE" if index % 2 else "STANDARD",
            "breakpoint": 1 if index % 3 else 6,
        }
        for index, customer_id in enumerate(customer_ids)
    }

    first = build_rm_presentation_overlay(customer_ids)
    unrelated_financial_and_crm_values.clear()
    second = build_rm_presentation_overlay(customer_ids)

    assert _rows(first) == _rows(second)


def test_writer_uses_only_the_presentation_schema_and_preserves_core_source(
    tmp_path: Path,
) -> None:
    core_source = tmp_path / "data" / "raw" / "customer_master.csv"
    core_source.parent.mkdir(parents=True)
    core_source.write_text(
        "customer_id,cash_balance,income,persona,final_outcome\\n"
        + "".join(
            f"{customer_id},{index * 1000},{index * 2000},persona,outcome\\n"
            for index, customer_id in enumerate(_portfolio_ids(), start=1)
        ),
        encoding="utf-8",
    )
    before_digest = hashlib.sha256(core_source.read_bytes()).hexdigest()
    output_path = write_rm_presentation_overlay_artifact(
        build_rm_presentation_overlay(_portfolio_ids()),
        tmp_path / "artifacts" / "rm_daily_review" / "presentation" / "overlay.json",
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert hashlib.sha256(core_source.read_bytes()).hexdigest() == before_digest
    assert payload["source"] == PRESENTATION_METADATA_SOURCE
    assert payload["disclaimer"] == SYNTHETIC_PRESENTATION_DISCLAIMER
    assert len(payload["customers"]) == 300
    assert set(payload["customers"][0]) == set(PRESENTATION_CUSTOMER_FIELDS)
    forbidden_fields = {
        "cash_balance",
        "income",
        "persona",
        "final_outcome",
        "breakpoint",
        "relationship_priority",
    }
    assert not forbidden_fields.intersection(payload["customers"][0])


def test_outside_portfolio_customer_is_rejected() -> None:
    overlay = build_rm_presentation_overlay(_portfolio_ids())

    with pytest.raises(KeyError, match="not part of this synthetic presentation overlay"):
        presentation_for_customer(overlay, "C999999")


def test_count_and_duplicate_validation_are_explicit() -> None:
    with pytest.raises(ValueError, match="exactly 300"):
        build_rm_presentation_overlay(_portfolio_ids(299))
    with pytest.raises(ValueError, match="must be unique"):
        build_rm_presentation_overlay([*_portfolio_ids(299), "C000001"])


def test_display_rows_are_synthetic_not_real_customer_attributes() -> None:
    overlay = build_rm_presentation_overlay(_portfolio_ids())

    assert all(customer.display_name.startswith("합성 고객 ") for customer in overlay.customers)
    assert all(customer.display_name_ko == customer.display_name for customer in overlay.customers)
    assert all(customer.display_name_en.startswith("Synthetic customer ") for customer in overlay.customers)
    assert all(customer.display_name_en.isascii() for customer in overlay.customers)
    assert all(customer.display_owner_or_team.startswith("RM 업무팀 ") for customer in overlay.customers)
    assert all(
        customer.display_owner_or_team_en.startswith("RM Review Team ")
        for customer in overlay.customers
    )
    assert all("??" not in customer.display_name for customer in overlay.customers)
    assert all("??" not in customer.display_name_en for customer in overlay.customers)
    assert all("??" not in customer.presentation_label for customer in overlay.customers)
    assert all(
        customer.presentation_label_en
        == "Synthetic customer display information for this PoC"
        for customer in overlay.customers
    )
