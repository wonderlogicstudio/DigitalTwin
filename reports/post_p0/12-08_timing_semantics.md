# 12-08 Why Now Timing and Historical Landmark Review

## Result

**GO.** The customer-level RM review now carries explicit prospective and
historical timing sources, with different contracts and display copy. Neither
source supplies a future event month or an individual lead-time estimate to the
current customer.

## Customer-level Why Now

- `Why Now` is built only from persisted policy/triage reason codes and the
  current/prior observation scope. The RM view model does not score, match,
  rank, or load the target's months 13–36.
- The prospective timing view model accepts only `source=prospective_signal`.
  It exposes the candidate signal month, declared operational label, and a
  metadata contract of `current_and_prior_only`.
- The current customer view model deliberately has no `event_month`,
  `event_type`, or `lead_time_months` field. Injecting an event-month field
  into a source record does not change its rendered prospective timing.
- The screen identifies the persisted demo-policy status and limitations.
  Policy-level lead-time distributions are described as retrospective
  validation evidence, not an individual customer timeline.

## Historical landmark

- Historical landmark data is always tagged `source=historical_landmark` and
  `is_live_alert_trigger=false` for found, not-found, insufficient, and
  unavailable states.
- It remains a separate RM section describing the month at which similar
  historical paths diverged. Its caption explicitly says that it is not a
  future date for the current customer.
- General-mode KPI, summary, chart title, and chart annotation copy no longer
  present the landmark as a personal “N months remaining” countdown.
- Presentation retains its existing five tabs. Its historical-landmark scene
  was already separated from the prospective current-review signal and
  required no structural change.

## Contract hardening

- `PolicyTimingEvidence` now rejects an historical source, invalid candidate
  month, empty evaluation status, and any non-null customer-level lead time.
- `HistoricalLandmarkContext` continues to reject use as a live trigger.
- No seed, customer count, feature, matcher, outcome, breakpoint calculation,
  What-if calculation, ranking, capacity, or canonical artifact was changed.

## Verification

- Timing/RM/Presentation/UI focused suite: **98 passed**.
- Full regression: **413 passed in 224.89s**.
- Bounded Streamlit health check: `python scripts\\start_streamlit.py --port 8519 --timeout 60` passed.
- The saved selection source remains a 5,000-customer synthetic population;
  this step introduced no new reconciliation output and no canonical-artifact
  mutation.

## Remaining boundary

The prospective policy and timing evidence are synthetic-demo methodology.
They do not establish a real-bank event forecast, RM productivity result,
intervention effect, or an approved operational policy. A historical landmark
is evidence about a matched historical cohort only.
