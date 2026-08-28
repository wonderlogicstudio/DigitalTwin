"""Deterministic synthetic RM Portfolio and CRM relationship overlay."""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np


DEFAULT_PORTFOLIO_SIZE = 300
DEFAULT_PORTFOLIO_SELECTION_SEED = 20_260_828
DEFAULT_RELATIONSHIP_ASSIGNMENT_SEED = 42
DEFAULT_RM_PORTFOLIO_ID = "RM-POC-001"
METADATA_VERSION = 1
METADATA_SOURCE = "synthetic_crm_overlay"
SYNTHETIC_CRM_DISCLAIMER = (
    "PoC용 synthetic CRM relationship metadata이며 실제 CRM/AUM 또는 자산가 분류가 아닙니다."
)

RELATIONSHIP_PRIORITY_ORDER = ("CORE", "PRIORITY", "STANDARD")
RELATIONSHIP_LABELS = {
    "CORE": "핵심관리",
    "PRIORITY": "우선관리",
    "STANDARD": "일반관리",
}
RELATIONSHIP_RATIOS = {
    "CORE": 0.10,
    "PRIORITY": 0.25,
    "STANDARD": 0.65,
}
PORTFOLIO_CUSTOMER_FIELDS = (
    "customer_id",
    "rm_portfolio_id",
    "relationship_priority",
    "relationship_label",
)


@dataclass(frozen=True)
class RmPortfolioCustomer:
    """One synthetic CRM overlay row for a Portfolio customer."""

    customer_id: str
    rm_portfolio_id: str
    relationship_priority: str
    relationship_label: str

    def as_dict(self) -> dict[str, str]:
        """Return the public overlay row without financial attributes."""

        return {
            "customer_id": self.customer_id,
            "rm_portfolio_id": self.rm_portfolio_id,
            "relationship_priority": self.relationship_priority,
            "relationship_label": self.relationship_label,
        }


@dataclass(frozen=True)
class RmPortfolio:
    """Synthetic RM Portfolio metadata independent of Financial Path Twin results."""

    rm_portfolio_id: str
    universe_customer_count: int
    portfolio_selection_seed: int
    relationship_assignment_seed: int
    customers: tuple[RmPortfolioCustomer, ...]

    @property
    def portfolio_size(self) -> int:
        """Return the number of Portfolio customers."""

        return len(self.customers)

    def relationship_counts(self) -> dict[str, int]:
        """Return counts for every supported relationship priority."""

        counts = Counter(customer.relationship_priority for customer in self.customers)
        return {priority: int(counts[priority]) for priority in RELATIONSHIP_PRIORITY_ORDER}

    def as_artifact(self) -> dict[str, object]:
        """Return a portable JSON artifact with only operational metadata."""

        counts = self.relationship_counts()
        return {
            "metadata_version": METADATA_VERSION,
            "source": METADATA_SOURCE,
            "disclaimer": SYNTHETIC_CRM_DISCLAIMER,
            "universe_customer_count": self.universe_customer_count,
            "rm_portfolio_id": self.rm_portfolio_id,
            "portfolio_size": self.portfolio_size,
            "portfolio_selection_seed": self.portfolio_selection_seed,
            "relationship_assignment_seed": self.relationship_assignment_seed,
            "relationship_distribution": {
                priority: {
                    "count": counts[priority],
                    "ratio": RELATIONSHIP_RATIOS[priority],
                    "label": RELATIONSHIP_LABELS[priority],
                }
                for priority in RELATIONSHIP_PRIORITY_ORDER
            },
            "customers": [customer.as_dict() for customer in self.customers],
        }


