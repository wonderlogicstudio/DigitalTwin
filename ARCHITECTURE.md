# ARCHITECTURE.md — 기술 구조 및 모듈 설계

## 1. 설계 원칙

- 계산 로직과 UI를 분리한다.
- 각 모듈은 하나의 책임만 가진다.
- CSV/JSON 기반으로 동작한다.
- 모든 핵심 함수는 Streamlit 없이 테스트할 수 있어야 한다.
- 설정값은 `config/settings.py`에 집중한다.
- 관측 구간과 미래 구간을 코드에서 명시적으로 분리한다.
- `app.py`에는 계산 공식을 직접 구현하지 않는다.

## 2. 논리 구조

```text
[Data Generator]
    ↓ raw CSV
[Validator]
    ↓ validated data
[Feature Engineering]
    ↓ customer-level features
[Matcher]
    ↓ top-k matched customers
[Outcome Analyzer]
    ↓ future outcome summary
[Breakpoint Analyzer]
    ↓ breakpoint result
[What-if Simulator]
    ↓ scenario results
[Advisor]
    ↓ narrative
[Streamlit UI]
```

## 3. 권장 폴더 구조

```text
financial-path-twin/
├── app.py
├── requirements.txt
├── config/
│   └── settings.py
├── data/
│   ├── raw/
│   ├── processed/
│   └── demo/
├── reports/
├── scripts/
│   ├── generate_data.py
│   ├── validate_data.py
│   ├── build_features.py
│   └── prepare_demo.py
├── src/
│   ├── models.py
│   ├── data_generator.py
│   ├── validator.py
│   ├── feature_engineering.py
│   ├── matcher.py
│   ├── outcome_analyzer.py
│   ├── breakpoint_analyzer.py
│   ├── whatif_simulator.py
│   ├── advisor.py
│   └── visualizations.py
└── tests/
```

## 4. 모듈 책임

### config/settings.py
- 경로
- 랜덤 시드
- 고객 수와 기간
- 페르소나 비율
- 상태 임계값
- 특징 목록과 가중치
- 분기점 기준
- 시뮬레이션 기준

### src/models.py
Pydantic 또는 dataclass 모델:
- GeneratorConfig
- CustomerProfile
- MonthlySnapshot
- MatchResult
- OutcomeSummary
- BreakpointResult
- WhatIfScenario
- WhatIfResult

### src/data_generator.py

권장 공개 함수:

```python
def generate_customer_master(config: GeneratorConfig) -> pd.DataFrame:
    ...

def generate_monthly_snapshots(
    customer_master: pd.DataFrame,
    config: GeneratorConfig,
) -> pd.DataFrame:
    ...

def assign_final_outcomes(
    monthly_df: pd.DataFrame,
    config: GeneratorConfig,
) -> pd.DataFrame:
    ...

def generate_dataset(
    config: GeneratorConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    ...
```

내부 책임:
- 초기 상태
- 페르소나
- 이벤트
- 월별 계산
- 상태 라벨
- 최종 라벨

### src/validator.py

```python
def validate_schema(df: pd.DataFrame) -> list[str]:
    ...

def validate_customer_months(df: pd.DataFrame) -> list[str]:
    ...

def validate_accounting_relationships(df: pd.DataFrame) -> list[str]:
    ...

def validate_distribution(df: pd.DataFrame) -> list[str]:
    ...

def run_all_validations(
    master_df: pd.DataFrame,
    monthly_df: pd.DataFrame,
) -> pd.DataFrame:
    ...
```

검증 보고서 컬럼:
- check_name
- status
- actual_value
- expected_value
- message

### src/feature_engineering.py

```python
def build_trajectory_features(
    monthly_df: pd.DataFrame,
    observation_end_month: int = 12,
) -> pd.DataFrame:
    ...
```

내부 함수:
- calculate_slope
- calculate_cv
- max_consecutive_declines
- count_large_expense_months

함수 첫 단계에서 `month <= observation_end_month` 필터를 강제한다.

