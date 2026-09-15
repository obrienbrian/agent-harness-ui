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


## PHONE-01 — private phone control (2026-09-15; UI 0.4.0 / core 0.3.0)

User authorized all four enhancements and private deployment. The user completed account login and
Tailscale HTTPS consent. No paid model probes, public hosting, or live external-session termination.

- `python3 -m unittest tests.test_ui`: 12 passed. Direct receipt assertions match the requested ID,
  so an older cancelled worker cannot be mistaken for the new delegation.
- Private venv `python -m unittest tests.test_mobile`: 5 passed. HTTP identity/origin, individual worker
  cancellation and typed receipt, real external-session ending, stale identity/service refusal, and
  orchestrator End refusing a busy turn while preserving history.
- Private venv `python -m unittest tests.test_push`: 5 passed. Durable restart/retry, partial append,
  attention receipt, expiry, unsubscribe, permanent failure, endpoint guards, and real Web Push
  encryption/decryption with an independently held recipient key. Redirects disabled; finite timeout.
  No provider call in this suite.
- `python3 -m unittest tests.test_page_smoke`: 2 passed, each at 1440x900 and 390x844. Native Node/CDP
  checks Sessions, Cancel, confirmation decline/accept, protected service rows, settings, no horizontal
  overflow, and no JavaScript exceptions.
- Identity mutation: replace `access.authorized` with always-true. The HTTP proof fails at the intended
  account boundary (`200 != 403`), with no unrelated errors.
- Live HTTPS: API, manifest, PNG, and service worker returned 200. Live Chromium at 390x844 reported
  a secure context, 390px document width, active service worker, push readiness, and zero JS exceptions.
  Private screenshot: `/tmp/harness-live-browser-bbd1kmsz/phone-sessions.png` (outside this public repo).
- **Android witness:** user confirmed “App loaded and alert arrived” after install/subscribe/test/home
  screen instructions. This proves actual display on the phone, beyond provider acceptance.
- Restart: UI service enabled/active, HTTPS recovered at UI 0.4.0/core 0.3.0; push public key and one
  subscription preserved; pending=0, failed=0, error=null.
- Python/JavaScript syntax and `git diff --check` passed. Optional `pywebpush==2.3.0` installed in a private
  venv. Keys/subscriptions/config stay outside Git. No external session was ended to test the controls.

Residual: delivery still depends on browser/provider/Android settings. The app needs an awake, connected
computer. This device witness is not a guarantee under every network/OS condition.

## UI-05 — workspace refresh (2026-09-15; UI 0.5.0 / core 0.3.0)

- Focused criteria and rollback: DESIGN-SPEC.md, Current workspace refresh. Runtime implementation
  remains a single dependency-free HTML file. Existing state/SSE and playbook/push endpoints retained.
- JavaScript parser (`node --check` on the extracted inline script and `tests/workspace_browser.mjs`),
  Python compilation of changed Python files, and `git diff --check`: passed.
- `python3 -m unittest tests.test_ui tests.test_page_smoke`: **15 passed**. The existing API proof
  exercises custom instruction injection into both turn and worker, active-document deletion refusal,
  and secret rejection. Existing browser tests exercise Sessions, worker Cancel, confirmed external
  End, protected services, and 1440/390 renders without invoking a real vendor.
- New native-CDP browser proof uses independent HTTP fixtures at widths **1440, 1000, 390, 320**:
  initial history has no arrival animation; new HTTP messages animate; unchanged polling retains card
  nodes; an exchange opens its feed task; tabs/keyboard/focus containment/return; six Codex effort
  choices; subscribed alerts fit; light/dark render; invalid file stays local; drag/drop upload does
  not activate; Use playbook sends only the selected playbook; unrelated settings save preserves it;
  busy selection is held; 100 messages leave three cards and bounded comets; literal markup stays
  text; collapsed/hidden views clear the queue; reduced motion preserves text without visible travel.
