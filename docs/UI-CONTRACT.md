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

## Phone control additions — 2026-09-15

These supersede the host-only and foreground-notification descriptions above. The listener stays on
loopback. `HARNESS_UI_ORIGIN` + `HARNESS_UI_TAILSCALE_USER` opts into one exact HTTPS origin and one
verified Serve identity. The remote page/assets also require that identity. Wrong identity/Host returns
403; mutation Origin must match HTTPS. Local access retains its optional bearer-token flow.

- State gains `workers: [{id,to,model,label,cwd,class,turn_id,started_at,status,process}]`. Clients cancel
  using `id`; `process` is a Linux identity, not a client-selected PID.
- `live_sessions` includes external Claude/Codex processes and adds `id`, `vendor`, `source`, `can_end`,
  `observed_at`. IDs bind boot/PID/start time. Managed workers are excluded; services have `can_end:false`.
- `POST /api/sessions/<id>/end {}` → 202 ending; 409 stale/ended; 403 service. Uses verified pidfd SIGTERM;
  retains transcripts. A bare PID is not accepted.
- `POST /api/orchestrator/end {}` → 200 ended; 409 busy. Clears the saved session, retaining history.
  Start/end are serialized so ending an idle session cannot race with a new turn.
- `POST /api/delegate/<id>/cancel {}` → 202 stopping; 409 finished/unknown. Cancels the isolated worker
  process group and persists `HARNESS_WORKER_CANCELLED`. Applies to direct/resumed/MCP workers. Turn Stop
  also cancels its workers. Orphan reconciliation preserves a `HARNESS_WORKER_INTERRUPTED` receipt.
- Completed turns append `status` messages with `meta.notification: complete|attention` and `turn_id`.
  Stopped turns do not alert. Direct receipts trigger alerts except for user cancellations.
- `GET /api/push` → readiness, public VAPID key, subscription/pending/failed counts, generic error.
- `POST /api/push/subscribe {subscription}` → 201 `{id,enabled:true}`. Valid encryption keys and trusted
  Google/Mozilla/Apple HTTPS endpoints required; at most 16 devices. Endpoints/keys stay private.
- `POST /api/push/unsubscribe {id}` → 200; removes subscription/queued jobs.
- `POST /api/push/test {id}` → 202 queued; 404 unregistered. Push uses normal auth/Origin guards; missing
  optional runtime → 503, without affecting ordinary use.

The manifest has a stable ID, standalone display, and 192/512 PNG icons. The service worker handles push
and clicks without caching APIs. Payloads contain generic text and a local saved-work link. Background
display requires the phone owner to subscribe and grant OS permission.

## Help and native goal additions — UI 0.6.0 / core 0.4.0

- `GET /api/goal` refreshes native metadata for the active Harness Codex thread only. Returns
  `{supported, goal, running, pending}`; unsupported providers include a message and null goal. Goal
  contains native `threadId`, `objective`, `status`, `tokenBudget`, `tokensUsed`, `timeUsedSeconds`, and
  timestamps. Optional `execution_error` records a Harness continuation failure. This is a metadata
  operation, never a model request. Unavailable native service returns 503.
- `POST /api/goal` takes `action: set|edit|pause|resume|clear`, plus an objective (1–4,000 characters)
  for set/edit and optional positive-integer `token_budget`. Null/omitted budget on set/edit removes a
  budget. Set/resume starts work; edit saves paused with reset accounting; pause/clear can stop active
  work. Native non-active status or turn failure stops continuation. Busy conflicts return 409;
  unsupported/invalid requests return 400. Provider/workspace/playbook/team/reset changes require pause.
- `/api/state` adds `goal` with the same shape from a cached snapshot: no native subprocess per poll.
  `orchestrator.busy` includes gaps between managed goal turns. After restart, `running:false` even if
  native status is active; explicit resume is required. Permission scope stays unchanged.
- `POST /api/clear` takes optional boolean `clear_view` (default true) and optional session `name`.
  Resets the active conversation, preserves history/receipts/settings, and if requested advances the
  persisted `orchestrator.feed_offset` to the current message-log byte length. Returns
  `{status:"cleared",feed_offset}`. Busy turns/goals return 409; bad input returns 400.
- New messages have an additive byte `offset`. State messages are read after the feed boundary. History,
  receipts, stats and exports still read all saved messages. Clients reject older feed generations and
  discard below-boundary replay events; `/new` calls clear with `clear_view:false`.
- Slash commands are frontend controls, not model instructions. `/api/say` refuses command-shaped
  single-slash text (400); `//` escapes one slash. Absolute filesystem paths remain valid prompts.
  Unsupported native CLI commands such as `/compact`, `/permissions`, `/mcp`, and native chat `/resume`
  are not forwarded. Worker receipt resume remains available in its existing drawer.
- Goal chains emit one terminal background notification instead of one per continuation. Native goal
  state is authoritative, including usage accounting that stops when the goal is marked complete.

All existing Host/Origin/auth/JSON/rate-limit checks apply to these routes. No thread ID or RPC method
is accepted from an API client. The installed vendor CLI alone handles its own credentials.
