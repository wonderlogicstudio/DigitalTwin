# RM Daily Review timing bucket 정책

## 1. 목적과 범위

이 문서는 저장된 월별 분석 Snapshot을 Daily Review로 전달할 때의 세 timing
bucket을 고정한다.

| 내부 이름 | 화면 이름 | 의미 |
| --- | --- | --- |
| REVIEW_NOW | 오늘 먼저 확인 | 분기 timing이 가깝고 현재 관측 근거도 있어 지금 확인할 가치가 높은 고객 |
| UPCOMING | 곧 확인 예정 | 분기 timing은 확인되지만 오늘 우선 검토보다 여유가 있는 고객 |
| MONITOR | 모니터링 | 현재 Daily 업무로 올릴 timing evidence가 부족하거나 먼 고객 |

이 정책은 새 risk score, prediction probability, composite score 또는 예측
모델이 아니다. Daily Review는 기존 월별 분석이 저장한 결과만 읽는다.

“오늘 먼저 확인”은 가장 위험한 고객, 미래 사건 발생일, 연락 기한 또는 자동
조치 지시를 뜻하지 않는다.

## 2. 읽기 전용 입력 계약

각 Portfolio 고객에 대해 Daily Review는 같은 월별 Snapshot에서 다음 기존
값만 읽는다.

| 입력 | 용도 |
| --- | --- |
| 분석 오류 또는 evidence 상태 | Snapshot이 업무 판단에 사용 가능한지 확인 |
| current summary의 12개월차 monthly_status | 현재 관측된 흐름이 healthy인지 아닌지 확인 |
| breakpoint status | found, not_found, insufficient_group_size 구분 |
| breakpoint month, months_from_current, primary factor | timing 및 “왜 오늘?” 설명 |
| RM Portfolio membership | Daily 업무 범위 제한 |
| relationship_priority | bucket 내부 badge, filter, 보조 정렬 |

current monthly_status는 기존 Financial Path Twin이 관측 구간에서 이미 저장한
상태다. 이 정책은 그 값을 다시 계산하거나 새 위험도로 변환하지 않는다.

Daily 경로는 Matching, Outcome, Breakpoint, What-if를 재실행하지 않는다.
persona, final_outcome, matched outcome 비율, What-if 개선값은 bucket 판정에
사용하지 않는다.

## 3. Timing window와 bucket 규칙

판정은 아래 순서로 한 번만 적용한다. 하나의 고객은 정확히 하나의 bucket에
속한다.

### 3.1 Evidence guard

아래 중 하나면 MONITOR다.

- Snapshot에 분석 오류가 있거나 필수 timing 값이 없다.
- breakpoint status가 not_found 또는 insufficient_group_size다.
- breakpoint status가 found이지만 months_from_current가 1~24 범위 밖이다.
- breakpoint status가 found이고 months_from_current가 5 이상이다.

not_found와 insufficient_group_size는 고객이 안전하거나 검토 불필요하다는
판정이 아니다. 해당 Snapshot에는 Daily timing evidence가 충분하지 않다는
뜻으로만 MONITOR에 표시한다.

### 3.2 REVIEW_NOW — 오늘 먼저 확인

아래 조건을 모두 만족하면 REVIEW_NOW다.

1. breakpoint status가 found다.
2. months_from_current가 1 또는 2다.
3. 저장된 12개월차 monthly_status가 watch, stress, delinquent 중 하나다.

이 규칙은 가까운 historical separation timing과 현재 관측된 확인 필요성을 함께
보는 업무 규칙이다. current monthly_status를 점수화·가중합·확률화하지 않는다.

### 3.3 UPCOMING — 곧 확인 예정

분석 오류가 없고 breakpoint status가 found인 고객 중 REVIEW_NOW가 아닌 다음
고객은 UPCOMING이다.

- months_from_current가 1 또는 2이고 12개월차 monthly_status가 healthy다.
- months_from_current가 3 또는 4다.

Breakpoint는 역사적으로 유사 고객 경로가 갈라진 월이지 미래 사건 일정이
아니다. 따라서 +1~2개월 healthy 고객을 오늘 업무에서 제외하는 것은 “안전” 또는
“연락하지 말라”는 뜻이 아니다. 현재 관측 근거가 없는 고객을 곧 확인 예정으로
분리해 RM이 맥락을 확인할 수 있게 하는 운영상 구분이다.

### 3.4 MONITOR — 모니터링

Evidence guard에 해당하는 고객과 found이면서 months_from_current가 5 이상인
고객은 MONITOR다. MONITOR에는 “timing evidence 부족” 또는 “현재 업무 시점이
더 먼 근거”를 함께 표시한다.

현재 Financial Path Twin 계약에서는 breakpoint_month가 13~36이므로 정상
Snapshot의 months_from_current는 1~24다. 0 또는 음수는 정상 결과로
해석하지 않고 evidence 상태를 확인하는 MONITOR 경로로 보낸다.

## 4. STEP 02 분포에 근거한 정책 검토

