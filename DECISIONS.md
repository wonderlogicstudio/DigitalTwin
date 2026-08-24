# DECISIONS.md — 결정 기록

## DEC-001 예측 모델 미사용
- 상태: 확정
- 결정: 딥러닝·분류 모델을 학습하지 않는다.
- 대안: 유사 궤적 집단의 실제 후속 분포.

## DEC-002 규모
- 고객 5,000명
- 36개월
- 관측 1~12월
- 미래 13~36월

## DEC-003 저장
- CSV/JSON
- DB 미사용

## DEC-004 매칭
- StandardScaler
- 가중 유클리드
- TOP 200

## DEC-005 누수 방지
- 특징은 1~12월
- persona/final_outcome/미래값 금지

## DEC-006 분기점
- |SMD| >= 0.5
- 2개월 연속
- 그룹당 최소 20명

## DEC-007 표현
- “예측 확률” 금지
- “유사 고객 중 발생 비율” 사용

## DEC-008 What-if
- 규칙 기반 현금흐름
- 위험 비율 자동 변경 없음

## DEC-009 UI
- Streamlit + Plotly

## DEC-010 AI
- 설명에만 사용
- Python 계산
- 실패 시 템플릿

## DEC-011 데모
- 고객 ID 및 결과 JSON 고정

## 변경 템플릿

```text
## DEC-XXX 제목
- 날짜:
- 상태:
- 결정:
- 이유:
- 영향 파일:
- 대체 결정:
```
## DEC-012 Monthly Ratio Bounds
- Date: 2026-07-17
- Status: accepted
- Decision: Monthly fixed_expense, variable_expense, and debt_payment are capped at income when income is positive.
- Reason: DATA_DICTIONARY.md requires ratio values to remain in the 0..1 range, and validation found rows where fixed_expense_ratio, variable_expense_ratio, or dsr exceeded 1.
- Impact files: src/data_generator.py, src/validator.py, reports/data_validation_report.csv
- Alternative: Allow ratios above 1 for stressed customers, but that conflicts with the documented validation rule.

## DEC-013 Demo Fallback Artifacts
- Date: 2026-07-18
- Status: accepted
- Decision: The hackathon demo may use fixed precomputed CSV/JSON artifacts when live calculation inputs or optional explanation paths fail.
- Reason: The core demo must remain available without internet, external LLM APIs, or full live recomputation.
- Impact files: src/demo_cache.py, app.py, src/pipeline.py, scripts/check_demo_readiness.py, run_demo.bat, run_demo.sh, reports/demo_backup
- Alternative: Require live recomputation every time, but that increases presentation failure risk.

## DEC-014 License File
- Date: 2026-07-18
- Status: pending owner decision
- Decision: Do not add a LICENSE file without an explicit project owner choice.
- Reason: License selection has legal and distribution implications and should not be inferred by the implementation agent.
- Impact files: README.md
- Alternative: Add a common permissive license such as MIT, but this was intentionally not done.

## DEC-015 Installation Reproducibility
- Date: 2026-07-18
- Status: accepted
- Decision: Keep requirements.txt to direct runtime/test dependencies only and document Windows and macOS/Linux commands separately.
- Reason: The project should be reproducible in a clean Python 3.11 virtual environment without hidden setup steps.
- Impact files: README.md, requirements.txt, .gitignore, .env.example
- Alternative: Pin exact transitive dependency versions, but the MVP keeps compatible version ranges for Python 3.11.

## DEC-016 Population artifact isolation
- Date: 2026-08-23
- Status: accepted
- Decision: Full-population detail, summary, and run-manifest artifacts live
  under `artifacts/population/`, separate from canonical analytics inputs and
  demo cache outputs.
- Reason: Population/reconciliation artifacts must not overwrite seed-42 CSV/
  JSON contracts used by the legacy application.
- Impact files: `src/population_result.py`, `src/population_batch.py`,
  `src/population_artifacts.py`.

## DEC-017 Prospective scoring and evaluator separation
- Date: 2026-08-23
- Status: accepted
- Decision: As-of scoring uses current/prior data and reference-only fitted
  objects; target future labels are available only to a separate evaluator.
- Reason: A prospective signal must be invariant to target months 13-36,
  `final_outcome`, and persona changes before evaluation.
- Impact files: `src/as_of_features.py`, `src/reference_matcher.py`,
  `src/prospective_signals.py`, `src/crossfit_backtest.py`,
  `src/prospective_evaluator.py`.

## DEC-018 Policy, triage, and Alert responsibility split
- Date: 2026-08-23
- Status: accepted
- Decision: Demo-policy eligibility is only a triage input. Triage produces
  complete dispositions and deterministic rank/capacity decisions. Alert
  creation consumes selected/routed decisions only.
- Reason: This prevents policy eligibility from silently becoming an RM queue
  or an Alert, and prevents future-label/demo cherry-picking.
- Impact files: `src/demo_policy.py`, `src/triage_universe.py`,
  `src/triage_selector.py`, `src/selection_manifest.py`, `src/alert_cycle.py`.

## DEC-019 File workflow prototype; DB remains unapproved
- Date: 2026-08-23
- Status: accepted
- Decision: P0 Alert/Case state, dedupe, and audit use atomic file-backed
  repositories under `artifacts/workflow/`; no DB/ORM/migration is added.
- Reason: A DB choice, data migration, recovery, access control, and retention
  plan require an explicit later decision.
- Impact files: `src/alert_case.py`, `src/alert_repository.py`,
  `src/audit_trail.py`, `src/banker_service.py`.

## DEC-020 Offline notification boundary
- Date: 2026-08-23
- Status: accepted
- Decision: P0 provides only provider-neutral Preview and Null notification
  services. Preview is explicitly not sent and makes no network call.
- Reason: External providers, credentials, channels, retries, and delivery
  controls are not approved for this prototype.
- Impact files: `src/notifications.py`, `NOTIFICATION_ADAPTER_CONTRACT.md`.
