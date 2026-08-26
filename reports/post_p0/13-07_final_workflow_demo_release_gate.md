# 13-07 Final Workflow Demo Release Gate

## Decision

**PARTIAL / `READY_WITH_WARNINGS`**

All critical code, artifact-isolation, workflow, audit, notification, and
bounded-app checks pass. The isolated Workflow Demo is technically ready for
an offline synthetic rehearsal. It is not given an unconditional presentation
release GO because the required manual Edge rehearsal remains `NOT_RUN` in
this execution environment.

This is not a product defect finding: no Edge connection was available to
perform truthful viewport and interaction observation. The 13-06 checklist
must be completed on the actual presentation device before calling the visual
release fully signed off.

## A-H release checks

| Gate | Result | Current evidence |
| --- | --- | --- |
| A. Default product preserved | PASS | App modes=3, Presentation=5 tabs, RM=4 tabs; default workflow/audit roots absent with 0 Cases and 0 audit events. |
| B. Explicit Demo entry | PASS | Secondary RM context only; no new app mode, RM tab, browser, or Streamlit application. Entry/back are tested and banner wording is synthetic/not-live/not-sent. |
| C. Fixture and isolation | PASS | Deterministic fixture=3 Cases (`C000001`, `C000008`, `C000010`), all initial `NEW`; future-label selection=false; default runtime is `DEMO_NOT_INITIALIZED:0`. |
| D. Banker workflow | PASS | State-aware Banker adapter actions, recommended follow-up, duplicate/stale handling, and reset freshness are covered by focused tests. |
| E. Audit | PASS | Existing isolated evidence has 3 Cases and 10 append-only audit events; focused tests reconcile event/order/state and protect Preview from audit mutation. |
| F. Notification | PASS | Preview/Null only: `sent=false`, external delivery=false, network=false; no provider, credential, or channel-selector dependency. |
| G. Artifact hashes | PASS | 13-01 protected sources match at 8/8; canonical analytics, triage selection, representative cohort, default workflow, and default audit remain unchanged. |
| H. Quality and claims | WARNING | Focused and full tests plus bounded health pass. Manual Edge rehearsal is not available here; readiness has noncritical Python/API-key/port warnings. |

## Reconciliation snapshot

| Item | Result |
| --- | --- |
| Population coverage | 5,000 expected / 5,000 output; missing=0, duplicate=0, unexpected=0 |
| Triage | eligible=1,522; queue-ready=1,522; monitor=371; no actionable signal=3,107 |
| Default RM | default workflow/audit paths absent; Case=0; audit=0; viewing RM creates no Case |
| Interactive demo fixture | 3 Cases maximum; runtime uninitialised by default; reset initial states are `NEW` |
| Existing dry-run evidence | 3 synthetic Cases; 10 audit events; network=false; sent=false |
| Protected inputs | SHA-256=8/8 match against 13-01 contract |

## Fresh verification

- Focused Presentation/RM/Workflow Demo suite: **86 passed in 42.88s**.
- Full regression: **486 passed in 245.06s**.
- `python scripts\check_demo_readiness.py`: `READY_WITH_WARNINGS`.
  Required packages, documents, raw/processed/demo data, cache, and C002608
  smoke test are ready. Warnings are Python 3.10.9 versus project target 3.11,
  optional `OPENAI_API_KEY` absent (template fallback), and an already-used
  port 8501; the existing port owner was not stopped.
- `python scripts\start_streamlit.py --port 8519 --timeout 60`: PASS; the
  temporary server stopped after health confirmation.
- `git diff --check`: PASS. Existing LF-to-CRLF warnings are informational.
- Tracked secret-file scan: 0; source secret-pattern scan: 0.

## Claims and operational boundary

The release decision covers an **offline synthetic demo only**. It does not
claim real customer validation, bank accuracy, RM productivity, intervention
effectiveness, external notification delivery, or production readiness. It
does not add a DB, provider SDK, credential, webhook, or automatic financial
decision. Historical landmarks remain retrospective peer evidence; What-if
remains rule-based simulation supporting evidence.

## Remaining release action

Run the 13-06 manual checklist in Microsoft Edge at 1366x768 and 1920x1080 on
the presentation device: General/Presentation/RM KR+EN, default RM safe state,
explicit Demo entry, three-case lifecycle, audit, Preview/not-sent, reset, and
return to unchanged default RM. Record PASS/FAIL truthfully. A visual blocker
returns to 13-03 through 13-06 according to root cause; no threshold, ranking,
fixture, or business-rule tuning is authorized by this gate.
