# 14-01 RM Guided Workflow Contract Audit

## Result

**GO for 14-02 only.** The RM foundation and checked artifacts are sound.  A
five-step guided state model and explicit handoff do not exist yet; they are the
bounded subject of 14-02 onward.  This audit made no product-code,
configuration, canonical-artifact, triage, default-workflow, or default-audit
change.

## Baseline and scope

- Branch: `main`
- HEAD and `origin/main` at audit start:
  `6744e962441ad56ffa17dfe24b13e04845e30be2`
  (`feat: add isolated workflow demo rehearsal`)
- `git status --short` was empty at audit start, and `git fetch origin main`
  completed before comparison.
- The only intended outputs are this report and
  `artifacts/post_p0/rm_guided_workflow/contract_manifest.json`.

## Source-of-truth inputs read

The audit read the RM workspace and review/application boundaries in
`app.py`, `src/rm_workspace.py`, `src/rm_customer_review.py`,
`src/rm_workflow_ui.py`, `src/banker_application_service.py`,
`src/workflow_demo_ui.py`, `src/workflow_demo.py`,
`src/triage_selector.py`, and `src/alert_cycle.py`; focused RM/demo tests;
current triage and demo artifacts; readiness/start scripts; and the handoff,
architecture, business-rule, decision, task, and manual documents.

## Current UI / function mapping

### Entry and workspace

`src/copy.py` declares three app modes: General, Presentation, and RM.
`app.py::render_rm_workspace_mode` renders four RM tabs in this order:
Portfolio, Queue, Customer Review, and Activity/Audit.  It loads artifacts and
cases read-only and constructs `RMWorkflowUIService` for the existing Banker
operation boundary.  Presentation remains five tabs.  Guided work must preserve
all of these counts and RM's four-tab shape.

### Portfolio and capacity

`build_rm_portfolio_queue_view_model` exposes saved selection funnel,
priority breakdown, capacity comparison, representative cohort, and operational
queue.  Capacity comparison is caller-supplied comparison only: it neither
re-ranks the saved queue nor approves a selection, creates a case, or sends a
notification.

### Queue selection

An operational queue record requires `selected_for_review=true`,
`selection_disposition=SELECTED_FOR_REVIEW`, and routing disposition
`CREATE_NEW_CASE` or `ROUTE_EXISTING_CASE`.  The row-to-context helper
accepts only an ID in the visible queue.  A representative customer helps
explain the portfolio but is not an operational selection.

### Customer evidence review

`build_rm_customer_review_view_model` is observation-only: it loads
current/prior fields through the as-of month; does not load target future data,
score/rank, mutate a case, or make a historical outcome a live trigger.  The UI
shows Selection Reason / Why Now, current evidence, prospective timing,
historical Twin outcomes, historical landmark, and recommended follow-up.

### RM action and audit

`_render_rm_action_controls` returns a no-case message when there is no
case.  With an existing case, operations route through `RMWorkflowUIService`
and the Banker application service.  Activity is read-only history.  Offline
notification Preview is `PREVIEW`, `sent=false`, with no network or external
delivery; it is supporting review, not audit/delivery replacement.

### Optional workflow-demo branch

The demo is explicit, uses the `rm_workflow_demo_` prefix and only
`artifacts/workflow_demo` paths, and never falls back to default
workflow/audit paths.  Reset is explicit; enter/exit clears only the demo
namespace.  It is optional, not a sixth guided step.

## Current artifact reconciliation

Canonical settings are seed `42`, `5,000` customers, observation months
`1–12`, future months `13–36`, and Top-K `200`.  The current
`rm_selection_manifest.v1` run is
`seed42_crossfit_5fold_asof12_unbounded`:

| Check | Current value |
| --- | --- |
| Records / unique customers | 5,000 / 5,000 |
| Selected for review | 1,522 |
| Not queue eligible | 3,478 |
| Reconciliation | Exact; no missing, duplicate, or unexpected IDs |
| Capacity scenario | `unbounded_demo`; not automatically chosen |
| Default workflow/audit | Directories absent; 0 cases / 0 audit events |

The saved funnel is `eligible_priority=1,148`, `eligible_review=374`,
`eligible_total=1,522`, `selected_queue_ready=1,522`,
`monitor_only=371`, `no_actionable_signal=3,107`, and
`monitored_total=5,000`; unavailable, deferred-capacity, and
insufficient-evidence are all zero.

The isolated demo runtime is `DEMO_READY`, with three cases
(`CLOSED`, `IN_REVIEW`, `NEW`) and eight audit events.  Its live hashes
differ from reset-manifest hashes because intentional demo actions happened
after reset.  This is expected mutable runtime evidence: do not reset or edit
it.  The fixture remains three initial NEW cases with no future-label selection,
network call, sent message, or external delivery attempt.

## Required guided-workflow contract

There is currently no persisted guided state model.  Thus `NOT_APPLICABLE`
below denotes this audit's lack of an active guided session, not a customer
outcome.  Future work must use only:
`COMPLETE`, `CURRENT`, `AVAILABLE`, `BLOCKED`, `NOT_APPLICABLE`.

