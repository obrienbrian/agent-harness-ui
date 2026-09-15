# Agent Harness UI — implementation spec

Everything needed to build `harness_ui/index.html` without guessing. Artboards live in
`Agent Harness UI.dc.html`; board ids (`1a`–`1j`) are referenced throughout.

## Current workspace refresh — UI 0.5.0

This section supersedes the original popover/graph geometry and motion limits below. The original
artboards remain the visual lineage. The additive v2 API, Stop, sessions, and push contracts in
UI-CONTRACT.md also supersede this document's original v1-only/no-Stop descriptions.

Focused WISDOM route: reversible UI changes; one mutation owner; preserve the existing API, WISDOM
default, saved history, and permission boundaries. Producer/consumer seam: existing state/SSE messages
→ bounded graph cards, existing playbook endpoints → separate selection, existing push state → status
and actions. No model calls, new dependencies, or polling for the redesign.

| Surface / criterion | Design and proof |
| --- | --- |
| Graph feels active without fabricated chatter | Compact dotted map beside three real message excerpts. Arrival uses a 240ms opacity/translate animation; click opens the full feed entry. Unchanged polling preserves nodes; history does not replay. Browser checks initial state, HTTP advance, feed navigation, unchanged state, and a 100-message burst. |
| Motion stays bounded | Four visible graph slots (overflow opens roster); desktop map 460×252, phone 390×150. Six active/six queued comets maximum. Hidden/collapsed views discard queued effects; reduced motion and device preference suppress animation. No new timer loop. Narrow graph containers show only the latest card. |
| Session settings remain usable | 580px centered dialog, Agent/Team/Preferences tabs, compact native model select, scrollable body, persistent save footer; phone bottom sheet. Keyboard tabs, focus containment/return, Escape, light/dark, widths 1440/1000/390/320 checked in Chromium. |
| WISDOM stays default; uploads require explicit selection | Dedicated top-bar playbook library; built-in WISDOM pinned first. Markdown file/drop input retains 256 KB/UTF-8/server secret validation. Upload stores; Use playbook switches only that setting. Busy UI holds selection. Browser verifies upload has no activation POST and unrelated Agent saves cannot overwrite playbook. Existing API proof covers actual injection and secret rejection. |
| Subscribed alerts do not overflow | Preferences displays an Enabled badge plus separate Test/Disable controls. Buttons have automatic height and wrapping; browser checks subscribed-state control bounds on narrow screens. Existing push backend retained. |

Plan: implement graph/menu/library → syntax/static checks → existing API and browser regressions plus
new interaction/layout checks → inspect fixture renders → observe private deployment. Rollback: restore
the preceding UI release and restart only when idle; no schema or persistent-data migration is involved.

## 0. Decisions

| Question | Decision |
| --- | --- |
| Layout | **Variant A** — graph band above the feed, collapsible to a 40px strip (`1b`). Rationale on board `00`. |
| Orchestrator label | `orchestrator.name` primary, persona + vendor + effort as caption. Workers lead with persona. |
| Accent | `#4FC3A1` dark / `#1c8f6e` light. One accent, interaction and pulses only. |
| Contract | v1 unchanged plus optional `meta.label` on `tool_use` (`1f`). |

## 1. Tokens

