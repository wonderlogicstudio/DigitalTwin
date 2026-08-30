"""Deterministic synthetic presentation overlay for the RM Daily Review."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_PRESENTATION_SEED = 20_260_829
DEFAULT_PORTFOLIO_CUSTOMER_COUNT = 300
PRESENTATION_METADATA_VERSION = 3
PRESENTATION_METADATA_SOURCE = "synthetic_presentation_overlay"
SYNTHETIC_PRESENTATION_DISCLAIMER = (
    "PoC용 합성 고객 표시 정보입니다. 실제 고객 또는 CRM 정보가 아닙니다."
)
SYNTHETIC_PRESENTATION_LABEL = "PoC용 합성 고객 표시 정보"
PRESENTATION_CUSTOMER_FIELDS = (
    "customer_id",
    "display_name",
    "display_name_ko",
    "display_name_en",
    "display_owner_or_team",
    "display_owner_or_team_ko",
    "display_owner_or_team_en",
    "presentation_label",
    "presentation_label_ko",
    "presentation_label_en",
)

_NAME_STEMS = (
    "가람",
    "나래",
    "다온",
    "라온",
    "마루",
    "바다",
    "새봄",
    "아라",
    "여울",
    "이든",
    "하람",
    "해든",
)
_ENGLISH_NAME_STEMS = (
    "Avery",
    "Blair",
    "Casey",
    "Devon",
    "Ellis",
    "Harper",
    "Jamie",
    "Jordan",
    "Morgan",
    "Parker",
    "Reese",
    "Rowan",
)
_OWNER_TEAMS = (
    "RM 업무팀 1",
    "RM 업무팀 2",
    "RM 업무팀 3",
    "RM 업무팀 4",
)


@dataclass(frozen=True)
class RmPresentationCustomer:
    """A display-only synthetic identity for one RM Portfolio customer."""

    customer_id: str
    display_name: str
    display_name_ko: str
    display_name_en: str
    display_owner_or_team: str
    display_owner_or_team_ko: str
    display_owner_or_team_en: str
    presentation_label: str
    presentation_label_ko: str
    presentation_label_en: str

    def as_dict(self) -> dict[str, str]:
        """Return display metadata without financial or CRM-priority attributes."""

        return {
            "customer_id": self.customer_id,
            "display_name": self.display_name,
            "display_name_ko": self.display_name_ko,
            "display_name_en": self.display_name_en,
            "display_owner_or_team": self.display_owner_or_team,
            "display_owner_or_team_ko": self.display_owner_or_team_ko,
            "display_owner_or_team_en": self.display_owner_or_team_en,
            "presentation_label": self.presentation_label,
            "presentation_label_ko": self.presentation_label_ko,
            "presentation_label_en": self.presentation_label_en,
        }


@dataclass(frozen=True)
class RmPresentationOverlay:
    """Standalone, deterministic display metadata for a single RM Portfolio."""

    portfolio_customer_count: int
    presentation_seed: int
    customers: tuple[RmPresentationCustomer, ...]

    def as_artifact(self) -> dict[str, object]:
        """Return the portable display-only JSON artifact."""

        return {
            "metadata_version": PRESENTATION_METADATA_VERSION,
            "source": PRESENTATION_METADATA_SOURCE,
            "disclaimer": SYNTHETIC_PRESENTATION_DISCLAIMER,
            "portfolio_customer_count": self.portfolio_customer_count,
            "presentation_seed": self.presentation_seed,
            "customers": [customer.as_dict() for customer in self.customers],
        }


def build_rm_presentation_overlay(
    customer_ids: Iterable[str],
    *,
    presentation_seed: int = DEFAULT_PRESENTATION_SEED,
    expected_customer_count: int = DEFAULT_PORTFOLIO_CUSTOMER_COUNT,
) -> RmPresentationOverlay:
    """Build display metadata from Portfolio customer IDs and a fixed seed only.

    This function intentionally receives no Financial Path Twin output, CRM
    relationship priority, persona, outcome, breakpoint, or feature value. The
    result is a display overlay, not a customer identity or an analytics input.
    """

    normalized_ids = _normalize_customer_ids(customer_ids)
    if expected_customer_count <= 0:
        raise ValueError("expected_customer_count must be positive.")
    if len(normalized_ids) != expected_customer_count:
        raise ValueError(
            "customer_ids must contain exactly "
            f"{expected_customer_count} Portfolio customers; found {len(normalized_ids)}."
        )

    customers = tuple(
        _build_presentation_customer(customer_id, presentation_seed)
        for customer_id in normalized_ids
    )
    return RmPresentationOverlay(
        portfolio_customer_count=len(customers),
        presentation_seed=int(presentation_seed),
        customers=customers,
    )


def presentation_for_customer(
    overlay: RmPresentationOverlay,
    customer_id: str,
) -> RmPresentationCustomer:
    """Return one Portfolio display row or raise when the ID is outside it."""

    normalized_customer_id = str(customer_id).strip()
    for customer in overlay.customers:
        if customer.customer_id == normalized_customer_id:
            return customer
    raise KeyError(
        "customer_id is not part of this synthetic presentation overlay: "
        f"{normalized_customer_id!r}"
    )


def write_rm_presentation_overlay_artifact(
    overlay: RmPresentationOverlay,
    json_path: Path | str,
) -> Path:
    """Write a standalone JSON display artifact and never a core data file."""

    output_path = Path(json_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(overlay.as_artifact(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output_path


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


def _build_presentation_customer(
    customer_id: str,
    presentation_seed: int,
) -> RmPresentationCustomer:
    digest = hashlib.sha256(
        f"{int(presentation_seed)}:{customer_id}".encode("utf-8")
    ).digest()
    name_stem = _NAME_STEMS[digest[0] % len(_NAME_STEMS)]
    english_name_stem = _ENGLISH_NAME_STEMS[digest[4] % len(_ENGLISH_NAME_STEMS)]
    name_suffix = int.from_bytes(digest[1:3], byteorder="big") % 100
    owner_team = _OWNER_TEAMS[digest[3] % len(_OWNER_TEAMS)]
    owner_team_number = (digest[3] % len(_OWNER_TEAMS)) + 1
    display_name_ko = f"합성 고객 {name_stem}-{name_suffix:02d}"
    display_name_en = f"Synthetic customer {english_name_stem}-{name_suffix:02d}"
    display_owner_or_team_en = f"RM Review Team {owner_team_number}"
    presentation_label_en = "Synthetic customer display information for this PoC"
    return RmPresentationCustomer(
        customer_id=customer_id,
        display_name=display_name_ko,
        display_name_ko=display_name_ko,
        display_name_en=display_name_en,
        display_owner_or_team=owner_team,
        display_owner_or_team_ko=owner_team,
        display_owner_or_team_en=display_owner_or_team_en,
        presentation_label=SYNTHETIC_PRESENTATION_LABEL,
        presentation_label_ko=SYNTHETIC_PRESENTATION_LABEL,
        presentation_label_en=presentation_label_en,
    )
