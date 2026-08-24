# 12-14 Synthetic vs Approved-real Validation Metrics Contract

## Result

**GO — predeclared aggregate metric contract only.** The report separates
synthetic, approved-real and comparison sections while making the approved-real
section explicitly absent and unvalidated by default.

## Evidence

- Eleven fixed comparison axes cover coverage, distributions, historical cohort
  shares, alert/timing behavior, triage capacity and insufficient evidence.
- Denominators are encoded in the aggregate input contract; review episodes per
  1,000 customer-months and no-event rate have focused tests.
- Differing or unavailable outcome definitions disable direct outcome-dependent
  comparison. No single actual-accuracy score is available.
- Feature and match distribution deltas are descriptive only; no threshold,
  PSI, KS or bank standard is declared.
- The contract cannot score, select triage, create Alerts, read a dataset or
  export row-level values.

## Remaining boundary

Actual validation requires approvals, a secure environment and independent
outcome agreement. Supplying future aggregate values later does not alter the
canonical synthetic contract or prove intervention efficacy.

## Verification

- Metrics, harness, governance, timing and trade-off focused suite:
  **37 passed**.
- Full regression suite: **446 passed**.
- The checked-in template equals the source-free metrics-report template and
  remains explicitly `real_absent`.
