# Notification Adapter Contract

P0 provides only `PreviewNotificationService` and `NullNotificationService`.
They never call a network, read credentials, or report an item as sent.

A future external adapter must implement `NotificationService.notify(request)` and
return a validated `NotificationResult`. Its work is deliberately sequenced as:

1. Implement the adapter behind the provider-neutral protocol.
2. Add reviewed configuration and explicit registration in a separate change.
3. Optionally expose it in a UI only after the first two steps are approved.

Alert, triage, audit, and Banker workflow modules must remain independent of
notification implementations. A notification result must not delete, revert, or
otherwise change Alert/Case state.
