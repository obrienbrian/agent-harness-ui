"""UI backend tests with stub vendor binaries (stream-json for Claude). Run: python3 -m unittest -v tests.test_ui"""
from __future__ import annotations

import http.client
import json
import os
import stat
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="harness-ui-tests-"))
os.environ["HARNESS_STATE_DIR"] = str(TMP / "state")
os.environ["HARNESS_CONFIG_DIR"] = str(TMP / "config")
os.environ["CODEX_HOME"] = str(TMP / "codex-home")
os.environ["HARNESS_OLLAMA_URL"] = "http://127.0.0.1:9"
os.environ["HARNESS_TURN_TIMEOUT_S"] = "20"
STUB_LOG = TMP / "stub-argv.jsonl"
os.environ["HARNESS_STUB_LOG"] = str(STUB_LOG)
REPO = Path(__file__).resolve().parents[1]
CORE = Path(os.environ.get("AGENT_HARNESS_ROOT", REPO.parent / "agent-harness"))
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(CORE))

from harness import orchestrator as orch  # noqa: E402
from harness_ui import server  # noqa: E402

RECEIPT = {"schema": "harness.delegation.receipt.v1", "id": "dlg_stub1", "to": "codex", "class": "readonly", "root_code": "ok",
           "result_text": "worker says hi", "duration_ms": 1234, "model": "gpt-5.6-sol"}

CLAUDE_STUB = r'''#!/usr/bin/env python3
import json, os, sys, time
args = sys.argv[1:]
with open(os.environ["HARNESS_STUB_LOG"], "a") as f:
    f.write(json.dumps({"bin": "claude", "argv": args}) + "\n")
prompt = args[args.index("-p") + 1]
if "SLOW" in prompt:
    time.sleep(4)
if "--output-format" in args and args[args.index("--output-format") + 1] == "stream-json":
    receipt = json.loads(os.environ["STUB_RECEIPT"])
    ev = [
      {"type": "system", "subtype": "init", "session_id": "sess-orch-1"},
      {"type": "assistant", "message": {"content": [{"type": "text", "text": "Let me ask Codex."}]}},
      {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "tu1", "name": "mcp__harness__delegate", "input": {"to": "codex", "prompt": "review this", "class": "readonly"}}]}},
      {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "tu1", "content": [{"type": "text", "text": json.dumps(receipt)}]}]}},
      {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "tu2", "name": "Bash", "input": {"command": "ls"}}]}},
      {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "tu2", "content": "file.txt"}]}},
      {"type": "assistant", "message": {"content": [{"type": "text", "text": "Done: " + prompt[:20]}]}},
      {"type": "result", "subtype": "success", "is_error": "FAIL" in prompt, "result": "Done: " + prompt[:20], "session_id": "sess-orch-1", "usage": {"input_tokens": 5}},
    ]
    for e in ev:
        print(json.dumps(e)); sys.stdout.flush()
    sys.exit(0)
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "OK", "session_id": "sess-direct", "usage": {}}))
'''


def setUpModule():
    (TMP / "bin").mkdir(parents=True, exist_ok=True)
    p = TMP / "bin" / "claude"
    p.write_text(CLAUDE_STUB)
    p.chmod(p.stat().st_mode | stat.S_IXUSR)
    os.environ["HARNESS_CLAUDE_BIN"] = str(p)
    os.environ["STUB_RECEIPT"] = json.dumps(RECEIPT)
    (TMP / "codex-home").mkdir(exist_ok=True)
    (TMP / "cwd").mkdir(exist_ok=True)
    orch.update_cfg({"cwd": str(TMP / "cwd")})
    global SRV, PORT
    SRV = server.make_server("127.0.0.1", 0)
    PORT = SRV.server_address[1]
    threading.Thread(target=SRV.serve_forever, daemon=True).start()


def tearDownModule():
    SRV.shutdown()


def call(method: str, path: str, body: dict | None = None, host: str | None = None):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=15)
    headers = {"Content-Type": "application/json"}
    if host:
        headers["Host"] = host
    c.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
    r = c.getresponse()
    data = r.read()
    c.close()
    try:
        return r.status, json.loads(data)
    except json.JSONDecodeError:
        return r.status, data


