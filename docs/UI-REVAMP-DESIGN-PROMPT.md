# Claude Design brief: Agent Harness UI revamp

Redesign the web UI of **Agent Harness** (repo `agent-harness-ui`) into a modern, clean, minimalist
control surface for a multi-agent coding harness. The centerpiece is a **live orchestration graph**:
the orchestrator at the top, its worker agents in a row beneath it, and animated pulses that travel
along the edges every time a message hops from one agent to another. Every worker shows the persona
name the harness gives it (Fable, Sol, Astra, Sonnet…) plus the role label the orchestrator assigned
for that delegation (Reviewer, Skeptic, Researcher…).

Produce a multi-artboard design canvas (artboards listed at the end) plus a written token and motion
spec precise enough that a developer can implement it in one dependency-free HTML file.

---

## 1. What the product is

Agent Harness runs coding-agent sessions on two subscriptions at once (Claude Code on the Claude
subscription, Codex CLI on the ChatGPT subscription) plus local Ollama models, on a single Linux
workstation. One **orchestrator** agent takes the user's prompt, delegates bounded tasks to **worker**
agents through a `delegate` tool, receives a typed **receipt** back from each worker, and replies to
the user. The UI is the window onto that traffic.

- **Single user.** The owner, who codes 24/7 and reaches the UI mostly **from a phone** over an SSH
  tunnel, sometimes from a 1440px desktop. Phone is first-class, not a breakpoint afterthought.
- **Private and local.** The server binds `127.0.0.1:7788` only. There is no login, no multi-tenant
  anything. The UI should quietly signal "this is your private loopback console".
- **Dark by default.** Used at night, on a phone, for long stretches. Provide a light token set too.

## 2. Hard implementation constraints (the design must respect these)

1. **One static file.** The page is a single `index.html`: vanilla JS, CSS, inline SVG. No build
   step, no framework, **no CDN, no web fonts, no icon fonts**. It must work offline on loopback.
   Use a system font stack (for example `Inter, "SF Pro Text", system-ui, -apple-system, "Segoe UI",
   Roboto, sans-serif`; Inter renders only if installed locally). Icons are small inline SVG line glyphs.
2. **Animations must be CSS/SVG-native.** Anything you specify has to be achievable with CSS
   keyframes on `transform`/`opacity`, SVG `stroke-dasharray`/`stroke-dashoffset`, CSS
   `offset-path`/`offset-distance`, or SVG `<animateMotion>`. No animation libraries.
3. **Data arrives by polling, not streaming.** The page polls `/api/state` every 2 s while the
   orchestrator is busy and every 8 s when idle, and `/api/stats` every 15 s. New messages therefore
   land in small batches. The "live flow" animation is a **replay of the hops that arrived since the
   last poll**, staggered in message order, not a token stream. Design the motion around that.
4. **Frozen API contract v1.** Everything below is what the backend already emits. Two small
   additive fields are proposed in §6 and clearly marked; design with a fallback if they are absent.
5. **Phone width ~390 px must work** with panels stacked, feed first, and the graph in a compact form.
6. **Accessibility.** Visible focus rings, `aria-live` feed, status never conveyed by color alone
   (always a glyph or text too), and a full `prefers-reduced-motion` fallback for every animation.
7. **Never render secrets.** The server redacts text already; the UI must not surface raw `meta`
   blobs, environment values, or paths from unexpected fields.
8. **Calm when idle.** No perpetual animation while nothing is happening (battery, phone, focus).
   Motion is reserved for real events.

## 3. Data model the UI renders (from `GET /api/state` and `GET /api/stats`)

**Agents** (`agents[]`): `id`, `name`, `vendor`, `model`, `role` (`user` | `orchestrator` | `worker`),
`status` (`idle` | `busy` | `error`), `messages` (count), `last_seen`.
- Ids: `user`, `orchestrator`, and workers like `worker:codex`, `worker:claude:sonnet`,
  `worker:local:gemma4:12b`.
- **Persona names** come from the harness name map: Fable, Opus, Sonnet, Haiku (Claude);
  Astra, Sol, Terra, Luna, Spark, GPT-5.5 (Codex); OSS-20B, Gemma (local). The user's display name
  comes from the same map (for example "Brian"; it defaults to the login name).
  The orchestrator's name is the persona of whatever model it currently runs (for example "Fable").

