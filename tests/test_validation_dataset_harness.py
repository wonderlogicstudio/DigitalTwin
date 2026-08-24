"""Contract tests for the synthetic-only validation dataset harness."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pandas as pd
import pytest

from config import settings
from src.as_of_features import build_as_of_trajectory_features
from src.data_generator import generate_dataset
from src.models import GeneratorConfig
from src.validation_dataset_harness import (
    SCORING_REQUIRED_FIELDS,
    VALIDATION_CONTRACT_TEMPLATE_FILENAME,
    ValidationDatasetContract,
    ValidationDatasetContractError,
    admit_injected_validation_dataset,
    build_admitted_as_of_features,
    export_validation_admission_report,
    synthetic_fixture_validation_contract,
    validation_dataset_contract_template,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def synthetic_monthly_fixture() -> pd.DataFrame:
    _, monthly = generate_dataset(GeneratorConfig(customer_count=10, random_seed=42))
    return monthly


def test_synthetic_fixture_admission_reuses_as_of_builder_without_evaluator_columns(
    synthetic_monthly_fixture: pd.DataFrame,
) -> None:
    result = admit_injected_validation_dataset(
        synthetic_monthly_fixture,
        synthetic_fixture_validation_contract(),
    )

    assert result.report.is_admitted is True
    assert result.report.to_dict()["counts"] == {
        "source_rows": 360,
        "source_customers": 10,
        "accepted_rows": 360,
        "accepted_customers": 10,
        "rejected_rows": 0,
        "rejected_customers": 0,
    }
    assert result.report.outcome_availability["status"] == "available"
    assert result.scoring_dataset is not None
    assert result.evaluator_dataset is not None
    assert "evaluation_outcome" not in result.scoring_dataset.rows.columns
    assert "evaluation_event" not in result.scoring_dataset.rows.columns

    actual = build_admitted_as_of_features(result.scoring_dataset, 12)
    expected = build_as_of_trajectory_features(synthetic_monthly_fixture, 12)
    pd.testing.assert_frame_equal(actual, expected)


def test_future_outcome_is_evaluator_only_and_cannot_change_as_of_features(
    synthetic_monthly_fixture: pd.DataFrame,
) -> None:
    contract = synthetic_fixture_validation_contract()
    baseline = admit_injected_validation_dataset(synthetic_monthly_fixture, contract)
    changed = synthetic_monthly_fixture.copy()
    changed.loc[changed["month"] > 12, "final_outcome"] = "changed_only_in_evaluator"
    mutated = admit_injected_validation_dataset(changed, contract)

    assert baseline.scoring_dataset is not None and mutated.scoring_dataset is not None
    pd.testing.assert_frame_equal(
        build_admitted_as_of_features(baseline.scoring_dataset, 12),
        build_admitted_as_of_features(mutated.scoring_dataset, 12),
    )
    assert baseline.evaluator_dataset is not None and mutated.evaluator_dataset is not None
    assert not baseline.evaluator_dataset.after_as_of(12).equals(mutated.evaluator_dataset.after_as_of(12))


def test_explicit_mapping_can_normalize_noncanonical_fixture_column_names(
    synthetic_monthly_fixture: pd.DataFrame,
) -> None:
    renamed_columns = {field: f"source_{field}" for field in SCORING_REQUIRED_FIELDS}
    renamed_columns.update({"final_outcome": "source_outcome", "event_type": "source_event"})
    source_named_fixture = synthetic_monthly_fixture.rename(columns=renamed_columns)
    contract = ValidationDatasetContract(
        contract_id="synthetic-renamed-v1",
        scoring_field_mapping={
            field: renamed_columns[field] for field in SCORING_REQUIRED_FIELDS
        },
        evaluator_field_mapping={
            "evaluation_outcome": "source_outcome",
            "evaluation_event": "source_event",
        },
    )

    result = admit_injected_validation_dataset(source_named_fixture, contract)

    assert result.report.is_admitted is True
    assert result.scoring_dataset is not None
    assert list(result.scoring_dataset.rows.columns) == list(SCORING_REQUIRED_FIELDS)


def test_unordered_fixture_is_normalized_to_deterministic_monthly_order(
    synthetic_monthly_fixture: pd.DataFrame,
) -> None:
    unordered = synthetic_monthly_fixture.sample(frac=1.0, random_state=7).reset_index(drop=True)

    result = admit_injected_validation_dataset(unordered, synthetic_fixture_validation_contract())

    assert result.report.is_admitted is True
    assert result.scoring_dataset is not None
    expected_order = result.scoring_dataset.rows.sort_values(["customer_id", "month"])
    pd.testing.assert_frame_equal(result.scoring_dataset.rows, expected_order.reset_index(drop=True))


def test_duplicate_and_missing_months_are_rejected_with_structural_counts(
    synthetic_monthly_fixture: pd.DataFrame,
) -> None:
    duplicate = pd.concat(
        [synthetic_monthly_fixture, synthetic_monthly_fixture.iloc[[0]]],
        ignore_index=True,
    )
    duplicate_result = admit_injected_validation_dataset(
        duplicate,
        synthetic_fixture_validation_contract(),
    )
    assert duplicate_result.report.is_admitted is False
    assert duplicate_result.scoring_dataset is None
    assert "customer_id and month rows must be unique" in duplicate_result.report.schema_errors

    missing = synthetic_monthly_fixture.loc[
        ~(
            (synthetic_monthly_fixture["customer_id"] == "C000001")
            & (synthetic_monthly_fixture["month"] == 8)
        )
    ].copy()
    missing_result = admit_injected_validation_dataset(missing, synthetic_fixture_validation_contract())
    assert missing_result.report.is_admitted is False
    assert missing_result.report.missing_period_customer_count == 1
    assert missing_result.report.missing_period_count == 1


def test_missing_numeric_values_and_accounting_mismatch_are_rejected(
    synthetic_monthly_fixture: pd.DataFrame,
) -> None:
    missing_numeric = synthetic_monthly_fixture.copy()
    missing_numeric.loc[0, "income"] = None
    missing_result = admit_injected_validation_dataset(
        missing_numeric,
        synthetic_fixture_validation_contract(),
    )
    assert missing_result.report.is_admitted is False
    assert "required numeric scoring fields must be non-missing numeric values" in missing_result.report.schema_errors

    accounting_mismatch = synthetic_monthly_fixture.copy()
    accounting_mismatch.loc[0, "savings_amount"] += 1
    accounting_result = admit_injected_validation_dataset(
        accounting_mismatch,
        synthetic_fixture_validation_contract(),
    )
    assert accounting_result.report.is_admitted is False
    assert "savings_amount must equal income minus total_expense within tolerance" in accounting_result.report.schema_errors


def test_outcome_mapping_can_be_unavailable_without_becoming_scoring_input(
    synthetic_monthly_fixture: pd.DataFrame,
) -> None:
    contract = ValidationDatasetContract(
        contract_id="synthetic-no-outcome-v1",
        scoring_field_mapping={field: field for field in SCORING_REQUIRED_FIELDS},
    )

    result = admit_injected_validation_dataset(synthetic_monthly_fixture, contract)

    assert result.report.is_admitted is True
    assert result.report.outcome_availability == {
        "evaluator_mapping_configured": False,
        "available_customer_count": 0,
        "unavailable_customer_count": 10,
        "status": "unavailable_without_outcome_mapping",
    }
    assert result.scoring_dataset is not None
    assert result.evaluator_dataset is not None
    assert "evaluation_outcome" not in result.scoring_dataset.rows


def test_forbidden_pii_mapping_and_non_fixture_mode_are_rejected() -> None:
    mapping = {field: field for field in SCORING_REQUIRED_FIELDS}
    mapping["customer_id"] = "account_number"
    with pytest.raises(ValidationDatasetContractError, match="forbidden PII"):
        ValidationDatasetContract(contract_id="bad-pii", scoring_field_mapping=mapping)

    with pytest.raises(ValidationDatasetContractError, match="synthetic injected fixtures only"):
        ValidationDatasetContract(
            contract_id="not-fixture",
            scoring_field_mapping={field: field for field in SCORING_REQUIRED_FIELDS},
            fixture_only=False,
        )


def test_unmapped_forbidden_pii_column_is_rejected_at_admission(
    synthetic_monthly_fixture: pd.DataFrame,
) -> None:
    injected = synthetic_monthly_fixture.assign(account_number="not-admitted")

    result = admit_injected_validation_dataset(injected, synthetic_fixture_validation_contract())

    assert result.report.is_admitted is False
    assert any("forbidden PII" in error for error in result.report.schema_errors)


def test_report_export_uses_injected_noncanonical_output_root(
    tmp_path: Path,
    synthetic_monthly_fixture: pd.DataFrame,
) -> None:
    result = admit_injected_validation_dataset(
        synthetic_monthly_fixture,
        synthetic_fixture_validation_contract(),
    )
    output_root = tmp_path / "validation_real"
    destination = export_validation_admission_report(
        result.report,
        output_root / "admission_report.json",
        allowed_root=output_root,
    )
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["row_level_values_exported"] is False
    assert not list(output_root.glob(".*.tmp"))

    with pytest.raises(ValidationDatasetContractError, match="injected readiness output root"):
        export_validation_admission_report(
            result.report,
            tmp_path / "outside" / "admission_report.json",
            allowed_root=output_root,
        )
    with pytest.raises(ValidationDatasetContractError, match="canonical data paths"):
        export_validation_admission_report(
            result.report,
            settings.DATA_RAW_DIR / "admission_report.json",
            allowed_root=settings.DATA_RAW_DIR,
        )


def test_checked_in_template_matches_source_free_contract() -> None:
    template_path = (
        PROJECT_ROOT
        / "artifacts"
        / "post_p0"
        / "real_data_readiness"
        / VALIDATION_CONTRACT_TEMPLATE_FILENAME
    )
    assert json.loads(template_path.read_text(encoding="utf-8")) == validation_dataset_contract_template()


def test_harness_has_no_connector_network_or_ui_imports() -> None:
    source = (PROJECT_ROOT / "src" / "validation_dataset_harness.py").read_text(encoding="utf-8")
    imported_roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])

    assert {"requests", "httpx", "urllib", "socket", "streamlit"}.isdisjoint(imported_roots)
    assert "read_csv" not in source
    attribute_names = {
        node.attr
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Attribute)
    }
    assert {"getenv", "environ"}.isdisjoint(attribute_names)


def test_adapter_document_keeps_real_data_and_synthetic_outcome_boundaries() -> None:
    document = (PROJECT_ROOT / "VALIDATION_DATASET_ADAPTER_CONTRACT.md").read_text(encoding="utf-8")
    assert "synthetic-fixture-only" in document
    assert "not reuse the synthetic `final_outcome` label" in document
    assert "Triage does not receive `EvaluatorOutcomeDataset`" in document
