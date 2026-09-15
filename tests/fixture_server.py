"""Fixture server: serve harness_ui/index.html against canned /api/state and /api/stats payloads.

Lets you render or hand-test the page in known states without a live harness:

    python3 tests/fixture_server.py 7801 live            # running turn: one worker done, one pending
    python3 tests/fixture_server.py 7802 idle            # history only
    python3 tests/fixture_server.py 7803 offline-after-first   # first poll ok, then 500s -> unreachable banner
    python3 tests/fixture_server.py 7804 empty           # no messages, no workers
    python3 tests/fixture_server.py 7805 live --advance  # 2nd poll appends two hops so comets fly
    python3 tests/fixture_server.py 7806 idle --many     # eight workers -> "+N" overflow node

Then open http://127.0.0.1:<port>/ (add #light for the light theme), or take headless renders:

    chromium --headless=new --hide-scrollbars --window-size=1440,900 --virtual-time-budget=1500 \
      --screenshot=out.png http://127.0.0.1:7801/

Content follows docs/DESIGN-SPEC.md §10 sample data. POST /api/say answers 409 in the live scenario.
"""
from __future__ import annotations

import datetime as dt
import json
import random
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "harness_ui" / "index.html"
SCENARIOS = ("live", "idle", "offline-after-first", "empty")


def iso(seconds_ago: float) -> str:
    return (dt.datetime.now().astimezone() - dt.timedelta(seconds=seconds_ago)).isoformat(timespec="seconds")


def msg(i: int, ago: float, frm: str, to: str, kind: str, text: str, meta: dict | None = None) -> dict:
    return {"id": f"m_{i:04x}", "ts": iso(ago), "from": frm, "to": to, "kind": kind, "text": text, "meta": meta or {}}


EXTRA = [("worker:codex:gpt-6-astra", "Astra", "Researcher"), ("worker:codex:gpt-5.6-terra", "Terra", "Tester"),
         ("worker:codex:gpt-5.6-luna", "Luna", "Critic"), ("worker:claude:haiku", "Haiku", "Scribe"),
         ("worker:local:gpt-oss:20b", "OSS-20B", "Fact-checker")]


