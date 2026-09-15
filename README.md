# agent-harness-ui

Current release: **0.6.0**, with core **0.4.0**. See [release notes](docs/RELEASE-NOTES.md).

This release adds private phone access, session controls, worker cancellation, and background push.
See [phone setup and daily use](docs/PHONE.md). The private app and Android test notification were verified.

Loopback web UI for [agent-harness](../agent-harness): a live **orchestration graph** (the orchestrator on top, its
workers beneath, a comet travelling along the edge for every hop, working rings and elapsed counters while a
delegation runs, and the role label the orchestrator gave each worker), a turn-grouped **feed** with paired
request/receipt delegation cards, an agent roster with system health, per-edge traffic sparklines and a turn
timeline, a composer with `/delegate` and Stop, a command palette (⌘K / Ctrl K), and orchestrator settings behind the session
pill. Dark by default with a light theme (`#light`), phone-first at 390px. Stdlib Python server + one
dependency-free HTML page (no CDN, no web fonts, no build step). Visual spec: `docs/DESIGN-SPEC.md`; design source:
`docs/design/`.

## Run

```
bin/harness-ui                 # serves http://127.0.0.1:7788 (loopback only)
bin/harness-ui serve --port 7790
bin/harness-ui install-unit    # writes ~/.config/systemd/user/harness-ui.service; you enable it
```

The core package is found via `AGENT_HARNESS_ROOT`, else the sibling `../agent-harness`, else
`~/GitHub/Projects/Personal/agent-harness`. The core CLI's `harness ui` simply execs this launcher.

From a phone: use the configured Tailscale Serve HTTPS address. The server still binds loopback and accepts
the exact configured remote hostname only for the authorized Tailscale account. An SSH local forward is
available as a fallback. See [PHONE.md](docs/PHONE.md).

## Layout

- `harness_ui/server.py` — HTTP API (contract: `docs/UI-CONTRACT.md`), reads/writes nothing but
  `~/.local/state/agent-harness/` plus playbooks/team presets in `~/.config/agent-harness/` through core modules.
- `harness_ui/index.html` — the page (vanilla JS, CSS, inline SVG; DOM built with createElement only).
- `tests/test_ui.py` — API tests with a stub Claude that emits stream-json, plus static checks on the page
  (`python3 -m unittest tests.test_ui`).
- `tests/fixture_server.py` — serves the page against canned states (live turn, idle, offline, empty, eight
  workers) for hand-testing and headless renders without a live harness.
- `docs/DESIGN-SPEC.md` — tokens, geometry, motion, components, data handling; `docs/design/` — the Claude Design
  canvas export it came from; `docs/UI-REVAMP-DESIGN-PROMPT.md` — the brief.
- `docs/screenshots/` — headless-Chromium renders at desktop and phone width.

Agent display names: `~/.config/agent-harness/agents.json`, e.g. `{"gpt-6-astra": "Astra", "codex": "Sol", "user": "Brian"}`.
Role labels under workers come from the orchestrator: pass `label` to the `delegate` tool (or `harness delegate --label
Reviewer …`); the backend echoes it as `meta.label` on the `tool_use` hop and the UI shows it as a chip.

Keyboard: Enter sends, Shift+Enter newline, `/delegate <target> [readonly|edit] <prompt>` opens the direct-delegate
sheet prefilled, ⌘K / Ctrl K command palette, ⌘G toggles the graph, ⌘⇧L toggles the theme, ⌘↓ jumps to latest, Esc
closes overlays.


## V2 controls

Settings includes full configured effort choices, uploaded markdown playbooks, and role-based team presets.
Workers inherit role defaults through the harness. Local/Ollama targets are disabled until explicitly enabled.
Stop terminates the current turn's process group; live events update the feed with polling as fallback.
Open a receipt to inspect its instruction provenance or resume the worker. History opens saved transcripts
and exports Markdown. Search filters the feed, and Settings can enable completion alerts.

For tunnel authentication, optionally supply `HARNESS_UI_TOKEN` through the server environment; the page
asks for it and stores it only for that browser tab session. No token belongs in a URL. The installable shell
never caches API data. Playbook uploads are UTF-8 `.md` files up to 256 KB and remain in the config directory.

Offline verification: `python3 -m unittest tests.test_ui` and `python3 -m unittest tests.test_page_smoke`.
The latter uses installed Chromium and independent fixtures; neither starts a paid vendor model call.
