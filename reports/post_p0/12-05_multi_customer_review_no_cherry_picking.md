# 12-05 Multi-customer Review and No-cherry-picking Proof

## Result

**GO.** RM review is not confined to a manually chosen customer. The Review
Queue exposes every selected/routed record from the persisted manifest, and
the four comparison categories are deterministic outputs of the fixed triage
universe rather than outcome-aware examples.

## Reproducible multi-customer flow

1. The persisted selection manifest records all 5,000 universe customers.
2. The Review Queue includes only `SELECTED_FOR_REVIEW` records with
   `CREATE_NEW_CASE` or `ROUTE_EXISTING_CASE`; persisted source count is 1,522.
3. A queue row may set a safe Customer Review context only if it remains a
   visible operational row.
4. Representative quick-selects are comparison contexts, not queue rows. A
   representative ID must be present in the saved manifest before routing is
   allowed.
5. A representative switch reruns the RM context only when the target differs.
   The Customer Review source is rebuilt for that ID; General/Presentation
   `selected_customer_id` and live analytics are not used by RM rendering.

The RM AppTest performed the persisted route `early_signal_review` to
`priority_review` and observed Customer Review headers `C000007` then
`C000001`, demonstrating that a prior context is not reused.

## Representative cohort proof

The persisted cohort has exactly one record in this fixed order:

| Category | Status | Saved source condition |
| --- | --- | --- |
| `priority_review` | selected | `ELIGIBLE_PRIORITY` / `Priority Review` |
| `early_signal_review` | selected | `ELIGIBLE_REVIEW` / `Review` with prospective timing reference |
| `monitor_no_alert_comparison` | selected | `MONITOR_ONLY` preferred over no-actionable comparison |
| `insufficient_or_landmark_not_found` | unavailable | No fixed-universe customer met the category rule; no condition was changed. |

For every selected representative, tests reconcile the saved customer ID,
primary disposition, operational label, signal run, and as-of month back to
the persisted selection-manifest record. The unavailable record has no
customer ID and is kept visibly unavailable.

The persisted selection rules state:

- `uses_triage_universe_only=true`
- `uses_operational_selection_result=false`
- `capacity_independent=true`
- Stable final tie-breaker: customer ID ascending after category evidence order
- Unavailable categories are not filled by modifying customer conditions.

`src.selection_manifest` remains isolated from `final_outcome`, persona,
evaluator, Streamlit, legacy demo-selector, and notification/provider imports;
the focused contract suite verifies this boundary.

## Additive hardening

- Representative quick-selects now retain their saved explanation for display.
- A cohort customer outside the selection manifest is explicitly unavailable
  and cannot become a Customer Review context.
- RM routing now compares the requested and current customer before rerunning,
  preventing stale representative context after a customer switch.

No selection policy, ranking, capacity, generator, canonical data, analytics,
or representative category rule was tuned or changed.

## Verification

- Representative selection, triage, RM Portfolio/Queue, Customer Review, and
  multi-customer AppTest suite: `44 passed`.
- Full regression and bounded app health are recorded in the step completion
  report.

## Remaining boundary

Representative cases make the synthetic workflow reviewable across distinct
states. They do not establish real customer outcomes, approved workload,
intervention efficacy, or production RM performance.
