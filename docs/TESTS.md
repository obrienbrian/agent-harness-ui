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

## UI-04 Revamped page (variant A design, 2026-09-15 12:xx EDT) — `harness_ui/index.html` 0.2.0

- criterion: contract v1 endpoints only + additive `meta.label`; no external assets; no markup-string DOM; every design
  state renders at 1440×900 and 390×844; motion is real (comets exist mid-flight) and degrades under reduced motion.
- design source: `docs/DESIGN-SPEC.md` + `docs/design/agent-harness-ui.dc.html` (Claude Design canvas, boards 1a–1j);
  brief in `docs/UI-REVAMP-DESIGN-PROMPT.md`. Variant A (graph band above the feed) as the designer chose.
- static checks (also enforced by `tests.test_ui.Api.test_index_static_checks`): `node --check` on the inline script
  OK; zero `innerHTML`/`insertAdjacentHTML`/`outerHTML`/`document.write`/`eval(`; the only URL is the SVG namespace;
  endpoints = /api/state, /api/stats, /api/orchestrator, /api/say, /api/delegate; viewport meta; 3 media queries incl.
  `prefers-reduced-motion`; one `<script>`, no `<link>`. File: 1 668 lines / 118 KB.
- unit suite: `python3 -m unittest tests.test_ui` → 8 tests OK (7 previous + static checks); the stub Claude's
  delegate call now carries `label: "  Reviewer "` and the recorded `tool_use.meta.label` is asserted `"Reviewer"`
  (trimmed); the direct delegation asserts `meta.direct` and `meta.label == "Checker"`.
- render check (headless Chromium 1440×900 and 390×844 against `tests/fixture_server.py`, which serves the page with
  the design's §10 sample content): live turn (orchestrator busy halo, Sol done ok 4.0s, Sonnet working with ring +
  dashed edge + elapsed counter, shimmer result, composer disabled with status line, "This turn" spans); idle with
  history (turn headers, collapsed older cards, usage line `1 288 tok in · 742 out`, direct card `Brian → Sol`);
  error receipt card (`HARNESS_TOOL_CALL_FAILED`, edit chip, retry-as-readonly action) + inline `error` row;
  unreachable (banner with last contact + retry countdown, `stale · as of`, dimmed content, stats placeholder);
  empty (orchestrator alone + placeholder text, welcome in the feed); light theme via `#light`; eight workers →
  five shown + `+3` node (desktop) / three shown + `+5` (phone), captions ellipsized to the pitch; tablet 1000 px
  (right rail hidden, stage scaled). Kept: `docs/screenshots/ui-desktop-2026-09-15-revamp.png`,
  `ui-phone-2026-09-15-revamp.png`, and `ui-desktop-2026-09-15-revamp-live-server.png` (the real server on :7788
  with the PONG turns: tool note row, `turn t_f4fd · 10:37:02 · 9.0s · 1 delegation`, `codex` worker, usage line).
- motion check: `--dump-dom --virtual-time-budget=2300` against the `--advance` fixture (second poll appends a
  receipt and a tool_use) shows two `.comet` divs mid-flight with `offset-path` set (`class="comet rev"` for the
  upward receipt), two `edge-lit` overlays, one `edge-work` dashed edge, and the new worker in `working` state.
- oracle independence: fixture payloads are hand-written from the contract, not captured from the page; the real
  server render uses live `~/.local/state/agent-harness` data.
- residual: hover/click interactions (node focus, settings popover, palette, delegate sheet, phone sheet) exercised
  by code review only, not by a browser driver; `offset-path` fallback (`<animateMotion>`) not exercised because
  Chromium supports `offset-path`; light theme only spot-checked on the live-turn screen.


## UI-V2 — playbooks, teams, live control, history (2026-09-15)

Core 0.2.0 / UI 0.3.0; all previous uncommitted design work retained. Both repos remain uncommitted.

- `python3 -m unittest tests.test_ui`: 12 passed (8 regression/static plus 4 v2 integration cases).
  A stub process that ignores SIGTERM and spawns a child is stopped within two seconds with no live orphan.
  An HTTP SSE reader sees a direct delegation hop within 500 ms. Tests cover playbook upload → selection →
  Claude system argv, strict role defaults → worker argv/provenance, active document deletion refusal,
  preset save/delete, resumed receipt parent persistence, saved history, token authentication, Origin guard,
  CSP script nonce matching, and a service worker that does not cache application data.
- `python3 -m unittest tests.test_page_smoke`: passed, with separate 1440×900 and 390×844 browser runs.
  Fixtures are authored independently from the UI and spend no vendor quota.
- Chromium DevTools interaction checks on the live loopback server and independent fixtures: six Codex
  effort buttons; a learned four-level model disables minimal/max; planned role ghosts; Stop while busy;
  settings, team roster, upload metadata, archived history, search; zero JavaScript exceptions. Phone document
  width is exactly 390 pixels after fixing the final graph-node overflow. Settings inputs/buttons use 44 px
  phone targets. Screenshot receipts:
  [desktop settings](screenshots/ui-desktop-v2-settings.png),
  [learned efforts](screenshots/ui-desktop-v2-learned-efforts.png),
  [desktop live](screenshots/ui-desktop-v2-live.png),
  [phone settings](screenshots/ui-phone-v2-settings.png),
  [phone team](screenshots/ui-phone-v2-team.png),
  [phone live](screenshots/ui-phone-v2-live.png),
  [phone history](screenshots/ui-phone-v2-history.png).
- `node --check` on the extracted inline script and `git diff --check`: passed.

No paid vendor calls. Model-specific support will be learned during normal use, per the user's choice.
The vendor help census timed out; no new per-model support claim is made. Notification permission and
actual phone home-screen installation are browser/OS actions, not exercised by headless Chromium. SSE
reconnects after 55 seconds and uses polling for catch-up; token enforcement is optional and currently off.
The real server was restarted only after confirming it was idle, using its verified PID; no service enabled.
