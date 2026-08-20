# TASKS.md — 구현 작업 목록

상태:
- `[ ]` 대기
- `[-]` 진행
- `[x]` 완료
- `[!]` 차단

## M0 초기화

- [ ] MD 문서 배치
- [ ] Python 3.11 가상환경
- [ ] requirements.txt
- [ ] 폴더 구조
- [ ] settings.py
- [ ] 빈 app.py
- [ ] pytest 기본 실행
- [ ] Streamlit 기본 실행

## M1 합성 데이터

- [ ] GeneratorConfig
- [ ] customer_master
- [ ] 페르소나 할당
- [ ] 초기 재무값
- [ ] 월별 36개월
- [ ] 이벤트
- [ ] 월별 지표
- [ ] monthly_status
- [ ] final_outcome
- [ ] CSV 저장
- [ ] 재현성 테스트
- [ ] 성능 확인

산출물:
- data/raw/customer_master.csv
- data/raw/customer_monthly_5000.csv

## M2 검증

- [ ] 스키마
- [ ] 고객별 36개월
- [ ] 중복
- [ ] 결측/inf
- [ ] 값 범위
- [ ] 총지출
- [ ] 저축
- [ ] 잔액 연속성
- [ ] 대출 음수
- [ ] 페르소나 분포
- [ ] 결과 분포
- [ ] 실패 시 종료

산출물:
- reports/data_validation_report.csv
- reports/persona_summary.csv
- reports/outcome_distribution.csv

## M3 특징

- [ ] month <= 12
- [ ] 최근 3개월 평균
- [ ] 12개월 기울기
- [ ] 지출 증가율
- [ ] DSR 변화
- [ ] 잔액 변화율
- [ ] CV
- [ ] 연속 감소
- [ ] 음수 저축 월
- [ ] 대형 지출
- [ ] 고객당 1행
- [ ] 누수 테스트

산출물:
- data/processed/trajectory_features.csv

## M4 매칭

- [ ] StandardScaler
- [ ] 가중치
- [ ] 유클리드 거리
- [ ] 자기 제외
- [ ] TOP 200
- [ ] 유사도
- [ ] 저장
- [ ] 속도
- [ ] 인공 테스트

산출물:
- data/processed/matched_customers.csv

## M5 결과

- [ ] 13~36월
- [ ] 결과 분포
- [ ] 최초 stress
- [ ] 최초 delinquent
- [ ] 미래 평균 잔액
- [ ] 미래 평균 DSR
- [ ] 궤적
- [ ] JSON

산출물:
- data/processed/outcome_summary.json
- data/processed/matched_future_trajectory.csv

## M6 분기점

- [ ] 위험/회피 분리
- [ ] 그룹 크기
- [ ] 월별 평균
- [ ] pooled std
- [ ] SMD
- [ ] 2개월 지속
- [ ] 최초 시점
- [ ] 주요 변수
- [ ] 미발견 처리

산출물:
- data/processed/breakpoint_result.json

## M7 What-if

- [ ] 최근 3개월 프로필
- [ ] baseline
- [ ] 변동비 -15%
- [ ] 고정비 -300,000
- [ ] 상환액 -20%
- [ ] 24개월
- [ ] 고갈 월
- [ ] 최소 잔액
- [ ] 평균 저축률
- [ ] 개선액

산출물:
- data/processed/whatif_results.json

## M8 데모 고객

- [ ] 메인 후보 검색
- [ ] 안정 고객
- [ ] 고위험 고객
- [ ] 결과 수동 검토
- [ ] ID 고정
- [ ] 스크린샷

산출물:
- data/demo/demo_customers.csv
- data/demo/main_demo_customer.json

## M9 UI

- [ ] 제목/컨셉
- [ ] 고객 선택
- [ ] 지표 카드
- [ ] 현재 궤적
- [ ] 유사 고객
- [ ] 미래 궤적
- [ ] 결과 막대
- [ ] 분기점
- [ ] 그룹 비교
- [ ] What-if 표
- [ ] 잔액 그래프
- [ ] 고객용 설명
- [ ] 직원용 설명
- [ ] 합성 데이터 고지
- [ ] 캐시
- [ ] 오류 처리

