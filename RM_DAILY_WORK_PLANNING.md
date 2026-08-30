# RM Daily Work Planning

## Purpose

This is an operational presentation layer on top of an already-saved Monthly
Snapshot. It does not run Financial Path Twin analytics, lower
`months_from_current` by calendar day, or introduce a risk score or prediction.

```text
Saved Monthly Snapshot + RM review log
→ saved timing buckets
→ deterministic work-plan horizon
→ Today / next workday / this month / next-month candidates
```

## PoC policy

- The saved `REVIEW_NOW` bucket remains the analytical timing bucket.
- Its existing order is preserved: relationship priority within the same bucket,
  then saved timing, then customer ID.
- The first three unfinished `REVIEW_NOW` customers form the **Today** plan.
- The next three form the **Next workday** plan.
- The full unfinished `REVIEW_NOW` bucket is available as the **This month**
  plan.
- `UPCOMING` customers with saved `months_from_current` of one or two are
  displayed as **Next-month candidates**. They remain in the `UPCOMING` bucket.
- The minimal workday calendar is Monday through Friday. It intentionally does
  not infer Korean public holidays or call an external calendar.

The three-customer grouping is a fixed PoC display rhythm, not a user-entered
capacity setting, a mandatory queue, or a new analytical threshold.

## Completion and carryover

A review event completed for the same Snapshot is excluded from future active
plans for that Snapshot. A review completed on the current date is also shown
in the current day's completed area. Unfinished customers naturally remain at
the front of the next plan; no customer is re-analysed or silently moved across
timing buckets.

## Boundary guard

The planning layer consumes only `DailyWorklist` items already derived from the
saved Snapshot and standalone review events. It must not call feature
engineering, matching, outcome aggregation, breakpoint analysis, What-if,
pipeline, monthly Snapshot build, or mutate core financial data.

## UI wording

The work-plan strip must identify itself as a saved-Snapshot operating plan.
It must not describe tomorrow or next month as a new risk prediction. Snapshot
freshness remains visible so an RM can distinguish a current monthly Snapshot
from an older one.
