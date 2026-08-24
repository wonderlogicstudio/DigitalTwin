# Offline E2E, Performance, and Security Regression Report

Date: 2026-08-24
Scope: synthetic-only P0 prototype; no external delivery or database

## Offline E2E result

- A deterministic 30-customer fixture completed reference-only as-of month 12
  cross-fit scoring, versioned demo-policy assessment, complete triage
  universe, capacity-aware selection, Alert creation, RM acknowledgement and
  review action, append-only audit, and provider-neutral notification Preview.
- The fixture uses a temporary workflow/audit repository. The Preview remains
  `PREVIEW`, `sent=false`, `external_delivery_attempted=false`, and does not
  mutate the Alert or audit history.
- The historical breakpoint supplied to timing evidence was `not_found`; it
  remains a `historical_landmark` with `is_live_alert_trigger=false`.

## 5,000-customer reconciliation

- Canonical population artifact: expected/processed/succeeded = 5,000;
  failures = 0; exact ID reconciliation.
- Canonical triage artifact: monitored = 5,000; eligible = 1,522; selected =
  1,522; Monitor = 371; no actionable signal = 3,107; exact ID and funnel
  reconciliation.
- A fresh reference-only cross-fit and selection run wrote only to a temporary
  directory. Its records, funnel, capacity scenario, and reconciliation were
  equal to the canonical selection artifact. It did not overwrite seed-42
  analytics or canonical P0 artifacts.

## Performance baseline on this workstation

These are observed baseline measurements, not SLAs or production capacity
claims. No feature, matching, breakpoint, or What-if rule was reduced.

| Operation | Result | Elapsed |
| --- | --- | ---: |
| Full 5,000-customer legacy-parity population analysis, in memory | 5,000 succeeded, 0 failed | 1,309.487 s |
| 5,000-customer reference-only cross-fit + triage selection to temporary output | exact reconciliation | 129.959 s |
| Load 5,000 selection artifact + build RM queue view model | 1,522 selected queue rows; exact | 0.0821 s |
| Bounded Streamlit launcher on port 8519 | healthy; temporary server stopped | 8.88 s |

The full-population analysis runtime is a release risk for repeated interactive
execution. Any future optimization must preserve the current analytics
contract and be validated separately; this stage did not add caching or alter
business rules.

## Security and offline checks

- No tracked `.env`, credential JSON, private-key, certificate, or token file
  was found.
- P0 delivery/workflow modules import no external delivery client such as
  `requests`, `httpx`, SMTP, socket, OpenAI, Graph, or provider SDKs.
- No email, phone, address, social-security, or account-number field is added
  to the P0 workflow boundary.
- `scripts/check_demo_readiness.py` uses a local socket only to inspect port
  availability and checks whether an optional `OPENAI_API_KEY` environment
  variable exists; it neither reads nor exposes a key value. Preview/Null
  notification services make no network calls.

## Regression evidence

- Focused offline/E2E, population, cross-fit, timing, triage, Alert,
  repository, Banker, audit, notification, and RM suites: `94 passed`.
- Full suite: `390 passed in 210.37s`.
- `git diff --check`: passed; only line-ending conversion warnings were
  emitted.

## Environment caveats

Readiness is `READY_WITH_WARNINGS`: this workstation uses Python 3.10.9 while
the project target is Python 3.11; port 8501 was already occupied; and no
optional API key is set, so the existing template fallback is used. These do
not enable external delivery or change the synthetic-only scope.
