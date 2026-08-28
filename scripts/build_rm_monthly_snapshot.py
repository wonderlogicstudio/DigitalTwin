"""Build one RM Portfolio Monthly Analysis Snapshot and workload report."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings  # noqa: E402
from src.daily_review import (  # noqa: E402
    MONITOR,
    REVIEW_NOW,
    UPCOMING,
    SnapshotTimingRecord,
    classify_daily_review_timing,
)
from src.matcher import TrajectoryMatcher  # noqa: E402
from src.monthly_review_snapshot import (  # noqa: E402
    MonthlyReviewSnapshot,
    build_monthly_review_snapshot,
    write_monthly_review_snapshot,
)
from src.rm_portfolio import (  # noqa: E402
    DEFAULT_PORTFOLIO_SELECTION_SEED,
    DEFAULT_PORTFOLIO_SIZE,
    DEFAULT_RELATIONSHIP_ASSIGNMENT_SEED,
    DEFAULT_RM_PORTFOLIO_ID,
    RELATIONSHIP_PRIORITY_ORDER,
    build_rm_portfolio,
)


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "rm_daily_review" / "monthly"
WORKLOAD_REPORT_VERSION = 1
BREAKPOINT_STATUS_KEYS = ("found", "not_found", "insufficient_group_size")
DAILY_REVIEW_STATES = (REVIEW_NOW, UPCOMING, MONITOR)


def load_customer_ids(customer_master_path: Path | str) -> list[str]:
    """Read only IDs from the core customer master without modifying it."""

    customer_master = pd.read_csv(customer_master_path, usecols=["customer_id"])
    return customer_master["customer_id"].astype(str).tolist()


def build_workload_report(snapshot: MonthlyReviewSnapshot) -> dict[str, object]:
    """Summarize saved Snapshot timing into workload counts without analysis."""

    breakpoint_counts = Counter()
    bucket_counts = Counter()
    relationship_by_bucket: dict[str, Counter[str]] = {
        priority: Counter() for priority in RELATIONSHIP_PRIORITY_ORDER
    }
    upcoming_core_customer_count = 0

    for record in snapshot.records:
        breakpoint_status = str(record.breakpoint.get("status") or "other")
        if breakpoint_status not in BREAKPOINT_STATUS_KEYS:
            breakpoint_status = "other"
        breakpoint_counts[breakpoint_status] += 1

        decision = classify_daily_review_timing(
            SnapshotTimingRecord(
                customer_id=record.customer_id,
                snapshot_id=record.snapshot_id,
                breakpoint_status=str(record.breakpoint.get("status") or ""),
                months_from_current=record.breakpoint.get("months_from_current"),
                primary_factor=record.breakpoint.get("primary_factor"),
                evidence_available=record.evidence.get("available") is True,
                current_status=record.current_summary.get("current_status"),
            )
        )
        bucket_counts[decision.review_state] += 1
        relationship_priority = str(
            record.relationship_metadata.get("relationship_priority") or "UNSPECIFIED"
        )
        relationship_by_bucket.setdefault(relationship_priority, Counter())
        relationship_by_bucket[relationship_priority][decision.review_state] += 1
        if decision.review_state == UPCOMING and relationship_priority == "CORE":
            upcoming_core_customer_count += 1

    priority_order = [
        *RELATIONSHIP_PRIORITY_ORDER,
        *sorted(
            priority
            for priority in relationship_by_bucket
            if priority not in RELATIONSHIP_PRIORITY_ORDER
        ),
    ]
    return {
        "workload_report_version": WORKLOAD_REPORT_VERSION,
        "snapshot_id": snapshot.snapshot_id,
        "analysis_as_of_month": snapshot.analysis_as_of_month,
        "rm_portfolio_id": snapshot.rm_portfolio_id,
        "portfolio_customer_count": len(snapshot.records),
        "breakpoint_status_distribution": {
            **{status: int(breakpoint_counts[status]) for status in BREAKPOINT_STATUS_KEYS},
            "other": int(breakpoint_counts["other"]),
        },
        "daily_review_distribution": {
            state: int(bucket_counts[state]) for state in DAILY_REVIEW_STATES
        },
        "relationship_priority_by_bucket": {
            priority: {
                state: int(relationship_by_bucket[priority][state])
                for state in DAILY_REVIEW_STATES
            }
            for priority in priority_order
        },
        "upcoming_core_customer_count": upcoming_core_customer_count,
    }


def write_workload_report(report: dict[str, object], output_path: Path | str) -> Path:
    """Write a standalone workload report and reject core Financial Path data."""

    path = Path(output_path)
    _ensure_separate_artifact_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser without any Financial Path methodology options."""

    parser = argparse.ArgumentParser(
        description=(
            "Build an RM Portfolio Monthly Analysis Snapshot and Daily Review workload report."
        )
    )
    parser.add_argument(
        "--snapshot-id",
        required=True,
        help="Stable identifier for this saved monthly analysis Snapshot.",
    )
    parser.add_argument(
        "--customer-master",
        type=Path,
        default=settings.CUSTOMER_MASTER_PATH,
        help="Existing core customer master; only customer_id is read.",
    )
    parser.add_argument(
        "--customer-monthly",
        type=Path,
        default=settings.CUSTOMER_MONTHLY_PATH,
        help="Existing core monthly Financial Path Twin CSV.",
    )
    parser.add_argument(
        "--trajectory-features",
        type=Path,
        default=settings.TRAJECTORY_FEATURES_PATH,
        help="Existing core trajectory features CSV for the full matching universe.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Standalone Snapshot JSON path; defaults under artifacts/rm_daily_review/monthly.",
    )
    parser.add_argument(
        "--workload-report-output",
        type=Path,
        help="Standalone workload report JSON path; defaults next to the Snapshot.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the fixed Monthly Analysis batch, then report saved timing workload."""

    parser = build_parser()
    args = parser.parse_args(argv)
    _validate_input_paths(parser, args)
    _validate_snapshot_id(parser, args.snapshot_id)

    customer_ids = load_customer_ids(args.customer_master)
    if len(customer_ids) != settings.CUSTOMER_COUNT:
        parser.error(
            "customer master must retain the configured 5,000-customer Financial Path Twin universe."
        )
    portfolio = build_rm_portfolio(
        customer_ids,
        portfolio_size=DEFAULT_PORTFOLIO_SIZE,
        portfolio_selection_seed=DEFAULT_PORTFOLIO_SELECTION_SEED,
        relationship_assignment_seed=DEFAULT_RELATIONSHIP_ASSIGNMENT_SEED,
        rm_portfolio_id=DEFAULT_RM_PORTFOLIO_ID,
    )
    monthly_df = pd.read_csv(args.customer_monthly)
    features_df = pd.read_csv(args.trajectory_features)
    matcher = TrajectoryMatcher().fit(features_df)
    snapshot = build_monthly_review_snapshot(
        portfolio,
        monthly_df,
        features_df,
        matcher,
        snapshot_id=args.snapshot_id,
        top_k=settings.TOP_K_MATCHES,
    )

    snapshot_path = args.output or DEFAULT_OUTPUT_DIR / f"{args.snapshot_id}.json"
    report_path = args.workload_report_output or snapshot_path.with_name(
        f"{snapshot_path.stem}_workload_report.json"
    )
    written_snapshot_path = write_monthly_review_snapshot(snapshot, snapshot_path)
    report = build_workload_report(snapshot)
    written_report_path = write_workload_report(report, report_path)
    _print_summary(written_snapshot_path, written_report_path, report)
    return 0


def _validate_input_paths(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    for argument_name in ("customer_master", "customer_monthly", "trajectory_features"):
        path = getattr(args, argument_name)
        if not path.is_file():
            parser.error(f"{argument_name.replace('_', '-')} does not exist: {path}")


def _validate_snapshot_id(parser: argparse.ArgumentParser, snapshot_id: str) -> None:
    normalized_snapshot_id = str(snapshot_id).strip()
    if not normalized_snapshot_id or Path(normalized_snapshot_id).name != normalized_snapshot_id:
        parser.error("snapshot-id must be a non-empty file-name-safe identifier.")


def _ensure_separate_artifact_path(path: Path) -> None:
    resolved_path = path.resolve()
    for core_directory in (
        settings.DATA_RAW_DIR,
        settings.DATA_PROCESSED_DIR,
        settings.DATA_DEMO_DIR,
    ):
        if resolved_path.is_relative_to(core_directory.resolve()):
            raise ValueError("Workload report must not overwrite core data artifacts.")


def _print_summary(
    snapshot_path: Path,
    report_path: Path,
    report: dict[str, object],
) -> None:
    breakpoint_counts = report["breakpoint_status_distribution"]
    review_counts = report["daily_review_distribution"]
    relationship_counts = report["relationship_priority_by_bucket"]

    print(f"snapshot: {snapshot_path}")
    print(f"workload_report: {report_path}")
    print(f"portfolio_customers: {report['portfolio_customer_count']}")
    print(f"breakpoint_found: {breakpoint_counts['found']}")
    print(f"breakpoint_not_found: {breakpoint_counts['not_found']}")
    print(f"breakpoint_insufficient_group_size: {breakpoint_counts['insufficient_group_size']}")
    print(f"오늘 먼저 확인: {review_counts[REVIEW_NOW]}")
    print(f"곧 확인 예정: {review_counts[UPCOMING]}")
    print(f"모니터링: {review_counts[MONITOR]}")
    print(f"곧 확인 예정 중 핵심관리 고객: {report['upcoming_core_customer_count']}명")
    for priority, bucket_counts in relationship_counts.items():
        print(
            f"{priority}: "
            f"오늘 먼저 확인 {bucket_counts[REVIEW_NOW]}, "
            f"곧 확인 예정 {bucket_counts[UPCOMING]}, "
            f"모니터링 {bucket_counts[MONITOR]}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
