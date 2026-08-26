# Financial Path Twin Project Handoff

## 0. Current implementation snapshot (2026-08-26)

The committed `main` baseline is
`6744e962441ad56ffa17dfe24b13e04845e30be2`, and it already contains the P0
implementation described below. At the current 14-07 gate start, `HEAD` and
`origin/main` matched. The local 14-01~14-07 Guided Workflow/doc-sync work is
uncommitted and must be reported separately from this committed P0 baseline.
Any later uncommitted feedback-closure work follows the same separation rule.

The dated verification record later in this handoff is retained as historical
evidence for the original demo. It is not the latest P0 or Post-P0 regression
result; use the current commands in `README.md`, `TEST_PLAN.md`, and the
latest `reports/post_p0/` report instead.

### Implemented after the original handoff

- Separate full-population result contract, deterministic batch engine, and
  atomic export: `artifacts/population/seed42_full_run/` contains 5,000
  success results, zero failures, 200 matches per customer, and exact ID
  reconciliation.
- Validation-only circularity mapping/negative-control and multi-seed/TOP_K
  sensitivity reports under `artifacts/validation/`. They leave canonical
  seed-42 files unchanged; `TOP_K_MATCHES=200` remains production invariant.
- Leakage-controlled prospective path: as-of features, reference-only matcher,
  sequential signal history, deterministic cross-fit scoring, and a separate
  evaluator. Timing evidence is prospective; a breakpoint stays a historical
  matched-cohort landmark and is never a live trigger.
- Versioned demo policy, complete 5,000-customer Triage Universe,
  deterministic transparent ranking/capacity selection, exact funnel
  reconciliation, and deterministic representative cohort without future
  labels or manual cherry-picking. The current selection export is
  `artifacts/triage/seed42_crossfit_5fold_asof12_unbounded/`.
- File-backed Alert/Case lifecycle, episode dedupe/cooldown/snooze, Banker
  application service, recommended-follow-up contracts, and append-only audit.
  DB remains unapproved and unimplemented.
- Provider-neutral notification Preview/Null services only; no external SDK,
  credential, provider, webhook, SMTP, Graph, or network delivery exists.
- A separate RM Workspace mode with Portfolio, Review Queue, Customer Review,
  and Activity/Audit tabs. General remains vertical and Presentation remains
  five tabs.
- A compact five-step Guided Workflow display shell. It reads prepared RM
  views and UI acknowledgements to explain Portfolio/Capacity, Queue,
  Customer Review, RM Action, and Activity/Audit; it does not make decisions,
  recalculate selection, or create a Case. Synthetic Workflow Demo remains an
  optional isolated practice branch, not a normal Guided step or bypass.

### Post-P0 feedback-readiness additions

- Human-entered, comparison-only capacity scenarios preserve the saved triage
  rank. The source unbounded selection is 1,522 synthetic records, **not** an
  approved operational workload or recommended threshold.
- Real-data governance, adapter, and aggregate validation-metric contracts are
  source-free readiness artifacts. Their status is `not_ready` / unvalidated:
  this public repository admits no actual or anonymized customer data.
- RM pilot protocol and a synthetic-only dry run provide engineering evidence
  for workflow, measurement, audit, and Preview/Null behavior. They are not
  evidence from actual RM participants, productivity, customer outcomes, or
  intervention efficacy.

### Current operational cautions

- All data, validation results, timing evidence, policies, triage outputs, and
  workflow examples are synthetic demo material—not bank accuracy, outcome,
  intervention-efficacy, or production-policy evidence.
- Triage does not use target future months, `final_outcome`, or persona.
  Policy eligibility, triage selection, and Alert creation have separate
  responsibilities.
- The only supported user startup is still
  `01_install_requirements.bat`, `02_run_pipeline.bat`, then
  `03_run_app.bat`. Automated checks must use the bounded launcher below.

## 1. 문서 목적과 기준

이 문서는 다음 작업자가 현재 프로젝트의 동작 범위, 검증 상태, 변경 금지 조건을 빠르게 확인할 수 있도록 정리한 인수인계 문서입니다.

- 작성 기준일: 2026-08-24 (12-17 sync)
- 기준 브랜치: `main`
- 기준 커밋: `c68c8cc` (P0 implementation baseline)
- 우선 근거: 현재 HEAD 코드, 기존 테스트, `config/settings.py`, 그리고 최신 검증 명령 결과

