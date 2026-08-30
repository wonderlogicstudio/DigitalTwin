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

## DEC-016 Synthetic RM Portfolio Metadata
- Date: 2026-08-28
- Status: accepted
- Decision: Define a separate deterministic synthetic CRM overlay for RM-POC-001: 300 customer IDs selected from the 5,000-customer universe with seed 20260828, then CORE 10%, PRIORITY 25%, and STANDARD 65% relationship metadata assigned with independent seed 42.
- Reason: Daily Review needs a bounded RM workload scope and relationship context without treating financial balances, income, persona, outcomes, or Digital Twin results as CRM value.
- Impact files: RM_PORTFOLIO_METADATA_DESIGN.md, src/rm_portfolio.py, scripts/build_rm_portfolio.py, and tests/test_rm_portfolio.py; generated overlay artifacts remain separate from core data files.
- Alternative: Infer customer importance from Financial Path Twin data, but that would falsely represent financial data as CRM/AUM information and violate the analysis/workflow boundary.

## DEC-017 Daily Timing Bucket Policy
- Date: 2026-08-28
- Status: accepted
- Decision: Classify stored Snapshot results as REVIEW_NOW only when breakpoint status is found, months_from_current is 1 or 2, and the stored month-12 status is watch, stress, or delinquent. Classify found healthy customers at 1 or 2 months and all found customers at 3 or 4 months as UPCOMING. Classify missing/error, not_found, insufficient_group_size, invalid timing, and found timing at 5 or more months as MONITOR.
- Reason: The measured Portfolio distribution clustered breakpoint evidence at 1 month. Timing alone produced 107 REVIEW_NOW customers out of 300; requiring an already stored current observation gives the “why today?” label an operational meaning without adding a score, prediction, or future-outcome cutoff.
- Impact files: RM_DAILY_REVIEW_POLICY.md, src/daily_review.py, and tests/test_daily_review.py; a Snapshot loader and Daily UI remain later implementation work.
- Alternative: Use a timing-only cutoff or tune a threshold to a target daily count. Both would either overfill REVIEW_NOW in the measured data or make the policy a workload-targeted risk proxy.

## DEC-018 Saved Snapshot Daily Delivery Boundary
- Date: 2026-08-29
- Status: accepted
- Decision: Build the RM monthly Snapshot through the existing `run_customer_analysis` service for the deterministic 300-customer Portfolio against the full 5,000-customer matcher universe. Build Daily worklists and the RM UI only from the saved Snapshot, independent Portfolio metadata, and manual JSONL review events.
- Reason: This makes the historical Breakpoint timing operationally available to an RM without changing Financial Path Twin methodology or creating a new risk model. The Daily layer remains an operational delivery cycle, not an analytics execution path.
- Impact files: `src/customer_analysis.py`, `src/monthly_review_snapshot.py`, `src/daily_review.py`, `src/daily_worklist.py`, `src/rm_daily_review_view.py`, `src/rm_review_store.py`, `app.py`, `scripts/build_rm_monthly_snapshot.py`, and RM Daily tests.
- Alternative: Recompute analytics whenever the RM opens the screen or derive a composite relationship-risk score. Both violate the saved Snapshot boundary and make relationship priority appear as Digital Twin risk.

## DEC-019 Saved RM UX Evidence and Read-only Retrieval
- Date: 2026-08-29
- Status: accepted
- Decision: Detail evidence for RM Daily is generated only when the existing Monthly Snapshot is built and saved as explicit provenance, why-now timing, observed change cards, historical cohort comparison data, minimal outcome summary, and optional What-if summary. The RM?s query action displays a 1.5?2 second read-only loading feedback while it reads the saved Snapshot, independent overlays, and review log; it does not run analytics or decrement timing by day.
- Reason: The RM needs an understandable, screenshot-level workflow from today?s worklist through evidence, conversation preparation, result recording, and completion without turning Daily Review into an unbounded analytics screen or a hidden new prediction model.
- Impact files: `RM_DAILY_REVIEW_UX_SPEC.md`; subsequent implementation may extend the separate Monthly Snapshot artifact, display overlays, pure Daily view model, and RM UI while preserving all core Financial Path Twin schemas and calculations.
- Alternative: Calculate detail evidence on demand in the Daily screen or imitate a risk chart with new score/probability. Both would blur the monthly-analysis/Daily-delivery boundary and misrepresent historical comparison evidence.

## DEC-020 UX-07 RM Daily E2E Guard and Manual Completion
- Date: 2026-08-29
- Status: accepted
- Decision: Lock an end-to-end saved-artifact path: Monthly Snapshot build may use existing analytics, while Daily query, detail view, review save, and rerun must work with analytics and snapshot-builder entry points monkeypatched to fail. A manual review event moves only the matching customer for the same snapshot and business date to the completed area.
- Reason: The RM workflow must demonstrate an operational loop without turning a page refresh, detail chart, or `FOLLOW_UP` result into a new analysis, Case, Alert, or automated action.
- Impact files: `tests/test_rm_daily_analysis_boundary.py`, `src/rm_daily_review_loader.py`, `src/rm_daily_review_view.py`, `src/rm_review_store.py`, `app.py`, and the RM Daily handoff documents.
- Alternative: Permit on-demand analytics or delegate follow-up to the existing selected/routed Case workflow. Both would blur ownership and violate the simple saved-Snapshot Daily flow.

## DEC-021 Synthetic Financial Universe v2
- Date: 2026-08-29
- Status: accepted
- Decision: Replace the prior deterministic 5,000-customer data-generation baseline with eight deterministic synthetic financial-flow archetypes: stable, gradual deterioration, event shock, recovery, overspending, synthetic business-income variability, synthetic liquidity resilience, and synthetic financial constraint. Keep customer count, master/monthly column schemas, month ranges, feature engineering, matching, outcome, breakpoint, and What-if implementations unchanged.
- Reason: Read-only measurement of the prior 300-customer RM Snapshot found that 84 of 107 found breakpoints used variable expense and all found breakpoints occurred one month after the observation window. The Daily list also always displayed its static cash card first, even when that was not the actual breakpoint factor. V2 broadens deterministic starting conditions and future pressure timing without tuning a Daily workload or an outcome threshold.
- Impact files: `SYNTHETIC_UNIVERSE_V2_DESIGN.md`, `config/settings.py`, `src/data_generator.py`, `src/models.py`, `src/labels.py`, `src/i18n.py`, data-generation tests, and regenerated local raw/processed/demo artifacts.
- Alternative: Change matching weights, breakpoint thresholds, Daily timing thresholds, or select Portfolio customers from outcomes. All would either change analytical methodology or target an operational result instead of diversifying source paths.