```css
:root {
  --bg:#0c0d0e; --panel:#121314; --raised:#17191a; --overlay:#1e2021; --sunk:#0e0f10;
  --line:rgba(255,255,255,.07); --line-strong:rgba(255,255,255,.12);
  --ink:#e8e9ea; --ink-2:#a2a6a8; --ink-3:#6b7073; --ink-4:#4b5053;
  --accent:#4FC3A1; --accent-soft:rgba(79,195,161,.12);
  --ok:#5fa37e; --warn:#c0964e; --err:#c76a62; --err-ink:#e0a7a2;
  --r-ctl:8px; --r-panel:12px; --r-sheet:16px;
  --s-1:4px; --s-2:8px; --s-3:12px; --s-4:16px; --s-5:24px; --s-6:32px; --s-7:48px;
  --font:Inter,"SF Pro Text",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,monospace;
  --shadow-overlay:0 16px 40px rgba(0,0,0,.55);
}
[data-theme="light"] {
  --bg:#fbfbfa; --panel:#f4f4f2; --raised:#fff; --overlay:#fff; --sunk:#fbfbfa;
  --line:rgba(0,0,0,.08); --line-strong:rgba(0,0,0,.14);
  --ink:#18191a; --ink-2:#5a5f61; --ink-3:#8a8f91; --ink-4:#9a9fa1;
  --accent:#1c8f6e; --accent-soft:rgba(28,143,110,.08);
  --ok:#2f7a55; --warn:#8a6220; --err:#a0442f; --err-ink:#8a3323;
  --shadow-overlay:0 16px 40px rgba(0,0,0,.14);
}
```

Focus ring, everywhere: `outline:2px solid var(--accent); outline-offset:2px`.
Surfaces are separated by 1px `--line`; no shadows except overlays.

### Type

| Token | Value | Use |
| --- | --- | --- |
| `--t-display` | 22px / 500 / -0.01em | empty states, overlay titles |
| `--t-head` | 16px / 500 | panel headers |
| `--t-body` | 13.5px / 400 / 1.55 | feed text |
| `--t-small` | 12px / 400 / 1.45 | captions |
| `--t-caps` | 11px / 600 / 0.04em / uppercase | section + chip labels |
| `--t-mono` | 12px `--mono` | times, durations, ids, paths |

`font-variant-numeric: tabular-nums` on every timestamp, duration, count, token figure.
Monospace only for code-like content inside messages, ids, and paths.

### Agent hues

```js
const hueOf = id => { let h = 0; for (const c of id) h = (h * 31 + c.charCodeAt(0)) % 360; return (h + 25) % 360; };
// dark:  --agent oklch(0.78 0.065 H)  --agent-fill oklch(0.78 0.065 H / .18)
// light: --agent oklch(0.55 0.09  H)  --agent-fill oklch(0.55 0.09  H / .16)
```

Fixture hues: Brian 252, Fable 305, Sol 68, Sonnet 205, Gemma 148.
Disc sizes: 24px (You origin), 28px (feed, roster), 40px (graph worker), 52px (graph orchestrator).
Orchestrator disc has a permanent 1px ring at 50% of its hue. Workers get a ring only while
working, or for 900ms on completion.

## 2. Layout

Top bar 48px. Below it: left rail 272px · centre flex · right rail 320px, 1px `--line` between.

- **Top bar** — product mark; session pill (`name · vendor · model · effort` + status dot, opens
  the settings popover); turn count; `loopback 127.0.0.1:7788`; `as of hh:mm:ss`; `⌘K` hint.
- **Graph band** — 30px header row + 798×240 stage, `--sunk` ground. Collapses to a 40px strip
  reading `Fable · idle · 0 pending` (`1e`).
- **Feed** — turn-grouped, newest at bottom, auto-follow, `aria-live="polite"`. Turn header is a
  centred rule: `t_9f21 · 10:36:58 · 21.4s · 2 delegations`.
- **Composer** — sticky, `--panel`, r12. Enter sends, Shift+Enter newline. Disabled during a turn
  with the thinking dots + `Fable is working · 0:12 · 1 delegation pending` line beneath.
- **Right rail** — one sparkline row per directed edge (`104×26` polyline, no axes, no legend) plus
  a per-delegation span chart for the current/last turn.

Phone 390px: rails collapse into a hamburger bottom sheet (`1g`), graph becomes a 126px strip with
straight edges, tap targets ≥44px, composer pinned with 28px bottom inset.

## 3. Graph geometry

Stage 798×240. Anchors: You centre (399,12); orchestrator disc top 44, centre (399,70) — its name
and caption sit **to the right of the disc**, not below it, so the vertical corridor under the disc
belongs entirely to the edges. Workers disc top 130, centres y=150, x at
`399 + (i - (n-1)/2) * 259` for n ≤ 3, tightening to a 132px pitch at n = 6, then a `+N` node.
The 288px rail variant instead starts its edges at y=142, below the caption block, with the worker
row at y=176.