def build_rm_portfolio(
    customer_ids: Iterable[str],
    *,
    portfolio_size: int = DEFAULT_PORTFOLIO_SIZE,
    portfolio_selection_seed: int = DEFAULT_PORTFOLIO_SELECTION_SEED,
    relationship_assignment_seed: int = DEFAULT_RELATIONSHIP_ASSIGNMENT_SEED,
    rm_portfolio_id: str = DEFAULT_RM_PORTFOLIO_ID,
) -> RmPortfolio:
    """Build a deterministic Portfolio from customer IDs only.

    This function intentionally accepts no financial values, persona, outcome,
    breakpoint, or analysis output. The selected customers remain part of the
    original full matching universe; this result defines only the RM work scope.
    """

    normalized_ids = _normalize_customer_ids(customer_ids)
    _validate_build_inputs(
        normalized_ids,
        portfolio_size=portfolio_size,
        rm_portfolio_id=rm_portfolio_id,
    )

    selection_rng = np.random.default_rng(portfolio_selection_seed)
    selected_ids = selection_rng.choice(
        np.asarray(normalized_ids, dtype=str),
        size=portfolio_size,
        replace=False,
    )
    selected_ids = sorted(str(customer_id) for customer_id in selected_ids)

    relationship_rng = np.random.default_rng(relationship_assignment_seed)
    assignment_order = [
        str(customer_id)
        for customer_id in relationship_rng.permutation(np.asarray(selected_ids, dtype=str))
    ]
    priority_by_customer = _assign_relationship_priorities(assignment_order)

    customers = tuple(
        RmPortfolioCustomer(
            customer_id=customer_id,
            rm_portfolio_id=rm_portfolio_id,
            relationship_priority=priority_by_customer[customer_id],
            relationship_label=RELATIONSHIP_LABELS[priority_by_customer[customer_id]],
        )
        for customer_id in selected_ids
    )
    return RmPortfolio(
        rm_portfolio_id=rm_portfolio_id,
        universe_customer_count=len(normalized_ids),
        portfolio_selection_seed=int(portfolio_selection_seed),
        relationship_assignment_seed=int(relationship_assignment_seed),
        customers=customers,
    )


def write_rm_portfolio_artifacts(
    portfolio: RmPortfolio,
    json_path: Path | str,
) -> tuple[Path, Path]:
    """Write standalone JSON and CSV overlay artifacts, never core data files."""

    output_json_path = Path(json_path)
    output_csv_path = output_json_path.with_suffix(".csv")
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(
        json.dumps(portfolio.as_artifact(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    with output_csv_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=PORTFOLIO_CUSTOMER_FIELDS)
        writer.writeheader()
        writer.writerows(customer.as_dict() for customer in portfolio.customers)

    return output_json_path, output_csv_path


def _normalize_customer_ids(customer_ids: Iterable[str]) -> list[str]:
    normalized_ids = [str(customer_id).strip() for customer_id in customer_ids]
    if not normalized_ids:
        raise ValueError("customer_ids must not be empty.")
    if any(not customer_id for customer_id in normalized_ids):
        raise ValueError("customer_ids must not contain blank values.")
    duplicates = sorted(
        customer_id
        for customer_id, count in Counter(normalized_ids).items()
        if count > 1
    )
    if duplicates:
        raise ValueError(f"customer_ids must be unique; duplicates: {duplicates[:3]}")
    return sorted(normalized_ids)


def _validate_build_inputs(
    customer_ids: list[str],
    *,
    portfolio_size: int,
    rm_portfolio_id: str,
) -> None:
    if portfolio_size <= 0:
        raise ValueError("portfolio_size must be positive.")
    if portfolio_size > len(customer_ids):
        raise ValueError("portfolio_size cannot exceed the customer ID universe.")
    if not str(rm_portfolio_id).strip():
        raise ValueError("rm_portfolio_id must not be blank.")


def _assign_relationship_priorities(assignment_order: list[str]) -> dict[str, str]:
    counts = _relationship_priority_counts(len(assignment_order))
    core_end = counts["CORE"]
    priority_end = core_end + counts["PRIORITY"]
    priority_by_customer: dict[str, str] = {}
    for index, customer_id in enumerate(assignment_order):
        if index < core_end:
            priority_by_customer[customer_id] = "CORE"
        elif index < priority_end:
            priority_by_customer[customer_id] = "PRIORITY"
        else:
            priority_by_customer[customer_id] = "STANDARD"
    return priority_by_customer


def _relationship_priority_counts(portfolio_size: int) -> dict[str, int]:
    core_count = int(portfolio_size * RELATIONSHIP_RATIOS["CORE"])
    priority_count = int(portfolio_size * RELATIONSHIP_RATIOS["PRIORITY"])
    return {
        "CORE": core_count,
        "PRIORITY": priority_count,
        "STANDARD": portfolio_size - core_count - priority_count,
    }
