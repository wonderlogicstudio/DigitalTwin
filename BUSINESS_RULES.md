# BUSINESS_RULES.md — 비즈니스 규칙

## 1. 기본 상수

```python
RANDOM_SEED = 42
CUSTOMER_COUNT = 5000
TOTAL_MONTHS = 36
OBSERVATION_END_MONTH = 12
FUTURE_START_MONTH = 13
FUTURE_END_MONTH = 36
TOP_K_MATCHES = 200
```

페르소나 비율:

```python
PERSONA_DISTRIBUTION = {
    "stable": 0.30,
    "gradual_deterioration": 0.20,
    "event_shock": 0.20,
    "recovery": 0.15,
    "overspending": 0.15,
}
```

## 2. 초기 분포

### 월소득
- 2,000,000~12,000,000원
- 중앙값 목표 약 4,500,000원
- 로그정규 또는 절단정규 권장

### 초기 잔액
- 1,000,000~100,000,000원
- 소득의 1~12배 중심

### 초기 대출
- 20~30% 무대출
- 보유자는 소득의 3~36배

### 지출
- 고정지출: 소득의 20~45%
- 변동지출: 소득의 15~40%
- 상환액: 소득의 0~35%
- 초기 총지출은 원칙적으로 소득의 130% 이하

## 3. 페르소나 규칙

### stable
- 소득 연 1~5% 증가
- 고정비 연 0~3% 증가
- 변동비 변화 -1~3%
- 저축률 15~30%
- 대출 점진 감소
- 연체 가능성은 매우 낮지만 0은 아님

### gradual_deterioration
- 소득 정체
- 변동지출 월 0.3~1.0% 상승
- 저축률 하락
- 후반 잔액 감소
- 스트레스 진입 주로 16~30월

### event_shock
- 이벤트 주로 13~28월
- 일부는 8~12월에 발생 가능
- 실직: 소득 70~100% 감소, 2~6개월
- 출산: 2~8백만원 일시비용 + 고정비 상승
- 의료비: 3~20백만원
- 금리 충격: 상환액 10~30% 증가
- 주거비 상승: 월 20~80만원 증가

### recovery
- 8~20월 스트레스
- 3~8개월 후 소득 회복 또는 지출 10~25% 절감
- 마지막 3개월 정상화 가능

### overspending
- 소득 안정
- 변동지출 빠른 증가
- 대형 지출 증가
- 저축률 하락
- 신규대출 가능
- stress 비중을 delinquent보다 높게 설계

## 4. 월별 상태

우선순위: delinquent → stress → watch → healthy

### delinquent
- delinquency_flag == 1
- 또는 2개월 연속 잔액 < -2,000,000원과 상환 미이행 이벤트

### stress
delinquent가 아니면서 하나 이상:
- cash_balance < 0
- 최근 3개월 savings_amount 모두 음수
- dsr >= 0.45
- emergency_months < 1
- fixed_expense_ratio >= 0.55
- 최근 3개월 잔액 감소율 합계 <= -0.30

### watch
상위 상태가 아니면서 하나 이상:
- savings_rate < 0.05
- dsr >= 0.35
- emergency_months < 3
- 잔액 3개월 연속 감소
- fixed_expense_ratio >= 0.45
- 최근 6개월 음수 저축 2개월 이상

### healthy
그 외.

## 5. 최종 결과

13~36개월만 사용.

### delinquent
미래에 delinquent 월이 1개 이상.

### recovered
- stress 월 2개 이상
- 마지막 3개월 모두 healthy
- 마지막 3개월 평균 저축률 >= 0.05
- 마지막 잔액 >= 0

### stress
delinquent/recovered가 아니면서 하나 이상:
- stress 월 6개 이상
- 마지막 3개월 중 2개 이상 stress 또는 watch
- 마지막 잔액 < 0
- 마지막 3개월 평균 DSR >= 0.45

### healthy
그 외.

## 6. 결과 분포 목표

| 결과 | 목표 |
|---|---:|
| healthy | 45~60% |
| recovered | 8~18% |
| stress | 20~35% |
| delinquent | 5~15% |

범위를 벗어나면 라벨을 직접 덮어쓰지 말고 생성 파라미터를 조정한다.

## 7. 매칭 특징과 가중치

```python
MATCH_WEIGHTS = {
    "avg_savings_rate_3m": 1.4,
    "avg_dsr_3m": 1.4,
    "avg_fixed_expense_ratio_3m": 1.2,
    "savings_rate_slope_12m": 1.4,
    "expense_growth_12m": 1.1,
    "dsr_change_12m": 1.2,
    "balance_change_ratio_12m": 1.3,
    "income_cv_12m": 0.8,
    "expense_cv_12m": 0.8,
    "max_consecutive_balance_decline_12m": 1.0,
}
```

처리:
1. StandardScaler
2. 표준화 값에 sqrt(weight) 곱하기
3. 유클리드 거리
4. 자기 자신 제외
5. 상위 200명

## 8. 위험군/회피군

- 위험군: stress, delinquent
- 회피군: healthy, recovered
- 각 그룹 20명 미만이면 분기점 분석 불가

## 9. 분기점

비교 지표:
- savings_rate
- fixed_expense_ratio
- variable_expense_ratio
- dsr
- cash_balance_ratio
- loan_balance_ratio

SMD:

```text
(risk_mean - avoidance_mean) / pooled_std
```

조건:
- |SMD| >= 0.5
- 같은 지표 2개월 연속
- 각 그룹 유효 데이터 20명 이상
- 가장 이른 월
- 같은 월이면 |SMD| 최대 지표

현재와의 거리:

```text
breakpoint_month - 12
```

표현:
- “주요 차이 요인”
- “가장 먼저 크게 갈라진 변수”