Edge paths (reused verbatim as `offset-path`):

```
you → orch        M399,26 L399,44
orch → worker L   M399,96 C399,116 140,110 140,130
orch → worker C   M399,96 L399,130
orch → worker R   M399,96 C399,116 658,110 658,130
```

Resting stroke weight by cumulative pair count: 1px (1–3), 2px (4–12), 3px (13+); colour
`--line-strong`. No arrowheads. Hover an edge → tooltip `Fable → Sol · 6 messages · last 10:37:10`.
Hover/tap a node → its edges at full opacity, everything else to 0.45; click scrolls the feed to
that agent's latest message and filters the roster.

## 4. Motion

All of it is CSS keyframes on `transform` / `opacity` / `offset-distance` / `stroke-dashoffset`.

```css
@keyframes ah-travel  { from { offset-distance:0% }  to { offset-distance:100% } }
@keyframes ah-dash    { to { stroke-dashoffset:-32 } }
@keyframes ah-spin    { to { transform:rotate(360deg) } }
@keyframes ah-breath  { 0%,100% { opacity:.35 } 50% { opacity:.7 } }
@keyframes ah-flash   { 0%,100% { opacity:0 }   40% { opacity:.6 } }
@keyframes ah-dots    { 0%,80%,100% { opacity:.22 } 40% { opacity:1 } }
@keyframes ah-shimmer { 0% { background-position:0% 0 } 100% { background-position:200% 0 } }
@keyframes ah-blip    { 0%,100% { opacity:.25 } 50% { opacity:1 } }
```

| Element | Spec |
| --- | --- |
| Hop comet | 11×4px, r2, `linear-gradient(90deg, transparent, var(--agent))`; `offset-path:path(var(--edge))`, `offset-rotate:auto`; `ah-travel 900ms cubic-bezier(.4,0,.2,1) var(--stagger) 1 both`; removed from the DOM on `animationend`. `receipt` and `result` add `reverse`. |
| Batch replay | Messages new since the last poll, in `ts` order, `--stagger: i * 120ms`; max 6 concurrent, remainder queued FIFO. |
| Edge in flight | Duplicate path on top at `--accent`, opacity 0 → .5 → 0 over the comet's 900ms. |
| Arrival flash | Destination disc ring `ah-flash 300ms ease-out`. |
| Working edge | `stroke-dasharray:6 10`, worker hue at 60%, `ah-dash 2s linear infinite`. |
| Working ring | 44px circle, `stroke-dasharray:34 104`, `ah-spin 1.6s linear infinite`; caption `working · m:ss`, counter from `tool_use.ts`. |
| Busy halo | Orchestrator only, while `orchestrator.busy`: radial gradient inset -7px, `ah-breath 2.4s ease-in-out infinite`. The only idle-ish loop in the page. |
| Completion | Ring arc closes to full in 300ms, fills ok/err for 600ms with check/alert glyph, fades out; elapsed counter freezes to `4.0s` for 3s then hides; edge returns to rest one weight step heavier. |
| Pending result | Two shimmer bars (72% / 48% width), `ah-shimmer 1.6s linear infinite`, second delayed 200ms. |
| Thinking dots | Three 4px dots, `ah-dots 1.4s ease-in-out infinite`, 180ms apart. |
| Status dot | `ah-blip 2.4s ease-in-out infinite` while busy; static while idle. |

**Reduced motion** (`@media (prefers-reduced-motion: reduce)`): no comets, no loops. A new hop lights
the edge and destination ring for 200ms via opacity only; working is a static dashed edge plus
`working · 0:08`; the halo, dash flow, spin, shimmer and dots are all static. Elapsed counters keep
ticking (they are text, not animation).