## M10 AI 선택 기능

- [ ] 템플릿
- [ ] JSON 입력
- [ ] 프롬프트
- [ ] 숫자 생성 금지
- [ ] 확정 예측 금지
- [ ] API 실패 fallback
- [ ] 끄기 옵션

## M11 최종

- [ ] pytest
- [ ] 3분 리허설
- [ ] 화면 크기
- [ ] 오프라인 핵심 기능
- [ ] API 실패 대비
- [ ] 데이터 백업
- [ ] 영상 백업
- [ ] Q&A
- [ ] Git tag
## M1 Synthetic Data Generator Status
- [x] GeneratorConfig
- [x] customer_master.csv generation
- [x] persona assignment
- [x] initial financial values
- [x] 36 monthly snapshots per customer
- [x] event handling
- [x] monthly financial metrics
- [x] monthly_status
- [x] final_outcome from months 13-36
- [x] CSV output
- [x] reproducibility tests
- [x] performance check
## M2 Data Validation Status
- [x] src/validator.py
- [x] scripts/validate_data.py
- [x] tests/test_validator.py
- [x] required column checks
- [x] type checks
- [x] row count and 36-month checks
- [x] duplicate and missing value checks
- [x] NaN and inf checks
- [x] amount and ratio range checks
- [x] accounting relationship checks
- [x] categorical value checks
- [x] persona and final_outcome distribution checks
- [x] reports/data_validation_report.csv
- [x] reports/persona_summary.csv
- [x] reports/outcome_distribution.csv

## M3 Trajectory Feature Status
- [x] src/feature_engineering.py
- [x] scripts/build_features.py
- [x] tests/test_feature_engineering.py
- [x] month <= 12 filter enforced at feature build start
- [x] 10-12 month averages
- [x] 12-month slope/change/growth/CV features
- [x] consecutive balance decline feature
- [x] recent negative savings and large expense features
- [x] one row per customer
- [x] future data leakage test
- [x] data/processed/trajectory_features.csv

## M4 Matcher Status
- [x] src/matcher.py
- [x] tests/test_matcher.py
- [x] scripts/run_matching_demo.py
- [x] MATCH_FEATURES loaded from settings
- [x] StandardScaler full-feature scaling
- [x] square-root feature weight application
- [x] Euclidean distance ranking
- [x] target customer exclusion
- [x] top 200 match output
- [x] display-only persona and final_outcome support
- [x] persona and final_outcome leakage tests
- [x] required matcher exception tests

## M6 Breakpoint Analyzer Status
- [x] src/breakpoint_analyzer.py
- [x] tests/test_breakpoint_analyzer.py
- [x] risk and avoidance group split
- [x] minimum group size handling
- [x] month 13-36 analysis window
- [x] cash and loan balance ratio derivation
- [x] monthly SMD calculation
- [x] pooled standard deviation zero handling
- [x] two-month persistence check
- [x] earliest breakpoint selection
- [x] same-month maximum absolute SMD selection
- [x] non-causal interpretation text
- [x] data/processed/breakpoint_result.json

## M7 What-if Simulator Status
- [x] src/whatif_simulator.py
- [x] tests/test_whatif_simulator.py
- [x] months 10-12 baseline profile
- [x] month 12 starting cash balance
- [x] 24-month simulation
- [x] baseline scenario
- [x] variable_expense_cut_15 scenario
- [x] fixed_expense_cut_300k scenario
- [x] debt_payment_cut_20 scenario
- [x] fixed expense floor at zero
- [x] baseline-relative improvement
- [x] total saved expense calculation
- [x] cash depletion month calculation
- [x] zero-income finite savings-rate handling
- [x] data/processed/whatif_results.json

