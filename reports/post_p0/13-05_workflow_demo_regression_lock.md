# 13-05 — Workflow Demo Isolation / Idempotency Regression Lock

## Result

GO — the Workflow Demo boundaries are now protected by explicit owning tests.
This step adds no analytics, selection, policy, capacity, or fixture-tuning
logic.

## Regression matrix

| Invariant | Owning test(s) | Expected writes | Forbidden writes |
|---|---|---|---|
| General, Presentation, and RM default views remain safe | test_all_three_default_app_modes_keep_default_workflow_and_audit_roots_unchanged | none | default workflow/audit |
| Opening the demo CTA is read-only | test_app_test_explicit_entry_and_return_keep_rm_four_tabs_and_default_roots_unchanged | none | demo runtime, default workflow/audit |
| Explicit initialization and reset stay isolated | test_demo_shell_is_read_only_until_explicit_initialize_and_reset_isolated; test_reset_is_deterministic_and_replaces_only_injected_demo_runtime | injected tmp demo runtime only | canonical, triage, default workflow/audit |
| Oversized fixture fails closed | test_fixture_rejects_empty_or_oversized_case_sets | test fixture only | silent truncation or runtime bootstrap |
| Same token and same payload replay once | test_demo_actions_are_idempotent_state_aware_and_reconcile_with_append_only_audit | injected demo Case and one audit event | duplicate state effect or audit event |
| Same token with changed payload conflicts | test_demo_actions_are_idempotent_state_aware_and_reconcile_with_append_only_audit | none after conflict | overwrite or second action |
| Streamlit retry has a stable demo token | test_demo_action_renderer_uses_application_adapter_and_demo_namespaced_widget_keys | injected demo runtime only | default service or un-namespaced retry |
| Stale expected state fails closed | test_demo_actions_are_idempotent_state_aware_and_reconcile_with_append_only_audit | none | overwrite of newer Case state |
| Reset invalidates stale UI service and selection | test_reset_invalidates_stale_demo_service_before_it_can_write_to_the_new_runtime | reset of injected demo runtime only | write through stale service |
| Interrupted reset is never exposed as ready | test_interrupted_reset_fails_closed_until_a_later_explicit_reset_recovers | injected reset marker only | partial ready runtime |
| Preview/Null has no delivery or mutation | test_demo_preview_is_offline_and_reset_restores_the_initial_fixture; test_offline_preview_has_no_network_or_case_audit_mutation | in-memory preview capture only | network, external delivery, Case/audit mutation |
| Fixture selection does not use future label/persona fields | test_module_is_ui_network_and_label_independent; test_workflow_demo_modules_are_ui_boundary_only_without_network_or_analytics_imports | none | label-dependent fixture selection |
| UI never writes repository/audit files directly | test_demo_action_renderer_uses_application_adapter_and_demo_namespaced_widget_keys; test_customer_action_renderer_has_no_direct_repository_or_audit_write | only Banker application adapter | direct create/update/append |
| App shell contract remains stable | test_all_three_default_app_modes_keep_default_workflow_and_audit_roots_unchanged; presentation/RM focused suites | none | fourth mode, sixth Presentation tab, fifth RM tab |

## Service freshness rule

The session retains a demo-only service plus its explicitly injected paths
under the rm_workflow_demo namespace. Reset and exit clear both. The demo
application adapter checks that the submitted service is still the session's
current object and that the injected runtime is ready before it calls the
existing Banker adapter. An old Streamlit callback therefore fails closed and
cannot mutate the reset runtime.

## Artifact boundary

All test mutations use tmp_path or injected demo roots. The default workflow
and audit roots remain absent during ordinary app rendering. Protected
canonical, population, and triage artifacts are hash-compared before and
after the owning workflow tests.

## Out of scope

This lock does not approve a production workflow, external delivery, a
database, a business capacity limit, or customer-data validation. It protects
only the explicit three-Case synthetic rehearsal.
