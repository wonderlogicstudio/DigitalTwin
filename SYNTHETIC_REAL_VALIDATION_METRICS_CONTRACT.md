# Synthetic vs Approved-real Validation Metrics Contract

## Purpose

This contract fixes the comparison axes before approved real-data aggregate
results exist. It is not a connector, bank-performance score, policy selector,
or claim that the synthetic prototype has been validated on customer data.

The report has three deliberately separate sections:

```text
synthetic aggregate metrics
approved-real aggregate metrics (optional; absent until approved work exists)
comparison compatibility and distribution deltas
```

No row-level values, customer identifiers, target outcome labels, or real data
are accepted by this report contract.

## Predeclared metric axes

| Axis | Definition |
|---|---|
| Coverage / missingness | Admitted and missing customer-month counts over expected customer-months. |
| Feature / trajectory shift | Per-feature mean, Q1, median and Q3; report deltas only when both aggregate sections exist. |
| Match distance / support | Distribution summaries for match distance and returned neighbor support count. |
| Historical cohort outcome shares | Descriptive matched-cohort shares, never a target prediction probability. |
| Alert rate | Review episodes per 1,000 declared customer-months. |
| Unique alerted / selected | Unique-alerted rate and triage-selected share reported separately. |
| No-event alert rate | No-event review episodes divided by review episodes. |
| Lead time | Median, Q1 and Q3 months only where independently defined outcomes/events are available. |
| Persistence / flip | Predeclared rates over the declared analysis period. |
| Triage / capacity | Selected, deferred, monitor, no-actionable-signal and insufficient-evidence shares under one declared scenario. |
| Insufficient evidence | Insufficient-evidence customers divided by all declared customers. |

The contract does not calculate PSI, KS, a threshold, a bank standard, or a
single “actual accuracy” score.

## Outcome compatibility gate

Outcome-dependent comparison is disabled when approved-real aggregate results
are absent, an outcome/event is unavailable, or the synthetic and approved-real
definitions have different predeclared comparison-basis IDs. It becomes
available only when the approved-real definition is independently agreed and
the basis IDs match. This is a compatibility flag, not evidence of accuracy.

`final_outcome` remains a synthetic analytical label. It must not become a
real-data ground truth by name or by substitution.

## Capacity and analytical boundaries

Capacity is recorded as a declared scenario with `draft`, `demo`, or explicitly
evidenced `approved` status. The report does not choose a capacity, policy,
threshold, triage disposition, Alert or RM queue.

The report accepts post-evaluation aggregate measurements only. It does not
receive as-of feature inputs, reference matcher inputs, policy inputs, triage
ranking inputs, target future rows, or evaluator label values. Historical
landmarks remain separate from prospective timing, and What-if is not an
intervention-effect measure.

## Template and output boundary

The checked-in template is
`artifacts/post_p0/real_data_readiness/synthetic_vs_real_validation_report_template.json`.
It explicitly marks approved-real results as absent and unvalidated. Future
aggregate report exports require an injected output root and atomic write; they
must not overwrite canonical data directories.
