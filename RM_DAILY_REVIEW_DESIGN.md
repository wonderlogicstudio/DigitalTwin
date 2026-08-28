# RM Daily Review 설계 계약

## 1. 목적과 적용 범위

이 문서는 Financial Path Twin의 **월별 분석(Monthly Analysis)** 결과를 RM의
일상 검토 업무로 안전하게 전달하기 위한 경계와 용어를 고정한다. 이 단계에서
실행 코드, 기존 데이터, CSV/JSON 스키마, 분석 계산식은 변경하지 않는다.

Daily Review는 새로운 예측 모델이나 위험 점수가 아니다. 이미 저장된 월별 분석
결과를 읽어 RM이 고객을 검토하고 결과를 기록할 수 있게 하는 업무 기능이다.

## 2. 고정 아키텍처

~~~text
[Analysis — Monthly]
5,000명 synthetic universe
→ 기존 Financial Path Twin 분석
→ 고객별 월별 분석 결과
        ↓
[Saved Monthly Snapshot]
        ↓
[Banker Workflow — Daily]
RM Portfolio만 조회
→ 오늘 먼저 확인
→ 곧 확인 예정
→ 모니터링
→ 고객 선택
→ 왜 오늘?
→ 대화 준비
→ 결과 기록
→ 완료
~~~

- 분석 영역은 기존 Financial Path Twin의 월별 계산 영역이다.
- 저장된 월별 분석 Snapshot은 분석 시점의 고객별 결과를 보존하는 읽기 전용
  묶음이다.
- 업무 영역은 Snapshot을 읽는 Daily Review이다. Daily Review는 Snapshot의
  결과를 다시 계산하거나 갱신하지 않는다.

## 3. 용어 계약

| 용어 | 고정된 의미 |
| --- | --- |
| 월별 분석(Monthly Analysis) | 기존 Financial Path Twin이 고객의 재무 궤적을 분석하는 계산 영역이다. |
| 분기점(Breakpoint) | 유사 고객 가운데 위험 경로와 위험 회피 경로가 역사적으로 처음 뚜렷하게 갈라진 월이다. 미래 사건 발생일이나 연락 기한이 아니다. |
| 월별 분석 Snapshot | 특정 분석 기준시점의 고객별 Digital Twin 결과를 저장한 읽기 전용 묶음이다. |
| Daily Review | Snapshot을 매일 읽어 RM에게 검토할 업무를 전달하는 기능이다. 새 분석이나 새 예측이 아니다. |
| RM Portfolio | 한 RM이 담당한다고 가정하는 고객 목록이다. 5,000명 Matching 모집단과 다르다. |
| 오늘 먼저 확인 | 분기 시점과 현재 관측된 흐름을 기준으로 지금 확인할 가치가 높은 고객 표시다. “가장 위험한 고객”이라는 뜻이 아니다. |
| 곧 확인 예정 | 분기 시점은 확인되지만 오늘 우선 검토 범위보다 시간적 여유가 있는 고객 표시다. |
| 모니터링 | 현재 Daily 업무로 올릴 timing evidence가 부족한 고객 표시다. 고객이 안전하거나 검토 불필요하다는 판정이 아니다. |
| 고객관계 중요도(Relationship Priority) | CRM 관점의 별도 업무 메타데이터다. Digital Twin의 위험 또는 timing과 독립된 축이다. |

분석 우선도와 고객관계 중요도는 합산하지 않는다. 한 화면에 두 축을 함께
보일 수는 있지만, 하나의 점수·순위·큐 규칙으로 결합하지 않는다.

## 4. 분석 영역의 잠금 계약

다음 항목은 기존 Financial Path Twin의 책임이며 Daily Review가 소유하거나
재실행하지 않는다.

- 합성 금융 데이터 생성 규칙과 5,000명 금융 데이터
- 1~12개월 관측 구간과 13~36개월 미래 구간
- Feature Engineering
- weighted nearest-neighbour Matching 및 그 가중치
- Outcome, Breakpoint, What-if 계산
- 기존 CSV/JSON 스키마와 저장 값의 의미

따라서 Daily 경로에서는 새 risk score, prediction probability, 고객별
우선순위 점수 또는 새로운 분석 파라미터를 만들지 않는다. 현재 고객 업무선별에
persona, final_outcome 또는 What-if 개선값을 사용하지 않는다.

## 5. Snapshot과 시간의 의미

Snapshot은 분석이 완료된 시점의 결과를 고정해 둔다. 고객별 Snapshot에는
Daily에서 설명에 사용할 수 있는 기존 결과, 예를 들어 다음 정보가 보존될 수
있다.

- current summary
- matched count
- outcome summary
- breakpoint status, month, months_from_current, primary factor
- 분석 오류 또는 evidence 상태

What-if는 필요할 때만 상세 근거로 열람할 수 있으며, Daily 업무선별이나 기본
대화 지시의 근거가 아니다.

분석은 월 단위이고 업무 전달은 Daily 단위이다. 같은 월별 Snapshot을 여러 날
읽더라도 months_from_current를 하루씩 감소시키지 않는다. 그 값은 Snapshot이
가리키는 분석 기준시점에 묶여 있다. 새 월별 Snapshot이 생성될 때에만 기존
Financial Path Twin 분석 결과에 따라 timing 정보가 갱신된다.

이 문서는 새 Snapshot 저장 형식을 지금 만들거나 기존 CSV/JSON 형식을
바꾸자는 제안이 아니다. 구현 단계에서 별도 읽기 전용 Snapshot 계약이 필요하면
기존 분석 산출물을 변환해 추가하며, 기존 저장 형식과 의미를 변경하지 않는다.

