# agent-harness-ui

Loopback web UI for [agent-harness](../agent-harness): a Discord-style log of every hop between agents (you, the
orchestrator, and its workers on Claude Code, Codex, or a local model), an agent roster, orchestrator controls
(vendor, model, effort, new session), a composer, a direct-delegate form, and a traffic panel (agent graph and a
messages-per-minute chart per edge). Stdlib Python server + one dependency-free HTML page.

## Run

```
bin/harness-ui                 # serves http://127.0.0.1:7788 (loopback only)
bin/harness-ui serve --port 7790
bin/harness-ui install-unit    # writes ~/.config/systemd/user/harness-ui.service; you enable it
```

The core package is found via `AGENT_HARNESS_ROOT`, else the sibling `../agent-harness`, else
`~/GitHub/Projects/Personal/agent-harness`. The core CLI's `harness ui` simply execs this launcher.

From a phone: `ssh -L 7788:127.0.0.1:7788 <host>` over Tailscale, then open http://127.0.0.1:7788. The server never
binds a non-loopback address and rejects requests whose `Host` header is not localhost.

## Layout

- `harness_ui/server.py` — HTTP API (contract: `docs/UI-CONTRACT.md`), reads/writes nothing but
  `~/.local/state/agent-harness/` through the core's `harness.orchestrator`.
- `harness_ui/index.html` — the page (vanilla JS, inline SVG).
- `tests/test_ui.py` — API tests with a stub Claude that emits stream-json (`python3 -m unittest tests.test_ui`).
- `docs/screenshots/` — headless-Chromium renders at desktop and phone width.

Agent display names: `~/.config/agent-harness/agents.json`, e.g. `{"gpt-6-astra": "Astra", "codex": "Sol", "user": "Brian"}`.
