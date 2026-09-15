# Agent Harness UI 0.6.0

Released locally on 2026-09-15. Requires Agent Harness core 0.4.0 and installed Codex with native goal support (verified with 0.154.0).

- **Help & instructions:** the top-bar **?** opens getting-started instructions and a command reference, on desktop and phone.
- **Slash commands:** type `/` to browse and select commands. `/clear` resets the conversation and visible feed while keeping saved history; `/new` keeps the feed visible. Model, effort, settings, playbook, team, sessions, status, history, theme, delegate, and Stop controls have commands too.
- **Native Codex goals:** `/goal <objective>` starts persistent work. `/goal` opens the goal panel, including an optional token budget. Pause, resume, edit, and clear are available from the panel or commands. The goal bar shows native status and usage. Claude goals and other terminal-only commands are explicitly unsupported.
- **Reliable controls:** busy work still permits commands such as pause/stop; resets are rejected while busy. Unknown slash commands never become prompts. Use `//` for literal slash text. Old event/poll data cannot restore a cleared feed.
- **Lightweight:** no new frontend dependencies, assets, recurring requests, or paid capability probes. Native goal metadata is read on demand; ordinary state updates use the saved snapshot. WISDOM remains the default.

Goals stop on completion, native limits/blocking, errors, or user Stop. After a service restart, resume explicitly. Goals use existing permissions. Saving an edited objective resets native goal accounting; a blank budget removes the cap.

# Agent Harness UI 0.5.0

Released locally on 2026-09-15. Requires Agent Harness core 0.3.0.

- **Live exchanges:** real message excerpts beside the agent graph, brief arrival animations, and
  click-through to the full feed entry. History loads quietly; new events drive the motion.
- **Session setup:** Agent, Team, and Preferences tabs replace the long popover. Compact model picker,
  keyboard navigation, contained scrolling, and a persistent save footer on desktop and phone.
- **Playbook library:** a dedicated top-bar button, WISDOM pinned as the built-in default, markdown
  drag-and-drop or file selection, and a separate activation step. Your running WISDOM selection stays intact.
- **Alert layout fix:** enabled status is a badge; Test and Disable use buttons that fit their text.
- **Lightweight motion:** three message cards, at most six active and six queued comets, no new polling,
  model calls, assets, or dependencies. Hidden tabs and reduced motion suppress animation; Preferences
  also offers a per-device toggle.

Validated with the UI/API suite and Chromium interactions at 1440, 1000, 390, and 320 CSS pixels,
including light/dark themes, subscribed-alert layout, markdown upload/activation, focus, burst traffic,
and reduced motion. Existing session/worker controls remain covered. See [test evidence](TESTS.md).

# Agent Harness UI 0.4.0

Released and deployed locally on 2026-09-15. Requires Agent Harness core 0.3.0.

- Private HTTPS through Tailscale, restricted to the configured account; automatic UI startup.
- **Sessions** drawer separates harness/external sessions, with graceful End and retained history.
- **Cancel worker** stops individual direct, resumed, or orchestrator-delegated workers.
- Encrypted background push with durable retries, test/disable controls, and saved-work links.
- Android installation icons and touch controls. See [phone instructions](PHONE.md).

Tests cover OS process trees, HTTP identity/origin checks, real encryption/decryption, restart/retry, and
desktop/phone browser controls. The user confirmed that the Android app loaded and the background test
notification arrived. No paid model probes.

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