**offset-path fallback**: `CSS.supports('offset-path','path("M0 0")')` — if false, render an SVG
`<circle r="2">` with `<animateMotion dur="0.9s" path="<same string>" fill="freeze">`.

## 5. Components

- **Delegation card** (r12, `--panel`): header `Fable → Sol · Reviewer · readonly · 10:37:05` then
  right-aligned `root_code` badge + duration; body = the `tool_use` text at `--t-small` `--ink-2`,
  clamped to 6 lines; result block on `--sunk` at `--t-body`. Pending shows the spinner badge with a
  live counter and shimmer bars. `class: "edit"` gets a warn-bordered `EDIT` chip. Collapsed is the
  header row alone. Error variant: err-tinted border and result block, mono error text, `retry as
  readonly` and `open unit log` as quiet text actions.
- **Turn header / unread divider** — centred rule, mono caption; unread divider uses the accent.
- **Roster row** — 28px disc, persona, `vendor-tag · model`, message count, status glyph. Status is
  never colour alone: idle = dot, working = spinner, ok = check, error = alert circle.
- **System section** — blockers as plain rows with a warn triangle, units as `name` + state pill,
  WISDOM `ok` badge, live sessions.
- **Overlays** (`1f`) — settings popover 360px; command palette 520px with grouped actions (New
  session, Switch vendor, Set effort, Delegate directly, Jump to latest, Toggle graph, Toggle
  light/dark); direct-delegate sheet 400px; `/delegate` inline affordance. All dismiss on Escape.
- **Toasts** — confirmations of the user's own actions only; bottom right desktop / top on phone;
  4s auto-dismiss.
- **Banners** — unreachable: 32px err-tinted strip with a blipping dot, last-contact and retry
  countdown, content behind greyed to 0.72. 409 busy: inline under the composer, text preserved.
- **Empty states** — graph shows the orchestrator alone over a dashed placeholder row; feed shows a
  short welcome with the composer focused.

## 6. Data handling

- Poll `/api/state` every 2s while `orchestrator.busy` or any turn is running, else 8s;
  `/api/stats?minutes=60` every 15s. Diff `messages[]` by `id` to find what is new; that set drives
  the comet replay.
- Pair `tool_use` ↔ `receipt` by `meta.delegation_id`. A `tool_use` without a receipt is pending.
- `meta.direct === true` → render at top level as `Brian → Sol`, outside any turn.
- Role chip comes from `meta.label`; absent, render nothing (no empty slot). Last label wins per
  worker per turn; the full history stays in the cards.
- Show `meta.usage` on a `result` only when non-empty.
- Render only known fields: `id, ts, from, to, kind, text, meta.{tool,class,label,delegation_id,
  turn_id,root_code,duration_ms,usage,direct}`. Never iterate `meta` generically, never print `cwd`
  outside the settings drawer, never surface a raw agent id except in a `title` tooltip.
- No Stop control. The composer explains the wait instead.

## Help and command flow — UI 0.6.0

One command registry supplies composer suggestions and the Help reference. Top-bar `?` and the command
palette open the existing focus-trapped drawer, with Getting started and Commands views. Command rows
insert text for review, never execute on tap. Help covers workspace choice, real exchanges, goals,
playbooks, team/delegation, sessions/history, Stop/reset, phone lifecycle, notifications, and shortcuts.

`/goal` uses the native Codex goal contract. A compact strip above the composer shows objective, status,
and native token usage. The detail drawer has pause/resume/edit/clear and an optional-budget form. Form
values are never overwritten by incoming state events. Unsupported providers explain how to select Codex.
`/clear` retains history but advances an exact feed boundary; stale polls and event replay cannot undo it.

Proof: API boundary/history tests; installed Codex + isolated localhost provider in core; Chromium
interactions through actual composer and forms, including busy commands, keyboard selection, clear/new,
unsupported-command refusal, 320/390/1440px layouts. Same existing overlay/focus, SSE/poll, and permission
mechanisms. Rollback UI and core together to 0.5.0/0.3.0 and restart only while idle.
