# 13-01 Workflow Demo Baseline Isolation Contract Gate

## Result

**GO** — the existing default RM Workspace and the isolated synthetic dry-run
are separable at the current code and artifact boundary. This step creates
only the contract report and baseline manifest; it does not add a fixture,
runtime root, UI entry, service instance, Alert, Case, or audit event.

## Current baseline

- Branch and current remote-tracking ref: `main` / `63e8751`.
- The app has exactly three modes: General, Presentation, and RM Workspace.
- Presentation has exactly five tabs. RM Workspace has exactly four tabs:
  Portfolio, Review Queue, Customer Review, and Activity/Audit.
- `src/rm_workspace.py` reads the default workflow root
  `artifacts/workflow` and returns a read-only snapshot. At this baseline,
  both `artifacts/workflow` and `artifacts/audit` are absent, so their direct
  counts are **0 Cases** and **0 audit events**.
- `src/triage_selector.py` defines `CREATE_NEW_CASE` as a future workflow
  contract and explicitly does not create a Case. In `app.py`, Customer Review
  returns before rendering action controls when no existing workflow Case is
  available.

Consequently, `열린 Alert 없음` and `선정됨 · Case 미생성` are expected
baseline states. Opening RM Workspace, browsing a queue row, running
`02_run_pipeline.bat`, and capacity comparison are not Case-creation paths.

## Existing isolated rehearsal evidence

The tracked source is
`artifacts/post_p0/pilot_dry_run/seed42_capacity_3/`.

| Check | Direct artifact value |
| --- | --- |
| Run mode | `synthetic_operational_rehearsal_only` |
| Capacity scenario | draft, caller-supplied `3`, comparison only |
| Source selection | saved rank-prefix cutoff only |
| Selected source customers | `C000001`, `C000008`, `C000010` (ranks 1–3) |
| Synthetic Case count | 3 |
| Append-only audit event count | 10 |
| Network / external delivery / sent | `false` / `false` / `false` |
| Selection and cohort checksums before/after | equal |

The three IDs are persisted rank-prefix evidence from the selection manifest,
not future-outcome, persona, month 13–36, or evaluator-label choices. The
existing rehearsal's final Case states (`CLOSED`, `IN_REVIEW`, `SNOOZED`) are
evidence only; they must not be treated as the runtime initial state for a new
interactive demo.

## Approved next-step contract

The new experience is an **explicit secondary context inside RM Workspace**.
It is neither a fourth app mode nor a fifth RM tab.

- Entry copy: `합성 Workflow Demo 열기` / `Open Synthetic Workflow Demo`.
- Entry itself must make **zero writes** and create **zero Cases**.
- The future demo banner must read: `합성 Workflow Demo · 실제 운영/발송 아님`.
- Exit copy: `기본 RM 업무로 돌아가기`.
- All future demo session keys must use `rm_workflow_demo_*`; they must not
  replace General, Presentation, customer-selector, or default
  `rm_workflow_ui_service` state.
- The future fixture has at most three Cases. Its initial interactive state is
  `NEW`; permitted presentation flow is `NEW → ACKNOWLEDGED → IN_REVIEW →
  RECORD_ACTION or FOLLOW_UP → audit → Preview (not sent)`.
- A fixture source is limited to persisted selection-rank evidence and
  dry-run provenance. It must not read target months 13–36, `final_outcome`,
  persona, or evaluator labels.

## Proposed path boundary

The paths below are contracts only at this step; neither exists yet.

```text
artifacts/workflow_demo/
  fixture_v1/                 immutable synthetic source
  runtime/
    workflow/                 mutable demo Cases only
    audit/                    mutable demo audit only
    runtime_manifest.json
```

These paths must never share the default roots `artifacts/workflow` or
`artifacts/audit`. A future reset may affect only its validated demo-runtime
child path, must be deterministic/idempotent, and must not modify the
selection manifest, representative cohort, canonical analytics, demo cache,
or the existing pilot dry-run evidence.

## Protected-source reconciliation baseline

`artifacts/post_p0/workflow_demo_contract/contract_manifest.json` records the
SHA-256 values for canonical raw/processed/demo artifacts, the triage
selection manifest, representative cohort, and existing dry-run Case/audit
files. Steps 13-02 through 13-07 must compare against those values.

## Non-blocking documentation finding

`PROJECT_HANDOFF.md` still calls `c68c8cc` the committed baseline and refers
to later feedback-closure work as uncommitted. Current HEAD is `63e8751`,
which has committed that work. This is documentation chronology drift, not a
runtime or P0/Post-P0 behavioral-contract conflict. Do not correct it in this
read-only gate; schedule it for a later documentation sync.

## Gate decision

The default RM baseline remains protected, the isolated rehearsal is a valid
provenance source, and a separate demo-root contract is feasible without
changing analytics, triage, default workflow behavior, mode count, or tab
count. **13-02 may proceed.**
