# RM Pilot Validation Protocol

## Status and boundary

**Status: protocol only; no pilot has been initiated.** This document defines
how a future, human-reviewed RM pilot could assess whether synthetic evidence
is understandable, timely enough to review, and manageable as work. It does
not recruit RMs, process customer data, send messages, create a production
queue, or authorize a financial decision.

The public repository is limited to synthetic, pseudonymous case and alert
references. Any future non-synthetic activity requires organization-specific
governance outside this repository, consistent with
[REAL_DATA_VALIDATION_GOVERNANCE.md](REAL_DATA_VALIDATION_GOVERNANCE.md).

## Human-approved scope

Before a pilot is considered, the responsible human governance group must
record all of the following outside this repository:

| Scope parameter | Protocol rule |
| --- | --- |
| Participating RMs | A human-approved count and participation process; no names are stored here. |
| Case cohort | A human-approved synthetic pseudonymous cohort reference; no customer identifiers. |
| Duration | A human-approved review-period count. |
| Review capacity | A human-approved per-period comparison input, not a bank standard or system recommendation. |

The checked-in default has `approval_status=not_requested` and no numerical
scope values. An `approved` scope must carry an external approval reference.
It still does not authorize execution from this repository.

## Primary process measurements

The measurement contract records one pseudonymous case/alert/review-period
entry. It is intended to aggregate:

- evidence usefulness, review/actionability, and perceived-timeliness ratings;
- review-completion time and completed reviews per declared period;
- reviewed, deferred, monitor, and no-action outcomes;
- recommendation accepted, modified, or rejected counts with a sanitized
  reason code where a reason is required;
- follow-up created or completed status; and
- insufficient-evidence frequency.

The protocol does not use early measurements to assert improvement in customer
financial outcomes. Any longer-term outcome evaluation needs a separately
approved definition, duration, and governance plan.

## Feedback and privacy boundary

- Measurements carry only opaque case, alert, reviewer, and review-period
  references. Customer identifiers, contact details, accounts, addresses, and
  other direct identifiers are not schema fields.
- Human overrides are optional and use a controlled override reason code.
- Unstructured feedback is optional, must be sanitized in the approved
  environment, and is represented here only by an optional sanitized code and
  a private-feedback-exists flag. Raw feedback is never exported to the public
  repository.

## Stop criteria and human review

The following conditions require an explicit human governance review:

1. workload overload;
2. confusing prospective-timing semantics;
3. high unusable-evidence occurrence;
4. a privacy or security issue; or
5. workflow corruption.

The protocol can record a pseudonymous evidence reference for an observed
condition, but it never stops or starts a pilot automatically. Policy and
capacity are not automatically approved from any ratings, counts, or stop
signals.

## Relationship to existing contracts

This protocol consumes no scorer, matcher, policy evaluator, triage ranker,
Alert repository, audit log, or notification provider. Existing policy,
triage, Alert, historical-landmark, prospective-timing, What-if, and Preview
boundaries remain unchanged. The protocol is for review-process measurement,
not an individual forecast or an intervention-effect study.

## Repository artifacts

- [pilot protocol template](artifacts/post_p0/rm_pilot/pilot_protocol_template.json)
- [pilot measurement schema template](artifacts/post_p0/rm_pilot/pilot_measurement_schema_template.json)
- [pilot governance checklist](artifacts/post_p0/rm_pilot/pilot_governance_checklist.json)

All are source-free templates in `artifacts/post_p0/rm_pilot/`. Any future
run output must use an injected, non-canonical output root and atomic write.