인과 표현 금지.

## 10. What-if

시작값:
- 10~12월 평균 income
- 10~12월 평균 fixed_expense
- 10~12월 평균 variable_expense
- 10~12월 평균 debt_payment
- 12월 cash_balance

기본 월 추세:
- 소득 0%
- 고정비 +0.15%
- 변동비 +0.20%
- 상환액 0%

시나리오:
- baseline
- variable_expense_cut_15
- fixed_expense_cut_300k
- debt_payment_cut_20

출력:
- ending_cash_balance
- minimum_cash_balance
- average_savings_rate
- cash_depletion_month
- improvement_vs_baseline
- months_with_negative_savings

What-if 결과로 위험 비율을 임의 변경하지 않는다.

## 11. 데모 고객

메인 고객 우선 조건:
- 12월 healthy 또는 watch
- 최근 저축률 하락
- 최근 평균 DSR 0.30~0.44
- 고정비 비중 0.38~0.49
- 유사 위험군 25~40%
- 분기점 13~16월
- 대응안 개선 효과 명확

추가:
- 안정 비교 고객 1명
- 고위험 고객 1명

## 12. 문장 규칙

필수:
- 유사 고객 수
- 주요 결과 비율
- 분기점
- 남은 개월
- 대응안 개선 효과
- 합성 데이터 고지

금지:
- 확정 예측
- 공포 조장
- 상품 판매
- 공식 신용평가 표현

## P0 prospective, triage, and workflow boundaries

The legacy generator, feature window, matcher, outcome aggregation,
breakpoint, and What-if rules above remain unchanged. The P0 additions use
these additional operational boundaries:

- **Prospective/as-of inputs:** target financial observations at or before the
  `as_of_month` only. Target months 13-36, `final_outcome`, persona, and
  evaluator labels are forbidden in feature construction, scaler fitting,
  matching, signal snapshots, policy input, and triage selection.
- **Reference-only matching:** scaler fitting and neighbor search references
  use the reference population only. An evaluation target cannot be in its
  reference set.
- **Historical cohort evidence:** matched-cohort outcome shares are historical
  shares, never prediction probabilities. A historical breakpoint is a
  retrospective landmark for similar paths, never a live alert date for the
  target customer.
- **Prospective timing:** lead-time evidence is calculated only after an
  independently defined synthetic future event is opened in the evaluator. An
  event-after alert is not counted as successful lead time.
- **What-if:** remains a rule-based cashflow simulation. It is supporting
  review evidence only and does not estimate intervention efficacy or adjust
  policy/Alert risk.
- **Demo policy:** the default policy is versioned `demo` status, not
  `approved`. Its output is eligibility/operational label/why-now evidence;
  it does not select the RM queue or create an Alert.
- **Triage:** all 5,000 customers receive exactly one primary disposition.
  Ranking is deterministic and uses only declared current/past evidence.
  Selection or representative demo cohorts must not use target future values,
  persona, or manual cherry-picking.
- **Alert creation:** only `SELECTED_FOR_REVIEW` or
  `ROUTE_EXISTING_CASE` decisions enter the Alert cycle. Deferred, monitor,
  no-actionable-signal, and insufficient-evidence decisions do not create a
  new Alert.
- **RM actions:** Recommended Follow-up supports human review. It must not
  approve/decline/restructure/sell a financial product automatically.

## Post-P0 evidence and public-repository boundaries

- **Capacity:** `unbounded_demo` is a synthetic reference, not a daily,
  optimal, recommended, or approved RM workload. A capacity scenario only
  selects a saved rank prefix and must remain human-supplied and `draft` until
  an external approval reference exists.
- **Real data:** No actual or anonymized customer data may be collected,
  downloaded, copied, transformed, stored, or processed in this public
  repository. Governance, adapter, and metric contracts are readiness-only;
  actual validation remains `not_ready` / unvalidated until the approved secure
  environment and external approvals exist.
- **Pilot evidence:** Synthetic pilot dry-run counts and durations are workflow
  instrumentation, not RM productivity, SLA, customer-outcome, or
  intervention-effect evidence. A pilot protocol does not initiate a pilot.
- **Claims:** Product functionality and video/slide production are separate.
  An available RM screen does not mean a recording, actual RM adoption, or
  real-bank deployment has occurred.
- **Security and delivery:** Preview/Null notification remains not-sent and
  offline. No provider credential, endpoint, webhook, direct identifier, raw
  feedback, or row-level real-data artifact belongs in source, tests, logs,
  artifacts, or reports.

## Guided RM workflow boundaries

- **Guidance only:** The five Guided steps explain an already-prepared RM
  context. They are not a policy, scoring, ranking, selection, capacity
  approval, Alert-creation, or financial-decision engine.
- **Capacity:** A human enters a comparison value and acknowledges that exact
  value. The saved Queue IDs and ranking digest remain unchanged; a new value
  invalidates the acknowledgement rather than changing the Queue.
- **Queue to review:** Only a visible `selected/routed` operational Queue row
  may establish an operational Customer Review context. Representative,
  Monitor, No actionable signal, Insufficient evidence, and deferred records
  never become an operational Guided completion by matching customer ID alone.
- **No Case is normal:** `NO_OPEN_ALERT`, `SELECTED_CASE_PENDING`, and
  `selected · Case not created` are safe, honest states. Guided UI must block
  the RM Action step and must not create a Case to remove that block.
- **Action/Audit:** An existing Case uses the Banker application boundary and
  append-only audit only. Preview remains `PREVIEW`, not sent, and offline.
- **Demo:** Synthetic Workflow Demo is optional practice, capped at three
  synthetic Cases, and retains normal RM/Guided session state on exit.
