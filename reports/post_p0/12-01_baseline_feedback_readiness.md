# 12-01 Post-P0 Baseline Feedback Readiness

**Gate result:** `GO` with documented non-blocking provenance and documentation drift.
**Baseline date:** 2026-08-24
**Repository state:** `main` / `c68c8cc79561e1a33d9a3e5031a29285cb8342db` equals fetched `origin/main`; the worktree was clean before this report was added.

## Scope

This is a read-and-verify baseline for the feedback-closure work. It does not
change canonical analytics, synthetic inputs, selection policy, capacity,
workflow state, or application calculations. Its companion machine-readable
snapshot is `artifacts/post_p0/baseline/feedback_readiness_manifest.json`.

## Canonical contract confirmed

| Contract | Observed value |
| --- | --- |
| Canonical population / seed | 5,000 customers / 42 |
| Timeline | 36 months; observation 1-12; peer future 13-36 |
| Matching | 10 weighted match features; `TOP_K_MATCHES=200` |
| Breakpoint | absolute SMD threshold 0.5; persistence 2; minimum group size 20 |
| What-if | 24-month rule-based cashflow simulation; four existing scenarios |
| App modes | General; Presentation with exactly five tabs; separate RM Workspace with exactly four tabs |

`config/settings.py`, code, and current contract tests agree on these values.
No canonical file or production setting was changed in this step.

## Artifact reconciliation

The detail-derived customer-ID comparison succeeded. The common sorted-ID
digest is `a501403bc78b04a6fb0f39a78488c519b650b96e68a430a221c298e011510a90`.

| Source | Unique IDs | Duplicate IDs | Missing / extra versus canonical |
| --- | ---: | ---: | ---: |
| `data/raw/customer_master.csv` | 5,000 | 0 | 0 / 0 |
| `data/raw/customer_monthly_5000.csv` | 5,000 | 0 | 0 / 0 |
| Population detail | 5,000 | 0 | 0 / 0 |
| Triage selection manifest records | 5,000 | 0 | 0 / 0 |

The monthly source has 180,000 rows and every customer has exactly 36 months.
Population detail has 5,000 successful records, all with 200 matches. Outcome
shares sum to one and distance min/mean/max ordering is valid for all records.
Breakpoint results are `found=1,732` and `insufficient_group_size=3,268`;
the latter remains an explicit safe non-finding, not a failure.

Triage funnel reconciliation is exact: 1,148 Priority Review, 374 Review,
1,522 selected queue-ready, 371 Monitor-only, and 3,107 no-actionable-signal.
The 1,522 selected records have ranks 1 through 1,522 with no gaps and all
have selection reasons, why-now reasons, prospective timing references, and
policy provenance. The representative cohort contains three deterministic
records and one honestly unavailable category.

## Workflow baseline state

No persisted runtime case repository or audit log exists under
`artifacts/workflow/` or `artifacts/audit/` in this clean baseline. Therefore
the persisted Alert and Audit customer sets are empty, have no broken
references, and do not constitute a full 5,000-customer Alert-cycle artifact.
This is not treated as a successful operational run. It is an explicit open
baseline fact: Alert-to-Audit behavior is evidenced by the passing focused and
full contract tests, while a later feedback-closure workflow step must retain
or create its own isolated run evidence if needed.

## Validation and application checks

- Circularity negative-control report: 61 eligible cohorts; original
  breakpoint found rate 61/61, seed-permuted control 0/61. This is
  synthetic-only internal evidence, not bank-performance evidence.
- Sensitivity report: validation seeds 7/42/99 and K grid 100/200/300;
  canonical input integrity is unchanged and production `TOP_K_MATCHES=200`
  remains unchanged.
- BAT-equivalent import preflight passed for
  `src.presentation_population.build_presentation_current_review_signal`.
  The legacy re-export and `import app` also passed, so the earlier
  presentation-helper ImportError did not reproduce.
- `python scripts/check_demo_readiness.py` returned `READY_WITH_WARNINGS`:
  Python is 3.10.9 while the documented target is 3.11, and no
  `OPENAI_API_KEY` is set. Required packages, data, demo cache, cached
  customer `C002608` with 200 matches, and port 8501 were ready. The template
  fallback makes the missing optional key non-blocking.
- The bounded launcher reported healthy Streamlit on port 8519 and stopped its
  temporary server.

## Test evidence

| Command or suite | Result |
| --- | --- |
| Population / triage / workflow / RM focused suite | 87 passed in 22.92s |
| Leakage / as-of / reference-only / policy / validation focused suite | 46 passed in 15.74s |
| Full `pytest -q` | 390 passed in 211.26s |
| Bounded Streamlit health | passed |
| `git diff --check` before report creation | passed |

The initially attempted methodology command named a non-existent historical
test filename, `tests/test_prospective_evaluator.py`; it did not run tests or
modify code. It was immediately corrected to the current test layout above.

## Recorded drift and open findings

1. Population and selection artifacts record `code_ref=bfc8d81...`, while the
   current committed baseline is `c68c8cc...`. Their settings snapshots,
   schemas, and ID reconciliations agree with current contracts, but the
   original artifacts were generated in the pre-commit P0 worktree. This is a
   provenance limitation, not a detected numeric or schema drift.
2. `PROJECT_HANDOFF.md` still describes `bfc8d81` and an uncommitted P0
   worktree; `CURRENT_ARCHITECTURE_COMPARISON.md` still compares GitHub at
   `bfc8d81` with a local worktree. Those statements are stale because P0 is
   now committed and pushed as `c68c8cc`. This step records rather than edits
   them; documentation synchronization belongs to a later step.
3. Population and triage manifests retain absolute local output paths. Current
   loaders resolve the artifact directory safely, but those provenance strings
   are not clone-portable.
4. Canonical raw and processed synthetic inputs are ignored by Git and are
   regenerated through the pipeline. Checked-in Population and Triage reports
   are therefore evidence artifacts, not replacements for pipeline inputs.

## Baseline conclusion

The code, canonical contract, Population/Triage exact coverage, app startup,
and test suites are ready to serve as the Post-P0 feedback-closure baseline.
The recorded drift items are explicit follow-up inputs, not permission to
overstate synthetic validation, capacity, external notification delivery, or
real-data readiness.
