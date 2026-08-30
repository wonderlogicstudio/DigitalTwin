# TASKS.md — 구현 작업 목록

상태:
- `[ ]` 대기
- `[-]` 진행
- `[x]` 완료
- `[!]` 차단

## 완료된 기반 작업 (M0~M11)

초기 작업 목록은 아래의 상세 완료 이력과 중복되어 있었으므로 미완료 체크박스를 제거했다. M0~M11의 구현 범위는 현재 코드와 테스트에 반영되어 있다.

- [x] 프로젝트 초기화, 설정, 테스트 및 Streamlit 기본 실행
- [x] 합성 데이터 생성, CSV 저장, 재현성 검증
- [x] 데이터 검증과 검증 보고서 생성
- [x] 관측 구간 특징 생성 및 미래 데이터 누수 방지
- [x] 유사 고객 매칭과 결과 분포 집계
- [x] 위험 분기점 분석과 미발견/표본 부족 처리
- [x] What-if 현금흐름 시나리오 비교
- [x] 메인, 안정 비교, 고위험 데모 고객 및 fallback 산출물
- [x] Streamlit 일반 모드, 발표 모드, Plotly 시각화, 브리핑
- [x] 공통 표시 포맷, 한국어/영어 전환, 자체 SVG/CSS 에셋
- [x] 전체 pytest, readiness, 제한시간 Streamlit 헬스체크 기반 데모 점검

상세 구현과 검증 이력은 아래 상태 섹션을 유지한다.

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

## RM Daily Review Status

- [x] UX-07 E2E Guard: saved Snapshot query → detail → JSONL review save → rerun을 analytics 및 snapshot builder monkeypatch 차단 상태에서 검증했다.
- [x] `오늘의 업무 조회`의 1.5~2초 read-only loading, 저장된 supporting evidence, synthetic presentation overlay, 완료 후 고객 단위 목록 갱신을 구현했다.

- [x] 5,000명 synthetic analysis universe와 deterministic 300명 RM Portfolio를 분리했다.
- [x] Portfolio의 relationship priority를 금융 데이터와 독립적인 synthetic CRM overlay로 만들었다.
- [x] 기존 고객 분석 서비스로 월별 Snapshot과 workload report를 별도 artifact에 저장한다.
- [x] Snapshot 기준 timing으로 `오늘 먼저 확인`·`곧 확인 예정`·`모니터링`을 결정한다.
- [x] Daily worklist와 Streamlit RM 화면은 Snapshot, Portfolio metadata, review log만 읽는다.
- [x] 핵심관리 고객 filter는 UPCOMING bucket 안에서만 제공하며 timing bucket을 바꾸지 않는다.
- [x] RM 결과를 JSONL에 기록하고 같은 Snapshot·같은 날의 미완료 목록에서 제외한다.
- [x] Daily에서 Feature/Matcher/Outcome/Breakpoint/What-if/Pipeline 재실행을 차단하는 회귀 Guard를 추가했다.
- [x] Case, 자동 연락, DB, 새 위험 점수, Capacity/Queue/Guided Stepper를 기본 흐름에서 제외했다.
- [x] 실제 5,000명 reference universe 기반 300명 Snapshot E2E에서 초기 업무량과 완료 후 목록 갱신을 확인했다.

## 다음 단계: DB 연결 설계 및 의사결정

- [ ] DB 종류와 로컬/배포 실행 환경을 결정한다.
- [ ] CSV/JSON과 DB의 역할, 읽기/쓰기 책임, 호환 범위를 정한다.
- [ ] 초기 적재, 마이그레이션, 백필, 롤백 계획을 작성한다.
- [ ] 환경변수, 비밀값, 샘플 설정, 배포 방식을 결정한다.
- [ ] Streamlit 캐시, 사전 계산 demo cache, fallback과의 관계를 설계한다.
- [ ] 실제 금융 데이터 도입 전 개인정보, 인증/권한, 감사 로그 요구사항을 확인한다.
- [ ] `DECISIONS.md`에 위 선택을 기록한 뒤에만 DB 구현 범위를 시작한다.

이 섹션은 설계 전제 조건이며, 데이터베이스 구현이 완료되었음을 의미하지 않는다.