**Messages** (`messages[]`, last 300, chronological): `id`, `ts`, `from`, `to`, `kind`, `text`, `meta`.
- Kinds and direction:
  - `prompt`   user → orchestrator
  - `text`     orchestrator → user (intermediate assistant text or a tool call summary)
  - `tool_use` orchestrator → worker (a delegation; `text` is the prompt sent)
  - `receipt`  worker → orchestrator (the result; `meta.root_code` is `ok` or an error code such as
    `HARNESS_TOOL_CALL_FAILED`; `meta.duration_ms`; `meta.delegation_id` pairs it with its `tool_use`)
  - `result`   orchestrator → user (end of turn; `meta.turn_id`, optional `meta.usage`)
  - `error`
- `tool_use` meta: `tool` ("delegate"), `class` (`readonly` | `edit`), `delegation_id`, `turn_id`,
  and `direct: true` when the user delegated directly (then `from` is `user`).

**Orchestrator** (`orchestrator`): `vendor` (`claude` | `codex`), `model`, `effort`, `name`, `cwd`,
`session_ref.id`, `turns`, `busy`, `current_turn`, and `options` (per-vendor model and effort lists:
Claude efforts low/medium/high/xhigh/max; Codex efforts low/medium/high).

**Harness health** (`harness`): `blockers[]` (plain strings), `units{}` (systemd unit → state),
`wisdom.root_code` (`ok` or not), plus `live_sessions[]` (`name`, `status`, `cwd`, `kind`).

**Stats** (`/api/stats?minutes=60`): minute buckets and directed `edges[]` with per-bucket counts.

**Actions** the UI can take: send a prompt (`POST /api/say`, returns 409 "busy" if a turn is running),
change orchestrator vendor/model/effort/name/cwd or reset the session (`POST /api/orchestrator`),
and delegate directly to a worker (`POST /api/delegate` with `to`, `prompt`, `class`, optional `model`).
There is **no stop/cancel endpoint** today; do not design a primary Stop control (a disabled,
clearly-future affordance is acceptable if noted).

## 4. Visual direction

**Modern, clean, minimalist.** Think Linear, Vercel, Raycast, and the calm end of developer tooling:
hairline borders, near-monochrome surfaces, a single accent, generous whitespace, small tracked-out
uppercase labels, tabular numerals for times and durations. Restraint is the brand.

- **Move away from the current look**: it is a Discord clone (blurple accent, saturated avatar
  circles, chunky cards). Do not carry that over.
- **Surfaces**: 3 to 4 stacked dark neutrals (page, panel, raised, overlay) separated by 1px borders
  at 6 to 10% white rather than shadows. Light theme mirrors the same roles.
- **One accent color**, used only for interaction and the live-flow pulse. Semantic colors (ok,
  warn, error) are muted, never neon.
- **Agent identity**: each agent gets a stable, low-saturation hue derived from its id, used as a soft
  tinted monogram disc (initial letter) and as the color of its pulses. Vendor is shown by a tiny
  inline glyph or two-letter tag (`cl`, `cx`, `lo`) next to the model, never by a logo.
- **Type**: 13 to 14px base, 11px caps labels at 0.04em tracking, `font-variant-numeric: tabular-nums`
  on timestamps, durations, counts. Monospace only for code-like text inside messages.
- **Radii** 8px controls, 12px panels. **Shadows** essentially none; overlays get one soft shadow.
- **Density**: comfortable on desktop, compact on phone. The feed is the reading surface; keep it quiet.

## 5. Information architecture and layout

Design two desktop layout variants (A and B) for the idle state, then carry one forward for the
remaining desktop artboards. Say which you chose and why.

**Top bar (48 px):** product name; a **session pill** that reads like `Fable · claude · high` with a
small status dot (idle / working); turn count; a `loopback 127.0.0.1:7788` hint; an "as of hh:mm:ss"
freshness stamp; a subtle keyboard hint for a command palette (`⌘K` / `Ctrl K`, see §8).

**Orchestration graph (the hero):**
- Variant A: full-width band above the feed in the center column, ~240 to 280 px tall, collapsible to
  a 40 px status strip when idle.
- Variant B: top of a right rail (320 px), always visible, feed gets the full center.
- Content and behavior are specified in §6.

