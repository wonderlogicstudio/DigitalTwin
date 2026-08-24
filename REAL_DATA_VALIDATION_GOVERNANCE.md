# Real-data Validation Governance Readiness

## Status and scope

**Status: NOT READY FOR REAL-DATA ADMISSION.** This is a governance-readiness
contract for the Financial Path Twin synthetic prototype. It contains no actual,
anonymized, external, or customer data; it grants no approval and is not a
real-data adapter.

The canonical P0 synthetic dataset remains 5,000 customers, seed 42, 36 months,
with months 1–12 observed and historical-peer months 13–36 held for retrospective
outcome and landmark analysis. This document neither changes that contract nor
asserts that a future bank dataset has the same availability.

## Required approvals before any separate real-data work

All of the following roles must record approval in the organization’s approved
governance system. Their status in this repository is **not requested**, not
pending or approved:

| Required role | Required decision |
|---|---|
| Data owner | Defines permitted purpose, minimum fields, cohort and independent event/outcome definition. |
| Security | Approves the secure environment, least-privilege access, audit logging, retention and deletion controls. |
| Privacy/DPO/legal, as applicable | Confirms the permitted anonymization/pseudonymization, processing basis, sharing and export restrictions. |

The public repository cannot serve as the evidence store for these decisions.
No approval may be inferred from this document, a demo result, an issue, or a
test pass.

## Data and environment boundary

Actual data may exist only in an approved secure environment outside this public
repository. Until every required approval and environment control is recorded by
the organization, this project must not download, collect, copy, transform,
store, or process real or anonymized customer data.

The required boundary is:

- Public repository: code, synthetic fixtures, governance metadata and empty
  report templates only.
- Approved secure environment: any separately approved adapter execution,
  validation run and controlled result review.
- Export: raw data, row-level extracts and direct identifiers are prohibited from
  leaving the approved environment. Any aggregate export requires its own
  approval.

## Minimum data concepts and exclusions

The future data owner must map only the minimum concepts necessary for the
predefined validation purpose:

| Required concept | Constraint |
|---|---|
| Pseudonymous customer key | Stable only within the approved validation environment. |
| Monthly timestamp or ordering | Supports approved observation and event windows. |
| Income, expense, debt and cash mappings | Use only fields approved as necessary for feature comparison. |
| Current-status mapping | Must have documented provenance and observation-time availability. |
| Observation window | Defined before scoring and evaluated for availability. |
| Independently defined future outcome/event | Defined with the data owner before evaluation and opened only in the evaluator stage. |

Do not admit direct identifiers, contact details, addresses, account numbers,
authentication credentials, or other unnecessary personal information.

## Required controls

- **Minimization:** use the smallest approved field set, cohort and retention
  period required for the stated validation.
- **Access control:** least privilege, named authorized users and approved
  environment access only.
- **Retention/deletion:** agree a retention period, deletion procedure and
  completion evidence before admission.
- **Auditability:** log access, processing runs, approved exports and deletion
  events in the secure environment.
- **Environment separation:** keep approved validation execution separate from
  this public repository and its canonical synthetic artifacts.
- **Export prohibition:** do not export raw rows, direct identifiers or hidden
  values to the repository, issue tracker, presentation, logs or test output.

## Analytical boundary

An actual-data outcome/event must be independently defined with the data owner.
The synthetic `final_outcome` label must not be copied or presented as an actual
bank ground truth. A real-data horizon may be compared with P0’s months 1–12 and
13–36 framing, but it cannot alter P0 settings, features, matching, outcome,
breakpoint or What-if contracts without a separate approved change.

The future adapter must preserve the existing safeguards: as-of scoring does not
read target future data, persona or evaluator labels; historical landmarks are
not live triggers; matched-cohort shares are not prediction probabilities; and
What-if remains supporting cash-flow evidence rather than intervention efficacy.

## What can proceed without data

Steps 12-13 and 12-14 may build an adapter harness and reporting template using
only injected synthetic fixtures. They must remain unable to read a public
repository path as real data, and must report **unvalidated on actual data**
until all external approvals and secure-environment controls are completed.

The machine-readable companion is
`artifacts/post_p0/real_data_readiness/governance_requirements.json`.
