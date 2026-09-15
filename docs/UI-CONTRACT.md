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
    {"id": "m_…", "ts": "…", "from": "orchestrator", "to": "worker:codex", "kind": "tool_use", "text": "<prompt sent>", "meta": {"tool": "delegate", "class": "readonly", "delegation_id": "dlg_…"}},
    {"id": "m_…", "ts": "…", "from": "worker:codex", "to": "orchestrator", "kind": "receipt", "text": "<result_text>", "meta": {"root_code": "ok", "delegation_id": "dlg_…", "duration_ms": 4000}},
    {"id": "m_…", "ts": "…", "from": "orchestrator", "to": "user", "kind": "result", "text": "…", "meta": {"turn_id": "t_…", "usage": {}}}
  ],
  "live_sessions": [{"pid": 123, "name": "bso-a6", "status": "busy", "cwd": "/home/bso", "kind": "interactive"}],
  "harness": {"blockers": ["…"], "wisdom": {"root_code": "ok", "build_id": "…"}, "units": {"claude-remote-control.service": "active", "codex-remote-control.service": "active"}}
}
```
`messages` = the last 300, chronological, `text` already redacted and truncated to 4000 chars.

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
Body `{"to": "codex", "prompt": "…", "class": "readonly", "model": "…"}`. Runs a direct harness delegation
asynchronously as the user (`from: "user"` → worker); returns `{"id": "dlg_…", "status": "started"}`.

## GET /api/turn/<turn_id>
`{"turn_id": "…", "status": "running|done|error", "started_at": "…", "ended_at": "…|null", "events": 17, "error": null}`

## Frontend expectations (for the page author)
- Single file `harness/ui/index.html`, no external assets (works offline, loopback). Vanilla JS + inline SVG.
- Dark chat-log look (avatar circle with initial + name + timestamp + text per message, like Discord).
- Panels: agent roster (left), message feed (center), orchestrator card with vendor/model/effort selects, Apply,
  New session (top), composer (bottom, Enter to send, Shift+Enter newline), traffic panel (right): node graph of
  agents with edge thickness = message count, and a multi-line chart of `/api/stats` per edge with legend.
- Poll `/api/state` every 2 s while `orchestrator.busy` or any turn running, else every 8 s; `/api/stats` every 15 s.
- Render `tool_use` as "→ delegate to <name>: <text>" and `receipt` with a root_code badge (green ok / red otherwise).
- Never render anything from `meta` that looks like a secret; the server already redacts.
- Phone width (~400 px) must work: panels stack vertically; feed first.