## 6. 5,000명 universe와 RM Portfolio의 분리

5,000명 synthetic universe는 그대로 유지하며, Financial Path Twin의 분석 및
유사고객 Matching reference universe다. RM Portfolio는 그중 한 RM의 업무 범위를
표현하는 별도 목록일 뿐, 원본 금융 데이터를 수정하거나 분석 모집단을 축소하는
수단이 아니다.

PoC에서는 300명을 기본 예시 크기로 검토할 수 있다. 이는 업무 범위 예시이며
분석 파라미터나 Daily 업무량 목표가 아니다. Portfolio 고객 선택은 결과를 보고
고르지 않고, 고정 seed와 안정적인 고객 식별자를 이용해 deterministic하게
생성한다. persona, final_outcome, Breakpoint, Outcome 또는 특정 Daily 개수를
맞추기 위한 선택은 금지한다.

Portfolio의 고객을 분석하더라도 각 고객의 Matching은 기존 5,000명 전체
reference universe를 유지한다. Daily Review는 Portfolio에 속한 고객의 Snapshot
행만 조회한다.

## 7. Daily Review의 업무 흐름

Daily Review의 기본 흐름은 단순하게 유지한다.

~~~text
오늘의 업무
→ 고객 선택
→ 왜 오늘 확인?
→ 대화 준비
→ 검토 결과 기록
→ 완료
~~~

첫 화면은 RM이 “누구를, 왜 지금 확인하는지”를 빠르게 파악하도록 한다.
오늘 먼저 확인, 곧 확인 예정, 모니터링은 Snapshot의 timing evidence를 이해하기
위한 분류이며, 목표 인원수나 복잡한 Queue가 아니다. 실제 건수는 저장된 분석
결과와 투명한 업무 정책에서 나온다.

고객 상세에서는 다음 순서를 따른다.

1. Snapshot에 저장된 근거로 “왜 오늘 확인?”을 설명한다.
2. 현금 흐름, 고정지출, 부채 부담, 소득 변화와 일시적·지속적 변화를 확인하는
   대화 준비 항목을 제시한다.
3. 필요할 때만 유사고객, Outcome, Breakpoint, What-if를 보조 evidence로
   열람한다.
4. RM이 검토 결과를 기록하고 해당 업무를 완료한다.

자동 고객 연락, 상품 추천, 필수 Case, Guided Stepper, capacity 입력과 복잡한
Queue는 이 기본 흐름 밖에 둔다. Case는 기본 플로우 밖이며, 별도 요구가
합의되기 전에는 Daily Review의 상태나 필수 단계로 도입하지 않는다.

## 8. Daily 경로의 허용 범위와 금지 범위

| 허용 | 금지 |
| --- | --- |
| 저장된 Snapshot 읽기 | Matching 재실행 |
| RM Portfolio 범위로 조회 | Outcome, Breakpoint, What-if 재계산 |
| 저장된 근거를 사람이 이해할 문장으로 표시 | 새 risk score 또는 prediction probability 생성 |
| 관계 중요도를 별도 CRM 메타데이터로 표시 | 위험/timing과 관계 중요도를 합산 |
| RM의 검토 결과를 기록하고 완료 표시 | persona/final_outcome 기반 현재 고객 업무선별 |
| 선택적 상세 evidence 열람 | 자동 고객 연락, DB·실제 데이터·외부 발송 |

업무 결과 기록은 분석 결과를 수정하지 않는다. 초기 PoC의 기록 방식은 별도로
정하되, DB나 외부 시스템 연동을 전제하지 않는다.

## 9. 구현된 application layer와 artifact 경계

`scripts/build_rm_monthly_snapshot.py`는 기존 core CSV와 5,000명 feature universe를
읽어 deterministic 300명 Portfolio의 월별 분석 Snapshot을
`artifacts/rm_daily_review/monthly/<snapshot_id>.json`에 저장한다. 같은 배치는 실제
저장값으로 workload report도 남긴다. 기존 demo/cache는 특정 demo 고객의 상세
결과이므로 RM Portfolio 근거로 재사용하지 않는다.

`src.monthly_review_snapshot`은 `src.customer_analysis.run_customer_analysis`를 재사용해
Snapshot을 만든다. `src.daily_review`, `src.daily_worklist`,
`src.rm_daily_review_view`, `src.rm_review_explainability`, `src.rm_review_store`와
`app.py`의 RM 모드는 Snapshot, Portfolio metadata, review event만 사용한다.
missing 또는 stale Snapshot은 CLI 안내·freshness 정보로 처리하며 자동 분석을 시작하지
않는다. 이 과정은 기존 분석 데이터 계약을 바꾸지 않으며, RM Workspace나 Guided
Workflow를 설계 기준으로 삼지 않는다.

## 10. 완료 기준

다음이 모두 충족될 때 Daily Review 설계가 이 계약을 따른다.

- 5,000명 분석 universe와 RM Portfolio가 분리되어 있다.
- Daily 화면은 저장된 월별 Snapshot만 읽고 분석을 재실행하지 않는다.
- timing은 Snapshot 기준이며 일 단위로 임의 감소하지 않는다.
- “오늘 먼저 확인”이 위험도 순위나 미래 사건 예고로 표현되지 않는다.
- 고객관계 중요도는 분석 우선도와 별도 축으로 유지된다.
- Case와 복잡한 업무 관리 기능은 기본 흐름에 포함되지 않는다.
- Monthly Snapshot build에는 기존 분석 서비스가 사용되고, Daily 경로의 analytics
  호출 수는 0으로 regression guard에서 검증된다.
