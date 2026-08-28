"""Tests for deterministic synthetic RM Portfolio metadata."""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import pytest

from scripts.build_rm_portfolio import load_customer_ids_from_csv, main
from src.rm_portfolio import (
    DEFAULT_PORTFOLIO_SELECTION_SEED,
    DEFAULT_RELATIONSHIP_ASSIGNMENT_SEED,
    DEFAULT_RM_PORTFOLIO_ID,
    PORTFOLIO_CUSTOMER_FIELDS,
    SYNTHETIC_CRM_DISCLAIMER,
    build_rm_portfolio,
    write_rm_portfolio_artifacts,
)


def _universe_ids(count: int = 5_000) -> list[str]:
    return [f"C{index:06d}" for index in range(1, count + 1)]


def _customer_rows(portfolio) -> list[dict[str, str]]:
    return [customer.as_dict() for customer in portfolio.customers]


def test_same_seed_produces_identical_portfolio_and_relationship_metadata() -> None:
    first = build_rm_portfolio(_universe_ids())
    second = build_rm_portfolio(_universe_ids())

    assert first.as_artifact() == second.as_artifact()
    assert first.portfolio_selection_seed == DEFAULT_PORTFOLIO_SELECTION_SEED
    assert first.relationship_assignment_seed == DEFAULT_RELATIONSHIP_ASSIGNMENT_SEED


def test_default_portfolio_has_300_unique_customers_from_5000_customer_universe() -> None:
    universe_ids = _universe_ids()
    portfolio = build_rm_portfolio(universe_ids)
    selected_ids = [customer.customer_id for customer in portfolio.customers]

    assert portfolio.portfolio_size == 300
    assert len(selected_ids) == len(set(selected_ids)) == 300
    assert set(selected_ids).issubset(set(universe_ids))
    assert portfolio.universe_customer_count == 5_000
    assert all(customer.rm_portfolio_id == DEFAULT_RM_PORTFOLIO_ID for customer in portfolio.customers)


def test_relationship_priority_distribution_is_deterministic_and_independent() -> None:
    portfolio = build_rm_portfolio(_universe_ids())

    assert portfolio.relationship_counts() == {
        "CORE": 30,
        "PRIORITY": 75,
        "STANDARD": 195,
    }
    assert {customer.relationship_label for customer in portfolio.customers} == {
        "핵심관리",
        "우선관리",
        "일반관리",
    }


def test_builder_requires_only_customer_ids_not_persona_outcome_or_breakpoint() -> None:
    parameter_names = set(inspect.signature(build_rm_portfolio).parameters)

    assert {"customer_ids", "portfolio_size", "portfolio_selection_seed", "relationship_assignment_seed"}.issubset(
        parameter_names
    )
    assert not {"persona", "final_outcome", "outcome", "breakpoint"}.intersection(parameter_names)


def test_external_financial_values_cannot_change_relationship_priority(tmp_path: Path) -> None:
    customer_ids = _universe_ids()
    first_master = tmp_path / "first_master.csv"
    second_master = tmp_path / "second_master.csv"
    first_master.write_text(
        "customer_id,persona,final_outcome,cash_balance,income,loan_balance\n"
        + "".join(
            f"{customer_id},stable,healthy,1000,2000,3000\n"
            for customer_id in customer_ids
        ),
        encoding="utf-8",
    )
    second_master.write_text(
        "customer_id,persona,final_outcome,cash_balance,income,loan_balance\n"
        + "".join(
            f"{customer_id},changed_persona,changed_outcome,{index * 1000000},{(5000 - index) * 2000000},{index * 3000000}\n"
            for index, customer_id in enumerate(customer_ids, start=1)
        ),
        encoding="utf-8",
    )

    first_rows = _customer_rows(build_rm_portfolio(load_customer_ids_from_csv(first_master)))
    second_rows = _customer_rows(build_rm_portfolio(load_customer_ids_from_csv(second_master)))

    assert first_rows == second_rows


def test_duplicate_customer_ids_are_rejected() -> None:
    duplicate_ids = [*_universe_ids(300), "C000001"]

    with pytest.raises(ValueError, match="must be unique"):
        build_rm_portfolio(duplicate_ids)


def test_artifacts_contain_only_overlay_schema(tmp_path: Path) -> None:
    portfolio = build_rm_portfolio(_universe_ids())
    json_path, csv_path = write_rm_portfolio_artifacts(
        portfolio,
        tmp_path / "artifacts" / "rm_daily_review" / "portfolio" / "rm_portfolio.json",
    )
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert csv_path.name == "rm_portfolio.csv"
    assert payload["disclaimer"] == SYNTHETIC_CRM_DISCLAIMER
    assert payload["source"] == "synthetic_crm_overlay"
    assert len(payload["customers"]) == 300
    assert set(payload["customers"][0]) == set(PORTFOLIO_CUSTOMER_FIELDS)
    forbidden_fields = {"cash_balance", "income", "loan_balance", "persona", "final_outcome", "breakpoint"}
    assert not forbidden_fields.intersection(payload["customers"][0])


def test_script_reads_only_customer_ids_and_preserves_core_data_file(tmp_path: Path) -> None:
    master_path = tmp_path / "data" / "raw" / "customer_master.csv"
    master_path.parent.mkdir(parents=True)
    master_path.write_text(
        "customer_id,persona,final_outcome,cash_balance,income,loan_balance\n"
        + "".join(
            f"C{index:06d},changed_persona,changed_outcome,{index * 1000},{index * 2000},{index * 3000}\n"
            for index in range(1, 5_001)
        ),
        encoding="utf-8",
    )
    original_digest = hashlib.sha256(master_path.read_bytes()).hexdigest()
    output_path = tmp_path / "artifacts" / "rm_daily_review" / "portfolio" / "rm_portfolio.json"

    assert main(["--customer-master", str(master_path), "--output", str(output_path)]) == 0

    assert hashlib.sha256(master_path.read_bytes()).hexdigest() == original_digest
    assert load_customer_ids_from_csv(master_path) == _universe_ids()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert len(payload["customers"]) == 300
    assert output_path.with_suffix(".csv").exists()
