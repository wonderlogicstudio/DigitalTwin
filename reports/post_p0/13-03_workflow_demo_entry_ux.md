# 13-03 Explicit Workflow Demo Entry / Return UX

## Result

`GO` — the synthetic workflow fixture is now reachable only through an
explicit secondary action inside RM Workspace. It is not an app mode, RM tab,
new browser, or separate Streamlit application.

## User path

1. Open **RM Workspace** and choose **Open Synthetic Workflow Demo**.
2. Read the persistent synthetic/non-operational and Preview-only notices.
3. If no demo runtime exists, choose the explicit **Initialize synthetic
   Cases** action. This is the only entry-path action that creates the
   isolated demo runtime.
4. Review at most three synthetic Cases and their current state/provenance.
5. Use **Return to default RM workspace** to leave; the default RM queue,
   filters, customers, workflow, and audit roots are not replaced.

## Boundary preserved

- App modes remain exactly General, Presentation, and RM Workspace.
- Presentation remains five tabs; normal RM Workspace remains four tabs.
- Entry, normal rendering, and return do not initialize/reset a demo case.
- The demo uses only `rm_workflow_demo_*` session keys. Default RM filters are
  retained but disabled while the secondary demo context is open.
- Missing fixture, uninitialized runtime, corrupted runtime, or stale selected
  Case are shown as demo-local states and never read from the default workflow
  repository.
- Banker action, audit submission, and notification-preview controls are
  deliberately deferred to 13-04.

## Verification

- Focused workflow-demo/UI/RM/Presentation suite: `60 passed`
- Full regression suite: `477 passed`
- Bounded Streamlit health check: passed; temporary server stopped.
- Readiness remains `READY_WITH_WARNINGS` only because Python 3.10.9 differs
  from the project 3.11 target and the optional template fallback has no
  `OPENAI_API_KEY`. Data, cache, packages, and the C002608 smoke check passed.
