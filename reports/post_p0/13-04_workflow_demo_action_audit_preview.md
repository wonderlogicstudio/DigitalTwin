# 13-04 — Demo Banker Action / Audit / Notification Preview

## Result

GO — the explicit Synthetic Workflow Demo can now exercise the existing
Banker application boundary without changing the default RM workspace.

## Scope

The only mutable roots for this step are created after an explicit user
initialization under:

artifacts/workflow_demo/runtime/{workflow,audit}

They are not artifacts/workflow, artifacts/audit, canonical analytics
artifacts, or the triage manifest. The fixture has exactly three synthetic
Cases. Default RM still reads its normal empty workflow root and does not
create a Case for the 1,522 selected customers.

## UI flow

1. In RM Workspace, choose **Open Synthetic Workflow Demo**.
2. Review the synthetic-only banner, then explicitly initialize the fixture.
3. Select one of the three synthetic Cases.
4. Use only actions permitted by the Case's current state:
   NEW → Acknowledge → ACKNOWLEDGED → Start Review → IN_REVIEW → Set Follow-up.
   A staff action may be recorded for an open Case and an explicit closure may
   be recorded through the existing Banker service.
5. Inspect the time-ordered, append-only demo audit and the collapsed offline
   Notification Preview.
6. Use reset to discard the synthetic session and restore all three Cases to
   NEW, or return to the ordinary RM workspace.

Reopen is deliberately not offered in this demonstration. Existing reopen
semantics create another Case, which would violate the fixed maximum-three
fixture contract. Reset is the honest way to restart the scripted demo.

## Boundaries

- The service is a separate session object named rm_workflow_demo_service;
  it is constructed with the explicit demo workflow and audit roots.
- UI mutations call perform_rm_workflow_operation() only. The UI has no
  direct Alert repository or audit store writes.
- Submission tokens include the workflow_demo namespace, alert ID, expected
  state, operation, and selected action/outcome. Identical retries replay
  without a second state effect or audit event; changed payloads with the same
  token fail closed.
- Recommended Follow-up remains a human review proposal. It does not make a
  financial decision or auto-execute an action. What-if is labelled
  simulation-only supporting evidence.
- Historical landmarks remain retrospective peer evidence, not alert triggers
  or an individual future date.
- Notification Preview remains PREVIEW, sent=false,
  external_delivery_attempted=false, and network=false. It changes neither
  Case nor audit state and exposes no channel selector.

## Reconciliation checks

The focused test suite verifies:

- runtime Case count remains three or fewer;
- audit event IDs, customer IDs, state transitions, and sequence ordering
  reconcile with the selected synthetic Case;
- duplicate replay produces zero additional audit events;
- stale expected state and token/payload conflicts fail closed;
- Preview produces zero Case/audit delta and no network delivery;
- reset invalidates the old demo service ledger and restores the three initial
  NEW Cases with no audit log;
- default workflow/audit roots and protected canonical/triage sources are
  unchanged by injected-runtime tests.

## Out of scope

This is an offline synthetic rehearsal only. It does not create operational
Cases for the 1,522 selected customers, prove actual RM performance, send a
message, use a database, or validate on customer data.