def wait_turn(tid: str, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        st, t = call("GET", f"/api/turn/{tid}")
        if t["status"] != "running":
            return t
        time.sleep(0.2)
    raise AssertionError("turn did not finish")


class Api(unittest.TestCase):
    def test_index_and_state_shape(self):
        st, body = call("GET", "/")
        self.assertEqual(st, 200)
        st, s = call("GET", "/api/state")
        self.assertEqual(st, 200)
        for k in ("as_of", "orchestrator", "agents", "messages", "live_sessions", "harness"):
            self.assertIn(k, s)
        self.assertEqual(s["orchestrator"]["vendor"], "claude")
        self.assertIn("claude", s["orchestrator"]["options"])
        self.assertTrue(any(a["id"] == "orchestrator" for a in s["agents"]))

    def test_host_header_guard(self):
        st, body = call("GET", "/api/state", host="evil.example.com")
        self.assertEqual(st, 403)
        st, body = call("POST", "/api/say", {"text": "x"}, host="evil.example.com:7788")
        self.assertEqual(st, 403)

    def test_orchestrator_update_validation_and_reset(self):
        st, o = call("POST", "/api/orchestrator", {"model": "sonnet", "effort": "low", "name": "Fable"})
        self.assertEqual(st, 200, o)
        self.assertEqual((o["model"], o["effort"], o["name"]), ("sonnet", "low", "Fable"))
        st, e = call("POST", "/api/orchestrator", {"effort": "ultra"})
        self.assertEqual(st, 400)
        st, e = call("POST", "/api/orchestrator", {"vendor": "gemini"})
        self.assertEqual(st, 400)
        st, o = call("POST", "/api/orchestrator", {"vendor": "codex"})
        self.assertEqual(o["vendor"], "codex"); self.assertIsNone(o["session_ref"]); self.assertIn(o["model"], o["options"]["codex"]["models"])
        st, o = call("POST", "/api/orchestrator", {"vendor": "claude", "model": "sonnet", "effort": "low"})
        self.assertEqual(o["vendor"], "claude")

    def test_turn_streams_messages_and_saves_session(self):
        call("POST", "/api/orchestrator", {"vendor": "claude", "model": "sonnet", "effort": "low", "reset": True})
        st, r = call("POST", "/api/say", {"text": "please review the repo"})
        self.assertEqual(st, 202, r)
        t = wait_turn(r["turn_id"])
        self.assertEqual(t["status"], "done", t)
        st, s = call("GET", "/api/state")
        kinds = [(m["from"], m["to"], m["kind"]) for m in s["messages"] if (m.get("meta") or {}).get("turn_id") == r["turn_id"] or m["kind"] == "receipt"]
        self.assertIn(("user", "orchestrator", "prompt"), kinds)
        self.assertIn(("orchestrator", "user", "text"), kinds)
        self.assertIn(("orchestrator", "worker:codex", "tool_use"), kinds)
        self.assertIn(("worker:codex", "orchestrator", "receipt"), kinds)
        receipt = [m for m in s["messages"] if m["kind"] == "receipt"][-1]
        self.assertEqual(receipt["meta"]["root_code"], "ok"); self.assertEqual(receipt["meta"]["delegation_id"], "dlg_stub1")
        self.assertEqual(s["orchestrator"]["session_ref"], {"kind": "claude_session", "id": "sess-orch-1"})
        names = {a["id"]: a for a in s["agents"]}
        self.assertIn("worker:codex", names)
        self.assertEqual(names["worker:codex"]["name"], "Sol")  # from receipt model gpt-5.6-sol
        self.assertEqual(names["orchestrator"]["name"], "Sonnet")
        argv = json.loads(STUB_LOG.read_text().splitlines()[-1])["argv"]
        for flag in ("--output-format", "stream-json", "--verbose", "--model", "--effort", "--permission-prompts", "--allowedTools", "mcp__harness__delegate"):
            self.assertIn(flag, argv)
        self.assertNotIn("--bare", argv)
        # second turn resumes the saved session
        st, r2 = call("POST", "/api/say", {"text": "and now?"})
        wait_turn(r2["turn_id"])
        argv2 = json.loads(STUB_LOG.read_text().splitlines()[-1])["argv"]
        self.assertEqual(argv2[argv2.index("--resume") + 1], "sess-orch-1")

    def test_busy_returns_409_and_error_turn_is_typed(self):
        call("POST", "/api/orchestrator", {"vendor": "claude", "reset": True})
        st, r = call("POST", "/api/say", {"text": "SLOW work"})
        self.assertEqual(st, 202)
        st2, r2 = call("POST", "/api/say", {"text": "again"})
        self.assertEqual(st2, 409)
        wait_turn(r["turn_id"])
        st, r3 = call("POST", "/api/say", {"text": "please FAIL"})
        t = wait_turn(r3["turn_id"])
        self.assertEqual(t["status"], "error")

    def test_stats_edges(self):
        st, s = call("GET", "/api/stats?minutes=30")
        self.assertEqual(st, 200)
        self.assertEqual(len(s["buckets"]), 30)
        self.assertTrue(any(e["from"] == "orchestrator" and e["to"] == "worker:codex" for e in s["edges"]))
        st, e = call("GET", "/api/stats?minutes=abc")
        self.assertEqual(st, 400)

    def test_direct_delegation_records_both_hops(self):
        st, r = call("POST", "/api/delegate", {"to": "claude", "prompt": "hello direct", "class": "readonly"})
        self.assertEqual(st, 202, r)
        deadline = time.time() + 15
        while time.time() < deadline:
            st, s = call("GET", "/api/state")
            recs = [m for m in s["messages"] if m["kind"] == "receipt" and m["to"] == "user"]
            if recs:
                break
            time.sleep(0.2)
        self.assertTrue(recs, "no direct receipt recorded")
        self.assertEqual(recs[-1]["from"], "worker:claude")
        self.assertEqual(recs[-1]["meta"]["root_code"], "ok")
        st, e = call("POST", "/api/delegate", {"to": "claude"})
        self.assertEqual(st, 400)


if __name__ == "__main__":
    unittest.main()
