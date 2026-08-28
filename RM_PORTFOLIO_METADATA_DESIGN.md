# Synthetic RM Portfolio 및 고객관계 메타데이터 설계

## 1. 목적과 이번 단계의 범위

이 문서는 5,000명 Financial Path Twin 분석 universe와 한 RM의 업무 범위를
분리하기 위한 **synthetic CRM overlay** 계약을 고정한다. Overlay는 금융 데이터가
아닌 PoC용 업무 메타데이터다.

STEP 05에서 이 계약의 Portfolio metadata generator와 standalone JSON/CSV artifact
writer를 구현한다. Snapshot 생성, Daily 화면, DB 또는 외부 연동은 이 범위에
포함하지 않는다.

## 2. 고정 원칙

- 5,000명 synthetic financial universe는 그대로 유지한다.
- RM Portfolio는 5,000명 중 Daily Review가 조회할 별도 업무 범위다.
- Portfolio를 만들기 위해 customer_master, customer_monthly 또는 기존
  processed/demo CSV/JSON을 수정하지 않는다.
- Portfolio 고객의 유사고객 Matching reference universe는 계속 5,000명 전체다.
- Portfolio 및 관계 중요도는 customer_id와 고정 seed만 사용해 deterministic하게
  만든다.
- 금융 outcome, breakpoint, persona, final_outcome, What-if, cash_balance,
  income, loan_balance 및 다른 Financial Twin 분석값을 Portfolio 선택이나
  관계 중요도 생성에 사용하지 않는다.

관계 중요도는 실제 AUM, 자산가 여부, VIP 등급 또는 실제 CRM 등급이 아니다.
항상 “PoC용 synthetic CRM relationship metadata”라고 표시한다.

## 3. 별도 overlay artifact

구현된 builder는 기존 금융 CSV와 별개인 아래 artifact를 생성한다.

~~~text
artifacts/rm_daily_review/portfolio/rm_portfolio.json
artifacts/rm_daily_review/portfolio/rm_portfolio.csv
~~~

이는 새로운 derived/demo artifact이며, 기존 CSV/JSON 스키마나 저장 값 의미를
변경하지 않는다. CSV는 Daily Review가 join할 업무 메타데이터이고, JSON은
생성 규칙·provenance·고지와 같은 고객 행을 함께 보관한다.

### 3.1 CSV 스키마

| 필드 | 형식 | 의미 |
| --- | --- | --- |
| customer_id | string | 기존 5,000명 universe에 존재하는 고객 식별자 |
| rm_portfolio_id | string | 담당 범위를 나타내는 synthetic Portfolio 식별자 |
| relationship_priority | enum | CORE, PRIORITY, STANDARD 중 하나 |
| relationship_label | string | 화면용 합성 CRM 레이블 |

기본 레이블은 아래와 같다.

| relationship_priority | relationship_label | 의미 |
| --- | --- | --- |
| CORE | 핵심관리 | PoC용 합성 CRM 메타데이터상 핵심관리 |
| PRIORITY | 우선관리 | PoC용 합성 CRM 메타데이터상 우선관리 |
| STANDARD | 일반관리 | PoC용 합성 CRM 메타데이터상 일반관리 |

CSV에는 위험 점수, 예측 확률, AUM 추정치, 자산가 여부, 금융 outcome, breakpoint,
persona 또는 최종 결과 필드를 넣지 않는다.

### 3.2 JSON envelope/manifest 계약

JSON envelope은 다음 provenance와 CSV와 동일한 고객 행을 기록한다.

| 필드 | 기본값 | 의미 |
| --- | --- | --- |
| metadata_version | 1 | overlay 계약 버전 |
| source | synthetic_crm_overlay | 실제 CRM 데이터가 아님을 나타냄 |
| universe_customer_count | 5000 | Matching universe 크기 |
| rm_portfolio_id | RM-POC-001 | PoC Portfolio 식별자 |
| portfolio_size | 300 | 업무 범위 예시 크기 |
| portfolio_selection_seed | 20260828 | Portfolio 고객 ID 선택 seed |
| relationship_assignment_seed | 42 | 관계 중요도 배정 seed |
| relationship_distribution | CORE 10%, PRIORITY 25%, STANDARD 65% | 합성 CRM 비율 |

JSON envelope과 Daily UI는 “실제 CRM/AUM 데이터가 아닌 PoC용 synthetic
metadata”라는 고지 문구를 표시한다. CSV는 3.1의 네 업무 메타데이터 필드만
유지한다.

## 4. Deterministic RM Portfolio 생성 계약

기본 PoC Portfolio는 RM-POC-001이며 크기는 300명이다. 크기 300은 분석
파라미터나 Daily 업무량 목표가 아니라 화면과 업무 범위의 예시다.

src/rm_portfolio.py의 generator는 다음 절차를 정확히 따른다.

1. existing 5,000명 universe에서 customer_id만 읽어 오름차순으로 정렬한다.
2. portfolio_selection_seed 20260828의 independent random generator로 300명을
   비복원 선택한다.
3. 선택된 customer_id를 정렬해 artifact를 안정적인 순서로 저장한다.
4. 선택 결과의 고객 ID 목록과 seed를 manifest에 기록한다.

이 절차에서는 customer_id 외의 고객 속성을 읽지 않는다. 특히 결과를 본 뒤
Portfolio를 교체하거나, 원하는 오늘 업무 건수를 맞추기 위해 선택을 다시
실행하지 않는다.

