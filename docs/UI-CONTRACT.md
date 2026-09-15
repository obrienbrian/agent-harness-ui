# agent-harness UI — API contract v1 (frozen 2026-09-15)

Server: `harness ui [--port 7788]` binds **127.0.0.1 only** (stdlib http.server). Static page at `/`.
All JSON. Errors: 4xx/5xx with `{"error": "<message>"}`. POST bodies are JSON; the server rejects
requests whose `Host` header is not localhost/127.0.0.1 (CSRF guard).

## Concepts
- **agent**: `user`, `orchestrator`, or a worker id `worker:<target>[:<model>]` (targets: claude, codex, local,
  codex-local, or a configured CLI name). Display names come from `~/.config/agent-harness/agents.json`
  (`{"gpt-6-astra": "Astra", "claude-fable-5-1": "Fable"}`), else the model, else the vendor.
- **message**: one hop between two agents. Kinds: `prompt` (user→orchestrator), `text` (orchestrator→user),
  `tool_use` (orchestrator→worker: a delegation request), `receipt` (worker→orchestrator: the result),
  `result` (orchestrator→user: end of turn), `error`.

## GET /api/state
```json
{
  "as_of": "2026-09-15T10:30:00-04:00",
  "orchestrator": {
    "vendor": "claude", "model": "fable", "effort": "high", "name": "Orchestrator",
    "session_ref": {"kind": "claude_session", "id": "…"} , "cwd": "/home/bso/GitHub/Projects",
    "busy": false, "turns": 3, "current_turn": null,
    "options": {
      "claude": {"models": ["fable", "opus", "sonnet", "haiku"], "efforts": ["low", "medium", "high", "xhigh", "max"]},
      "codex":  {"models": ["gpt-5.6-sol", "gpt-6-astra", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5"], "efforts": ["low", "medium", "high"]}
    }
  },
  "agents": [
    {"id": "user", "name": "Brian", "vendor": null, "model": null, "role": "user", "status": "idle", "messages": 12, "last_seen": "…"},
    {"id": "orchestrator", "name": "Fable", "vendor": "claude", "model": "fable", "role": "orchestrator", "status": "busy", "messages": 20, "last_seen": "…"},
    {"id": "worker:codex", "name": "Sol", "vendor": "codex", "model": "gpt-5.6-sol", "role": "worker", "status": "idle", "messages": 6, "last_seen": "…"}
  ],
  "messages": [
    {"id": "m_…", "ts": "…", "from": "user", "to": "orchestrator", "kind": "prompt", "text": "…", "meta": {}},
    {"id": "m_…", "ts": "…", "from": "orchestrator", "to": "worker:codex", "kind": "tool_use", "text": "<prompt sent>", "meta": {"tool": "delegate", "class": "readonly", "turn_id": "t_…", "label": "Reviewer"}},
    {"id": "m_…", "ts": "…", "from": "worker:codex", "to": "orchestrator", "kind": "receipt", "text": "<result_text>", "meta": {"root_code": "ok", "delegation_id": "dlg_…", "duration_ms": 4000}},
    {"id": "m_…", "ts": "…", "from": "orchestrator", "to": "user", "kind": "result", "text": "…", "meta": {"turn_id": "t_…", "usage": {}}}
  ],
  "live_sessions": [{"pid": 123, "name": "bso-a6", "status": "busy", "cwd": "/home/bso", "kind": "interactive"}],
  "harness": {"blockers": ["…"], "wisdom": {"root_code": "ok", "build_id": "…"}, "units": {"claude-remote-control.service": "active", "codex-remote-control.service": "active"}}
}
```
`messages` = the last 300, chronological, `text` already redacted and truncated to 4000 chars.

Pairing: a `tool_use` is written before the delegation runs, so it carries no `delegation_id`; the matching `receipt`
does. Pair them first-in-first-out per (orchestrator, worker) edge, using `delegation_id` only as a tiebreaker. A
`tool_use` with no receipt is *pending* while `orchestrator.busy` and its `turn_id` is `current_turn` (direct ones:
for 30 minutes). `receipt` hops carry no `turn_id`.

Additive field (v1.1, 2026-09-15): `meta.label` on `tool_use` — an optional role name (≤40 chars) the orchestrator
gave the worker for this task (`delegate` tool input `label`, CLI `--label`). Absent when not supplied; the UI shows
it as a chip under the worker and in the delegation card, and renders nothing when it is missing.

## GET /api/stats?minutes=60
```json
{"from": "…", "to": "…", "bucket_s": 60, "buckets": ["…", "…"],
 "edges": [{"from": "orchestrator", "to": "worker:codex", "counts": [0, 2, 1]}, {"from": "worker:codex", "to": "orchestrator", "counts": [0, 2, 1]}]}
```
Edges are directed; the frontend may merge a pair for the node graph. Buckets are minute-aligned.