**Feed (center, fills):** a turn-grouped timeline, newest at the bottom, auto-follow with a
"jump to latest" pill when scrolled up.
- A **turn** starts at the user's `prompt` and ends at the `result`. Show a slim turn header with the
  turn id (short), start time, total duration once it ends, and number of delegations.
- The orchestrator's `text` messages render as plain, quiet assistant text with the persona monogram.
- Each delegation is a **delegation card** nested under the turn, pairing the `tool_use` with its
  `receipt` by `delegation_id`: header row `Fable → Sol · Reviewer · readonly`, the prompt text
  (clamped to ~6 lines with "show more"), then the result block with a `root_code` badge (`ok` in
  muted green with a check glyph, anything else in muted red with an alert glyph), duration
  (`4.0s`), and a live elapsed timer while pending. Pending cards show a soft shimmer bar where the
  result will appear. `edit` class gets a small distinct chip so it stands out from `readonly`.
- Direct delegations (`meta.direct`) show `Brian → Sol` and sit at top level, not inside a turn.
- `error` kind messages get an inline error row, not a toast.
- Long texts collapse; code-like content in a monospace block with a copy button on hover.
- Timestamps are `hh:mm:ss` with relative time on hover.

**Composer (sticky bottom of center):** one textarea, Enter to send, Shift+Enter newline, a
single send button. While a turn runs: the composer stays visible but disabled, with an inline
status line `Fable is working · 0:12` and a thinking indicator (three dots). A 409 "busy" reply is
shown inline under the composer, not as a toast.

**Orchestrator settings:** move the current permanent card into a **popover or drawer** opened from
the session pill: vendor as a two-way segmented control, model as a list, effort as a segmented
control whose options change with vendor, name, working directory, an Apply button, and a
"New session" action with a one-line confirmation. Include the note "Model and effort take effect
on the next turn."

**Direct delegate:** secondary, out of the way. Either a small "Delegate directly" sheet reached from
the composer's overflow, or a slash-command affordance in the composer (typing `/delegate` shows a
compact inline form: target, class, optional model, prompt). Design whichever reads cleaner; the
sheet is the safer default.

**Left rail (desktop, 260 to 280 px):** the **agent roster** (monogram, persona name, vendor · model,
status dot, message count, last seen) and a collapsible **System** section: blockers (each a plain
row with a warning glyph), systemd units as name + state pill, a WISDOM `ok` badge, and live
sessions. On phone this lives behind a menu or bottom sheet.

**Insights (right rail or a collapsible panel):** the messages-per-minute chart as a set of small
sparklines, one per directed edge, with the edge name (`Fable → Sol`) and current-hour total, rather
than one busy multi-line chart with a legend. Optional stretch: a **turn timeline** (Gantt-style
spans, one bar per delegation from `tool_use` time to `receipt` time) for the last turn.

**Empty state:** the graph shows the orchestrator alone with a faint placeholder row and the text
"No workers yet. Delegations will appear here as the orchestrator hands out work."; the feed shows a
short welcome with the composer focused.

**Unreachable state:** a slim top banner "Cannot reach harness server. Retrying…" with a pulsing
dot; the page keeps its last known content greyed slightly.

## 6. The live orchestration graph (specify this in detail)

**Topology.** A vertical hierarchy:
- Row 0: a small **You** origin (monogram "B", label "Brian"), or on phone the composer itself is
  the origin.
- Row 1: the **orchestrator node**, larger, centered: monogram disc, persona name ("Fable"),
  caption `claude · fable · high`, a status ring around the disc.
- Row 2: **worker nodes** in a row, evenly spaced, each with monogram disc, persona name ("Sol"),
  caption `codex · gpt-5.6-sol`, status ring, and, when known, the **assigned role label** as a small
  chip under the name (`Reviewer`). Up to 6 fit comfortably at desktop; beyond that, collapse into
  a `+N` node or allow horizontal scroll on phone.
- **Edges** are smooth vertical S-curves from the orchestrator's bottom anchor to each worker's top
  anchor, and one from You to the orchestrator. At rest an edge is a 1 to 2 px hairline whose weight
  encodes cumulative message count between the pair (1px for a few, up to 3px for many). No
  arrowheads at rest; direction is conveyed by placement and by pulse motion.

