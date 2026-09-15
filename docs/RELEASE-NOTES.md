# Agent Harness UI 0.3.0

Released locally on 2026-09-15. Requires Agent Harness core 0.2.0.

## What's new

- **Orchestration view:** refreshed desktop/phone layout, live agent graph, delegation cards, role labels,
  pending-work indicators, traffic charts, and planned team roles.
- **Playbook controls:** select WISDOM or an uploaded markdown document, view its provenance, and manage uploads.
- **Team editor:** choose or save presets, edit worker roles, and select suggested or strict role rules.
- **Effort controls:** display the configured vendor choices and disable levels a model has explicitly rejected.
- **Stop and live updates:** stop an active turn from the composer; new messages stream immediately with polling fallback.
- **Receipt drawer:** inspect results, execution details, usage, and instruction provenance; resume a worker with a follow-up.
- **History and search:** browse saved turns, jump to the feed, export Markdown, search messages, and view today's activity.
- **Phone features:** installable shell and opt-in completion alerts. The page remains dependency-free.

## Security and defaults

The server still binds loopback. Optional `HARNESS_UI_TOKEN` protects API and event-stream access;
the page keeps the token in sessionStorage, never in a URL. CSP nonces, Origin checks, JSON-body validation,
and mutation rate limits protect the HTTP boundary. The service worker does not cache API data or credentials.
WISDOM remains selected by default; local/Ollama targets require explicit opt-in in core.

## Verification and limits

Twelve API tests and desktop/phone Chromium smoke checks pass. Interaction checks cover learned effort limits,
planned roles, settings, receipts/history, search, and a 390-pixel phone layout without horizontal overflow.
Core tests verify instruction handling and role defaults. No paid model probes were run; support is learned
during normal use. Vendor CLI help verification timed out. Actual phone installation and OS notification
delivery were not exercised by headless tests. See [TESTS.md](TESTS.md) for evidence and screenshots.