class Fixture:
    def __init__(self, scenario: str, advance: bool, many: bool):
        self.scenario, self.advance, self.many = scenario, advance, many
        self.calls = 0

    @property
    def busy(self) -> bool:
        return self.scenario in ("live", "offline-after-first")

    def messages(self) -> list[dict]:
        T = 900
        ms = [
            msg(1, T, "user", "orchestrator", "prompt", "Have Codex re-run the rollback check now that the unit names changed.", {"turn_id": "t_7b90aa11", "model": "fable", "effort": "high"}),
            msg(2, T - 1, "orchestrator", "worker:codex", "tool_use", "Re-verify the rollback table in docs/RUNBOOK.md and fix any row whose unit name is stale.", {"tool": "delegate", "class": "edit", "label": "Reviewer", "turn_id": "t_7b90aa11"}),
            msg(3, T - 1.3, "worker:codex", "orchestrator", "receipt", "codex exited 1 · remote-control unit did not accept the request", {"root_code": "HARNESS_TOOL_CALL_FAILED", "delegation_id": "dlg_x1", "duration_ms": 300, "class": "edit"}),
            msg(4, T - 2, "orchestrator", "user", "error", "turn ended early; no result was produced.", {"turn_id": "t_7b90aa11"}),
            msg(5, 400, "user", "orchestrator", "prompt", "Review docs/DESIGN.md for missing failure modes and have Codex double-check the rollback table in docs/RUNBOOK.md.", {"turn_id": "t_9f21bb22", "model": "fable", "effort": "high"}),
            msg(6, 398, "orchestrator", "user", "text", "🛠 ToolSearch: {\"max_results\": 1, \"query\": \"select:mcp__harness__delegate\"}", {"tool": "ToolSearch", "turn_id": "t_9f21bb22"}),
            msg(7, 393, "orchestrator", "worker:codex", "tool_use", "Review docs/DESIGN.md for missing failure modes. Return a numbered list with file line references.", {"tool": "delegate", "class": "readonly", "label": "Reviewer", "turn_id": "t_9f21bb22"}),
            msg(8, 392, "orchestrator", "worker:claude:sonnet", "tool_use", "Independently verify every row of the rollback table in docs/RUNBOOK.md against the files it names.", {"tool": "delegate", "class": "readonly", "label": "Skeptic", "turn_id": "t_9f21bb22"}),
            msg(9, 389, "worker:codex", "orchestrator", "receipt", "Found 3 gaps: 1) no failure mode for a stuck remote-control unit; 2) nothing covers a partial WISDOM build; 3) the rollback table has no owner column.\n\nDetails:\n- docs/DESIGN.md:212 lists units but not their failure states\n- docs/DESIGN.md:240 assumes the compiled kernel exists\n- docs/RUNBOOK.md:88 rollback table lacks an owner", {"root_code": "ok", "delegation_id": "dlg_a1", "duration_ms": 4000, "class": "readonly", "model": "gpt-5.6-sol"}),
            msg(10, 381, "worker:claude:sonnet", "orchestrator", "receipt", "All 7 rows checked. Row 4 points at ~/.local/state/agent-harness/backups/2026-09-15/units which does not exist yet.", {"root_code": "ok", "delegation_id": "dlg_a2", "duration_ms": 11200, "class": "readonly", "model": "sonnet"}),
            msg(11, 379, "orchestrator", "user", "text", "Two gaps confirmed by both reviewers; one rollback row points at a backup path that does not exist yet. I would add an owner column to the rollback table and create the backups directory as part of install.", {"turn_id": "t_9f21bb22"}),
            msg(12, 379, "orchestrator", "user", "result", "", {"turn_id": "t_9f21bb22", "same_as_text": True, "usage": {"input_tokens": 1288, "output_tokens": 742}}),
            msg(13, 200, "user", "worker:codex", "tool_use", "List every systemd unit referenced in docs/RUNBOOK.md that does not exist on this box.", {"tool": "delegate", "class": "readonly", "direct": True}),
            msg(14, 194, "worker:codex", "user", "receipt", "Two units are referenced but absent: harness-ui.service, ollama.service.", {"root_code": "ok", "delegation_id": "dlg_d1", "duration_ms": 6100, "class": "readonly", "model": "gpt-5.6-sol"}),
        ]
        if self.busy:
            ms += [
                msg(15, 12, "user", "orchestrator", "prompt", "Also confirm the backup path exists before we ship, and get a second opinion on the owner column.", {"turn_id": "t_a3c7cc33", "model": "fable", "effort": "high"}),
                msg(16, 8, "orchestrator", "worker:codex", "tool_use", "Check whether ~/.local/state/agent-harness/backups/2026-09-15/units exists and list its contents.", {"tool": "delegate", "class": "readonly", "label": "Reviewer", "turn_id": "t_a3c7cc33"}),
                msg(17, 7, "orchestrator", "worker:claude:sonnet", "tool_use", "Argue against adding an owner column to the rollback table. Be concrete.", {"tool": "delegate", "class": "readonly", "label": "Skeptic", "turn_id": "t_a3c7cc33"}),
                msg(18, 4, "worker:codex", "orchestrator", "receipt", "The directory exists and holds 3 files: hyprland.conf.bak, settings.json.bak, AGENTS.md.bak.", {"root_code": "ok", "delegation_id": "dlg_b1", "duration_ms": 4000, "class": "readonly", "model": "gpt-5.6-sol"}),
                msg(19, 3, "orchestrator", "user", "text", "Sol's check is in. Holding the summary until Sonnet finishes the counter-argument.", {"turn_id": "t_a3c7cc33"}),
            ]
        if self.advance and self.calls >= 2:
            ms += [
                msg(20, 1, "worker:claude:sonnet", "orchestrator", "receipt", "Counter-argument: an owner column duplicates the unit's systemd metadata; use `systemctl show -p Description` instead.", {"root_code": "ok", "delegation_id": "dlg_b2", "duration_ms": 9800, "class": "readonly", "model": "sonnet"}),
                msg(21, 0, "orchestrator", "worker:local:gemma4:12b", "tool_use", "Summarize both opinions in 3 bullets.", {"tool": "delegate", "class": "readonly", "label": "Summarizer", "turn_id": "t_a3c7cc33"}),
            ]
        if self.many:
            for i, (wid, nm, role) in enumerate(EXTRA):
                ms += [msg(100 + i * 2, 300 - i * 10, "orchestrator", wid, "tool_use", f"Task for {nm}", {"tool": "delegate", "class": "readonly", "label": role, "turn_id": "t_9f21bb22"}),
                       msg(101 + i * 2, 295 - i * 10, wid, "orchestrator", "receipt", f"{nm} done", {"root_code": "ok", "delegation_id": f"dlg_m{i}", "duration_ms": 2000 + i * 700, "class": "readonly"})]
        return [] if self.scenario == "empty" else ms

    def state(self) -> dict:
        self.calls += 1
        ms = self.messages()

        def count(aid: str) -> int:
            return sum(1 for m in ms if aid in (m["from"], m["to"]))

        agents = [
            {"id": "user", "name": "Brian", "vendor": None, "model": None, "role": "user", "status": "idle", "messages": count("user"), "last_seen": iso(3)},
            {"id": "orchestrator", "name": "Fable", "vendor": "claude", "model": "fable", "role": "orchestrator", "status": "busy" if self.busy else "idle", "messages": count("orchestrator"), "last_seen": iso(3)},
        ]
        if self.scenario != "empty":
            agents += [
                {"id": "worker:codex", "name": "Sol", "vendor": "codex", "model": "gpt-5.6-sol", "role": "worker", "status": "idle", "messages": count("worker:codex"), "last_seen": iso(4)},
                {"id": "worker:claude:sonnet", "name": "Sonnet", "vendor": "claude", "model": "sonnet", "role": "worker", "status": "idle", "messages": count("worker:claude:sonnet"), "last_seen": iso(7)},
                {"id": "worker:local:gemma4:12b", "name": "Gemma", "vendor": "local", "model": "gemma4:12b", "role": "worker", "status": "idle", "messages": count("worker:local:gemma4:12b"), "last_seen": None},
            ]
            if self.many:
                for wid, nm, _ in EXTRA:
                    parts = wid.split(":", 2)
                    agents.append({"id": wid, "name": nm, "vendor": parts[1], "model": parts[2], "role": "worker", "status": "idle", "messages": count(wid), "last_seen": iso(290)})
        return {
            "as_of": iso(0), "version": "fixture", "core_version": "fixture",
            "orchestrator": {"vendor": "claude", "model": "fable", "effort": "high", "name": "Orchestrator", "session_ref": {"kind": "claude_session", "id": "86b8a730-fixture"},
                             "cwd": "/home/user/projects", "busy": self.busy, "turns": 4 if self.busy else 3, "current_turn": "t_a3c7cc33" if self.busy else None,
                             "playbook": "review-guide", "team": {"mode": "suggest", "roles": [{"label": "Verifier", "to": "claude", "model": "haiku", "effort": "high", "class": "readonly", "brief": "Check evidence."}]},
                             "options": {"targets": ["claude", "codex"], "claude": {"models": ["fable", "opus", "sonnet", "haiku"], "efforts": ["low", "medium", "high", "xhigh", "max"]},
                                         "codex": {"models": ["gpt-5.6-sol", "gpt-6-astra", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5", "gpt-5.3-codex-spark"], "efforts": ["minimal", "low", "medium", "high", "xhigh", "max"], "model_efforts": {"gpt-5.6-sol": ["low", "medium", "high", "xhigh"]}}}},
            "agents": agents + [{"id": "worker:claude:haiku", "name": "Verifier", "vendor": "claude", "model": "haiku", "role": "worker", "status": "planned", "ghost": True, "messages": 0, "last_seen": None}], "messages": ms,
            "playbooks": [{"slug":"wisdom","name":"WISDOM","builtin":True},{"slug":"none","name":"None","builtin":True},{"slug":"review-guide","name":"Review guide","summary":"Review evidence before changing code","sha256":"a"*64,"bytes":2048,"uploaded_at":iso(500)}],
            "teams": [{"slug":"solo","name":"Solo","builtin":True,"team":{"mode":"suggest","roles":[]}}],
            "today": {"turns":4,"delegations":8,"tokens":12750,"ok_rate":.875,"p50_duration_ms":4000},
            "live_sessions": [{"pid": 17665, "name": "bso-a6", "status": "busy", "cwd": "/home/user", "kind": "interactive"}, {"pid": 1035395, "name": "projects-e8", "status": "idle", "cwd": "/home/user/projects", "kind": "interactive"}],
            "harness": {"blockers": ["tailscale: NeedsLogin (SSH fallback unavailable; user: `sudo tailscale up --ssh`)"],
                        "units": {"claude-remote-control.service": "active", "codex-remote-control.service": "active"}, "wisdom": {"root_code": "ok", "build_id": "fixture"}},
        }

    def stats(self) -> dict:
        now = dt.datetime.now().astimezone().replace(second=0, microsecond=0)
        buckets = [(now - dt.timedelta(minutes=59 - i)).isoformat(timespec="seconds") for i in range(60)]
        rnd = random.Random(7)

        def series(scale: int) -> list[int]:
            return [max(0, int(rnd.random() * scale) - (1 if rnd.random() < .5 else 0)) for _ in range(60)]

        edges = [] if self.scenario == "empty" else [
            {"from": "orchestrator", "to": "worker:codex", "counts": series(4)}, {"from": "worker:codex", "to": "orchestrator", "counts": series(4)},
            {"from": "orchestrator", "to": "worker:claude:sonnet", "counts": series(3)}, {"from": "worker:claude:sonnet", "to": "orchestrator", "counts": series(3)},
            {"from": "user", "to": "orchestrator", "counts": series(2)}, {"from": "orchestrator", "to": "user", "counts": series(3)},
        ]
        return {"from": buckets[0], "to": buckets[-1], "bucket_s": 60, "buckets": buckets, "edges": edges}


def make_handler(fx: Fixture):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # noqa: D401
            return

        def _json(self, code: int, obj) -> None:
            b = json.dumps(obj).encode()
            self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

        def do_GET(self):  # noqa: N802
            p = self.path.split("?")[0]
            if p in ("/", "/index.html"):
                b = INDEX.read_bytes()
                self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
            if p == "/api/state":
                if fx.scenario == "offline-after-first" and fx.calls >= 1:
                    fx.calls += 1; self.send_response(500); self.end_headers(); return
                return self._json(200, fx.state())
            if p == "/api/stats":
                if fx.scenario == "offline-after-first" and fx.calls >= 2:
                    self.send_response(500); self.end_headers(); return
                return self._json(200, fx.stats())
            self._json(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            n = int(self.headers.get("Content-Length") or 0); self.rfile.read(n)
            if self.path == "/api/say":
                return self._json(409, {"error": "busy"}) if fx.busy else self._json(202, {"turn_id": "t_new", "status": "started"})
            if self.path == "/api/orchestrator":
                return self._json(200, fx.state()["orchestrator"])
            if self.path == "/api/delegate":
                return self._json(202, {"id": "dlg_new", "status": "started"})
            self._json(404, {"error": "not found"})

    return H


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in SCENARIOS:
        print(__doc__); return 2
    port, scenario = int(argv[0]), argv[1]
    fx = Fixture(scenario, "--advance" in argv, "--many" in argv)
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(fx))
    print(f"fixture {scenario}{' --advance' if fx.advance else ''}{' --many' if fx.many else ''} on http://127.0.0.1:{port}/", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