- Visual inspection found worker role chips clipped at the bottom of the compact map; increased the
  desktop map height to 252px. The screenshot's alert overflow is covered by enabled-status control
  bounds checks. Early browser proof caught a test-driver focus assumption; clicks now focus their
  target as an actual interaction does. CDP's media-query event delivery was intermittent, so the
  reduced-motion proof checks browser media state and visible animation behavior instead of an
  internal CSS class. Final combined suite passed with that independent visual oracle.
- Fixture-only reference renders (no live prompts or results):
  [desktop](screenshots/ui-0.5-desktop.png), [phone preferences](screenshots/ui-0.5-phone-preferences.png),
  [phone playbook library](screenshots/ui-0.5-phone-library.png).
- Size: approximately 175 KB HTML versus 151 KB before; about 44 KB versus 38 KB if compressed.
  No new runtime dependency, image/font asset, polling interval, or paid model call. This is a bounded
  workload/design check, not a device battery benchmark.
- Private deployment: restart only after observing idle orchestrator and zero workers. Live Chromium
  through Tailscale HTTPS at 390×844: secure context, UI 0.5.0/core 0.3.0, WISDOM still selected, three
  exchange cards, both menus fit, zero mutation requests and JavaScript errors. Push ready, pending=0,
  failed=0, error=null. The existing Android subscription remains; no new alert was sent for this pass.

The actual Android alert-delivery witness is PHONE-01 above; this refresh was inspected in Chromium
emulation and on the private served page. Reload the installed app to load the new HTML.

## UI-06 Help, commands and goal control — 2026-09-15

Criteria: HELP-GOAL-01 in core and UI 0.6.0 additions in DESIGN-SPEC/UI-CONTRACT.

- `python3 -m unittest tests.test_ui` — **15 passed**. New checks prove unknown commands cause no
  vendor invocation, `//` preserves a literal slash, reset rejects busy work, `/new` retains the feed,
  `/clear` retains durable turn history but empties state messages, malformed clear flags are rejected,
  and Claude goal control is explicitly unavailable. Existing auth/Origin/CSP, stop, SSE, and receipts
  remain green.
- `python3 -m unittest tests.test_page_smoke` — **4 passed**. New real Chromium interaction drives
  Help, keyboard suggestions, unsupported commands, the goal form/budget, busy pause/clear, edit with
  blank budget, resume/stop/clear, model/effort/theme, and new/clear. No command is sent to `/api/say`;
  the literal escape is. Simulated old polls and below-boundary events cannot restore cleared messages.
  Layouts cover 320/390/1440px; existing workspace suite also covers 1000px. No JS exceptions.
- Core suites — **60 passed** (40 regression, 7 v2, 5 worker lifecycle, 8 native goal). Installed
  Codex 0.154.0 executes against a localhost fake Responses provider in isolated CODEX_HOME; its real
  native goal tool marks completion after a continuation. No paid model requests or user credentials.
- Author review: command dispatch never forwards unsupported commands; metadata methods are allowlisted;
  native states/accounting are retained; no goal resumes implicitly after server restart. Same current
  session permission scope and WISDOM selection. No new frontend dependency or periodic goal RPC.
- Deployed core 0.4.0 / UI 0.6.0 after verifying no active turn or workers. Existing private HTTPS URL
  loaded in Chromium at 390px: secure context, WISDOM, Help, slash suggestions, native goal metadata,
  **zero POSTs and zero JS errors**. Push remained ready with 2 subscriptions, 0 pending/failed.
- Inspected screenshots: `/tmp/harness-help-shots/phone-commands.png`, `phone-active-goal.png`,
  `live-phone-help.png`, `live-phone-slash-menu.png`, `live-phone-goal-form.png`. Fixture images are
  reproducible with `HARNESS_TEST_SCREENSHOTS=/tmp/harness-help-shots python3 -m unittest tests.test_page_smoke`.
- Limit: no paid real-model task was launched for release verification; the live check reads metadata
  and opens controls only. Native goals are Codex-only; unsupported terminal commands are documented.

Rollback: revert this release and core 0.4.0 together to UI 0.5.0/core 0.3.0, then restart the idle user
service. Durable history, push subscriptions and uploaded playbooks stay in their existing data dirs.