**Assigned role labels (proposed additive contract field).** Today a worker's name comes only from
its model. The revamp proposes that the orchestrator can pass a `label` when it delegates
(`delegate` tool input `label: "Reviewer"`), which the backend echoes as `meta.label` on the
`tool_use` message. The UI shows persona name first, role label second: **Sol** · Reviewer. When
`label` is absent, show only the persona name and vendor · model; the layout must not look broken
without it. If the same worker id receives different labels in one turn, show the most recent and
keep the history in the delegation cards.

**Hop pulses (the core animation).** For every new message that arrived since the last poll:
- A small comet (a 4 px dot with a short fading tail, in the sending agent's hue) travels along the
  edge from `from` to `to`. `tool_use` travels down; `receipt` travels up; `prompt` travels from You
  to the orchestrator; `result` travels from the orchestrator back to You.
- Duration ~900 ms, `cubic-bezier(0.4, 0, 0.2, 1)`. On arrival the destination disc gives a single
  soft flash (ring opacity 0 → 0.6 → 0 over 300 ms).
- A batch of N new messages plays in message order with a 120 ms stagger; cap concurrent comets at
  6, queuing the rest, so a busy turn stays legible instead of turning into confetti.
- While a comet is in flight the edge itself brightens from hairline neutral to 50% accent.

**Working state.** A delegation is pending when its `tool_use` has no matching `receipt` yet.
- The edge switches to a slow directional dash flow (dash 6 / gap 10, `stroke-dashoffset` cycling
  every 2 s) in the worker's hue at 60% opacity.
- The worker's status ring becomes an indeterminate arc rotating once per 1.6 s, and a live elapsed
  counter (`0:08`) appears under the caption. The node's caption line reads `working`.
- The orchestrator, while `busy`, gets a slow breathing halo (opacity 0.35 → 0.7, 2.4 s ease-in-out
  loop). This is the only idle-ish loop allowed, and only while busy.

**Completion.** When the receipt lands: the ring arc completes to a full circle in 300 ms, fills
ok-green (or error-red) for 600 ms with a check (or alert) glyph, then fades back to the neutral
ring; the elapsed counter freezes into a duration badge (`4.0s`) for a few seconds, then hides. The
edge returns to its resting hairline, one step heavier than before.

**Selection and hover.** Hovering or tapping a node highlights its edges and dims the rest; clicking
scrolls the feed to that agent's latest message and filters the roster row. Hovering an edge shows
a tooltip `Fable → Sol · 6 messages · last 10:37:10`.

**Reduced motion.** No travel, no loops. A new hop highlights the edge and destination ring for
200 ms via opacity only; the working state is a static dashed edge plus the text `working · 0:08`.

**Phone variant.** A compact strip: orchestrator chip centered on top, worker chips in a horizontally
scrollable row beneath, connected by short straight edges. Pulses still play (shorter path, ~600 ms).
The strip collapses to a single line (`Fable · working · 2 delegations`) when the user scrolls the
feed, and expands on tap.

## 7. Agent identity and naming rules

- Persona name is the primary label everywhere (feed, roster, graph). Vendor and model are the
  caption. Never show raw ids like `worker:codex` except in a tooltip.
- Monogram disc: first letter of the persona name, soft tinted background in the agent's hue at
  ~18% alpha with the hue at full for the letter, 28 px in the feed, 40 px for workers in the graph,
  52 px for the orchestrator.
- The orchestrator's disc gets a thin permanent ring to mark its role; workers get a ring only while
  working or briefly on completion.
- Role label chip: 11px, tracked caps, neutral border, no fill.

## 8. Modern-harness details to include

Design these as real components, not decorations:
- Thinking indicator (three dots) and result shimmer while pending.
- Delegation cards with paired request/result, class chip, `root_code` badge, duration.
- Turn headers with total duration and delegation count; optional turn timeline spans.
- Live elapsed counters on pending work; freeze to a duration badge on completion.
- Command palette (`⌘K` / `Ctrl K`) with actions: New session, Switch vendor, Set effort, Delegate
  directly, Jump to latest, Toggle graph, Toggle light/dark. Design the palette surface.
- Keyboard-first composer: Enter sends, Shift+Enter newline, `/delegate` slash affordance,
  Escape closes overlays.
- "Jump to latest" pill and an unread divider when new messages arrive while scrolled up.
- Connection freshness stamp, unreachable banner, inline 409 busy notice.
- Copy on hover for message text and code blocks; relative time on hover.
- Usage line on a turn's `result` when `meta.usage` is present (tokens in, out); hide when empty.
- Toasts only for confirmations of the user's own actions (settings applied, session reset), bottom
  right on desktop, top on phone, auto-dismiss.

## 9. States to show

Idle with history; live turn with two workers (one working, one just completed ok); a turn with an
error receipt; empty (no traffic yet); server unreachable; composer busy with 409; settings popover
open; command palette open; phone idle; phone live; light theme of one desktop screen.

## 10. Sample content (use this, it is realistic for this harness)

- Brian → Fable (prompt, 10:36:58): "Review docs/DESIGN.md for missing failure modes and have Codex
  double-check the rollback table in docs/RUNBOOK.md."
- Fable → Sol · Reviewer · readonly (tool_use, 10:37:05): "Review docs/DESIGN.md for missing failure
  modes. Return a numbered list with file line references."
- Fable → Sonnet · Skeptic · readonly (tool_use, 10:37:06): "Independently verify every row of the
  rollback table in docs/RUNBOOK.md against the files it names."
- Sol → Fable (receipt ok · 4.0s, 10:37:10): "Found 3 gaps: 1) no failure mode for a stuck
  remote-control unit…"
- Sonnet → Fable (receipt, pending, working · 0:08)
- Fable → Brian (result, 10:37:19): "Two gaps confirmed by both reviewers; one rollback row points
  at a backup path that does not exist yet…"
- An earlier turn where a receipt failed: `root_code HARNESS_TOOL_CALL_FAILED · 0.3s`.
- Roster: Brian (user), Fable (claude · fable, orchestrator, working), Sol (codex · gpt-5.6-sol),
  Sonnet (claude · sonnet), Gemma (local · gemma4:12b, idle).
- System: blockers "local: ollama not reachable (user: sudo pacman -Syu ollama-vulkan)",
  "tailscale: NeedsLogin"; units `claude-remote-control.service active`,
  `codex-remote-control.service active`; WISDOM `ok`; live sessions `bso-a6 · busy`.

## 11. What to avoid

Discord look-alikes; blurple; saturated avatar discs; glassmorphism, heavy gradients, glows, neon;
more than one accent; arrowhead-heavy diagrams; a legend-laden multi-line chart; bouncy or springy
easing; perpetual idle animation; dashboard clutter; external fonts, icon fonts, or any CDN asset;
raw agent ids or JSON in the UI; a Stop button that the API cannot honor.

## 12. Deliverables (artboards)

1. **Tokens and type sheet**: dark and light palettes as CSS custom properties, type scale, spacing,
   radii, agent hue formula, semantic colors, focus ring.
2. **Desktop 1440×900, idle, variant A** (graph hero above feed).
3. **Desktop 1440×900, idle, variant B** (graph in right rail).
4. **Desktop 1440×900, live turn** in the chosen variant: orchestrator busy, Sol done ok 4.0s,
   Sonnet working 0:08, two comets mid-flight, nested delegation cards, composer busy.
5. **Desktop, error and unreachable**: an error receipt card, the unreachable banner, the inline 409.
6. **Desktop overlays**: settings popover/drawer, command palette, direct-delegate sheet, toasts.
7. **Phone 390×844, idle** and **phone live turn** with the compact graph strip and bottom sheet.
8. **Component sheet**: agent node (idle / working / ok flash / error flash / selected), edge states
   (rest ×3 weights / in-flight / working dash), delegation card (pending / ok / error / collapsed),
   turn header, chips and badges, composer states, roster row, sparkline row, empty states.
9. **Motion spec board**: a storyboard of one hop pulse at t = 0 / 300 / 600 / 900 ms, the working
   ring, the completion flash, and a batch stagger of three hops, each frame annotated with the exact
   CSS (`@keyframes`, durations, easings, `offset-path` or `stroke-dashoffset` approach) and the
   reduced-motion equivalent.
10. **Light theme** of artboard 4.

Also return a short written spec section listing every token, animation, and component with its CSS
values so the single-file implementation can be derived without guessing.

## 13. Decisions already made (do not re-open)

Dark-first with a light set; system font stack; single accent; orchestrator on top, workers below;
persona names primary with role labels secondary; polling-driven replay animation rather than
streaming; no external assets; phone is first-class; the API contract stays v1 with only the additive
`label` field proposed.
