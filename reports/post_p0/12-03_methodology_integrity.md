# 12-03 Methodology Leakage Robustness Regression Hardening

**Gate result:** `GO`

## Scope

This step adds no calculation, threshold, generator, policy, ranking, or
capacity change. It audits the existing methodology safety net and records the
actual current test ownership rather than relying on an earlier test-module
count. No additional regression test was needed because every required
critical invariant has direct focused coverage below.

## Test ownership matrix

| Critical invariant | Production boundary | Existing focused regression evidence | Result |
| --- | --- | --- | --- |
| Month-12 legacy feature parity | `src/as_of_features.py` | `test_as_of_month_12_has_exact_legacy_feature_parity` | pass |
| Future mutation and deletion cannot change as-of features | `src/as_of_features.py` | `test_future_mutation_and_deletion_do_not_change_month_12_features`; `test_data_after_any_as_of_month_does_not_change_features` | pass |
| As-of builder does not require persona or final outcome | `src/as_of_features.py` | `test_as_of_builder_never_requires_persona_or_final_outcome` | pass |
| Scaler fits reference rows only; target is excluded | `src/reference_matcher.py` | `test_scaler_fit_receives_reference_features_only`; `test_target_id_in_reference_is_rejected` | pass |
| Matching ignores target future/persona/final outcome and is deterministic | `src/reference_matcher.py` | `test_future_mutation_does_not_affect_as_of_reference_or_target_matching`; `test_persona_and_final_outcome_columns_do_not_affect_matching`; `test_neighbors_are_deterministic` | pass |
| Cross-fit folds are complete and disjoint | `src/crossfit_backtest.py` | `test_deterministic_folds_are_disjoint_complete_and_excluded_from_scaler_fit`; `test_crossfit_manifest_reconciles_all_expected_customer_months` | pass |
| Scorer/evaluator label boundary is enforced | `src/crossfit_backtest.py`, `src/prospective_evaluator.py` | `test_scorer_has_no_label_access_while_evaluator_opens_labels`; `test_target_future_mutation_before_evaluator_does_not_change_its_snapshot` | pass |
| Signal snapshots/history do not access labels or future data | `src/prospective_signals.py` | `test_snapshot_does_not_access_final_outcome_or_persona`; `test_future_mutation_does_not_change_current_or_prior_snapshot`; `test_snapshot_and_history_are_deterministic` | pass |
| Policy, triage, ranking, and representative selection have no future-label route | `src/demo_policy.py`, `src/triage_universe.py`, `src/triage_selector.py`, `src/selection_manifest.py` | Policy/triage/selector/manifest dependency and deterministic-selection tests | pass |
| Historical landmark cannot be a live trigger | `src/demo_policy.py`, `src/triage_universe.py`, `src/rm_customer_review.py` | `test_historical_landmark_cannot_be_created_as_a_live_trigger`; `test_historical_landmark_is_never_a_policy_trigger`; retrospective Customer Review tests | pass |
| Insufficient comparison cohort remains an explicit non-finding | `src/breakpoint_analyzer.py` | `test_group_size_19_returns_insufficient_group_size` | pass |
| Circularity control, sensitivity isolation, and canonical-input integrity hold | validation-only modules | Circularity reproducibility/weakening, sensitivity isolation/checksum/settings, and canonical-output rejection tests | pass |

The prospective domain modules listed above have no Streamlit imports. The
only intentional target-label/future-event access is in
`src/prospective_evaluator.py`, after scoring, where it is covered by the
scorer/evaluator separation tests.

## Current evidence and provenance

- The current focused methodology suite contains **76 tests** and passed on
  this run.
- The circularity report retains synthetic-only scope: 61 eligible cohorts,
  61 original landmark findings, and 0 findings after the seed-permuted label
  control. It is falsification evidence within the synthetic generator, not
  real-bank validation.
- The sensitivity report retains seeds 7/42/99 and K 100/200/300 only in
  validation. Canonical input integrity is unchanged and production
  `TOP_K_MATCHES=200` is unchanged.
- Existing Population and Triage artifacts record a pre-commit `bfc8d81`
  code reference. This provenance warning remains recorded in 12-01; this
  step neither regenerates artifacts nor relabels their provenance.

## Hardening decision

No critical coverage gap was found. Adding duplicate tests would obscure the
existing contract ownership, so this step adds the matrix and runs the current
focused suite rather than altering production or test behavior.

## Claims boundary retained

- Historical matched-cohort outcome shares are not prediction probabilities.
- A historical breakpoint is retrospective cohort evidence, not a current
  customer's prospective trigger or future date.
- What-if remains a rule-based cashflow simulation, not intervention efficacy.
- Triage and representative selection do not use target month 13-36 data,
  `final_outcome`, persona, or evaluator labels.
- `insufficient_group_size` is an honest non-finding, never an error to tune
  away by changing the generator, threshold, or cohort rules.