STEP 02는 기존 seed 42의 5,000명 universe와 결과와 무관하게 seed 20260828로
선택한 300명 Portfolio에서 기존 matcher와 breakpoint를 호출해 분포를 측정했다.
found는 거의 모두 months_from_current 1에 집중됐다.

| 정책 dry-run | 전체 5,000명 | RM Portfolio 300명 |
| --- | ---: | ---: |
| REVIEW_NOW: found +1~2 및 현재 non-healthy | 303 | 19 |
| UPCOMING: found +1~2 healthy 또는 +3~4 | 1,429 | 88 |
| MONITOR: evidence 부족 또는 +5 이상 | 3,268 | 193 |

이 수치는 목표 업무량이 아니다. 특히 “오늘 19명”을 만들기 위해 threshold를
조정한 것이 아니다. found +1~2만으로 분류했을 때 Portfolio 107명이 오늘
업무가 되어, “가까운 historical timing”만으로는 오늘 확인의 업무 의미가 너무
넓다는 측정 결과에 따른 것이다.

REVIEW_NOW가 가까운 timing과 저장된 현재 관측 상태를 함께 요구하므로, 금융
outcome에 맞춘 cutoff나 새 위험 점수 없이도 “왜 오늘?”을 설명할 수 있다.
새 월별 Snapshot에서는 실제 저장된 값에 따라 이 수치가 달라질 수 있다.

## 5. Relationship Priority의 위치

Relationship Priority는 synthetic CRM overlay의 별도 축이다. timing bucket이
항상 1차이며, 관계 중요도는 이미 결정된 bucket 내부에서만 사용한다.

| 허용 | 금지 |
| --- | --- |
| 같은 bucket에서 CORE, PRIORITY, STANDARD 순의 보조 정렬 | REVIEW_NOW, UPCOMING, MONITOR 간 이동 |
| UPCOMING 가운데 CORE 또는 PRIORITY badge/filter | timing과 관계 중요도를 합산한 점수 |
| 관계 중요도 미설정 시 customer_id 순 정렬 | UPCOMING CORE가 REVIEW_NOW STANDARD보다 먼저 보이도록 bucket 순서 변경 |

보조 정렬의 동률은 customer_id 오름차순으로 결정한다. CORE, PRIORITY,
STANDARD는 CRM 레이블 순서일 뿐 숫자 점수나 Digital Twin 위험도는 아니다.

## 6. 화면 업무량과 노출 원칙

기본 PoC Portfolio의 REVIEW_NOW dry-run은 19명이므로, 이 정책은 현재 화면
상단 표시 개수를 제한하지 않는다. 오늘 전체 대상은 한 목록으로 모두 접근
가능해야 하며, Capacity 입력이나 숨겨진 Queue를 만들지 않는다.

향후 실제 Snapshot 분포에서 상단 강조 목록이 필요해지면 다음 원칙을 따른다.

- 전체 REVIEW_NOW 수와 전체 목록 접근 경로를 항상 표시한다.
- 상단 강조 개수는 분석 threshold나 위험 기준이 아닌 UI workload display
  limit임을 명시한다.
- 강조 목록 밖 REVIEW_NOW 고객을 제거·은닉·MONITOR 이동하지 않는다.
- 표시 순서는 이 문서의 bucket 순서와 bucket 내부 보조 정렬만 사용한다.

## 7. Snapshot 시간 규칙

분석은 월 단위이고 Daily 전달은 일 단위다. 같은 월별 Snapshot을 다음 날 다시
읽어도 months_from_current 또는 bucket은 하루 단위로 자동 변경하지 않는다.

새 월별 Snapshot이 생성될 때에만 기존 Financial Path Twin 분석 결과와 current
summary가 갱신되고, 이 정책은 새로 저장된 값에 대해 다시 적용된다. Daily
Review 자체는 분석을 수행하지 않는다.

## 8. 제외 범위

이 정책은 다음을 도입하지 않는다.

- 자동 고객 연락, 외부 발송, DB 또는 실제 데이터 연결
- Case, mandatory Case, Guided Stepper, Capacity 입력, 복잡한 Queue
- 상품 추천이나 대출·투자 권고
- 분석 결과 또는 관계 중요도의 수정

고객 상세는 “왜 오늘?”과 대화 준비를 지원할 수 있으나, RM이 결과를 기록하고
완료하는 단순 Daily 흐름 밖의 자동 조치를 만들지 않는다.

## 9. 구현 수용 기준

후속 application layer는 아래를 모두 만족해야 한다.

- Portfolio overlay와 동일 Snapshot의 customer_id만 결합한다.
- 각 고객을 이 정책의 세 bucket 중 하나에 결정적으로 분류한다.
- 오류·not_found·insufficient_group_size를 MONITOR로 안전하게 표시한다.
- relationship_priority가 timing bucket을 바꾸지 못하게 한다.
- 같은 Snapshot을 며칠 읽어도 bucket이 변하지 않게 한다.
- bucket 판정 중 기존 분석 함수를 호출하지 않게 한다.