| Ordinal / step_id | Baseline status | Completion condition | Next action | Block reason | Source evidence | Safe to proceed | Target tab |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 `PORTFOLIO_CAPACITY` | `NOT_APPLICABLE` | Usable saved artifact + exact reconciliation; user acknowledges a human-entered draft capacity comparison; queue unchanged. | Select visible operational Queue row. | Missing/invalid artifact or acknowledgement. | Manifest, funnel, capacity comparison. | Only after acknowledgement; comparison never approves selection. | `portfolio_capacity` |
| 2 `QUEUE_SELECTION` | `NOT_APPLICABLE` | Visible operational Queue row safely selected; representative never counts. | Open Customer Review. | No eligible visible row, unsafe ID, or no selection. | Filtered queue and operational predicate. | Only for resolved operational customer. | `queue_selection` |
| 3 `CUSTOMER_EVIDENCE_REVIEW` | `NOT_APPLICABLE` | Operational review available and user UI-only acknowledges Selection Reason / Why Now. | Review existing case/action availability. | No operational customer, evidence unavailable, or acknowledgement absent. | Observation-only review model. | Only within no-future-label boundary. | `customer_evidence_review` |
| 4 `RM_ACTION` | `NOT_APPLICABLE` | Existing Case plus successful Banker action, or current case audit confirms relevant action. | Open Activity/Audit; Preview supports only. | Selected customer without a case is `BLOCKED`; never auto-alert/case. | Existing case, Banker result, case audit. | Only after legitimate existing-case outcome. | `rm_action` |
| 5 `AUDIT_PREVIEW` | `NOT_APPLICABLE` | Activity/Audit available and user acknowledges relevant audit record; Preview is never delivery. | Finish or deliberately enter optional demo. | Activity/audit unavailable or acknowledgement absent. | Read-only activity and offline Preview. | Read-only acknowledgement; no external send. | `audit_preview` |

## Required state and navigation behavior

14-02 must introduce a pure view model and reserve a separate `rm_guided_`
namespace, for example `rm_guided_state`, `rm_guided_customer_id`,
`rm_guided_customer_origin`, `rm_guided_step_statuses`,
`rm_guided_acknowledgements`, `rm_guided_last_action`, and
`rm_guided_requested_target_tab`.  It must not reuse `rm_workflow_demo_` or
implicitly treat ordinary RM workspace context as guided state.

Each step must expose ordinal, status, completion condition, next action, block
reason, source evidence, safe-to-proceed, and target-tab ID.  Acknowledgements
are UI-only: never mutate policy, triage selection, alert, case, audit,
capacity, or delivery state.

Installed Streamlit 1.57.0 exposes keyed/default/on-change `st.tabs`, but the
project range starts at 1.36 and the app currently calls unkeyed `st.tabs`.
14-03 must prove an official API route over the supported range, or use a
truthful target-tab CTA fallback.  DOM/JavaScript tab hacks are prohibited.

## Gaps found before implementation

1. No `rm_guided_*` state, step status, acknowledgement, completion, or block
   reason exists.
2. `rm_workspace_requested_tab` is written in Portfolio/Queue but never read
   to navigate.
3. `rm_queue_scope` is collected but is not provided to the queue view-model.
   It must be retired or defined truthfully with tests, never broadened to all
   customers.
4. Representative versus operational origin is not explicitly preserved in
   current customer context.
5. The normal no-case baseline lacks guided `BLOCKED` explanation; it must
   retain no-auto-case/no-auto-alert behavior.
6. Action controls, Activity/Audit, and Preview need honest guided handoff.

## Deferred, non-blocking drift

Historical 13-06/13-07 gate reports describe an earlier uninitialized
demo/default condition while this audit records current isolated
`DEMO_READY` runtime.  `PROJECT_HANDOFF.md` opens with the older
`c68c8cc` baseline.  Documentation/manual alignment, including manual Edge
rehearsal marked `NOT_RUN`, belongs to 14-07.  This does not block the
engineering audit, but prevents unqualified visual/manual sign-off until 14-07.

## Verification

```text
pytest tests/test_rm_workspace.py tests/test_rm_customer_review.py tests/test_capacity_scenarios.py tests/test_workflow_demo.py tests/test_workflow_demo_ui.py tests/test_workflow_demo_actions.py -q
57 passed in 30.31s

pytest -q
486 passed in 216.29s (0:03:36)

python scripts/check_demo_readiness.py
READY_WITH_WARNINGS
  Python 3.10.9 vs project target 3.11; OPENAI_API_KEY unset with template fallback.
  All remaining checks READY.

python scripts/start_streamlit.py --port 8519 --timeout 60
Healthy; smoke complete and temporary server stopped.
```

## Next-step boundary

This audit authorizes consideration of **14-02 only**.  It does not execute
14-02, change product behavior, or authorize 14-03 through 14-07.
