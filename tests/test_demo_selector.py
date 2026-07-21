import json

import pandas as pd
import pytest

from config import settings
from src.demo_selector import save_demo_outputs, select_demo_customers


@pytest.fixture(scope="module")
def demo_outputs() -> tuple[pd.DataFrame, dict]:
    if settings.DEMO_CUSTOMERS_PATH.exists() and settings.MAIN_DEMO_CUSTOMER_PATH.exists():
        demo_df = pd.read_csv(settings.DEMO_CUSTOMERS_PATH)
        main_json = json.loads(settings.MAIN_DEMO_CUSTOMER_PATH.read_text(encoding="utf-8"))
        return demo_df, main_json

    monthly_df = pd.read_csv(settings.CUSTOMER_MONTHLY_PATH)
    features_df = pd.read_csv(settings.TRAJECTORY_FEATURES_PATH)
    demo_df, main_json = select_demo_customers(
        monthly_df,
        features_df,
        generated_at="2026-07-17T00:00:00+00:00",
    )
    save_demo_outputs(demo_df, main_json)
    return demo_df, main_json


def test_demo_customers_are_three_distinct_customers(
    demo_outputs: tuple[pd.DataFrame, dict],
) -> None:
    demo_df, _ = demo_outputs

    assert len(demo_df) == 3
    assert demo_df["customer_id"].nunique() == 3


def test_demo_roles_are_exactly_three_expected_roles(
    demo_outputs: tuple[pd.DataFrame, dict],
) -> None:
    demo_df, _ = demo_outputs

    assert set(demo_df["demo_role"]) == set(settings.DEMO_ROLES)


def test_main_customer_has_found_breakpoint(
    demo_outputs: tuple[pd.DataFrame, dict],
) -> None:
    demo_df, main_json = demo_outputs
    main_row = demo_df.loc[demo_df["demo_role"] == "main"].iloc[0]

    assert main_row["breakpoint_status"] == "found"
    assert main_json["breakpoint_result"]["status"] == "found"
    assert 13 <= int(main_row["breakpoint_month"]) <= 18


def test_main_customer_has_200_matches(
    demo_outputs: tuple[pd.DataFrame, dict],
) -> None:
    demo_df, main_json = demo_outputs
    main_row = demo_df.loc[demo_df["demo_role"] == "main"].iloc[0]

    assert int(main_row["matched_count"]) == settings.TOP_K_MATCHES
    assert main_json["outcome_summary"]["matched_count"] == settings.TOP_K_MATCHES


def test_stable_customer_healthy_recovered_ratio_is_high(
    demo_outputs: tuple[pd.DataFrame, dict],
) -> None:
    demo_df, _ = demo_outputs
    stable_row = demo_df.loc[demo_df["demo_role"] == "stable_comparison"].iloc[0]

    assert stable_row["healthy_ratio"] + stable_row["recovered_ratio"] >= 0.80


def test_high_risk_customer_risk_ratio_is_high(
    demo_outputs: tuple[pd.DataFrame, dict],
) -> None:
    demo_df, _ = demo_outputs
    high_risk_row = demo_df.loc[demo_df["demo_role"] == "high_risk"].iloc[0]

    assert high_risk_row["risk_group_ratio"] >= 0.60


def test_main_demo_json_is_serializable(demo_outputs: tuple[pd.DataFrame, dict]) -> None:
    _, main_json = demo_outputs

    encoded = json.dumps(main_json, ensure_ascii=False)
    decoded = json.loads(encoded)

    assert decoded["customer_id"] == main_json["customer_id"]


def test_same_data_selects_same_customers(demo_outputs: tuple[pd.DataFrame, dict]) -> None:
    saved_demo_df, _ = demo_outputs
    monthly_df = pd.read_csv(settings.CUSTOMER_MONTHLY_PATH)
    features_df = pd.read_csv(settings.TRAJECTORY_FEATURES_PATH)

    selected_df, _ = select_demo_customers(
        monthly_df,
        features_df,
        generated_at="2026-07-17T00:00:00+00:00",
    )

    saved_pairs = saved_demo_df.sort_values("demo_role")[["demo_role", "customer_id"]].reset_index(drop=True)
    selected_pairs = selected_df.sort_values("demo_role")[["demo_role", "customer_id"]].reset_index(drop=True)
    pd.testing.assert_frame_equal(saved_pairs, selected_pairs)


def test_relaxation_rule_is_recorded_for_main_customer(
    demo_outputs: tuple[pd.DataFrame, dict],
) -> None:
    demo_df, _ = demo_outputs
    main_reason = demo_df.loc[demo_df["demo_role"] == "main", "selection_reason"].iloc[0]

    assert "relaxed:" in main_reason