## POST /api/orchestrator
Body: any of `{"vendor": "claude|codex", "model": "…", "effort": "…", "name": "…", "cwd": "/abs", "reset": true}`.
`reset` (or a vendor change) drops the session so the next turn starts fresh. Returns the `orchestrator` object.
Model and effort take effect on the next turn (they are per-invocation flags on the vendor CLI).

## POST /api/say
Body `{"text": "…"}`. Starts one orchestrator turn asynchronously; returns `{"turn_id": "t_…", "status": "started"}`
or 409 `{"error": "busy"}` if a turn is running. Messages appear in `/api/state` as the turn streams.

## POST /api/delegate
Body `{"to": "codex", "prompt": "…", "class": "readonly", "model": "…", "label": "Reviewer"}` (`model`, `label` optional). Runs a direct harness delegation
asynchronously as the user (`from: "user"` → worker); returns `{"id": "dlg_…", "status": "started"}`.

## GET /api/turn/<turn_id>
`{"turn_id": "…", "status": "running|done|error", "started_at": "…", "ended_at": "…|null", "events": 17, "error": null}`

## Frontend expectations (for the page author) — revised 2026-09-15, see `docs/DESIGN-SPEC.md`
- Single file `harness_ui/index.html`, no external assets (works offline, loopback): vanilla JS + CSS + inline SVG,
  no CDN, no web fonts, no build step. Build DOM with `createElement`/`textContent` only (no markup strings).
- Look: dark by default with a light token set; hairline borders, one accent, persona monograms tinted by a stable
  per-id hue. Layout: top bar (session pill opens settings), left rail (agents + system), centre (orchestration graph
  band → turn-grouped feed → composer), right rail (per-edge sparklines + turn timeline).
- Orchestration graph: orchestrator on top, workers in a row beneath, a "You" origin above; a comet travels the edge
  for every hop that arrived since the last poll (replay, staggered 120 ms, max 6 concurrent); pending delegations
  show a dashed edge, a spinning ring and an elapsed counter; completion flashes ok/err then shows the duration.
  Beyond six workers (four on phone) the least-recent ones collapse into a `+N` node. `prefers-reduced-motion`
  replaces travel with a 200 ms highlight and stops every loop.
- Feed: turns start at `prompt` and end at `result`; `tool_use` + paired `receipt` render as one delegation card
  (from → to · label chip · class · time · root_code badge · duration); `meta.direct` hops sit outside turns;
  `text` with `meta.tool` is a quiet tool note; `result` with empty text or `same_as_text` is not a row (its
  `usage` goes under the last orchestrator text). Never iterate `meta`; render only the fields named above.
- Poll `/api/state` every 2 s while `orchestrator.busy`, any delegation pending, or the message set changed, else
  every 8 s; `/api/stats` every 15 s. Unreachable server → banner with last contact and retry countdown; content
  stays visible but dimmed; stats show a placeholder rather than a stale chart.
- No Stop control (the API has none). A 409 from `/api/say` is shown inline under the composer, text preserved.
- Phone width (390 px) must work: rails move into a bottom sheet, the graph becomes a 150 px strip that collapses
  once the feed scrolls, tap targets ≥ 44 px, composer pinned above the safe-area inset.

## v2 additions (implemented 2026-09-15; all additive, v1 clients keep working; see agent-harness `docs/PLAN.md` slices 11–17)

`GET /api/state` gains:
```json
{
  "orchestrator": {
    "playbook": "wisdom",                       // "wisdom" | "none" | "<slug>"
    "team": {"mode": "suggest", "roles": [{"label": "Reviewer", "to": "codex", "model": "gpt-6-astra", "effort": "high", "class": "readonly", "brief": "Find gaps; cite file:line."}]},
    "options": {
      "targets": ["claude", "codex"],           // enabled delegation targets (local/codex-local only when enabled)
      "claude": {"models": ["fable", "opus", "sonnet", "haiku"], "efforts": ["low", "medium", "high", "xhigh", "max"], "model_efforts": {"haiku": ["low", "medium", "high"]}},
      "codex":  {"models": ["gpt-5.6-sol", "gpt-6-astra", "…"], "efforts": ["minimal", "low", "medium", "high", "xhigh", "max"], "model_efforts": {"gpt-5.3-codex-spark": ["low", "medium", "high"]}}
    }
  },
  "playbooks": [{"slug": "acme-review", "name": "ACME review protocol", "bytes": 18211, "sha256": "…", "uploaded_at": "…", "summary": "first heading or line"}],
  "teams": [{"slug": "reviewer-skeptic", "name": "Reviewer + Skeptic", "builtin": true, "team": {"mode": "suggest", "roles": ["…"]}}]
}
```
`model_efforts` lists only models whose support is known to differ from the vendor enum (learned from typed
`HARNESS_EFFORT_UNSUPPORTED` receipts); absent means "all vendor levels".