## M8 Demo Selector Status
- [x] src/demo_selector.py
- [x] scripts/prepare_demo.py
- [x] tests/test_demo_selector.py
- [x] main demo candidate scoring
- [x] main candidate relaxation rules
- [x] stable comparison selection
- [x] high-risk selection
- [x] matched outcome summary calculation
- [x] breakpoint and What-if integration
- [x] deterministic selection test
- [x] data/demo/demo_customers.csv
- [x] data/demo/main_demo_customer.json

## Visualization Function Module Status
- [x] src/visualizations.py
- [x] tests/test_visualizations.py
- [x] scripts/export_demo_charts.py
- [x] reports/charts output directory
- [x] current income/expense, savings rate, DSR charts with presentation titles and reference lines
- [x] twin trajectory chart with default 10-90 percentile band, group medians, and opt-in raw samples
- [x] matched outcome horizontal bar chart with fixed Korean status order
- [x] breakpoint comparison chart with Korean metric labels, group means, and empty-state figure
- [x] What-if balance chart with baseline/best scenario emphasis
- [x] What-if improvement horizontal bar chart
- [x] feature similarity radar chart
- [x] Plotly Figure JSON serialization tests

## M9 Streamlit MVP Status
- [x] app.py
- [x] src/ui_components.py
- [x] src/advisor.py template brief helpers
- [x] .streamlit/config.toml
- [x] tests/test_app_helpers.py
- [x] README.md run instructions
- [x] top notice and synthetic-data disclaimer
- [x] sidebar customer and metric controls
- [x] current customer summary cards and trajectory charts
- [x] matching button with cached matcher
- [x] future twin trajectory tab
- [x] outcome distribution tab
- [x] breakpoint tab
- [x] What-if cash-flow tab
- [x] template briefing tabs
- [x] data-missing and feature-level error handling

## M10 Template Advisor Status
- [x] src/advisor.py
- [x] tests/test_advisor.py
- [x] customer-facing brief template
- [x] staff-facing brief template
- [x] found breakpoint wording
- [x] not_found breakpoint wording
- [x] insufficient_group_size wording
- [x] null cash-depletion wording
- [x] negative balance formatting
- [x] forbidden phrase tests
- [x] app.py advisor connection retained

## Pipeline Runner Status
- [x] src/pipeline.py
- [x] scripts/run_pipeline.py
- [x] tests/test_pipeline.py
- [x] synthetic data generation orchestration
- [x] validation gating and failure stop
- [x] trajectory feature generation
- [x] matcher preparation
- [x] demo customer selection with small-run fallback
- [x] main demo outcome, breakpoint, and What-if refresh
- [x] demo CSV and JSON saving
- [x] optional chart HTML export
- [x] skip and force CLI options
- [x] reproducibility tests with small customer counts

## Hackathon Demo Stabilization Status
- [x] fixed precomputed demo artifacts under data/demo
- [x] matched_customers.csv fallback artifact
- [x] matched_future_trajectory.csv fallback artifact
- [x] outcome_summary.json fallback artifact
- [x] breakpoint_result.json fallback artifact
- [x] whatif_results.json fallback artifact
- [x] app calculation mode badge
- [x] live/cache/demo fallback app flow
- [x] template advisor fallback wrapper
- [x] chart-to-table fallback handling
- [x] run_demo.bat
- [x] run_demo.sh
- [x] scripts/check_demo_readiness.py
- [x] reports/demo_backup outputs
- [x] fallback and readiness tests

## Final Documentation and Reproducibility Status
- [x] README final table of contents
- [x] Windows and macOS/Linux command separation
- [x] requirements.txt direct dependency review
- [x] .gitignore added
- [x] .env.example added
- [x] LICENSE not added; need owner/license decision before distribution
- [x] README command and script filename check
- [x] demo readiness command documented
- [x] final pytest run
- [x] final Streamlit startup check

