# 12-09 Alert/Case Timely Delivery and SLA Review

## Result

**GO.** A selected, versioned `TriageDecision` is the only path that can
create or route an Alert/Case. The prototype defines delivery only as an open
case created and visible in the in-app RM work queue. It does not send, claim,
or depend on an external message.

## In-app delivery and due-window contract

- `AlertCreationPolicy` is versioned and now records `status`, rationale,
  limitations, and optional approval evidence. `approved` is rejected without
  an explicit approval-evidence reference.
- The default `alert_case_creation_demo v0.1.0` is **demo**, with a fixed
  24-hour due window. This is a configurable demonstration parameter, not an
  approved bank SLA, capacity standard, or external-delivery commitment.
- For a created case, `created_at`, `due_at`, priority, and state are persisted
  by the cycle and surfaced in the RM Queue. Queue rows distinguish
  `CASE_IN_RM_QUEUE` from `SELECTED_CASE_PENDING`; the latter is never
  presented as delivered.
- Existing episode deduplication, cooldown, snooze, resume, reopen, state
  transition, and idempotent rerun rules remain the lifecycle controls.

## Scope and safety boundaries

- Only `SELECTED_FOR_REVIEW` with `CREATE_NEW_CASE` or
  `ROUTE_EXISTING_CASE` reaches the Alert cycle. Deferred, Monitor,
  No-actionable-signal, and Insufficient-evidence decisions create no case.
- Preview/Null notification behavior remains offline-only. A skipped or failed
  preview does not mutate, close, delete, or otherwise change a case.
- No provider SDK, network call, credential, DB, or external channel was
  added. The Alert cycle retains no notification/provider dependency.
- This change does not alter the seed-42 analytics, 5,000-customer population,
  triage ranking, selection manifest, or canonical artifacts.

## Fixture reconciliation evidence

The delivery fixture contains five monitored customers, two selected queue
records, and one matching open Alert/Case:

| Measure | Count |
| --- | ---: |
| Monitored | 5 |
| Selected queue rows | 2 |
| Cases in in-app RM queue | 1 |
| Selected but case pending | 1 |
| Due / overdue matching cases | 1 / 1 |
| Monitor or non-selected queue rows | 0 |

The corresponding production selection source remains the read-only synthetic
seed-42 manifest: 5,000 monitored, 1,522 selected under its explicitly
unbounded demo scenario. It is not used here to create workflow files.

## Verification

- Lifecycle, due-window, dedupe, snooze/cooldown, repository, banker/audit,
  preview-independence, legacy queue rendering, RM Portfolio/Queue, and RM
  Workspace focused suite: **73 passed in 25.59s**.
- Full regression: **416 passed in 217.06s**.
- Bounded Streamlit health check: `python scripts\\start_streamlit.py --port
  8519 --timeout 60` passed; the temporary server stopped cleanly.

## Remaining boundary

No approved bank SLA, actual RM capacity, external notification delivery, or
real customer-data workflow is claimed. Those require separate business and
governance approval; this prototype only makes their future contract explicit.
