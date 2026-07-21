import pandas as pd
import pytest

from config import settings
from src.data_generator import generate_dataset
from src.models import GeneratorConfig
from src.validator import (
    REPORT_COLUMNS,
    build_outcome_distribution,
    build_persona_summary,
    has_failures,
    run_all_validations,
    save_validation_reports,
    validate_accounting_relationships,
    validate_distribution,
)


@pytest.fixture(scope="module")
def generated_dataset() -> tuple[pd.DataFrame, pd.DataFrame]:
    return generate_dataset(GeneratorConfig())


def test_run_all_validations_passes_generated_dataset(
    generated_dataset: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    master_df, monthly_df = generated_dataset
    report = run_all_validations(master_df, monthly_df)

    assert list(report.columns) == list(REPORT_COLUMNS)
    assert not has_failures(report)


def test_accounting_validation_fails_for_total_expense_mismatch(
    generated_dataset: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    master_df, monthly_df = generated_dataset
    broken_monthly = monthly_df.copy()
    broken_monthly.loc[0, "total_expense"] += 1

    report = pd.DataFrame(validate_accounting_relationships(master_df, broken_monthly))
    check = report.loc[report["check_name"] == "total_expense_formula"].iloc[0]

    assert check["status"] == "failure"
    assert check["actual_value"] == "1"


def test_distribution_validation_warns_for_outcome_target_departure(
    generated_dataset: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    master_df, monthly_df = generated_dataset
    skewed_monthly = monthly_df.copy()
    skewed_monthly["final_outcome"] = "healthy"

    report = pd.DataFrame(validate_distribution(master_df, skewed_monthly))
    check = report.loc[report["check_name"] == "final_outcome_distribution"].iloc[0]

    assert check["status"] == "warning"


def test_summary_reports_have_expected_shapes(
    generated_dataset: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    master_df, monthly_df = generated_dataset
    persona_summary = build_persona_summary(master_df)
    outcome_distribution = build_outcome_distribution(monthly_df)

    assert set(persona_summary["persona"]) == set(settings.PERSONAS)
    assert set(outcome_distribution["final_outcome"]) == set(settings.FINAL_OUTCOMES)
    assert persona_summary["count"].sum() == settings.CUSTOMER_COUNT
    assert outcome_distribution["count"].sum() == settings.CUSTOMER_COUNT


def test_save_validation_reports_writes_csv_files(
    tmp_path,
    generated_dataset: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    master_df, monthly_df = generated_dataset
    validation_report = run_all_validations(master_df, monthly_df)
    persona_summary = build_persona_summary(master_df)
    outcome_distribution = build_outcome_distribution(monthly_df)

    paths = save_validation_reports(
        validation_report,
        persona_summary,
        outcome_distribution,
        reports_dir=tmp_path,
    )

    for path in paths:
        assert path.exists()
        assert path.read_text(encoding="utf-8")
