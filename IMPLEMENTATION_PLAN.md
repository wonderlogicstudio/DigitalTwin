# IMPLEMENTATION_PLAN.md — 바로 구현 가능한 단계별 계획

## 1. 구현 전략

전체 앱을 한 번에 만들지 않는다.

> 데이터 → 검증 → 특징 → 매칭 → 결과 → 분기점 → What-if → UI → 설명

각 단계는 독립 실행과 테스트를 완료한 뒤 다음 단계로 이동한다.

## 2. 프로젝트 초기화

### 생성 파일
- requirements.txt
- config/settings.py
- src/models.py
- app.py
- tests/test_bootstrap.py

### requirements.txt 권장

```text
pandas>=2.2,<3.0
numpy>=1.26,<3.0
scikit-learn>=1.5,<2.0
streamlit>=1.36,<2.0
plotly>=5.22,<7.0
pytest>=8.2,<9.0
pydantic>=2.7,<3.0
```

### 완료
```bash
pytest -q
streamlit run app.py
```

## 3. 합성 데이터

### 구현 순서
1. 고객 마스터
2. 초기 재무 상태
3. 페르소나 추세
4. 이벤트
5. 월별 계산
6. 상태 판정
7. 최종 결과
8. CSV

### 권장 내부 함수

```python
def create_base_customer(...)
def apply_stable_pattern(...)
def apply_gradual_deterioration_pattern(...)
def apply_event_shock_pattern(...)
def apply_recovery_pattern(...)
def apply_overspending_pattern(...)
def apply_monthly_event(...)
def calculate_monthly_metrics(...)
def classify_monthly_status(...)
def classify_final_outcome(...)
```

## 4. 데이터 검증

UI보다 먼저 완료한다.

필수:
- 스키마
- 고객별 36개월
- 회계식
- 결측/inf
- 분포
- 재현성

실패 시:

```python
raise SystemExit(1)
```

## 5. 특징 생성

핵심 위험:
- 미래 누수
- 원 단위 규모 차이
- 분모 0
- 이상치

원칙:
- 함수 첫 줄에서 month <= 12
- 비율·변화·기울기 중심
- 고객당 1행
- 최종 결측 0건

## 6. 매칭

의사코드:

```python
features = load_features()
X = features[MATCH_FEATURES]
X_scaled = scaler.fit_transform(X)

weights = np.array([MATCH_WEIGHTS[name] for name in MATCH_FEATURES])
X_weighted = X_scaled * np.sqrt(weights)

target_index = ...
distances = np.linalg.norm(
    X_weighted - X_weighted[target_index],
    axis=1,
)
distances[target_index] = np.inf

top_indices = np.argsort(distances)[:TOP_K_MATCHES]
```

점검:
- 상위 10명 궤적 수동 확인
- persona는 참고만
- 결과 비율을 맞추기 위한 임의 교체 금지

## 7. 미래 결과

유사 고객 ID와 13~36월 데이터로:
- 결과 분포
- 최초 위험 월
- 미래 평균 지표
- 궤적 CSV

## 8. 분기점

1. 위험/회피 분리
2. 월별 평균
3. pooled std
4. SMD
5. 임계값
6. 연속성
7. 최초 월

시각화:
- 위험군 평균
- 회피군 평균
- 분기점 세로선

## 9. What-if

```text
next_balance
= current_balance
+ income
- fixed_expense
- variable_expense
- debt_payment
```

한 표와 한 그래프로 비교한다.

## 10. 데모 고객

후보 점수 예시:

```text
demo_score
= 분기점 존재
+ 위험군 비율 25~40%
+ 현재 watch
+ 대응 개선액
+ 분기점 13~16월
```

후보 10명을 CSV로 저장하고 최종 1명 수동 선택.

## 11. UI 배치

### 상단
- 프로젝트명
- 한 줄 컨셉
- 고객 선택

### 중단
- 지표 카드
- 현재 궤적
- 유사 고객 미래 궤적
- 결과 분포

### 하단
- 분기점
- 대응 비교
- 설명

그래프:
- 유사 고객 200개 반투명
- 또는 결과별 샘플 50개
- 중앙값/10~90 분위수 밴드
- 현재 고객 굵게
- 현재/미래 배경 구분

## 12. 설명 템플릿

```text
선택한 고객과 유사한 재무 궤적을 보인 고객 {matched_count}명을 확인했습니다.
이 가운데 {risk_ratio}%가 이후 24개월 내 스트레스 또는 연체 상태에 진입했습니다.
두 집단이 가장 먼저 크게 달라진 시점은 {breakpoint_month}개월 차였으며,
주요 차이 지표는 {primary_factor}였습니다.
현재는 12개월 차이므로 해당 시점까지 약 {months_from_current}개월이 남아 있습니다.
{best_scenario} 시나리오에서는 24개월 후 잔액이 기준 대비 {improvement}원 개선되었습니다.
본 결과는 합성 데이터 기반 PoC이며 실제 신용평가 결과가 아닙니다.
```

## 13. 하루 일정

| 시간 | 작업 |
|---|---|
| 0~0.5h | 문서 및 초기화 |
| 0.5~2.5h | 합성 데이터 |
| 2.5~3.5h | 검증/조정 |
| 3.5~4.5h | 특징 |
| 4.5~5.5h | 매칭 |
| 5.5~6.5h | 결과/분기점 |
| 6.5~7.5h | What-if |
| 7.5~9.5h | UI |
| 9.5~10.5h | 테스트 |
| 10.5~11.5h | 데모 고정 |
| 11.5~12h | 백업 |

## 14. 첫 번째 Codex 요청

```text
프로젝트 루트의 모든 MD 파일을 읽고, 특히 SPEC.md,
DATA_DICTIONARY.md, BUSINESS_RULES.md, ARCHITECTURE.md를 준수하라.

이번 작업 범위는 프로젝트 초기화만이다.

1. 문서에 정의된 폴더 구조 생성
2. Python 3.11 기준 requirements.txt 생성
3. config/settings.py 생성
4. src/models.py에 기본 Pydantic 모델 생성
5. app.py에 문서 제목과 데이터 미생성 안내만 표시
6. tests/test_bootstrap.py 작성
7. README 설치 명령 검증

아직 합성 데이터 생성 로직은 구현하지 마라.

작업 후:
- 변경 파일
- 실행 명령
- pytest 결과
- 다음 권장 작업
을 보고하라.
```
