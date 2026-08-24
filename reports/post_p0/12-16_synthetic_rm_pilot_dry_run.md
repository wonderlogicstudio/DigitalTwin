# 12-16 Synthetic RM Pilot Dry Run

## Result

**GO.** An isolated synthetic rehearsal now verifies the existing selection,
capacity, Alert/Case, Banker, audit, measurement, and offline-preview
contracts together. It is an engineering readiness check, not an actual RM
pilot or evidence of a customer outcome.

## Isolated seed-42 rehearsal

The checked-in run is
`artifacts/post_p0/pilot_dry_run/seed42_capacity_3/`. It reads the saved
selection manifest and representative cohort without changing either source.

| Check | Result |
| --- | --- |
| Caller-supplied comparison capacity | 3, `draft`, not automatically approved |
| Eligible / selected / deferred | 1,522 / 3 / 1,519 |
| Workflow sample | first 3 saved-rank selected records only; selection ranking was not recomputed |
| Initial rehearsal decisions | 5: 3 selected/new cases + 2 non-review skips |
| Duplicate signal | 3 existing routes, 0 new cases, 0 failures |
| Active snooze repeat | 1 no-op, 0 new cases |
| Workflow state sample | 3 synthetic cases: 1 closed, 1 in review, 1 snoozed |
| Append-only audit | 10 events |
| Measurement capture | 3 synthetic records; 2 completed reviews per declared period |
| Notification | Preview only; sent=false, external delivery=false, network=false |

The selection-manifest and representative-cohort SHA-256 values were equal
before and after the run. The run output contains aggregate summaries and
isolated synthetic workflow/audit files only; it does not overwrite the
canonical analytics, population, or triage artifacts.

## Failure-path evidence

- No historical landmark is handled without using a historical landmark as a
  live trigger.
- Insufficient evidence is recorded as a synthetic measurement only; no case
  is created.
- Duplicate signal and active-snooze repetition create no duplicate case.
- A non-review/no-action decision creates no case.
- An unavailable offline Preview is handled without changing case or audit
  state.

## Boundaries

- The capacity value is a caller-supplied rehearsal input, not an approved RM
  workload or bank standard.
- Measurement times and counts are instrumentation only, not RM productivity
  or SLA evidence.
- The deterministic actor/reference is synthetic; no RM participant or
  customer data is present.
- No policy or capacity becomes approved from this run, and no financial
  intervention effect is claimed.

## Verification

- Focused synthetic dry-run/capacity/Alert/Banker/audit/notification suite:
  **59 passed in 1.65s**.
- Full regression: **459 passed in 229.49s**.
- Bounded Streamlit health check on port 8519 passed; the temporary server
  stopped cleanly.
