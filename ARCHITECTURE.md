# Financial Path Twin Architecture

## 1. 문서 기준

이 문서는 현재 `main` 브랜치의 실제 `src/`, `app.py`, `config/settings.py`, 테스트 구조를 기준으로 작성한다. 과거 계획 문서에 있더라도 현재 존재하지 않는 모듈은 현재 아키텍처 구성 요소로 취급하지 않는다.

## 2. 설계 원칙

- 분석 계산과 Streamlit 표시 로직을 분리한다.
- CSV/JSON 파일을 현재 저장 계약으로 유지한다.
- 공통 계산 함수는 Streamlit 없이 테스트할 수 있어야 한다.
- `app.py`는 분석 공식을 직접 구현하지 않고, 준비된 모듈을 조합한다.
- 관측 구간은 1~12개월, 비교 결과 구간은 13~36개월로 명확히 분리한다.
- 다국어, 숫자 포맷, 시각화는 원본 수치와 분석 결과를 변경하지 않는 표시 계층으로 둔다.

## 3. 논리 흐름

```text
Synthetic Data Generator
  -> Validator
  -> Feature Engineering (months 1-12 only)
  -> Trajectory Matcher
  -> Demo Customer Selection
  -> Outcome Aggregation (months 13-36)
  -> Breakpoint Analyzer
  -> What-if Simulator
  -> Demo Cache / Backup / Chart Export
  -> Streamlit UI
```

결과 집계는 별도 `outcome_analyzer.py` 모듈이 아니라 `src/demo_selector.py`의 `summarize_matched_outcomes`를 통해 수행한다. 현재 `src/outcome_analyzer.py`는 존재하지 않는다.

## 4. 저장소 구조

```text
DigitalTwin/
├── app.py
├── config/
│   └── settings.py
├── data/
│   ├── raw/          # 합성 원본 CSV
│   ├── processed/    # 특징 및 분석 JSON/CSV
│   └── demo/         # 데모 고객 및 사전 계산 fallback
├── reports/
│   ├── charts/       # Plotly HTML export
│   └── demo_backup/  # 데모 fallback 및 runbook
├── scripts/
│   ├── run_pipeline.py
│   ├── check_demo_readiness.py
│   └── start_streamlit.py
├── src/
├── tests/
├── assets/
├── .streamlit/
└── 01_install_requirements.bat / 02_run_pipeline.bat / 03_run_app.bat
```

## 5. 분석 및 데이터 모듈

| 모듈 | 현재 책임 |
| --- | --- |
| `config/settings.py` | 경로, 관측/미래 기간, 매칭 수, 분기점 및 What-if 상수 |
| `src/models.py` | 생성과 분석에서 사용하는 Pydantic/dataclass 모델 |
| `src/data_generator.py` | 합성 고객 마스터와 36개월 월별 재무 데이터 생성, 상태 및 최종 결과 산출 |
| `src/validator.py` | 스키마, 회계식, 결측, 범위, 분포 검증과 보고서 저장 |
| `src/feature_engineering.py` | 1~12개월 재무 흐름 특징 생성 및 저장 |
| `src/matcher.py` | StandardScaler와 가중 유클리드 거리 기반 유사 고객 매칭 |
| `src/demo_selector.py` | 데모 고객 선택, 현재 지표 및 유사 고객 결과 집계 |
| `src/breakpoint_analyzer.py` | 위험/회피 그룹 구분, 월별 SMD, 지속 조건 기반 분기점 탐지 |
| `src/whatif_simulator.py` | 최근 프로필 기반 24개월 현금흐름 시나리오 계산 |
| `src/pipeline.py` | 생성부터 데모 산출물, cache, 선택적 차트 export까지의 전체 오케스트레이션 |

`src/pipeline.py`는 파이프라인 실행을 담당하지만, 개별 계산의 규칙은 각 도메인 모듈에 둔다.

## 6. 데모, 캐시, fallback

| 모듈 | 현재 책임 |
| --- | --- |
| `src/demo_cache.py` | 사전 계산 데모 산출물 저장/검증/로드, 백업 차트 및 fallback 요약 생성 |
| `src/presentation.py` | 발표 모드 데이터 로드, fallback 순서, 5개 탭 view model과 장면 메시지 |
| `scripts/check_demo_readiness.py` | 필수 데이터, 데모 cache, 패키지, 포트, API 키 상태 점검 |
| `scripts/start_streamlit.py` | 제한시간 HTTP 헬스체크용 Streamlit 실행 및 임시 프로세스 종료 |

