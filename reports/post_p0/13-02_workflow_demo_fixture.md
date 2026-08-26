# 13-02 Deterministic Synthetic Workflow Demo Fixture

## Result

`GO` — a three-case synthetic fixture and a separately mutable runtime are now
available. No Streamlit entry point is added in this step.

## Contract implemented

- Immutable source: `artifacts/workflow_demo/fixture_v1/workflow_demo_fixture.json`
- Mutable demo-only runtime: `artifacts/workflow_demo/runtime/`
- Maximum fixture/runtime cardinality: 3 cases; empty and oversized fixture
  inputs fail closed.
- Each fixture customer identifier is checked against the seed-42 synthetic
  customer universe by identifier only; this check performs no selection,
  scoring, or label lookup.
- Reset is explicit (`reset_demo(...)`) and never runs on import, default RM
  render, pipeline execution, or ordinary RM navigation.
- Every reset creates the same initial `NEW` cases, IDs, case ordering, UTC
  timestamps, due references, policy/signal provenance, and zero audit events.
- A reset marker prevents a partially rebuilt runtime from being treated as
  ready. The runtime manifest is written atomically only after staged cases
  validate.
- Missing runtime is `DEMO_NOT_INITIALIZED`; malformed manifest/repository is
  `DEMO_CORRUPT`. Neither state reads from `artifacts/workflow` or
  `artifacts/audit`.

## Safety boundary

The fixture is a deterministic synthetic demo source, not an alert cycle,
capacity approval, external delivery, real RM result, or customer outcome
claim. It preserves persisted policy/signal references solely as provenance.
It has no network, provider, credential, database, Streamlit, analytics
scoring, or selection implementation dependency.

The default RM roots remain `artifacts/workflow` and `artifacts/audit`; this
fixture uses neither. Canonical data, triage artifacts, representative cohort,
and default workflow/audit artifacts are not modified by fixture reset tests.

## Verification

- Focused workflow/repository/audit/RM suite: `43 passed`
- Full regression suite: `470 passed`
- Bounded Streamlit health check: passed (temporary server stopped)
- Readiness: `READY_WITH_WARNINGS` only for Python 3.10.9 versus the 3.11
  project target and an absent optional `OPENAI_API_KEY` fallback; data, cache,
  packages, and core C002608 smoke checks passed.

## Deferred to 13-03

The separate in-app entry/return UX, warning banner, and session-state
isolation have deliberately not been added yet. Step 13-03 must connect this
already-tested fixture only through an explicit user action.
