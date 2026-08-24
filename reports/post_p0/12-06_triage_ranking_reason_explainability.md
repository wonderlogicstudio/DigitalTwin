# 12-06 Triage Ranking Reason Explainability

## Result

**GO.** The RM display now translates every persisted triage reason code into
human-readable text and exposes the declared ordering structure without
re-ranking a customer or presenting a composite risk score.

## Actual selection-order inventory

The source is `default_triage_selection_policy()` in `src/triage_selector.py`.
The selector orders only already eligible candidates with this lexicographic
tuple, where lower tuple components appear first:

| Order | Dimension | Persisted source fields | Meaning |
| ---: | --- | --- | --- |
| 1 | Operational priority band | `operational_label`, `primary_disposition` | Priority Review before Review. |
| 2 | Prospective timing bucket | `timing_bucket` | Declared current-signal timing reference; never target future lead time. |
| 3 | Signal persistence | `signal_persistence` | Persistent before non-persistent evidence. |
| 4 | Neighbor stability | `signal_stability` | Stable before changed, initial, or unavailable evidence. |
| 5 | Evidence sufficiency/quality | `evidence_sufficiency`, `evidence_quality` | Sufficient available evidence is required. |
| 6 | Deterministic tie-breaker | `customer_id` | Technical reproducibility only; not risk evidence. |

`why_now_reason_codes` are displayed separately. They explain the current
policy/signal context and are not substituted for the selection tuple.
Historical landmarks are not ranking inputs, and the ranking uses neither a
0–100 score nor probability wording.

## Display contract

- Queue rows show translated selection and why-now details rather than raw
  reason codes.
- Customer Review keeps **Why selected** and **Why now** separate, then offers
  an expandable saved-order explanation.
- The explanation marks `is_composite_risk_score=false` and states that review
  rank is versioned queue order, not an individual risk or credit score.
- Unknown persisted reason codes fail safely to a localized unavailable message;
  they are never passed through as a misleading raw UI label.

For the persisted first selected record, the display evidence is: Priority
Review ordering; a prospective timing reference; non-persistent current
stress; initial neighbor snapshot with sufficient evidence; unbounded demo
capacity/new-case route; and a technical final tie-breaker. Its why-now text
contains current observed status and current financial-stress factors.

## Additive implementation

- Added `src/triage_explainability.py`, a UI-independent formatter of saved
  records only.
- Added localized ranking section and safety copy.
- Added Queue and Customer Review view-model fields consuming the formatter.
- Added tests for complete reason coverage in Korean and English, safe unknown
  codes, deterministic ordering explanation, no future-label/UI dependency,
  and display-model integration.

No feature, matching, outcome, breakpoint, What-if, policy eligibility,
ranking tuple, capacity, or canonical artifact was changed.

## Verification

- Focused triage/RM explanation suite: `47 passed`.
- Compatibility and presentation/action regression subset: `29 passed`.
- Full regression: `397 passed in 215.72s`.
- Bounded Streamlit health check on port 8519: passed.

## Remaining boundary

The ranking explains a synthetic demo queue. It is not a personal risk score,
credit score, production policy approval, or evidence of customer outcomes.
