# 12-15 Small RM Pilot Protocol and Measurement

## Result

**GO.** This step adds a synthetic-only, protocol-level contract for a future
human-reviewed RM pilot. It does not initiate a pilot, recruit RMs, handle
customer data, create an operational queue, or approve policy or capacity.

## Delivered contract

- `RM_PILOT_VALIDATION_PROTOCOL.md` defines the human-approved scope,
  measurement intent, privacy boundary, and stop criteria.
- `src/rm_pilot_protocol.py` supplies a source-free protocol model,
  pseudonymous measurement schema, aggregate process summary, human-review
  stop-signal checkpoint, and atomic metadata-only export helper.
- `artifacts/post_p0/rm_pilot/` contains protocol, measurement-schema, and
  governance-checklist templates only. There are no pilot observations.

## Scope and decision boundary

Participating-RM count, synthetic cohort reference, duration, and per-period
review capacity are optional human-supplied fields. The default scope is
`not_requested`, with no numerical value. An `approved` scope requires an
external approval reference and every parameter, but still cannot start an
actual pilot from this repository.

The protocol reports evidence usefulness, actionability, perceived timeliness,
review completion, review outcomes, recommendation decisions, follow-up state,
and insufficient evidence. It does not measure or claim customer financial
outcome improvement, intervention effect, RM productivity, or a bank-standard
capacity.

## Privacy and workflow safeguards

- Each schema record uses only opaque case, alert, reviewer, and review-period
  references; it has no customer identifier or direct-identifier field.
- Human override is optional and reason-coded. Unstructured feedback is held
  outside the public repository; the public contract permits only a sanitized
  feedback code and a private-feedback-exists flag.
- Observed workload, timing, evidence, privacy/security, or workflow concerns
  require a human governance review. They do not automatically start or stop a
  pilot, or approve policy/capacity.
- The module has no Streamlit, analytics, policy, triage, Alert/Case,
  repository, audit, notification, data-reader, or network dependency.

## Verification

- Focused pilot/capacity/timing/follow-up/workflow suite: **47 passed in
  2.61s**.
- Full regression: **454 passed in 217.93s**.
- No canonical synthetic analytics artifact, setting, policy, ranking, or
  capacity scenario was changed.

## Remaining boundary

This is preparation for a future synthetic dry run, not evidence from actual
RM participants. Any non-synthetic pilot or longer-term outcome evaluation
remains subject to separate organizational governance, approved environment,
and duration.
