# Validation Dataset Adapter Harness Contract

## Scope

This is a provider-neutral, **synthetic-fixture-only** readiness harness. It
does not contain a bank connector, path reader, downloader, credential, network
client, real field mapping, or actual customer data. Actual data remains blocked
by [the governance contract](REAL_DATA_VALIDATION_GOVERNANCE.md).

## Logical boundary

```text
Injected synthetic fixture
        │ explicit source-to-canonical mapping
        ▼
Admitted validation dataset
        ├── ScoringObservationDataset ──► as-of features / reference matching / policy / triage
        └── EvaluatorOutcomeDataset ────► evaluator only, after scoring
```

`ScoringObservationDataset` excludes evaluator outcome/event fields by type and
by column selection. Triage does not receive `EvaluatorOutcomeDataset`. This
keeps the target’s future outcome/event unavailable to as-of scoring, reference
matching, policy and selection.

## Required mapping contract

An approved environment must provide an explicit, source-specific mapping for
these canonical scoring concepts only:

- pseudonymous `customer_id` and monthly `month` order;
- `income`, `total_expense`, `savings_amount`, `savings_rate`,
  `fixed_expense_ratio`, `dsr`, `cash_balance` and current `monthly_status`.

The contract checks non-empty pseudonymous IDs, unique customer/month rows,
integer order, full P0 comparison coverage (months 1–36), non-missing numeric
fields, accounting plausibility, and status availability. Missing periods,
duplicates and schema errors reject admission and are reported only as counts
and structural messages—never row-level values.

`evaluation_outcome` and `evaluation_event` are optional, separately mapped
evaluator fields. Outcome availability is reported, but outcome absence does not
turn into a scoring value or a synthetic label substitute.

## Data and artifact boundary

- Only injected synthetic DataFrames are accepted in this repository.
- No source-specific bank column is embedded in analytics modules; mapping is
  supplied at this harness boundary.
- Direct identifiers, contact details, addresses, account numbers and
  authentication credentials are forbidden mapping concepts.
- Report exports contain counts and structural errors only, use atomic writes,
  and require an injected output root. They cannot target canonical
  `data/raw`, `data/processed` or `data/demo`.
- The checked-in template is
  `artifacts/post_p0/real_data_readiness/validation_dataset_contract_template.json`.

## Approval-time work still required

Before an approved secure environment uses an actual dataset, the data owner
must independently agree its event/outcome definition and availability. This
must not reuse the synthetic `final_outcome` label as bank ground truth. Any
different coverage horizon needs a separately approved validation plan; it does
not alter the canonical P0 settings.

This harness does not make an actual-data claim, change the legacy analytics,
or authorize real-data processing.