Messages: `tool_use.meta` may add `"playbook": "<source>"` and receipts may add `"provenance": {"source": "wisdom" | "playbook:<slug>", "sha256": "…", "bytes": n}`.
A stopped turn ends with an `error` hop whose `meta.root_code` is `HARNESS_TURN_STOPPED`.

New endpoints:
- `GET /api/playbooks` → `{"playbooks": [...]}`; `POST /api/playbooks` body `{"name": "…", "content": "<markdown ≤ 256 KB>", "replace": false}` → 201 `{"slug": …, "sha256": …}` (409 if the slug exists and `replace` is false; 400 on size/encoding/name); `DELETE /api/playbooks/<slug>` → 204 (409 while it is the active playbook).
- `GET /api/teams`; `POST /api/teams` body `{"name": "…", "team": {…}}` → 201; `DELETE /api/teams/<slug>` (builtin presets are read-only → 405).
- `POST /api/orchestrator` accepts `playbook` and `team` in addition to the v1 fields; both are validated (unknown slug, disabled target, unsupported effort → 400 with a message naming the field).
- `POST /api/turn/<turn_id>/stop` → 202 `{"turn_id": …, "status": "stopping"}`; 404 unknown; 409 not running.
- `GET /api/events` → `text/event-stream`; events `message` (one hop), `state` (orchestrator changed), `stats` (every 15 s); the page keeps polling as fallback and must dedupe by message `id`.
- `GET /api/receipt/<dlg_id>` → the ledger receipt (already redacted); 404 unknown.
- `POST /api/delegate/<dlg_id>/resume` body `{"prompt": "…"}` → 202 like `/api/delegate`.
- `GET /api/turns?limit=50` → `{"turns": [{"turn_id", "status", "started_at", "ended_at", "events", "error", "delegations", "prompt_head"}]}`.

Frontend expectations added: Settings popover gains "Playbook" (radio list + Upload .md + delete) and "Team"
(preset picker, roster editor, mode) sections using the existing `.field/.seg/.list/.chips-row` components; the
session pill caption shows the playbook slug when it is not `wisdom`; the graph draws dashed ghost nodes for team
roles that have not delegated yet; the composer busy line gets a Stop control; the effort control greys out levels
absent from `model_efforts[model]` and shows a one-line reason.


### V2 runtime details

Core 0.2.0 / UI 0.3.0 implement the additions above. `options.targets` is authoritative even when older
messages mention a now-disabled local target. Unlisted model effort support is unverified; the user chose
learning from normal use without probe calls. Vendor help census currently times out in this environment.

`GET /api/turn/<id>` also returns the redacted `messages` for that turn and its delegation count. New
turns persist a summary JSON beside the event JSONL; pre-v2 turns appear as `archived`, and interrupted
summaries become `error` after restart. `GET /api/state.today` and `/api/stats?minutes=1440.today` report
turns, delegations, success fraction (`ok_rate`), median duration (`p50_duration_ms`), and observed token usage.
Resumed receipts persist `resumed_from`, the original `playbook`, and its provenance hash.

Playbook documents over 60,000 UTF-8 bytes use an immutable file pointer with full SHA-256 instead of an
oversized argv element. Uploads still accept 256 KB. `provenance.delivery` says `pointer` or `inline` for
uploaded worker instructions. WISDOM uses its prior hooks/pointers; `none` omits harness-added instructions.

SSE sends bounded process-local events immediately and closes after 55 seconds for reconnection. Clients
must use state polling for durable catch-up and deduplicate message IDs. At most eight streams are open.
Stop targets the isolated turn process group, TERM then KILL after 600 ms; prior file edits are not reverted.

With `HARNESS_UI_TOKEN` set, every API request (including SSE) requires `Authorization: Bearer …`. The root
page is an uncredentialed shell that requests the token and keeps it in sessionStorage. Tokens never go in
URLs. Host checks remain; mutation requests also validate Origin, require JSON for POST, and allow up to
120 mutations per minute. HTML has fresh CSP nonces for script/style blocks; existing style attributes
remain allowed. `/manifest.webmanifest`, `/icon.svg`, and `/sw.js` are public shell assets. The service
worker never caches API data or credentials. Browser notifications require user permission via Settings.
