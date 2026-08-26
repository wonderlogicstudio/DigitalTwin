# 14-07 RM Guided Workflow Final Gate

## Decision

**GO / `READY_WITH_WARNINGS`** for the completed Guided RM Workflow
documentation and read-only engineering gate.  All structural, state,
reconciliation, focused/full regression, readiness, and bounded app-health
checks passed.  This is not an unconditional visual presentation sign-off:
the new Guided Workflow still requires the explicitly documented manual Edge
viewport rehearsal, recorded as `NOT_RUN`.

The decision covers an offline synthetic PoC only.  It makes no claim about
real-bank operation, real customer outcomes, RM productivity, delivery, or
production readiness.

## Source-of-truth and documentation synchronization

The final review read the current implementation/tests; the 14-01 through
14-06 reports; `README.md`, `ARCHITECTURE.md`, `DECISIONS.md`,
`BUSINESS_RULES.md`, `DATA_DICTIONARY.md`, `TEST_PLAN.md`, `TASKS.md`, and
`PROJECT_HANDOFF.md`; the operating-manual generator/assets; and the
13-07 release gate.  Product/analytics/workflow code was frozen for this
stage.  Changes are documentation, the manual generator/output, and this
final evidence only.

The synced documents now state that Guided Workflow is a display/orchestration
layer rather than a policy or decision engine, preserves the four RM tabs,
uses capacity only as a comparison, treats no-Case as a normal honest block,
keeps Preview offline/not sent, and separates the optional isolated Demo from
the default RM workspace.

## Operating manual result

`scripts/generate_operating_manual.py --docx-only` regenerated
`reports/operating_manual/Financial_Path_Twin_운영_사용자_매뉴얼.docx`.
Section 8.1 gives the five Guided steps and explicit safety boundaries.  It
does not hard-code mutable Demo audit-event counts; it states the bounded
three-case/append-only-audit contract instead.

LibreOffice conversion and PDF rendering completed successfully.  The final
manual has 50 pages.  All pages were visually checked as contact sheets; the
new Guided content and its page break/table layout on pages 18--19 were also
checked at original render resolution.  No clipped or overlapping content was
found after the layout correction.

`reports/operating_manual/SCREEN_CAPTURE_GUIDE.md` marks the Guided viewport
capture as `NOT_RUN`.  Existing PNGs are not represented as evidence for the
new shell.  The exact 1366x768/1920x1080 and Korean/English capture checklist
remains the required human follow-up.

## Read-only reconciliation snapshot

| Check | Current result |
| --- | --- |
| Branch / baseline | `main`; HEAD and `origin/main` are both `6744e962441ad56ffa17dfe24b13e04845e30be2` (`feat: add isolated workflow demo rehearsal`) |
| App structure | modes=3; Presentation tabs=5; RM tabs=4; Guided steps=5 |
| Canonical population | 5,000; seed=42; observation months 1--12; matched-peer comparison months 13--36; `TOP_K_MATCHES=200` |
| Saved funnel | eligible priority=1,148; eligible review=374; eligible=1,522; monitor=371; no actionable signal=3,107; selected Queue=1,522 |
| Queue boundary | 1,522 operational IDs; before/after-capacity ID digest `5b3e8542935495d619210ffb4edcb095be85e791f61b188230e5360c6faa31ef`; safe first-row handoff `C000001`; excluded `NOT_QUEUE_ELIGIBLE`=3,478 |
| Human capacity comparison | input=3; selected=3; deferred=1,519; saved-rank digest unchanged at `5b3e8542935495d619210ffb4edcb095be85e791f61b188230e5360c6faa31ef`; no auto-choice, source mutation, Queue mutation, Alert creation, or re-ranking |
| Default RM state | default workflow/audit roots absent; normal RM cases=0; no-Case creation delta=0 |
| Demo isolation | `DEMO_READY`; 3 cases (`CLOSED`, `IN_REVIEW`, `NEW`); 8 append-only audit events with valid Case/customer references; default roots=false, delivery/network/sent=false, future-label selection=false |
| Preview | Preview/Null contract only; `sent=false`, no network/external delivery |
| Manual viewport | `NOT_RUN`; human Edge sign-off remains required |

## Contract gates

- Guided state is pure/display-only: no Streamlit import, analytics or triage
  recomputation, persistence, Queue mutation, capacity approval, Case creation,
  repository mutation, or future-data load.
- Capacity is caller-supplied `comparison_only`; Queue/rank reconciliation is
  unchanged.
- Queue-to-review handoff accepts only a visible operational row.  Excluded
  records and representative comparisons do not satisfy the Queue step.
- Selection Reason and Why Now remain separate from historical landmark evidence;
  no future outcome/persona/future-timing leakage is introduced.
- Existing Case actions remain at the Banker/application-service boundary;
  no-Case remains blocked without auto-Case creation; audit remains append-only;
  Preview is not delivery.
- Workflow Demo remains an explicit, isolated secondary context with at most
  three fixture cases and no default-root contamination.
- No DB/ORM/migration, provider SDK, credential/API key, webhook, SMTP, or
  external-network delivery was added.

## Fresh verification

```text
pytest tests/test_documentation_sync.py tests/test_rm_guided_workflow.py \
  tests/test_rm_guided_stepper.py tests/test_rm_guided_handoff.py \
  tests/test_rm_guided_customer_action_handoff.py \
  tests/test_rm_guided_demo_regression.py tests/test_rm_workspace.py \
  tests/test_rm_customer_review.py tests/test_workflow_demo.py \
  tests/test_workflow_demo_ui.py tests/test_workflow_demo_actions.py -q
94 passed in 52.61s

pytest -q
530 passed in 264.72s (0:04:24)

python scripts/check_demo_readiness.py
READY_WITH_WARNINGS
  Python 3.10.9 versus project target 3.11; OPENAI_API_KEY unset, so template
  fallback is used.  Packages, source data, processed data, cached artifacts,
  and C002608 smoke checks are READY.

python scripts/start_streamlit.py --port 8501 --timeout 60
PASS; temporary Streamlit server was stopped after health confirmation.

git diff --check
PASS (line-ending notices only)
```

## Remaining warning and follow-up

Run the `SCREEN_CAPTURE_GUIDE.md` checklist on the actual presentation device
in Microsoft Edge and record the new Guided Workflow viewport results as
PASS/FAIL.  Until that happens, retain `READY_WITH_WARNINGS`; do not present
the existing screenshots as fresh Guided-shell evidence.  Also align the
runtime with the Python 3.11 target when the execution environment is changed.

No subsequent numbered task is authorized or executed by this final gate.
