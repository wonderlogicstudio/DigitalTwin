# DATA_DICTIONARY.md — 데이터 사전

## 1. 공통 규칙

- 금액: 원
- 비율 저장: 0~1 실수
- 월: 1~36
- 고객 ID: C000001 형식
- 필수 컬럼 결측 금지
- 이벤트 없음: `none`
- 분모 0은 별도 규칙 적용

## 2. customer_master.csv

| 컬럼 | 타입 | 설명 |
|---|---|---|
| customer_id | string | 고객 ID |
| persona | category | 생성 페르소나 |
| age_group | category | 20s~60s |
| household_type | category | 가구 유형 |
| initial_income | int | 초기 월소득 |
| initial_cash_balance | int | 초기 잔액 |
| initial_loan_balance | int | 초기 대출 |
| base_fixed_expense | int | 기본 고정비 |
| base_variable_expense | int | 기본 변동비 |
| base_debt_payment | int | 기본 상환액 |
| primary_event_type | category | 주요 이벤트 |
| primary_event_month | int | 없으면 0 |
| random_seed | int | 재현성 |

persona:
- stable
- gradual_deterioration
- event_shock
- recovery
- overspending

## 3. customer_monthly_5000.csv

행 수: 180,000

| 컬럼 | 타입 | 설명 |
|---|---|---|
| customer_id | string | 고객 ID |
| month | int | 1~36 |
| persona | category | 검증용, 매칭 금지 |
| income | int | 월소득 |
| fixed_expense | int | 고정지출 |
| variable_expense | int | 변동지출 |
| debt_payment | int | 대출상환액 |
| event_expense | int | 이벤트 비용 |
| total_expense | int | 총지출 |
| savings_amount | int | 소득-총지출 |
| savings_rate | float | 저축금액/소득 |
| fixed_expense_ratio | float | 고정지출/소득 |
| variable_expense_ratio | float | 변동지출/소득 |
| dsr | float | 상환액/소득 |
| cash_balance | int | 누적 잔액 |
| loan_balance | int | 대출 잔액 |
| debt_to_income_ratio | float | 대출잔액/월소득 |
| emergency_months | float | 잔액/생활비 |
| income_change_rate | float | 전월 대비 |
| expense_change_rate | float | 전월 대비 |
| balance_change_rate | float | 전월 대비 |
| event_type | category | 월 이벤트 |
| delinquency_flag | int | 0/1 |
| monthly_status | category | healthy/watch/stress/delinquent |
| final_outcome | category | healthy/recovered/stress/delinquent |

event_type:
- none
- job_loss
- job_change
- childbirth
- medical_cost
- housing_cost_increase
- interest_rate_shock
- income_recovery
- expense_reduction
- new_loan

## 4. 계산식

```text
total_expense
= fixed_expense + variable_expense + debt_payment + event_expense
```

```text
savings_amount = income - total_expense
```

소득 > 0:

```text
savings_rate = savings_amount / income
fixed_expense_ratio = fixed_expense / income
variable_expense_ratio = variable_expense / income
dsr = debt_payment / income
```

소득 = 0:

```text
savings_rate = -1.0
fixed_expense_ratio = 1.0
variable_expense_ratio = 1.0
dsr = 1.0
```

현금 잔액:

```text
month 1: initial_cash_balance + savings_amount
month t: previous_cash_balance + savings_amount
```

대출 잔액:

```text
principal_repayment = min(debt_payment * 0.70, previous_loan_balance)
loan_balance = max(0, previous_loan_balance - principal_repayment + new_loan_amount)
```

비상자금:

```text
living_expense = fixed_expense + variable_expense
emergency_months = max(cash_balance, 0) / max(living_expense, 1)
```

변화율:

```text
previous > 0: (current - previous) / previous
previous = 0: 0
```

## 5. trajectory_features.csv

고객당 1행, 1~12개월만 사용.

| 컬럼 | 설명 |
|---|---|
| customer_id | 고객 ID |
| avg_savings_rate_3m | 10~12월 평균 |
| avg_dsr_3m | 10~12월 평균 |
| avg_fixed_expense_ratio_3m | 10~12월 평균 |
| savings_rate_slope_12m | 저축률 기울기 |
| expense_growth_12m | 1~3월 대비 10~12월 지출 증가율 |
| dsr_change_12m | 12월-1월 |
| balance_change_ratio_12m | 잔액 변화율 |
| income_cv_12m | 소득 CV |
| expense_cv_12m | 지출 CV |
| max_consecutive_balance_decline_12m | 최대 연속 잔액 감소 |
| recent_negative_savings_months_6m | 최근 6개월 음수 저축 월 |
| recent_large_expense_count_12m | 평균+1.5표준편차 초과 횟수 |

기울기:

```python
numpy.polyfit(months, values, 1)[0]
```

CV:

```text
abs(mean) < 1e-9이면 0
그 외 std / abs(mean)
```

## 6. matched_customers.csv

