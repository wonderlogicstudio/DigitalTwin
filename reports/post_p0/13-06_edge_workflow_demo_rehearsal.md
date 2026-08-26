# 13-06 App Regression / KR-EN / Edge Rehearsal QA

## Result

**PARTIAL — automated regression and bounded health checks pass; the required
manual Edge rehearsal is `NOT_RUN`.** This execution environment could not
attach to Microsoft Edge, so it did not claim visual or interactive evidence it
could not observe. No UI blocker was found by the automated checks, but a human
Edge rehearsal at the presentation device is still required before 13-07 can be
given a GO decision.

## Scope and unchanged boundaries

- App modes remain **3**: General, Presentation, RM Workspace.
- Presentation remains **5 tabs** and RM Workspace remains **4 tabs**.
- The Workflow Demo is an explicit, in-context RM action; it is not an app
  mode, RM tab, browser window, or second Streamlit application.
- Default `artifacts/workflow` and `artifacts/audit` remain absent. The default
  RM workspace therefore has zero Cases and creates none while the user views
  the funnel, queue, or capacity comparison.
- The demo fixture contains **3** synthetic Cases maximum. Its uninitialised
  default runtime is `DEMO_NOT_INITIALIZED:0`.
- The protected canonical, triage, dry-run workflow, and audit inputs matched
  the 13-01 contract at **8/8 SHA-256 hashes**.

## Automated regression evidence

| Check | Result | Evidence |
| --- | --- | --- |
| General / Presentation / RM default rendering | PASS | Workflow-demo AppTests explicitly enter all three modes and retain empty default workflow/audit roots. |
| Presentation and RM tab contracts | PASS | 3 modes / Presentation 5 / RM 4 are asserted in presentation, RM, and workflow-demo suites. |
| KR/EN Workflow Demo entry and return | PASS | `test_app_test_workflow_demo_entry_keeps_english_copy_and_return_contract` plus Korean AppTests. |
| Demo entry is read-only until explicit initialization | PASS | `test_demo_shell_is_read_only_until_explicit_initialize_and_reset_isolated`. |
| Missing fixture, uninitialised/corrupt runtime, stale selected Case | PASS | Demo-local `DEMO_FIXTURE_UNAVAILABLE`, `DEMO_NOT_INITIALIZED`, `DEMO_CORRUPT`, and stale-selection tests fail closed without default fallback. |
| Stale state/retry/reset protection | PASS | Idempotency, stale expected-state, stale-service, and interrupted-reset tests fail closed. |
| Preview remains offline | PASS | Preview tests assert `PREVIEW`, `sent=false`, zero Case/audit mutation, and zero network use. |
| Focused app/RM/Workflow Demo regression | PASS | `86 passed in 43.98s` across presentation, RM, action/audit, and workflow-demo suites. |
| Full regression | PASS | `486 passed in 266.78s` (`pytest -q`). |

## Required human Edge rehearsal — NOT_RUN

The Edge automation connection was unavailable for this run. No substitute
browser, screenshot, or separate local Streamlit session was used. At the
actual presentation device, perform the following with `03_run_app.bat` and
the normal app URL only. Record each item as PASS/FAIL; a failure is a return
to 13-03 through 13-05 according to its root cause.

1. At **1366x768**, open General, Presentation, and RM Workspace. Confirm the
   sidebar/mode selector is usable; General has no presentation tabs;
   Presentation has exactly five tabs; RM has exactly four tabs.
2. Repeat the essential labels at **1920x1080**. Confirm the Presentation hero
   and language selector do not overlap, and the RM compact header, funnel,
   and queue table remain readable without a blocking overlay.
3. Switch each of the above screens from Korean to English. Confirm the
   language selector, mode names, tabs, `Open Synthetic Workflow Demo`, and
   `Return to default RM workspace` remain readable and correctly translated.
4. In the default RM Portfolio, capture the safe baseline: no open Alert/Case
   is normal, and selected-for-review does **not** mean a Case was created.
5. Choose **Open Synthetic Workflow Demo**. Confirm the persistent synthetic,
   non-operational, and Preview/not-sent wording. Confirm default RM queue
   filters are not replaced by demo state.
6. Explicitly initialise the synthetic Cases. Confirm there are exactly three
   Cases, then select Case 1.
7. Demonstrate `Acknowledge`, then `Start review`; inspect Recommended
   Follow-up and record an allowed action or follow-up. Confirm no automated
   financial decision is presented.
8. Inspect the Activity/Audit timeline and Notification Preview. It must state
   Preview/not sent; it must not imply delivery or expose a channel selector.
9. Compare Case 2 and Case 3 without creating a fourth Case. Use Reset and
   confirm all three Cases return to the deterministic initial `NEW` state.
10. Use **Return to default RM workspace**. Reconfirm default open Alert/Case
    remains zero and that the 5,000-person funnel/selection evidence is
    unchanged.

Suggested evidence captures, if allowed by the presentation team: safe default
RM Portfolio; synthetic banner with three Cases; an action/follow-up view;
append-only audit; Preview/not-sent; post-reset state; and returned default RM
Portfolio. Captures are evidence of an offline synthetic rehearsal only—not
real customer, RM, delivery, or intervention evidence.

## Current artifact reconciliation

| Item | Current value |
| --- | --- |
| Population expected/output IDs | 5,000 / 5,000; exact, missing 0, duplicate 0, unexpected 0 |
| Triage eligible total | 1,522 (Priority 1,148 + Review 374) |
| Selected queue-ready | 1,522 (unbounded reference; not an approved workload) |
| Monitor only / no actionable signal | 371 / 3,107 |
| Default workflow/audit roots | absent / absent |
| Default demo runtime | absent; `DEMO_NOT_INITIALIZED:0` |
| Fixture maximum | 3 Cases |
| Preview delivery | `sent=false`, network=false |

## Command evidence

- `pytest -q` — PASS, 486 passed in 266.78s.
- `python scripts\\check_demo_readiness.py` — `READY_WITH_WARNINGS` only:
  Python 3.10.9 vs the project 3.11 target, and optional `OPENAI_API_KEY` is
  unset so template fallback is used. All packages, data, cache, and C002608
  cached-analysis smoke checks are ready.
- `python scripts\\start_streamlit.py --port 8519 --timeout 60` — PASS;
  temporary server stopped after the health check.

## Remaining condition

This report is deliberately not a visual sign-off. Complete the 1366x768 and
1920x1080 Edge checklist above on the presentation device, attach only
truthful PASS/FAIL notes, and then rerun the focused UI tests and bounded
health check. Until that human evidence exists, the correct status is
`PARTIAL`, not GO.
