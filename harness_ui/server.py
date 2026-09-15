"""Stdlib HTTP server for the harness UI (contract: docs/UI-CONTRACT.md v1). Binds loopback only.

Depends on the agent-harness core package `harness` (separate repo), put on sys.path by bin/harness-ui."""
from __future__ import annotations

import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from harness import __version__ as core_version
from harness import orchestrator as orch
from harness.receipts import now_iso

from . import __version__

INDEX = Path(__file__).with_name("index.html")
FALLBACK = b"<!doctype html><title>agent-harness</title><body style='font-family:sans-serif;background:#111;color:#ddd;padding:2rem'>" \
           b"<h1>agent-harness UI</h1><p>index.html is not built yet. API is live: <a href='/api/state' style='color:#9cf'>/api/state</a></p></body>"
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "[::1]", "::1")


class Cache:
    def __init__(self):
        self.lock = threading.Lock()
        self.live: tuple[float, list] = (0.0, [])
        self.harness: tuple[float, dict] = (0.0, {"blockers": ["status pending"], "wisdom": {}, "units": {}})
        self.refreshing = False

    def live_sessions(self) -> list:
        with self.lock:
            ts, val = self.live
        if time.time() - ts > 15:
            try:
                p = subprocess.run(["claude", "agents", "--json"], capture_output=True, text=True, timeout=15, stdin=subprocess.DEVNULL, check=False)
                rows = json.loads(p.stdout) if p.stdout.strip() else []
                val = [{"pid": r.get("pid"), "name": r.get("name"), "status": r.get("status"), "cwd": r.get("cwd"), "kind": r.get("kind")} for r in rows if isinstance(r, dict)]
            except Exception:  # noqa: BLE001
                val = []
            with self.lock:
                self.live = (time.time(), val)
        return val

    def harness_status(self) -> dict:
        with self.lock:
            ts, val = self.harness
            stale = time.time() - ts > 60
            if stale and not self.refreshing:
                self.refreshing = True
                threading.Thread(target=self._refresh, daemon=True).start()
        return val

    def _refresh(self):
        try:
            from harness.status import collect
            d = collect()
            val = {"blockers": d.get("blockers", []), "wisdom": d.get("wisdom", {}),
                   "units": {u: s.get("state") for u, s in (d.get("units") or {}).items()}, "as_of": d.get("as_of")}
        except Exception as e:  # noqa: BLE001
            val = {"blockers": [f"status collection failed: {type(e).__name__}"], "wisdom": {}, "units": {}}
        with self.lock:
            self.harness = (time.time(), val)
            self.refreshing = False


CACHE = Cache()


def state_view() -> dict:
    cfg = orch.load_cfg()
    busy = orch.REGISTRY.busy()
    msgs = orch.read_messages(300)
    o = {k: cfg.get(k) for k in ("vendor", "model", "effort", "name", "session_ref", "cwd", "turns")}
    o.update(busy=busy, current_turn=orch.REGISTRY.current if busy else None, options=orch.OPTIONS)
    return {"as_of": now_iso(), "version": __version__, "core_version": core_version, "orchestrator": o, "agents": orch.agents_view(msgs, cfg, busy),
            "messages": msgs, "live_sessions": CACHE.live_sessions(), "harness": CACHE.harness_status()}


class Handler(BaseHTTPRequestHandler):
    server_version = f"agent-harness/{__version__}"

    def log_message(self, fmt, *args):  # quiet by default; errors still go to stderr via log_error
        return

    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, sort_keys=True).encode("utf-8"))

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0].strip().lower()
        if host.startswith("[") and "]" in (self.headers.get("Host") or ""):
            host = (self.headers.get("Host") or "").split("]")[0].lower() + "]"
        return host in LOOPBACK_HOSTS

    def _body(self) -> dict | None:
        n = int(self.headers.get("Content-Length") or 0)
        if n > 1_000_000:
            return None
        raw = self.rfile.read(n) if n else b"{}"
        try:
            obj = json.loads(raw.decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        return obj if isinstance(obj, dict) else None

    def do_GET(self):  # noqa: N802
        if not self._host_ok():
            return self._json(403, {"error": "loopback only"})
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            body = INDEX.read_bytes() if INDEX.is_file() else FALLBACK
            return self._send(200, body, "text/html; charset=utf-8")
        if u.path == "/api/state":
            return self._json(200, state_view())
        if u.path == "/api/stats":
            q = parse_qs(u.query)
            try:
                minutes = int(q.get("minutes", ["60"])[0])
            except ValueError:
                return self._json(400, {"error": "minutes must be an integer"})
            return self._json(200, orch.stats_view(orch.read_messages(5000), minutes))
        if u.path.startswith("/api/turn/"):
            t = orch.REGISTRY.get(u.path.rsplit("/", 1)[-1])
            return self._json(200, t) if t else self._json(404, {"error": "unknown turn"})
        return self._json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        if not self._host_ok():
            return self._json(403, {"error": "loopback only"})
        u = urlparse(self.path)
        body = self._body()
        if body is None:
            return self._json(400, {"error": "body must be a JSON object"})
        if u.path == "/api/orchestrator":
            cfg, err = orch.update_cfg(body)
            if err:
                return self._json(400, {"error": err})
            o = {k: cfg.get(k) for k in ("vendor", "model", "effort", "name", "session_ref", "cwd", "turns")}
            o.update(busy=orch.REGISTRY.busy(), options=orch.OPTIONS)
            return self._json(200, o)
        if u.path == "/api/say":
            try:
                tid = orch.start_turn(body.get("text"))
            except orch.Busy:
                return self._json(409, {"error": "busy"})
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            return self._json(202, {"turn_id": tid, "status": "started"})
        if u.path == "/api/delegate":
            if not isinstance(body.get("to"), str) or not isinstance(body.get("prompt"), str) or not body["prompt"].strip():
                return self._json(400, {"error": "to and prompt are required"})
            req = {k: body[k] for k in ("to", "prompt", "class", "model", "cwd", "schema", "wisdom", "timeout_s", "effort") if k in body}
            rid = orch.start_direct_delegation(req)
            return self._json(202, {"id": rid, "status": "started"})
        return self._json(404, {"error": "not found"})


def make_server(host: str = "127.0.0.1", port: int = 7788) -> ThreadingHTTPServer:
    if host not in LOOPBACK_HOSTS:
        raise ValueError("the harness UI binds loopback only; reach it remotely through an SSH/Tailscale tunnel")
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    return srv


def serve(host: str = "127.0.0.1", port: int = 7788) -> int:
    srv = make_server(host, port)
    print(f"agent-harness UI on http://{host}:{srv.server_address[1]}/  (loopback only; Ctrl-C to stop)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0