| 컬럼 | 설명 |
|---|---|
| target_customer_id | 타깃 |
| matched_customer_id | 유사 고객 |
| rank | 1부터 |
| distance | 가중 거리 |
| similarity_score | 1/(1+distance) |
| matched_final_outcome | 표시용 |
| matched_persona | 검증용, UI 숨김 |

## 7. matched_future_trajectory.csv

| 컬럼 | 설명 |
|---|---|
| target_customer_id | 타깃 |
| matched_customer_id | 유사 고객 |
| month | 13~36 |
| savings_rate | 저축률 |
| fixed_expense_ratio | 고정비 비율 |
| variable_expense_ratio | 변동비 비율 |
| dsr | DSR |
| cash_balance | 잔액 |
| cash_balance_ratio | 잔액/최근 평균소득 |
| loan_balance | 대출 |
| loan_balance_ratio | 대출/최근 평균소득 |
| monthly_status | 월 상태 |
| final_outcome | 최종 결과 |

## 8. outcome_summary.json 예시

```json
{
  "target_customer_id": "C000123",
  "matched_count": 200,
  "outcomes": {
    "healthy": {"count": 106, "ratio": 0.53},
    "recovered": {"count": 18, "ratio": 0.09},
    "stress": {"count": 60, "ratio": 0.30},
    "delinquent": {"count": 16, "ratio": 0.08}
  },
  "first_stress_month_median": 18,
  "first_delinquency_month_median": 25
}
```

## 9. breakpoint_result.json 예시

```json
{
  "status": "found",
  "breakpoint_month": 14,
  "months_from_current": 2,
  "primary_factor": "fixed_expense_ratio",
  "risk_group_mean": 0.47,
  "avoidance_group_mean": 0.36,
  "standardized_difference": 0.72,
  "persistence_months": 3
}
```

## 10. 데이터 누수 금지

매칭 특징에 절대 사용 금지:

- persona
- final_outcome
- 13~36월 event_type
- 13~36월 delinquency_flag
- 13~36월 monthly_status
- 13~36월 모든 금액·비율

특징 함수 첫 단계에서 반드시 `month <= 12`를 강제한다.

## 11. Separate P0 prototype artifacts

The following files are additive prototype artifacts. They are not canonical
input schemas and must not overwrite `data/raw`, `data/processed`, or
`data/demo`.

| Root / file | Schema | Purpose and minimum contract |
|---|---|---|
| `artifacts/population/<run>/population_detail.csv/json` | `population_detail.v1` | One result per expected customer: `customer_id`, `matched_count`, distance summary, historical outcome shares, breakpoint status/month/factor/support, `analysis_status`, and structured error fields. |
| `artifacts/population/<run>/population_summary.json` | `population_summary.v1` | Population counts, analysis/breakpoint status distributions, matched-count and historical-outcome-share distributions. |
| `artifacts/population/<run>/population_manifest.json` | `population_manifest.v1` | Run ID, code/settings/seed snapshot, counters, output paths, and exact expected/output-ID reconciliation. |
| `artifacts/validation/.../*.json` | validation-specific | Synthetic circularity/negative-control and multi-seed/TOP_K sensitivity reports. Canonical seed-42 input hashes are recorded, not replaced. |
| `artifacts/triage/<run>/rm_selection_manifest.json` | `rm_selection_manifest.v1` | All expected customer IDs, exactly one primary disposition, policy/signal references, reason codes, deterministic rank, and funnel/reconciliation. |
| `artifacts/triage/<run>/rm_representative_cohort.json` | representative-cohort schema | Deterministic display-only comparison cases; unavailable categories remain unavailable. It does not alter operational selection. |
| `artifacts/workflow/` | workflow schemas | File-backed Alert/Case and append-only audit prototype data. This root is independent of analytics artifacts. |
| `artifacts/post_p0/capacity/` | `capacity_comparison.v1` | Aggregate, saved-rank capacity comparison. `draft` does not mean an approved workload. |
| `artifacts/post_p0/real_data_readiness/` | readiness-only schemas | Governance, adapter, and metric templates with no admitted real-data rows or approval evidence. |
| `artifacts/post_p0/rm_pilot/` | pilot protocol templates | Source-free future-pilot measurement contract; not pilot observations. |
| `artifacts/post_p0/pilot_dry_run/<run>/` | `synthetic_rm_pilot_dry_run.v1` | Isolated synthetic rehearsal manifest, workflow and audit artifacts. It cannot claim actual RM or customer results. |

Terminology restrictions:

- `historical_outcome_shares` are matched synthetic-cohort shares, not target
  probabilities.
- `historical_landmark` and `prospective_signal` are distinct sources and must
  remain separate in records and UI.
- Analytical `final_outcome` and a human RM CaseOutcome/closure reason are
  distinct fields and must not be substituted for one another.
- Post-P0 artifacts must contain aggregate/synthetic references only. Direct
  identifiers, contact data, account data, credentials, raw feedback, and
  admitted real-data rows are prohibited.