과거 계획서나 QA 보고서와 현재 코드가 다를 때는 과거 문서를 임의로 신뢰하지 말고, 위 우선 근거를 사용합니다.

## 2. 서비스 개요

Financial Path Twin은 최근 12개월 재무 흐름이 유사한 합성 고객 집단을 찾아, 그 집단의 이후 24개월 결과와 대응 시나리오를 보여주는 Streamlit 기반 PoC입니다.

이 서비스는 실제 신용평가, 미래의 확정적 예측, 금융상품 추천이 아닙니다. 결과는 유사한 합성 고객 집단의 관찰 결과와 규칙 기반 현금흐름 시뮬레이션을 함께 보여줍니다.

## 3. 현재 완료 기능

- 5,000명 합성 고객의 36개월 월별 재무 데이터 생성
- 스키마, 회계식, 분포, 결측 및 재현성 검증
- 1~12개월 관측 구간만 사용하는 특징 생성
- StandardScaler와 가중 유클리드 거리 기반 유사 고객 매칭
- 유사 고객의 13~36개월 결과 분포 집계
- 위험 경로와 위험 회피 경로의 위험 분기점 분석
- 24개월 What-if 현금흐름 시나리오 비교
- 메인, 안정 비교, 고위험 데모 고객 선정 및 사전 계산 캐시
- 한국어와 영어 화면 전환
- 일반 모드와 5개 탭 발표 모드
- 공통 금액, 비율, 기간, 상태명 포맷
- Plotly 시각화, 자체 SVG 에셋, CSS 금융 대시보드 스타일
- 외부 LLM API 없이 동작하는 템플릿 브리핑 및 사전 계산 fallback

## 4. 현재 데이터와 저장 방식

- 원본 데이터: `data/raw/*.csv`
- 처리 결과: `data/processed/*.csv`, `data/processed/*.json`
- 데모 및 fallback 결과: `data/demo/*.csv`, `data/demo/*.json`
- 차트 및 백업: `reports/charts/`, `reports/demo_backup/`
- 데이터베이스: 현재 사용하지 않음

CSV/JSON의 컬럼과 저장 원본 숫자는 현재 동작 계약의 일부입니다.

## 5. 실제 사용자 실행 방법

Windows에서 처음 실행할 때는 프로젝트 루트에서 다음 순서로 실행합니다.

1. `01_install_requirements.bat`
2. `02_run_pipeline.bat`
3. `03_run_app.bat`

`03_run_app.bat`은 Streamlit 서버가 실행되는 동안 창을 유지합니다. 콘솔에 출력된 `http://localhost:8501` 주소를 브라우저에서 열고, 종료할 때는 해당 창에서 `Ctrl+C`를 누릅니다. 8501 포트가 사용 중이면 `DEMO_PORT`를 다른 포트로 지정합니다.

`.env`와 `OPENAI_API_KEY`는 실행에 필요하지 않습니다. 현재 브리핑은 외부 LLM을 호출하지 않는 템플릿 기반 구현이며, `.env.example`은 향후 확장용 설정 예시입니다.

## 6. Codex 및 자동 검증 방법

자동 검증에서는 장시간 실행되는 서버를 전면 실행하지 않습니다.

```powershell
pytest -q
python scripts\check_demo_readiness.py
python scripts\start_streamlit.py --port 8519 --timeout 60
```

`streamlit run app.py`는 정상적으로 서버를 유지하므로 자동 명령에서는 종료되지 않습니다. 사람이 수동으로 서버를 사용할 때만 해당 명령 또는 `03_run_app.bat`을 사용합니다.

## 7. 최신 검증 결과

`214 passed` 기록은 2026-08-20의 original-demo 검증 이력이다. P0와
Post-P0 feedback-readiness 최신 검증은 아래처럼 별도 취급한다. Guided
Workflow의 현재 결과는 `reports/post_p0/14-07_rm_guided_workflow_final_gate.md`
와 그 보고서에 기록된 fresh commands를 우선한다.

