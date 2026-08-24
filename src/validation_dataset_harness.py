"""Injected-fixture harness for future approved validation datasets.

This is a provider-neutral schema and admission boundary, not a connector or a
reader. It never opens a source dataset from a path, uses credentials, or makes
network requests. A separately approved secure environment may inject a frame
into this contract in a later phase; this repository exercises it with
synthetic fixtures only.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from config import settings
from src.as_of_features import AS_OF_REQUIRED_COLUMNS, build_as_of_trajectory_features
from src.real_data_governance import EXCLUDED_DATA_CONCEPTS


VALIDATION_DATASET_CONTRACT_SCHEMA_VERSION = "validation_dataset_contract.v1"
VALIDATION_ADMISSION_REPORT_SCHEMA_VERSION = "validation_admission_report.v1"
VALIDATION_READINESS_ARTIFACT_DIR = (
    settings.BASE_DIR / "artifacts" / "post_p0" / "real_data_readiness"
)
VALIDATION_CONTRACT_TEMPLATE_FILENAME = "validation_dataset_contract_template.json"

SCORING_REQUIRED_FIELDS = (*AS_OF_REQUIRED_COLUMNS, "monthly_status")
EVALUATOR_OPTIONAL_FIELDS = ("evaluation_outcome", "evaluation_event")
FORBIDDEN_SOURCE_MAPPING_NAMES = frozenset(EXCLUDED_DATA_CONCEPTS)


class ValidationDatasetContractError(ValueError):
    """A mapping or injected-output request violates this readiness contract."""


@dataclass(frozen=True)
class ValidationDatasetContract:
    """Explicit mapping from provider fields into a validation-only vocabulary.

    ``scoring_field_mapping`` contains only the fields needed at or before an
    as-of month. ``evaluator_field_mapping`` is separate and may contain an
    independently agreed outcome/event only for evaluator use.
    """

    contract_id: str
    scoring_field_mapping: Mapping[str, str]
    evaluator_field_mapping: Mapping[str, str] = field(default_factory=dict)
    expected_first_month: int = settings.OBSERVATION_START_MONTH
    expected_last_month: int = settings.TOTAL_MONTHS
    observation_end_month: int = settings.OBSERVATION_END_MONTH
    schema_version: str = VALIDATION_DATASET_CONTRACT_SCHEMA_VERSION
    fixture_only: bool = True

    def __post_init__(self) -> None:
        if not self.contract_id or not str(self.contract_id).strip():
            raise ValidationDatasetContractError("contract_id must be non-empty")
        if self.schema_version != VALIDATION_DATASET_CONTRACT_SCHEMA_VERSION:
            raise ValidationDatasetContractError("unexpected validation dataset contract schema version")
        if not self.fixture_only:
            raise ValidationDatasetContractError(
                "this public-repository harness supports synthetic injected fixtures only"
            )
        if (
            self.expected_first_month != settings.OBSERVATION_START_MONTH
            or self.expected_last_month != settings.TOTAL_MONTHS
            or self.observation_end_month != settings.OBSERVATION_END_MONTH
        ):
            raise ValidationDatasetContractError(
                "the readiness template compares against the unchanged canonical P0 horizon"
            )
        _validate_mapping(
            self.scoring_field_mapping,
            required_keys=SCORING_REQUIRED_FIELDS,
            label="scoring_field_mapping",
        )
        _validate_mapping(
            self.evaluator_field_mapping,
            required_keys=(),
            allowed_keys=EVALUATOR_OPTIONAL_FIELDS,
            label="evaluator_field_mapping",
        )
        shared_sources = set(self.scoring_field_mapping.values()) & set(
            self.evaluator_field_mapping.values()
        )
        if shared_sources:
            raise ValidationDatasetContractError(
                "evaluator source fields must be separate from scoring source fields"
            )

    def to_template_dict(self) -> dict[str, object]:
        """Return a source-free template, never an actual provider mapping."""

        return {
            "schema_version": self.schema_version,
            "scope": "synthetic_fixture_harness_only",
            "contract_id": "<approved_validation_contract_id>",
            "fixture_only": True,
            "source_specific_mapping_required": True,
            "scoring_required_fields": list(SCORING_REQUIRED_FIELDS),
            "evaluator_optional_fields": list(EVALUATOR_OPTIONAL_FIELDS),
            "source_field_mapping_template": {
                field_name: "<approved_source_column>" for field_name in SCORING_REQUIRED_FIELDS
            },
            "evaluator_field_mapping_template": {
                field_name: "<approved_source_column_or_unavailable>"
                for field_name in EVALUATOR_OPTIONAL_FIELDS
            },
            "boundaries": {
                "actual_data_connector_present": False,
                "public_repository_data_storage_allowed": False,
                "scoring_receives_evaluator_fields": False,
                "evaluator_fields_open_only_after_scoring": True,
                "canonical_p0_settings_mutated": False,
            },
            "p0_comparison_window": {
                "first_month": self.expected_first_month,
                "observation_end_month": self.observation_end_month,
                "future_start_month": settings.FUTURE_START_MONTH,
                "last_month": self.expected_last_month,
            },
        }


@dataclass(frozen=True)
class ScoringObservationDataset:
    """Admitted monthly observations with no evaluator-only field."""

    rows: pd.DataFrame
    contract_id: str

    def as_of_input(self, as_of_month: int) -> pd.DataFrame:
        if isinstance(as_of_month, bool) or not isinstance(as_of_month, int):
            raise TypeError("as_of_month must be an integer")
        if as_of_month < settings.OBSERVATION_START_MONTH or as_of_month > settings.TOTAL_MONTHS:
            raise ValueError("as_of_month is outside the canonical P0 comparison horizon")
        return (
            self.rows.loc[self.rows["month"] <= as_of_month, AS_OF_REQUIRED_COLUMNS]
            .copy()
            .sort_values(["customer_id", "month"])
            .reset_index(drop=True)
        )


@dataclass(frozen=True)
class EvaluatorOutcomeDataset:
    """Evaluator-only outcomes/events; it is not a scoring or triage input."""

    rows: pd.DataFrame
    contract_id: str

    def after_as_of(self, as_of_month: int) -> pd.DataFrame:
        if isinstance(as_of_month, bool) or not isinstance(as_of_month, int):
            raise TypeError("as_of_month must be an integer")
        return (
            self.rows.loc[self.rows["month"] > as_of_month].copy()
            .sort_values(["customer_id", "month"])
            .reset_index(drop=True)
        )


@dataclass(frozen=True)
class ValidationAdmissionReport:
    """Counts and structural findings only; it never contains row-level values."""

    source_row_count: int
    source_customer_count: int
    accepted_row_count: int
    accepted_customer_count: int
    rejected_row_count: int
    rejected_customer_count: int
    schema_errors: tuple[str, ...]
    missing_period_customer_count: int
    missing_period_count: int
    outcome_availability: Mapping[str, object]
    schema_version: str = VALIDATION_ADMISSION_REPORT_SCHEMA_VERSION

    @property
    def is_admitted(self) -> bool:
        return not self.schema_errors

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "scope": "synthetic_fixture_admission_report_only",
            "is_admitted": self.is_admitted,
            "counts": {
                "source_rows": self.source_row_count,
                "source_customers": self.source_customer_count,
                "accepted_rows": self.accepted_row_count,
                "accepted_customers": self.accepted_customer_count,
                "rejected_rows": self.rejected_row_count,
                "rejected_customers": self.rejected_customer_count,
            },
            "schema_errors": list(self.schema_errors),
            "missing_periods": {
                "customer_count": self.missing_period_customer_count,
                "month_count": self.missing_period_count,
            },
            "outcome_availability": dict(self.outcome_availability),
            "row_level_values_exported": False,
            "limitations": [
                "This report is a structural readiness result, not real-data validation evidence.",
                "Actual data may be handled only in an independently approved secure environment.",
            ],
        }


@dataclass(frozen=True)
class ValidationAdmissionResult:
    """A rejected frame exposes no admitted dataset to downstream callers."""

    report: ValidationAdmissionReport
    scoring_dataset: ScoringObservationDataset | None
    evaluator_dataset: EvaluatorOutcomeDataset | None


def synthetic_fixture_validation_contract() -> ValidationDatasetContract:
    """Map existing synthetic fixture columns without becoming a production connector."""

    return ValidationDatasetContract(
        contract_id="synthetic-fixture-v1",
        scoring_field_mapping={field_name: field_name for field_name in SCORING_REQUIRED_FIELDS},
        evaluator_field_mapping={
            "evaluation_outcome": "final_outcome",
            "evaluation_event": "event_type",
        },
    )


def admit_injected_validation_dataset(
    injected_monthly_frame: pd.DataFrame,
    contract: ValidationDatasetContract,
) -> ValidationAdmissionResult:
    """Validate an injected synthetic frame and split scoring from evaluator data.

    The caller provides an in-memory fixture. This function performs no file,
    environment, credential, or transport operation.
    """

    if not isinstance(injected_monthly_frame, pd.DataFrame):
        raise TypeError("injected_monthly_frame must be a pandas DataFrame")

    source_rows = int(len(injected_monthly_frame))
    source_customers = _source_customer_count(
        injected_monthly_frame,
        contract.scoring_field_mapping["customer_id"],
    )
    errors = _mapping_schema_errors(injected_monthly_frame, contract)
    if errors:
        return _rejected_result(
            source_rows=source_rows,
            source_customers=source_customers,
            errors=errors,
        )

    scoring_rows = _normalise_scoring_rows(injected_monthly_frame, contract)
    structural_errors, missing_customer_count, missing_period_count = _structural_errors(
        scoring_rows,
        contract,
    )
    outcome_rows, outcome_availability = _build_evaluator_rows(
        injected_monthly_frame,
        scoring_rows,
        contract,
    )
    all_errors = tuple((*structural_errors,))
    if all_errors:
        return ValidationAdmissionResult(
            report=ValidationAdmissionReport(
                source_row_count=source_rows,
                source_customer_count=source_customers,
                accepted_row_count=0,
                accepted_customer_count=0,
                rejected_row_count=source_rows,
                rejected_customer_count=source_customers,
                schema_errors=all_errors,
                missing_period_customer_count=missing_customer_count,
                missing_period_count=missing_period_count,
                outcome_availability=outcome_availability,
            ),
            scoring_dataset=None,
            evaluator_dataset=None,
        )

    report = ValidationAdmissionReport(
        source_row_count=source_rows,
        source_customer_count=source_customers,
        accepted_row_count=len(scoring_rows),
        accepted_customer_count=int(scoring_rows["customer_id"].nunique()),
        rejected_row_count=0,
        rejected_customer_count=0,
        schema_errors=(),
        missing_period_customer_count=0,
        missing_period_count=0,
        outcome_availability=outcome_availability,
    )
    return ValidationAdmissionResult(
        report=report,
        scoring_dataset=ScoringObservationDataset(scoring_rows, contract.contract_id),
        evaluator_dataset=EvaluatorOutcomeDataset(outcome_rows, contract.contract_id),
    )


def build_admitted_as_of_features(
    scoring_dataset: ScoringObservationDataset,
    as_of_month: int,
) -> pd.DataFrame:
    """Reuse the legacy-safe as-of builder with evaluator data absent by type."""

    if not isinstance(scoring_dataset, ScoringObservationDataset):
        raise TypeError("only ScoringObservationDataset may enter the as-of feature builder")
    return build_as_of_trajectory_features(scoring_dataset.as_of_input(as_of_month), as_of_month)


def export_validation_admission_report(
    report: ValidationAdmissionReport,
    output_path: Path,
    *,
    allowed_root: Path,
) -> Path:
    """Atomically export report metadata only to an injected readiness output root."""

    destination = Path(output_path)
    root = Path(allowed_root)
    _assert_injected_output_path(destination, root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        temporary.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, destination)
    except OSError:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
        raise
    return destination


def validation_dataset_contract_template() -> dict[str, object]:
    """Return a checked-in source-free template for a future approved mapping."""

    return synthetic_fixture_validation_contract().to_template_dict()


def _validate_mapping(
    mapping: Mapping[str, str],
    *,
    required_keys: tuple[str, ...],
    label: str,
    allowed_keys: tuple[str, ...] | None = None,
) -> None:
    mapping_keys = tuple(mapping)
    allowed = set(required_keys if allowed_keys is None else allowed_keys)
    if allowed_keys is None and set(mapping_keys) != set(required_keys):
        raise ValidationDatasetContractError(
            f"{label} must contain exactly the required canonical fields"
        )
    if allowed_keys is not None and not set(mapping_keys) <= allowed:
        raise ValidationDatasetContractError(f"{label} contains an unsupported evaluator field")
    missing = set(required_keys) - set(mapping_keys)
    if missing:
        raise ValidationDatasetContractError(f"{label} is missing canonical fields: {sorted(missing)}")
    source_columns = []
    for canonical_field, source_field in mapping.items():
        if not isinstance(source_field, str) or not source_field.strip():
            raise ValidationDatasetContractError(
                f"{label}[{canonical_field!r}] must be a non-empty source field name"
            )
        if source_field.strip().lower() in FORBIDDEN_SOURCE_MAPPING_NAMES:
            raise ValidationDatasetContractError(
                f"{label}[{canonical_field!r}] maps a forbidden PII field concept"
            )
        source_columns.append(source_field)
    if len(source_columns) != len(set(source_columns)):
        raise ValidationDatasetContractError(f"{label} source field names must be unique")


def _mapping_schema_errors(
    frame: pd.DataFrame,
    contract: ValidationDatasetContract,
) -> tuple[str, ...]:
    required_source_columns = set(contract.scoring_field_mapping.values()) | set(
        contract.evaluator_field_mapping.values()
    )
    missing = sorted(required_source_columns - set(frame.columns))
    errors: list[str] = []
    if missing:
        errors.append(f"mapped source columns are missing: {missing}")
    prohibited_columns = sorted(
        str(column)
        for column in frame.columns
        if str(column).strip().lower() in FORBIDDEN_SOURCE_MAPPING_NAMES
    )
    if prohibited_columns:
        errors.append(f"injected frame includes forbidden PII field concepts: {prohibited_columns}")
    return tuple(errors)


def _normalise_scoring_rows(
    frame: pd.DataFrame,
    contract: ValidationDatasetContract,
) -> pd.DataFrame:
    source_columns = list(contract.scoring_field_mapping.values())
    inverse_mapping = {source: canonical for canonical, source in contract.scoring_field_mapping.items()}
    rows = frame.loc[:, source_columns].rename(columns=inverse_mapping).copy()
    rows["customer_id"] = rows["customer_id"].astype(str).str.strip()
    rows["month"] = pd.to_numeric(rows["month"], errors="coerce")
    for field_name in SCORING_REQUIRED_FIELDS:
        if field_name not in {"customer_id", "month", "monthly_status"}:
            rows[field_name] = pd.to_numeric(rows[field_name], errors="coerce")
    rows["monthly_status"] = rows["monthly_status"].astype(str).str.strip()
    return rows.sort_values(["customer_id", "month"], kind="mergesort").reset_index(drop=True)


def _structural_errors(
    rows: pd.DataFrame,
    contract: ValidationDatasetContract,
) -> tuple[tuple[str, ...], int, int]:
    errors: list[str] = []
    if rows["customer_id"].eq("").any() or rows["customer_id"].eq("nan").any():
        errors.append("pseudonymous customer_id values must be non-empty")
    if rows["month"].isna().any() or not (rows["month"] % 1 == 0).all():
        errors.append("month values must be non-missing integers")
    else:
        rows["month"] = rows["month"].astype(int)
    numeric_fields = tuple(
        field_name
        for field_name in SCORING_REQUIRED_FIELDS
        if field_name not in {"customer_id", "month", "monthly_status"}
    )
    if rows.loc[:, numeric_fields].isna().any().any():
        errors.append("required numeric scoring fields must be non-missing numeric values")
    if rows["monthly_status"].eq("").any() or rows["monthly_status"].eq("nan").any():
        errors.append("current status values must be non-empty")
    if errors:
        return tuple(errors), 0, 0

    if not rows["month"].between(contract.expected_first_month, contract.expected_last_month).all():
        errors.append("month values are outside the canonical P0 comparison horizon")
    if rows.duplicated(["customer_id", "month"]).any():
        errors.append("customer_id and month rows must be unique")
    missing_customer_count, missing_period_count = _missing_period_counts(rows, contract)
    if missing_customer_count:
        errors.append(
            "monthly ordering/completeness is invalid: "
            f"{missing_customer_count} customer(s) have {missing_period_count} missing period(s)"
        )
    if (rows["income"] < 0).any() or (rows["total_expense"] < 0).any():
        errors.append("income and total_expense must be non-negative for accounting plausibility")
    accounting_delta = (rows["income"] - rows["total_expense"] - rows["savings_amount"]).abs()
    if (accounting_delta > 0.01).any():
        errors.append("savings_amount must equal income minus total_expense within tolerance")
    for ratio_field in ("savings_rate", "fixed_expense_ratio", "dsr"):
        if not rows[ratio_field].between(-1.0 if ratio_field == "savings_rate" else 0.0, 1.0).all():
            errors.append(f"{ratio_field} is outside the synthetic comparison plausibility range")
    return tuple(errors), missing_customer_count, missing_period_count


def _missing_period_counts(rows: pd.DataFrame, contract: ValidationDatasetContract) -> tuple[int, int]:
    expected = set(range(contract.expected_first_month, contract.expected_last_month + 1))
    missing_counts = [
        len(expected - set(group["month"].astype(int)))
        for _, group in rows.groupby("customer_id", sort=False)
    ]
    return sum(count > 0 for count in missing_counts), sum(missing_counts)


def _build_evaluator_rows(
    source_frame: pd.DataFrame,
    scoring_rows: pd.DataFrame,
    contract: ValidationDatasetContract,
) -> tuple[pd.DataFrame, dict[str, object]]:
    base_mapping = contract.scoring_field_mapping
    source_columns = [base_mapping["customer_id"], base_mapping["month"]]
    source_columns.extend(contract.evaluator_field_mapping.values())
    evaluator_rows = source_frame.loc[:, source_columns].copy()
    rename_mapping = {
        base_mapping["customer_id"]: "customer_id",
        base_mapping["month"]: "month",
        **{source: canonical for canonical, source in contract.evaluator_field_mapping.items()},
    }
    evaluator_rows = evaluator_rows.rename(columns=rename_mapping)
    evaluator_rows["customer_id"] = evaluator_rows["customer_id"].astype(str).str.strip()
    evaluator_rows["month"] = pd.to_numeric(evaluator_rows["month"], errors="coerce")
    if not evaluator_rows["month"].isna().any():
        evaluator_rows["month"] = evaluator_rows["month"].astype(int)
    evaluator_rows = evaluator_rows.sort_values(["customer_id", "month"], kind="mergesort").reset_index(
        drop=True
    )

    customer_count = int(scoring_rows["customer_id"].nunique())
    if "evaluation_outcome" not in evaluator_rows.columns:
        return evaluator_rows, {
            "evaluator_mapping_configured": False,
            "available_customer_count": 0,
            "unavailable_customer_count": customer_count,
            "status": "unavailable_without_outcome_mapping",
        }
    future_rows = evaluator_rows.loc[evaluator_rows["month"] > contract.observation_end_month]
    available = 0
    for _, group in future_rows.groupby("customer_id", sort=False):
        values = group["evaluation_outcome"]
        if values.notna().all() and values.astype(str).str.strip().ne("").all():
            available += 1
    return evaluator_rows, {
        "evaluator_mapping_configured": True,
        "available_customer_count": available,
        "unavailable_customer_count": customer_count - available,
        "status": "available" if available == customer_count else "partially_unavailable",
    }


def _source_customer_count(frame: pd.DataFrame, customer_source_field: str) -> int:
    if customer_source_field not in frame.columns:
        return 0
    return int(frame[customer_source_field].dropna().astype(str).str.strip().replace("", pd.NA).nunique())


def _rejected_result(
    *,
    source_rows: int,
    source_customers: int,
    errors: tuple[str, ...],
) -> ValidationAdmissionResult:
    return ValidationAdmissionResult(
        report=ValidationAdmissionReport(
            source_row_count=source_rows,
            source_customer_count=source_customers,
            accepted_row_count=0,
            accepted_customer_count=0,
            rejected_row_count=source_rows,
            rejected_customer_count=source_customers,
            schema_errors=errors,
            missing_period_customer_count=0,
            missing_period_count=0,
            outcome_availability={
                "evaluator_mapping_configured": False,
                "available_customer_count": 0,
                "unavailable_customer_count": source_customers,
                "status": "unavailable_due_to_schema_error",
            },
        ),
        scoring_dataset=None,
        evaluator_dataset=None,
    )


def _assert_injected_output_path(destination: Path, allowed_root: Path) -> None:
    resolved_destination = destination.resolve()
    resolved_root = allowed_root.resolve()
    try:
        resolved_destination.relative_to(resolved_root)
    except ValueError as error:
        raise ValidationDatasetContractError(
            "validation report metadata must be written under its injected readiness output root"
        ) from error
    for forbidden_root in (
        settings.DATA_RAW_DIR,
        settings.DATA_PROCESSED_DIR,
        settings.DATA_DEMO_DIR,
    ):
        try:
            resolved_destination.relative_to(forbidden_root.resolve())
        except ValueError:
            continue
        raise ValidationDatasetContractError("validation reports must not overwrite canonical data paths")
