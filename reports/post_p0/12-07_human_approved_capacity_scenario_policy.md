# 12-07 Human-approved Capacity Scenario Policy

## Result

**GO.** RM capacity is now an explicit, comparison-only input over the saved
triage rank order. The app never treats the 1,522 unbounded-demo customers as
an operating workload standard and never chooses a capacity automatically.

## Contract

- `max_reviews_per_cycle=None` remains the explicit source unbounded-demo
  reference. It is not a persistent RM default.
- `CapacityScenario` supports only `comparison_only` scope. Its default status
  is `draft`; `approved` is rejected unless an approval-evidence reference is
  supplied. The UI creates draft scenarios only.
- A capacity changes only the saved rank-prefix cutoff. It does not rerun
  policy/scoring, change the lexicographic tuple, alter the source manifest,
  create Alerts, or mutate the operational queue.
- The Portfolio has an opt-in **human-entered capacity comparison**. It shows
  the unbounded reference and the current draft input side by side, including
  selected/deferred counts, Priority/Review composition, coverage, and a
  one-cycle carry-over count. Carry-over is explicitly not an SLA or RM
  productivity estimate.

## Boundary comparison artifact

`artifacts/post_p0/capacity/seed42_boundary_comparison.json` was created from
the saved seed-42 selection detail only. The listed values are draft boundary
checks, not a workload recommendation or approval.

| Scenario | Status | Capacity | Selected | Deferred | Coverage |
| --- | --- | ---: | ---: | ---: | ---: |
| Source unbounded reference | demo | unbounded | 1,522 | 0 | 100.00% |
| Boundary zero | draft | 0 | 0 | 1,522 | 0.00% |
| Boundary one | draft | 1 | 1 | 1,521 | 0.07% |
| At eligible count | draft | 1,522 | 1,522 | 0 | 100.00% |
| Above eligible count | draft | 1,523 | 1,522 | 0 | 100.00% |

The saved eligible composition is 1,148 Priority Review and 374 Review. The
capacity-one scenario selects the first saved Priority Review only. It proves
the cutoff behavior; it does not imply that one review per cycle is suitable.

## Reconciliation and isolation

- Detail-derived record count = monitored total = **5,000**.
- Detail-derived ranked eligible count = manifest eligible total = **1,522**.
- Customer-ID digest remains `a501403b...011510a90`; ranked-order digest is
  `5b3e8542...6faa31ef` for every scenario.
- The comparison output is in `artifacts/post_p0/capacity/`; the canonical
  `data/` paths and `artifacts/triage/` source manifest were read only.
- The capacity service has no Streamlit, matcher, evaluator, future-label,
  persona, notification, Alert, or case-workflow dependency.

## Verification

- Capacity service and CLI contract tests: `11 passed`.
- Capacity/RM/i18n/legacy selection focused suite: `49 passed`.
- Full regression: `409 passed in 226.21s`.
- Bounded Streamlit health check on port 8519: passed.

## Remaining boundary

No human-approved operational capacity has been configured. A real approval
must be supplied by the responsible business/governance process; this feature
only makes the resulting selected/deferred trade-off visible and reproducible.