- 12-16 synthetic RM pilot dry run 직전 전체 회귀: `459 passed in 229.49s`.
- 같은 단계의 focused workflow/capacity/audit/notification suite: `59 passed`.
- bounded Streamlit health: `python scripts\start_streamlit.py --port 8519 --timeout 60` 통과 후 임시 서버 종료.
- 사전 계산 cache smoke check: 메인 고객 `C002608`, 유사 고객 `200명` 로드 성공.
- 12-17 이후 문서와 public-repository security scan은 이 handoff의 수치가 아니라
  `reports/post_p0/12-17_feedback_security_sync.md`의 실행 결과를 기준으로 한다.

현재 readiness 경고는 아래 두 가지입니다.

- 현재 Python은 `3.10.9`이며 프로젝트 목표 버전은 Python `3.11`입니다. 이는
  compatibility warning이며, 배포/발표 전 Python 3.11 환경에서 재확인이 필요합니다.
- `OPENAI_API_KEY`가 설정되지 않았다는 readiness 경고가 남지만, 현재 앱은 외부 LLM을 호출하지 않으므로 템플릿 브리핑 동작에는 영향이 없습니다.

## 8. 유지해야 할 불변 조건

다음은 UI, 데이터 저장소, DB 연동 등 이후 작업에서도 유지해야 합니다.

- 합성 데이터 생성 로직을 변경하지 않는다.
- 특징 생성, 매칭, 결과 집계, 위험 분기점, What-if 계산식을 변경하지 않는다.
- 기존 CSV/JSON 스키마를 변경하지 않는다.
- 저장된 원본 숫자를 변경하지 않고 화면 표시용 변환만 추가한다.
- 기존 테스트를 삭제하거나 완화하지 않는다.
- 일반 모드와 발표 모드의 핵심 수치를 일치시킨다.
- 번역, 캐시, fallback이 분석값을 재계산하거나 변형하지 않도록 한다.

## 9. 현재 UI와 실행 경계

- `app.py`는 화면 상태, 캐시 사용, 모드 선택, 렌더링 조합을 담당합니다.
- `src/ui_components.py`, `src/visualizations.py`, `src/formatters.py`, `src/labels.py`, `src/i18n.py`는 표시와 문구를 담당합니다.
- 분석 계산은 데이터 생성, 특징, 매칭, 결과 집계, 분기점, What-if 모듈에 남깁니다.
- 발표 모드는 메인 고객의 사전 계산 결과를 우선 사용하며, 탭 전환과 언어 전환에서 준비된 결과를 재사용합니다.
- RM Workspace는 정확히 네 탭을 유지합니다. 그 위의 Guided shell은
  `현재 단계 / 완료 조건 / 다음 행동 / 차단 사유`를 보여주는 display-only
  orchestration이며, capacity, Queue, Alert/Case를 변경하지 않습니다.

## 10. DB 연결 전 결정할 항목

DB는 아직 구현 범위가 아닙니다. 도입을 시작하기 전에 아래 항목을 먼저 설계하고 `DECISIONS.md`에 기록합니다.

1. DB 종류와 실행 환경: 로컬, 개발, 배포 환경의 엔진과 접속 방식
2. CSV/JSON과 DB의 역할: 어떤 데이터가 DB로 이동하고 어떤 파일 호환성을 유지하는지
3. 초기 적재, 마이그레이션, 백필, 롤백 방식
4. 환경변수, 비밀값, 샘플 설정 파일, 배포 구성
5. Streamlit 캐시, 데모 fallback, 사전 계산 산출물과의 관계
6. 실제 금융 데이터 도입 시 개인정보, 접근 제어, 감사 로그, 보존 정책
7. 기존 파이프라인과 테스트를 깨지 않는 전환 및 회귀 검증 전략

DB 종류나 스키마는 위 결정이 완료되기 전까지 임의로 선택하거나 구현하지 않습니다.

## 11. 다음 작업자가 먼저 읽을 파일

1. `PROJECT_HANDOFF.md`
2. `README.md`
3. `ARCHITECTURE.md`
4. `DECISIONS.md`
5. `TASKS.md`
6. `config/settings.py`, `app.py`, 관련 `src/` 모듈과 `tests/`

새 작업은 코드 수정 전에 현재 테스트와 실제 구현을 다시 확인하고, 문서와 코드의 불일치를 먼저 보고해야 합니다.