발표 모드는 메인 고객의 `data/demo/main_demo_customer.json`과 사전 계산 결과를 먼저 사용한다. 필요한 경우 processed JSON, 기존 실시간 분석 순서로 준비하며, 이미 준비한 payload는 session state에서 재사용한다.

## 7. UI와 표시 계층

| 모듈 | 현재 책임 |
| --- | --- |
| `app.py` | 페이지 설정, 언어/모드/고객 상태, Streamlit 캐시, 화면 조립 |
| `src/ui_components.py` | Hero, 고객 요약, KPI, 표, 브리핑, 표시용 view model, 안전한 HTML 렌더링 |
| `src/visualizations.py` | Plotly Figure, 축/hover/범례/annotation, 공통 layout, JSON 직렬화 가능한 차트 |
| `src/formatters.py` | 한국어/영어 통화, 퍼센트, 기간, 축 단위 변환 |
| `src/labels.py` | 상태, 페르소나, 지표, 시나리오 라벨과 용어 도움말 |
| `src/i18n.py` | 한국어/영어 번역 딕셔너리, fallback, 안전한 변수 치환, 번역 key 검증 |
| `src/copy.py` | 공통 화면 문구, 금지 표현 및 내부 용어 검사 |
| `src/advisor.py` | 고객용/직원용 템플릿 브리핑과 API 실패 fallback |
| `src/theme.py` | 상태와 그래프가 공유하는 의미 기반 디자인 토큰 |
| `src/assets.py` | SVG/CSS pathlib 로드와 누락 시 inline fallback |

`app.py`의 일반 모드는 세로형 5개 섹션으로 흐르고, 발표 모드는 다음 5개 탭으로 같은 분석 결과를 표현한다.

1. 현재 상태
2. 유사 경로
3. 위험 분기점
4. 대응 시나리오
5. 분석 요약

한국어/영어 전환은 `st.session_state["ui_language"]`에 저장된다. 언어, 탭, 표시 지표를 바꿔도 기존 분석값을 변경하거나 다시 계산하지 않는다.

## 8. UI와 계산의 경계

- `formatters`, `labels`, `i18n`, `ui_components`, `visualizations`, `advisor`는 표시와 설명을 담당한다.
- `data_generator`, `feature_engineering`, `matcher`, `demo_selector`, `breakpoint_analyzer`, `whatif_simulator`는 도메인 계산을 담당한다.
- UI에서 필요한 분석 조합은 `ui_components.run_customer_analysis`와 `pipeline.run_pipeline`이 기존 도메인 함수를 호출해 준비한다.
- 표시 계층은 입력 DataFrame과 저장 JSON/CSV 원본을 변경하지 않아야 한다.

## 9. 실행과 캐시

`app.py`는 월별 데이터, 특징 데이터, 데모 목록에 `st.cache_data`를 사용하고 matcher에는 `st.cache_resource`를 사용한다. 고객이 바뀌면 현재 분석 상태만 갱신하며, 언어와 발표 탭 전환에서는 준비된 분석 결과를 유지한다.

수동 서버 실행은 `03_run_app.bat` 또는 `python -m streamlit run app.py`를 사용한다. 자동 검증은 종료되지 않는 서버 프로세스를 피하기 위해 `scripts/start_streamlit.py --timeout ...`을 사용한다.

## 10. 테스트 경계

`tests/`는 데이터 생성, 검증, 특징 누수, 매칭, 분기점, What-if, pipeline, demo cache, UI components, formatters, i18n, visualization, presentation mode/tab, bounded Streamlit launcher를 분리해 검증한다.

테스트를 삭제하거나 완화해 UI나 저장소 변경을 통과시키지 않는다. 계산 결과와 파일 스키마에 영향을 주는 변경은 도메인 테스트와 전체 `pytest -q`를 함께 통과해야 한다.

## 11. 데이터베이스 확장 상태

현재 데이터베이스는 아키텍처 구성 요소가 아니다. 데이터는 CSV/JSON 파일과 데모 cache로 관리한다.

DB를 도입할 때는 먼저 DB 종류, 파일과 DB의 역할 분리, 마이그레이션/백필/롤백, 환경변수와 비밀값, 캐시와 fallback, 배포/보안 정책을 결정하고 `DECISIONS.md`에 기록한다. 기존 CSV/JSON 계약과 분석 계산을 바꾸는 구현은 이 결정 이후에 별도 단계로 진행한다.
