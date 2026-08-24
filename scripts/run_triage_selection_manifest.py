"""Build a separate, reference-only RM selection manifest for all customers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings  # noqa: E402
from src.crossfit_backtest import (  # noqa: E402
    build_deterministic_folds,
    reconcile_customer_month_keys,
)
from src.demo_policy import assess_policy_snapshot, default_demo_policy  # noqa: E402
from src.prospective_evaluator import build_reference_historical_share_provider  # noqa: E402
from src.prospective_scoring import (  # noqa: E402
    prepare_observed_scoring_data,
    score_reference_only_fold,
)
from src.selection_manifest import (  # noqa: E402
    TRIAGE_ARTIFACT_DIR,
    export_selection_artifacts,
    load_selection_artifacts,
)
from src.triage_selector import TriageSelector, default_triage_selection_policy  # noqa: E402
from src.triage_universe import TriageDecisionInput, build_triage_universe  # noqa: E402


DEFAULT_RUN_ID = "seed42_crossfit_5fold_asof12_unbounded"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse bounded, synthetic-only selection-export options."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--capacity", type=int, default=None)
    parser.add_argument("--fold-count", type=int, default=5)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args(argv)


def run_selection_manifest(args: argparse.Namespace) -> dict[str, object]:
    """Score fixed month 12 snapshots, then export triage-only selection outputs."""

    if not str(args.run_id).strip() or Path(str(args.run_id)).name != str(args.run_id):
        raise ValueError("run_id must be a non-empty directory name")
    if args.capacity is not None and args.capacity < 0:
        raise ValueError("capacity must be non-negative or omitted")

    monthly_df = pd.read_csv(settings.CUSTOMER_MONTHLY_PATH)
    customer_ids = tuple(sorted(monthly_df["customer_id"].astype(str).unique()))
    if len(customer_ids) != settings.CUSTOMER_COUNT:
        raise ValueError(
            f"canonical customer count must be {settings.CUSTOMER_COUNT}; got {len(customer_ids)}"
        )
    if len(monthly_df) != settings.CUSTOMER_COUNT * settings.TOTAL_MONTHS:
        raise ValueError("canonical monthly row count does not match configured customer/month contract")

    observed_scoring_data = prepare_observed_scoring_data(monthly_df, as_of_months=(12,))
    scored_records = []
    failures = []
    for fold in build_deterministic_folds(customer_ids, fold_count=args.fold_count):
        reference_share_provider = build_reference_historical_share_provider(
            monthly_df,
            reference_customer_ids=fold.reference_customer_ids,
        )
        fold_result = score_reference_only_fold(
            observed_scoring_data,
            fold_id=fold.fold_id,
            reference_customer_ids=fold.reference_customer_ids,
            evaluation_customer_ids=fold.evaluation_customer_ids,
            as_of_months=(12,),
            historical_share_provider=reference_share_provider,
            top_k=settings.TOP_K_MATCHES,
        )
        scored_records.extend(fold_result.records)
        failures.extend(fold_result.failures)

    reconciliation = reconcile_customer_month_keys(
        tuple((customer_id, 12) for customer_id in customer_ids),
        tuple(record.key for record in scored_records),
    )
    if failures or not reconciliation.is_exact:
        raise RuntimeError(
            "reference-only scoring did not reconcile exactly: "
            f"failures={len(failures)}, missing={len(reconciliation.missing_keys)}, "
            f"unexpected={len(reconciliation.unexpected_keys)}, "
            f"duplicates={len(reconciliation.duplicate_processed_keys)}"
        )

    policy = default_demo_policy()
    decision_inputs = tuple(
        TriageDecisionInput(
            record.snapshot.customer_id,
            record.snapshot,
            assess_policy_snapshot(policy, record.snapshot),
        )
        for record in sorted(scored_records, key=lambda item: item.key)
    )
    universe = build_triage_universe(
        expected_customer_ids=customer_ids,
        triage_as_of_month=12,
        signal_run_id=f"crossfit_seed42_{args.fold_count}fold_asof12",
        decision_inputs=decision_inputs,
    )
    selection_policy = default_triage_selection_policy(max_reviews_per_cycle=args.capacity)
    selection = TriageSelector().select(universe, selection_policy)
    destination = args.output_dir or TRIAGE_ARTIFACT_DIR / str(args.run_id)
    capacity_scenario_id = "unbounded_demo" if args.capacity is None else f"capacity_{args.capacity}"
    paths = export_selection_artifacts(
        universe,
        selection,
        run_id=str(args.run_id),
        output_dir=destination,
        capacity_scenario_id=capacity_scenario_id,
    )
    loaded = load_selection_artifacts(destination)
    cohort = loaded["representative_cohort"]
    return {
        "paths": paths.to_dict(),
        "scoring_reconciliation": reconciliation.to_dict(),
        "selection_funnel": loaded["selection_manifest"]["funnel"],
        "selection_reconciliation": loaded["selection_manifest"]["reconciliation"],
        "representative_cohort": {
            record["category_id"]: {"status": record["status"], "customer_id": record["customer_id"]}
            for record in cohort["records"]
        },
    }


def main(argv: list[str] | None = None) -> int:
    """Run and print the machine-readable selection-manifest summary."""

    try:
        result = run_selection_manifest(parse_args(argv))
    except (OSError, RuntimeError, ValueError) as error:
        print(f"triage_selection_manifest_failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
