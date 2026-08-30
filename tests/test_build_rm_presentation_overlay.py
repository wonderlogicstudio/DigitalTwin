"""Tests for the explicit RM Daily presentation-overlay build command."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.build_rm_presentation_overlay import main


def _write_customer_master(path: Path) -> None:
    rows = ["customer_id,cash_balance,persona,final_outcome"]
    rows.extend(
        f"C{index:06d},{index * 1000},ignored,ignored"
        for index in range(1, 501)
    )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_explicit_overlay_rebuild_reads_only_customer_ids_and_preserves_core_source(
    tmp_path: Path,
) -> None:
    customer_master = tmp_path / "data" / "raw" / "customer_master.csv"
    customer_master.parent.mkdir(parents=True)
    _write_customer_master(customer_master)
    before_hash = hashlib.sha256(customer_master.read_bytes()).hexdigest()
    output_path = tmp_path / "artifacts" / "rm_daily_review" / "presentation" / "overlay.json"

    exit_code = main(
        [
            "--customer-master",
            str(customer_master),
            "--output",
            str(output_path),
            "--portfolio-size",
            "300",
        ]
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert hashlib.sha256(customer_master.read_bytes()).hexdigest() == before_hash
    assert payload["portfolio_customer_count"] == 300
    assert all("??" not in row["display_name"] for row in payload["customers"])
    assert all(row["display_name_en"].startswith("Synthetic customer ") for row in payload["customers"])
    assert all(row["display_name_en"].isascii() for row in payload["customers"])
    assert all("??" not in row["presentation_label"] for row in payload["customers"])
    assert all(
        row["presentation_label_en"]
        == "Synthetic customer display information for this PoC"
        for row in payload["customers"]
    )
