# Test evidence ledger — agent-harness-ui

Receipts for the web UI. The core harness receipts live in the agent-harness repo.

## UI-01 harness UI backend (v1) — unit suite and live turn

- criterion: H9 (loopback + Host guard), O5 (every hop visible), O4 (orchestrator session resumes), typed turn errors.
- unit suite: `python3 -m unittest tests.test_ui` (from this repo; core located via AGENT_HARNESS_ROOT or the sibling agent-harness checkout) → 7 tests OK (stub Claude emitting stream-json: init, text, a
  `mcp__harness__delegate` tool_use, its tool_result receipt, an unrelated Bash tool, result). Asserts: prompt/text/
  tool_use/receipt/result hops recorded with the right from→to ids, worker named from the receipt model (`Sol`),
  orchestrator named from its model (`Sonnet`), `--resume` used on the second turn, 409 while busy, error turn typed,
  stats edges present, direct delegation records both hops, foreign Host → 403.
- test isolation: test modules pin `HARNESS_STATE_DIR`/`CODEX_HOME` at import and the package reads them once per
  process, so `bin/run-tests` runs each module in its own interpreter (a combined single-process run cross-contaminates).
- live turn: see UI-02 below.

## UI-02 Live orchestrator turns through the UI backend (2026-09-15 10:31 and 10:37 EDT)

- criterion: O5 (every hop visible), O4 (session resume), H5 (worker least authority), real stream-json shapes.
- turn 1 (`t_3ac35160`, Sonnet, effort low, prompt "Reply with exactly the word OK…"): 3 s; events streamed were
  `system/hook_started`, `system/hook_response` (the WISDOM drift hook fired inside the orchestrator session),
  `system/init`, `assistant`, `rate_limit_event`, `result`. Messages recorded: prompt → text "OK" → result
  (`same_as_text`). `session_ref` saved (claude_session 86b8a730…), `turns` = 1.
- turn 2 (`t_f4fd5bc8`, same session resumed, prompt asking for exactly one harness `delegate` to codex): 10 s,
  10 events. Hops recorded, in order: user→orchestrator prompt; orchestrator tool note (ToolSearch loading the
  delegate tool); orchestrator→worker:codex `tool_use` "Reply with exactly the word PONG…"; worker:codex→orchestrator
  `receipt` root_code `ok`, result_text "PONG", 5000 ms; orchestrator→user text quoting the receipt; result.
  Agents view: user (bso), orchestrator "Sonnet", worker:codex. This required allowlisting the harness MCP tools on the
  orchestrator invocation (`--allowedTools mcp__harness__*`); without it `--permission-prompts none` denies the call.
- residual: worker display name for Codex delegations without an explicit model is the vendor ("codex") because the
  receipt carries no model; `~/.config/agent-harness/agents.json` can map `"codex": "Sol"`.

## UI-03 Frontend page (harness/ui/index.html, 888 lines, single file)

- criterion: contract v1 endpoints only; no external assets; no raw HTML injection; renders at desktop and phone width.
- static checks: only URL in the file is the SVG namespace; endpoints used = /api/state, /api/stats, /api/orchestrator,
  /api/say, /api/delegate; zero `innerHTML` uses, 38 `textContent` uses; `node --check` on the inline script OK;
  viewport meta and a media query present.
- render check: headless Chromium screenshots against the live server (`docs/screenshots/ui-desktop-2026-09-15.png`,
  `ui-phone-2026-09-15.png`): roster with status dots and counts; orchestrator card (vendor/model/effort selects, Apply,
  New session, session id, turns, idle/busy); feed showing the real turns including the delegation hop
  ("→ delegate to codex: …" with class badge) and the worker receipt with an `ok · 5.0s` badge; agent graph; per-edge
  messages-per-minute chart with legend; harness blockers/units/wisdom box; phone layout stacks feed → orchestrator →
  composer → direct delegate → roster → traffic.
- defect found and fixed: empty turn-end `result` rows rendered as blank orchestrator lines; the backend no longer emits
  them (the final text block is the result; turn status is `/api/turn/<id>`).
- residual: interaction (Apply/Send/Delegate buttons) exercised only through the API tests, not by a browser click.