### src/matcher.py

```python
class TrajectoryMatcher:
    def __init__(
        self,
        feature_names: list[str],
        feature_weights: dict[str, float],
    ) -> None:
        ...

    def fit(self, features_df: pd.DataFrame) -> "TrajectoryMatcher":
        ...

    def match(
        self,
        target_customer_id: str,
        top_k: int = 200,
    ) -> pd.DataFrame:
        ...
```

보관 상태:
- scaler
- customer_ids
- transformed_matrix
- source_features

### src/outcome_analyzer.py

```python
def analyze_outcomes(
    target_customer_id: str,
    matched_ids: list[str],
    monthly_df: pd.DataFrame,
    future_start_month: int = 13,
) -> dict:
    ...
```

### src/breakpoint_analyzer.py

```python
def find_breakpoint(
    matched_ids: list[str],
    monthly_df: pd.DataFrame,
    min_group_size: int = 20,
    effect_threshold: float = 0.5,
    persistence_months: int = 2,
) -> dict:
    ...
```

### src/whatif_simulator.py

```python
def build_baseline_profile(
    customer_id: str,
    monthly_df: pd.DataFrame,
) -> dict:
    ...

def simulate_scenario(
    profile: dict,
    scenario: dict,
    simulation_months: int = 24,
) -> pd.DataFrame:
    ...

def compare_scenarios(
    profile: dict,
    scenarios: list[dict],
) -> dict:
    ...
```

### src/advisor.py

```python
def build_customer_brief(
    outcome_summary: dict,
    breakpoint_result: dict,
    whatif_results: dict,
) -> str:
    ...

def build_staff_brief(
    current_metrics: dict,
    outcome_summary: dict,
    breakpoint_result: dict,
    whatif_results: dict,
) -> str:
    ...
```

### src/visualizations.py

- create_current_trajectory_chart
- create_twin_trajectory_chart
- create_outcome_bar_chart
- create_breakpoint_comparison_chart
- create_whatif_balance_chart

### app.py

담당:
- Streamlit 상태
- 화면 배치
- 모듈 호출
- 로딩 및 오류 메시지

금지:
- 거리 공식 재구현
- 상태 라벨 재계산
- 분기점 통계 재계산

## 5. 캐시

```python
@st.cache_data
def load_monthly_data(...):
    ...

@st.cache_data
def load_features(...):
    ...

@st.cache_resource
def build_matcher(...):
    ...
```

고객 선택 변경만으로 CSV를 다시 읽지 않는다.

## 6. 오류 처리

### 데이터 파일 없음
- 생성 명령 안내
- 기술적 스택트레이스 대신 사용자 메시지

### 고객 ID 없음
- ValueError
- UI에 선택 고객 없음 표시

### 그룹 크기 부족
- status=`insufficient_group_size`

### 분기점 없음
- status=`not_found`

### 소득 0
- DATA_DICTIONARY 규칙 적용
- NaN/inf 금지

## 7. 설정 파일 기본 예시

```python
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

RANDOM_SEED = 42
CUSTOMER_COUNT = 5000
TOTAL_MONTHS = 36
OBSERVATION_END_MONTH = 12
TOP_K_MATCHES = 200

DATA_RAW_DIR = BASE_DIR / "data" / "raw"
DATA_PROCESSED_DIR = BASE_DIR / "data" / "processed"
DATA_DEMO_DIR = BASE_DIR / "data" / "demo"
REPORTS_DIR = BASE_DIR / "reports"

BREAKPOINT_EFFECT_THRESHOLD = 0.5
BREAKPOINT_PERSISTENCE_MONTHS = 2
BREAKPOINT_MIN_GROUP_SIZE = 20
```

## 8. 구현 순서

1. settings.py
2. models.py
3. data_generator.py
4. validator.py
5. feature_engineering.py
6. matcher.py
7. outcome_analyzer.py
8. breakpoint_analyzer.py
9. whatif_simulator.py
10. visualizations.py
11. advisor.py
12. app.py
