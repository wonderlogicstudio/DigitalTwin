# TEST_PLAN.md — 테스트 계획

## 1. 목표

- 합성 데이터의 재무적 일관성
- 관측/미래 구간 분리
- 매칭 재현성
- 결과 집계 정확성
- 분기점 규칙
- What-if 회계식
- 전체 데모 흐름

## 2. 데이터 생성 테스트

### TC-DG-001 고객 수
- 기대: master 5,000행

### TC-DG-002 월별 행
- 기대: 180,000행

### TC-DG-003 고객별 기간
- 모든 고객 36행

### TC-DG-004 중복
- customer_id + month 중복 0

### TC-DG-005 재현성
- 같은 시드 두 번 생성 결과 동일

### TC-DG-006 다른 시드
- 시드 42와 43 결과가 동일하지 않음

### TC-DG-007 페르소나 비율
- 설정 대비 ±1.5%p 이내 권장

## 3. 회계식 테스트

### TC-AC-001 총지출

```text
total_expense
= fixed_expense + variable_expense + debt_payment + event_expense
```

허용 오차 1원.

### TC-AC-002 저축

```text
savings_amount = income - total_expense
```

### TC-AC-003 잔액 연속성

```text
cash_balance_t
= cash_balance_(t-1) + savings_amount_t
```

### TC-AC-004 대출
- loan_balance >= 0

### TC-AC-005 결측
- 필수 숫자 컬럼 NaN/inf 0건

## 4. 상태 판정 테스트

### TC-ST-001 healthy
- 저축률 20%, DSR 20%, 비상자금 6개월

### TC-ST-002 watch
- DSR 37%

### TC-ST-003 stress
- 현금잔액 음수

### TC-ST-004 delinquent 우선
- delinquency_flag=1이면 다른 값과 무관하게 delinquent

### TC-ST-005 소득 0
- savings_rate=-1
- dsr=1
- inf 없음

## 5. 최종 결과 테스트

### TC-FO-001 delinquent
- 미래 delinquent 1개월 이상

### TC-FO-002 recovered
- 미래 stress 2개월 이상
- 마지막 3개월 healthy
- 평균 저축률 5% 이상

### TC-FO-003 stress
- stress 6개월 이상

### TC-FO-004 healthy
- 다른 조건 미충족

## 6. 특징 테스트

### TC-FE-001 고객당 1행
- 5,000명 → 5,000행

### TC-FE-002 미래 누수
- 13~36월 값을 극단적으로 바꿔도 특징 불변

### TC-FE-003 기울기
- 증가 수열 slope > 0

### TC-FE-004 연속 감소
- 알려진 5개월 감소 → 5

### TC-FE-005 CV
- 상수 수열 → 0

## 7. 매칭 테스트

### TC-MA-001 자기 제외
### TC-MA-002 정확히 200명
### TC-MA-003 거리 오름차순
### TC-MA-004 유사도 0~1
### TC-MA-005 동일 입력 동일 순위
### TC-MA-006 final_outcome 변경 영향 없음
### TC-MA-007 인공 데이터 최근접 rank 1

## 8. 결과 집계 테스트

### TC-OU-001 인원 합계 = matched_count
### TC-OU-002 비율 합계 약 1.0
### TC-OU-003 12월 데이터 미포함
### TC-OU-004 최초 stress 월 정확
### TC-OU-005 연체 없음 → median null

## 9. 분기점 테스트

### TC-BP-001 명확한 분기
- 14~16월 fixed_expense_ratio 차이
- 기대 month=14

### TC-BP-002 한 달 차이
- 지속 조건 미충족 → 분기점 아님

### TC-BP-003 그룹 19명
- insufficient_group_size

### TC-BP-004 |SMD| < 0.5
- not_found

### TC-BP-005 동월 다중 지표
- |SMD| 최대 지표 선택

### TC-BP-006 pooled std 0
- 예외 없이 제외

## 10. What-if 테스트

### TC-WH-001 baseline 수작업 일치
### TC-WH-002 지출 절감 후 잔액이 baseline 이상
### TC-WH-003 고정비 하한 0
### TC-WH-004 최초 음수 월 기록
### TC-WH-005 개선액 계산
### TC-WH-006 음수 저축 월 수

## 11. 통합 테스트

### TC-IT-001 전체 파이프라인

```text
generate
→ validate
→ features
→ matcher
→ outcome
→ breakpoint
→ what-if
```

기대:
- 예외 없음
- JSON 직렬화 가능
- 필수 키 존재