STEP 02에서 timing 분포를 측정한 300명은 동일한 seed와 고객 ID 정렬 규칙을
사용한다. 따라서 후속 구현은 같은 기준의 Portfolio를 재현해야 한다.

## 5. Deterministic 관계 중요도 배정 계약

관계 중요도는 Portfolio 300명에게만 부여하는 independent synthetic CRM
metadata다. Portfolio 고객의 금융 데이터나 분석 결과를 참조하지 않는다.

구현된 generator는 정렬된 300 customer_id에 대해
relationship_assignment_seed 42의 independent random generator로 순열을 만들고
아래의 고정된 수량을 배정한다.

| 우선도 | 비율 | 300명 기준 수량 |
| --- | ---: | ---: |
| CORE | 10% | 30 |
| PRIORITY | 25% | 75 |
| STANDARD | 65% | 195 |

순열의 앞 30명은 CORE, 다음 75명은 PRIORITY, 나머지 195명은 STANDARD로
배정한 뒤 customer_id 순서로 저장한다. 이 방법은 비율과 결과를 재현 가능하게
하지만, 해당 고객의 재무상태나 실제 관계 가치를 의미하지 않는다.

## 6. Daily Review에서의 사용 규칙

Relationship Priority와 분석 timing은 서로 다른 축이다.

| 허용 | 금지 |
| --- | --- |
| 관계 중요도 badge와 별도 filter 표시 | 관계 중요도로 REVIEW_NOW, UPCOMING, MONITOR timing bucket 변경 |
| 같은 timing bucket 안에서 CORE, PRIORITY, STANDARD 순의 보조 정렬 | timing과 관계 중요도를 더한 숨은 점수 또는 단일 순위 생성 |
| “곧 확인 예정” 고객 가운데 CORE 또는 PRIORITY만 보는 filter | 관계 중요도를 Digital Twin 위험도나 미래 예측으로 표현 |
| “PoC용 synthetic CRM metadata” 고지 표시 | 관계 중요도 생성에 cash_balance, income, loan_balance 사용 |

보조 정렬은 이미 결정된 timing bucket 안에서만 적용한다. 관계 중요도가 높다고
timing evidence가 없는 고객을 오늘 업무로 이동시키지 않으며, 낮다고 오늘
업무에서 제외하지 않는다.

## 7. Snapshot 및 분석 경계

분석은 월별 Financial Path Twin 계산 후 고객별 월별 분석 Snapshot을 생성한다.
Daily Review는 Snapshot과 별도 Portfolio overlay를 customer_id로 읽어 결합한다.

~~~text
5,000명 Financial Path Twin 분석
→ 고객별 월별 분석 Snapshot
                         ↑
300명 synthetic RM Portfolio metadata overlay
                         ↓
Daily Review: Portfolio 범위의 Snapshot만 읽음
~~~

Overlay를 결합해도 Daily Review는 Matching, Outcome, Breakpoint, What-if를
재실행하지 않는다. 관계 중요도도 timing bucket 계산에 입력되지 않는다.

## 8. 실제 CRM/AUM 데이터로의 교체 경계

후속 구현은 metadata provider interface를 둬 synthetic overlay와 향후 실제 CRM
source를 교체 가능하게 한다. provider의 출력 계약은 3.1의 네 필드로 제한한다.

- synthetic provider: 이 문서의 seed·비율·고지 규칙을 사용한다.
- future CRM provider: 승인된 실제 CRM source를 해당 네 필드로 매핑한다.
- Financial Path Twin generator, feature, matcher, outcome, breakpoint, What-if
  모듈은 두 provider 어느 쪽에도 의존하지 않는다.

실제 CRM/AUM source의 연결은 별도 권한과 요구사항이 필요한 후속 작업이며,
이번 PoC에 포함하지 않는다.

## 9. 구현 시 검증 조건

후속 generator와 loader는 다음을 검증해야 한다.

- 정확히 300개의 고유 customer_id가 있고 모두 5,000명 universe에 존재한다.
- 모든 행의 rm_portfolio_id가 RM-POC-001이다.
- relationship_priority와 relationship_label 조합이 허용된 세 값 중 하나다.
- CORE 30명, PRIORITY 75명, STANDARD 195명이다.
- 같은 input customer_id 목록과 두 seed에서 동일 artifact가 생성된다.
- 생성 코드가 persona, final_outcome, outcome, breakpoint, What-if 또는 금융
  금액·비율 컬럼에 접근하지 않는다.
- Daily loader가 Snapshot에 없는 Portfolio 고객을 분석하거나 추정하지 않고
  evidence 없음으로 처리한다.

이 검증은 기존 Financial Path Twin 테스트를 삭제·완화하지 않고 새 overlay
전용 테스트로 추가한다.

## 10. 이번 단계의 완료 기준

- Portfolio 300명과 5,000명 Matching universe의 분리가 문서화되어 있다.
- 관계 중요도가 합성 CRM 메타데이터임이 명확하다.
- 금융 데이터와 분석 결과에서 독립된 deterministic 생성 규칙이 고정되어 있다.
- timing과 관계 중요도의 비합산 원칙 및 화면 사용 범위가 고정되어 있다.
- Portfolio generator와 standalone artifact writer는 구현되어 있으며, Daily UI와
  Snapshot 결합은 아직 구현하지 않았다.