## Presentation Mode Status
- [x] 사이드바에 `일반 모드`와 `발표 모드` 선택을 추가했다.
- [x] 발표 모드는 `data/demo/main_demo_customer.json`의 메인 고객으로 시작하고, 데모 고객 선택값을 유지한다.
- [x] 발표 모드에서 세부 raw 궤적, 내부 기술 설정, 파일 경로, JSON 원문, 개발자용 상세 정보를 기본 화면에서 숨겼다.
- [x] 발표 모드를 5개 탭 흐름으로 구성했다: 현재 상태, 유사 경로, 위험 분기점, 대응 시나리오, 분석 요약.
- [x] 발표 모드 fallback 순서를 `main_demo_customer.json` → processed JSON → 실시간 계산 → 친절한 오류 메시지로 정리했다.
- [x] 발표 모드 문구와 view model을 `src/presentation.py`에서 관리해 `app.py`에 계산 로직을 복제하지 않았다.
- [x] 발표 모드 회귀 테스트를 `tests/test_presentation_mode.py`에 추가했다.
- [x] `tests/test_presentation_tabs.py`에서 5개 탭, 한국어/영어 라벨, Summary 장면, 탭 렌더링 중 분석 재실행 방지를 검증했다.

## Internationalization Status

- [x] `src/i18n.py`에 한국어/영어 번역 딕셔너리와 fallback 조회 함수를 추가했다.
- [x] 기본 언어를 한국어(`ko`)로 유지했다.
- [x] Hero 영역 오른쪽에 언어 선택기를 추가하고 `st.session_state["ui_language"]`로 상태를 유지했다.
- [x] 일반 모드와 발표 모드 모두 같은 언어 선택값을 사용한다.
- [x] 앱 제목, Hero 문구, 섹션 제목, KPI, 상태명, 지표명, 시나리오명, 표 컬럼, 오류/안내 메시지, 그래프 제목/축/hover, 고객용/직원용 브리핑을 언어별로 표시한다.
- [x] 한국어 금액 표시와 영어 KRW 표시를 `src/formatters.py`에서 공통 관리한다.
- [x] 언어 변경은 표시 문자열만 바꾸며 CSV/JSON 스키마와 저장 숫자, 분석 계산식은 변경하지 않는다.
- [x] `tests/test_i18n.py`를 추가하고 전체 `pytest -q`를 통과했다.

## UI Layout Overlap Fix Status

- [x] `UI_LAYOUT_FIX_REPORT.md`를 생성해 겹침 문제, 수정 방식, 검증 결과를 기록했다.
- [x] Plotly 공통 layout 헬퍼에서 제목 wrap, legend 상단 배치, 동적 top margin, annotation font size를 관리한다.
- [x] 영어 차트 전용 짧은 제목, 짧은 지표명, 짧은 시나리오 범례를 `src/i18n.py`에서 관리한다.
- [x] KPI 카드의 최소 높이, 줄바꿈, 배지 wrap, 숫자 크기 규칙을 `assets/styles.css`에 반영했다.
- [x] Hero 언어 선택기 공간을 넓히고 Streamlit 표시 호출을 `width="stretch"`로 정리했다.
- [x] `tests/test_ui_layout.py`를 추가해 긴 영어 제목, legend 위치, annotation 축약, KPI CSS guard를 검증한다.
- [x] 한국어/영어, 일반/발표 모드, 메인/안정 비교/고위험 고객 AppTest 예외 0건을 확인했다.
- [x] `pytest -q`, `python scripts/check_demo_readiness.py`, 제한 시간 Streamlit 헬스체크를 수행했다.
- [x] 단일 지표 그래프의 중복 범례와 현재 시점 annotation을 줄여 제목/선/라벨 겹침을 완화했다.
- [x] 영어 유사 고객 궤적 범례를 `Similar Median`, `Risk Median`, `Avoid Median`, `10-90% Range`로 축약했다.
- [x] 결과 분포와 저축률/DSR 제목을 더 짧게 바꾸고 Plotly top margin/title 위치를 보수적으로 조정했다.
- [ ] 실제 1366x768 및 1920x1080 브라우저 픽셀 스크린샷은 발표 전 사람이 최종 확인한다.
