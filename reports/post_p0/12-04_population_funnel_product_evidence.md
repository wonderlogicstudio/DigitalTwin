# 12-04 Population Triage Funnel Product Evidence

## Result

**GO.** The RM Workspace Portfolio and Review Queue now expose the persisted
selection-manifest funnel without re-running analytics, triage, ranking, or
workflow mutation. The source remains synthetic-only and the demonstrated
unbounded capacity scenario is not an approved RM workload.

## Product contract

| Surface | Saved source | Display contract |
| --- | --- | --- |
| Portfolio funnel | `rm_selection_manifest.json` `funnel` | Every displayed count is manifest-derived: monitored, Priority/Review eligibility, selected, deferred, monitor, no-actionable, insufficient-evidence, and data-unavailable. |
| Review Queue | `records` in the same manifest | Only `SELECTED_FOR_REVIEW` plus `CREATE_NEW_CASE`/`ROUTE_EXISTING_CASE` records; no Monitor or non-actionable row is made operational. |
| Customer Review | Queue customer context | Context originates at the selected manifest row and is handed to the existing display-only review model. |
| Provenance caption | Saved manifest metadata | Policy ID/version, as-of month, and signal run are shown without changing the saved decision. |
| Missing/partial/corrupt artifact | Read-only loader | Counts are unavailable; the shell does not substitute `settings.CUSTOMER_COUNT` or infer a successful 5,000-person run. |

## Persisted seed-42 evidence

The tested persisted source is
`artifacts/triage/seed42_crossfit_5fold_asof12_unbounded/rm_selection_manifest.json`.
Its 5,000 customer IDs exactly equal the population detail IDs, with zero
duplicates, missing IDs, or unexpected IDs.

| Funnel value | Count |
| --- | ---: |
| Monitored customers | 5,000 |
| Priority Review eligible | 1,148 |
| Review eligible | 374 |
| Eligible / selected queue | 1,522 / 1,522 |
| Deferred by capacity | 0 |
| Monitor only | 371 |
| No actionable signal | 3,107 |
| Insufficient evidence / data unavailable | 0 / 0 |

The Portfolio reconciliation returned `is_exact=true`, `record_count=5,000`,
`selected_count=1,522`, and `unique_customer_ids=true`. Its saved provenance
is `transparent_triage_selection_demo v0.1.0`, as-of month 12, signal run
`crossfit_seed42_5fold_asof12`, and capacity scenario `unbounded_demo`.

## Additive hardening

- Added explicit `data_unavailable` funnel display rather than folding a
  non-zero value into an insufficient-evidence label.
- Treat incomplete selection manifests as unavailable.
- Do not display a default 5,000 population count when the artifact is absent.
- Added product-source tests that compare the persisted population detail,
  triage manifest, RM view model, queue count, and saved provenance directly.

No generator, feature, matching, outcome, breakpoint, What-if, policy,
ranking, capacity, canonical data, or analytics artifact was changed.

## Verification

- RM Portfolio/Queue, RM Workspace, Presentation, and Customer Review focused
  suite: `46 passed`.
- Bounded Streamlit health check: passed on port 8519.
- Full regression and diff checks are recorded in the step completion report.

## Remaining boundary

This is reproducible synthetic product evidence, not evidence of bank
prediction accuracy, RM productivity, intervention efficacy, or an approved
real-world queue capacity.
