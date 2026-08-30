# Synthetic Financial Universe v2

## Decision

This document defines a new deterministic baseline for the 5,000-customer
synthetic Financial Path Twin universe. It supersedes the prior data-generation
baseline only. The customer count, monthly CSV column schemas, 36-month horizon,
months 1–12 observation window, months 13–36 future window, feature engineering,
weighted nearest-neighbour matching, outcome rules, breakpoint rules, and
what-if rules remain unchanged.

Daily Review continues to read saved Monthly Snapshots only. It does not use a
persona, a new risk score, or a live analytics call to select work.

## Why a new baseline is needed

Read-only review of the previous deterministic 5,000-customer data and the
saved 300-customer RM Snapshot found two separate issues:

| Observation | Measured evidence | Interpretation |
| --- | --- | --- |
| Breakpoint factor concentration | Of 107 `found` records, 84 (78.5%) used `variable_expense_ratio`, 22 (20.6%) used `cash_balance_ratio`, and 1 used `savings_rate`. | The prior generator did not create a sufficiently balanced variety of financial paths for a demonstration of timing evidence. |
| Breakpoint timing concentration | All 107 `found` records had `months_from_current = 1`. | Future pressures began in too similar a part of the horizon; this is unsuitable for explaining Review Now versus Upcoming as naturally different timings. |
| Screen-level cash repetition | Every one of the 300 saved records put `cash_availability` first in `current_change_cards`, even where the primary factor was variable expense. | This was a saved-card ordering issue, not proof that every customer had the same cash-related analysis result. The Daily list must prefer the actual saved primary factor. |

The new generator is not calibrated to produce a target number of Daily items,
breakpoints, or outcomes. Those counts remain observed outputs.

## Synthetic financial-path archetypes

The following values remain in the existing `persona` column; no core column is
added. They are path-generation inputs, not CRM labels and not a statement about
a real customer.

| Persona | Share | Synthetic path purpose |
| --- | ---: | --- |
| `stable` | 20% | Stable income, moderate expenses, and improving/steady cash. |
| `gradual_deterioration` | 15% | Modest early pressure followed by varied fixed-cost and debt pressure after the observation window. |
| `event_shock` | 15% | Existing discrete employment, medical, housing, childbirth, or rate-shock pattern. |
| `recovery` | 12% | Existing pressure then recovery pattern. |
| `overspending` | 13% | Variable-cost acceleration beginning at a deterministic but varied future month. |
| `self_employed` | 12% | **Synthetic business-income variability**: seasonal and volatile income/expense flow. It is not a real job or business record. |
| `asset_resilient` | 8% | **Synthetic liquidity-resilient path**: higher income/cash-buffer range and lower debt pressure. It is not AUM, wealth, VIP, or CRM classification. |
| `financially_constrained` | 5% | **Synthetic financially constrained path**: lower buffer and higher fixed/debt exposure with varied future pressure. It is not a judgment about a real person. |

The shares sum to 100% and deterministically yield 5,000 rows with seed 42.

## Generation rules

1. Initial income, cash buffer, loan likelihood/amount, and expense ratios are
   drawn from deterministic persona-specific ranges.
2. The underlying raw data columns remain exactly the existing customer-master
   and monthly schemas. No AUM, occupation, VIP, CRM rank, or external data is
   introduced.
3. `self_employed` adds deterministic seasonal/volatile financial flow; it does
   not add an employment field.
4. `asset_resilient` represents a synthetic buffer profile only; it must never
   be presented as a wealthy customer or relationship priority.
5. For gradual deterioration, overspending, and financially constrained paths,
   future pressure starts on a deterministic customer-specific month within the
   13–24 range. This distributes the generated path timing without manipulating
   breakpoint thresholds or Daily workload counts.
6. Existing event/outcome/breakpoint/matching/what-if code receives the
   generated data unchanged; it is neither copied nor retuned.

## Acceptance checks

- 5,000 master rows and 180,000 monthly rows; 36 months per customer.
- Existing master/monthly column lists remain unchanged.
- Same seed reproduces the data exactly; a different seed changes it.
- All configured personas appear at their configured deterministic counts.
- The income, cash-buffer, expense, debt, and income-volatility distributions
  differ across archetypes without a hidden Daily selection score.
- The regenerated universe passes the existing validator, pipeline, matching,
  breakpoint, what-if, General Mode, Presentation Mode, and Daily boundary tests.
- A new RM Monthly Snapshot is explicitly built from the regenerated universe;
  Daily never rebuilds it automatically.

## Non-goals

- No target such as “7 / 18 / 275” is used.
- No change is made to risk thresholds, matching weights, outcome rules,
  breakpoint persistence/group size, or What-if formulas.
- No real-person segmentation, actual business classification, AUM, CRM,
  case/alert, capacity, queue, or automatic contact is added.