### TC-IT-002 데모 고객
- matched_count=200
- 결과 비율 합 1
- breakpoint found
- 시나리오 4개

## 12. UI 수동 체크

- 최초 실행 오류 없음
- 데이터 없음 안내
- 메인 고객 기본 선택
- 고객 변경 시 차트 갱신
- 로딩 표시
- 축 단위
- 현재 월 세로선
- 미래 구간 배경 구분
- 분기점 표시
- 결과 수/비율 일치
- 1366×768 발표 가능
- AI 미연결 동작
- 3분 데모 가능

## P0 regression extensions

The active suite additionally locks these contracts:

- population result serialization/single-customer parity, deterministic exact
  batch input, duplicate rejection, failure isolation, atomic export, and
  5,000-ID reconciliation;
- validation-only negative-control reproducibility and canonical-input
  integrity; isolated multi-seed/TOP_K sensitivity with production K unchanged;
- month-12 as-of parity, future-mutation invariance, reference-only scaler
  fitting, target exclusion, deterministic folds, scorer/evaluator separation,
  and customer-month reconciliation;
- prospective timing edge cases, policy version/status/why-now fields, and no
  historical-landmark live-trigger behavior;
- complete triage universe, deterministic transparent capacity ranking,
  selection manifest reconciliation, no future-label/persona selection, and
  representative-cohort non-cherry-picking rules;
- Alert state machine/repository/dedupe/cooldown/snooze, selected-to-Alert
  idempotency, Banker-service guards, append-only audit consistency, and
  Preview/Null notification no-network behavior;
- General/Presentation/RM mode isolation, Presentation five-tab preservation,
  RM four-tab portfolio/queue/customer-review/audit contracts, KR/EN AppTest,
  and bounded Streamlit health checks.

Focused test modules include `test_population_*.py`,
`test_circularity_validation.py`, `test_sensitivity_validation.py`,
`test_as_of_features.py`, `test_reference_matcher.py`,
`test_prospective_signals.py`, `test_crossfit_backtest.py`,
`test_demo_policy.py`, `test_triage_*.py`, `test_alert_*.py`,
`test_banker_*.py`, `test_notifications.py`, and `test_rm_*.py`.

## Post-P0 feedback-readiness regression extensions

The suite additionally verifies that:

- capacity comparison reads the persisted rank only, is deterministic and
  monotonic, and cannot automatically approve a workload;
- customer-facing `Why Now` remains prospective and separate from a historical
  landmark, without prediction-probability or future-date wording;
- selected-only workflow, banker action, append-only audit, and offline
  Preview/Null remain idempotent and do not depend on external delivery;
- governance, validation-adapter, and synthetic-vs-real metric contracts admit
  only injected synthetic fixtures in tests and keep actual-data status
  unvalidated;
- synthetic pilot protocol and dry run preserve canonical checksums, isolate
  output, record no actual RM/customer evidence, and retain capacity/policy
  approval as human decisions; and
- source-of-truth docs retain synthetic-only, no-secret, no-network, no-DB,
  no-automatic-financial-decision claims.

Relevant modules include `test_capacity_scenarios.py`,
`test_real_data_governance.py`, `test_validation_dataset_harness.py`,
`test_validation_metrics_report.py`, `test_rm_pilot_protocol.py`,
`test_synthetic_rm_pilot_dry_run.py`, and `test_documentation_sync.py`.

## Guided RM final regression gate

The Guided RM suite additionally verifies the five-step state matrix, current
step/completion/next-action/block copy, KR/EN AppTest access, and preservation
of three app modes, five Presentation tabs, and four RM tabs. It locks:

- human-entered capacity acknowledgement against the exact value while Queue
  IDs, saved rank digest, and Alert creation remain unchanged;
- selected/routed-only Queue eligibility, safe Queue-to-Customer Review
  handoff, excluded-disposition rejection, and representative comparison
  blocking;
- evidence acknowledgement before RM Action, honest no-Case/service/audit
  blocks, Banker-only actions, append-only audit, and offline Preview;
- Synthetic Workflow Demo entry/action/reset/exit isolation, three-Case cap,
  default-root digest preservation, and Guided state restoration; and
- documentation/manual generator wording for the display-only Guide and the
  manual Edge capture checklist. Pixel-perfect viewport sign-off remains a
  human Edge result (`PASS` / `FAIL` / `NOT_RUN`), never an AppTest claim.

## 13. 완료 기준

```bash
pytest -q
```

- 실패 0
- 핵심 모듈 커버리지 80% 권장
