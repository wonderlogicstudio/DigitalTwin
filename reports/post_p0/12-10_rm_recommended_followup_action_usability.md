# 12-10 RM Recommended Follow-up Action Usability

## Result

**GO.** RM Customer Review now makes the human workflow clearer without
changing analytics or selecting an action automatically:

`Why Now → observed evidence → similar-path evidence → historical landmark →
Recommended Follow-up → What-if context → RM action record`.

## Usability contract

- Recommended Follow-up retains the persisted reason codes and prospective
  timing reference used to explain the suggestion. Its scope explicitly says
  automatic execution, automatic financial decisions, and action-effectiveness
  estimation are all false.
- Suggested record actions appear first in the RM action control with
  human-readable localized labels. Other existing, recordable RM actions stay
  available and are explicitly labelled as such; the UI never chooses one.
- Each submission still passes the current expected state to
  `BankerApplicationService`. The service remains the only write boundary and
  returns a state/audit result. Post-submit feedback now names the operation,
  resulting Case state, and append-only audit recording.
- Missing case, closed case, unavailable current evidence, missing historical
  landmark, and unavailable What-if context remain honest states. No Case is
  created by the UI to make a recommendation appear.

## Evidence boundaries

- Recommended Follow-up contains review/contact/monitor/referral/follow-up
  records only. It contains no approve/decline/product/loan-term decision.
- What-if remains a labelled hypothetical cash-flow context. The UI continues
  to state that it neither estimates nor guarantees the result of an RM action.
- Historical landmark remains a retrospective similar-path display. It is not
  a current-customer trigger or predicted date.
- The RM UI does not rerun analytics, mutate triage selection, read target
  future outcomes, or directly write workflow/audit files.

## Verification

- Follow-up, Banker service/workflow, RM action/audit/preview, Customer Review,
  RM Workspace, and notification focused suite: **51 passed in 19.74s**.
- i18n, Presentation compatibility, RM action AppTest, and Customer Review
  focused suite: **29 passed in 10.86s**.
- Full regression: **417 passed in 222.99s**.
- Bounded Streamlit health check: `python scripts\\start_streamlit.py --port
  8519 --timeout 60` passed; the temporary server stopped cleanly.

## Remaining boundary

The prototype does not claim an approved RM procedure, action efficacy,
external notification, or a real-data outcome. Human RM and governance
approval remain required before an operational deployment.
