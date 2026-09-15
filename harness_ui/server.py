"""Stdlib HTTP server for the harness UI (contract: docs/UI-CONTRACT.md v1). Binds loopback only.

Depends on the agent-harness core package `harness` (separate repo), put on sys.path by bin/harness-ui."""
from __future__ import annotations

import json
import os
import secrets
import hmac
import re
import collections
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from harness import __version__ as core_version
from harness import orchestrator as orch
from harness.receipts import now_iso, load_receipt, safe_data
from harness import playbooks, teams, events

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
STREAM_SLOTS = threading.BoundedSemaphore(8)
RATE_LOCK = threading.Lock()
RATE = collections.deque()


def state_view() -> dict:
    cfg = orch.load_cfg()
    busy = orch.REGISTRY.busy()
    msgs = orch.read_messages(300)
    o = {k: cfg.get(k) for k in ("vendor", "model", "effort", "name", "session_ref", "cwd", "turns", "playbook", "team")}
    o.update(busy=busy, current_turn=orch.REGISTRY.current if busy else None, options=orch.options())
    return {"as_of": now_iso(), "version": __version__, "core_version": core_version, "orchestrator": o, "agents": orch.agents_view(msgs, cfg, busy),
            "messages": msgs, "playbooks": playbooks.catalog(), "teams": teams.catalog(), "today": orch.today_stats(), "live_sessions": CACHE.live_sessions(), "harness": CACHE.harness_status()}


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
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        nonce = getattr(self, "nonce", "")
        self.send_header("Content-Security-Policy", f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; style-src-attr 'unsafe-inline'; connect-src 'self'; img-src 'self' data: blob:; manifest-src 'self'; worker-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, sort_keys=True).encode("utf-8"))

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0].strip().lower()
        if host.startswith("[") and "]" in (self.headers.get("Host") or ""):
            host = (self.headers.get("Host") or "").split("]")[0].lower() + "]"
        return host in LOOPBACK_HOSTS

    def _authorized(self) -> bool:
        token = os.environ.get("HARNESS_UI_TOKEN", "")
        return not token or hmac.compare_digest(self.headers.get("Authorization", "").encode(), ("Bearer " + token).encode())

    def _mutation_ok(self) -> bool:
        if not self._host_ok():
            self._json(403, {"error": "loopback only"}); return False
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + self.headers.get("Host", "") and origin != "https://" + self.headers.get("Host", ""):
            self._json(403, {"error": "origin rejected"}); return False
        if not self._authorized():
            self._json(401, {"error": "authentication required"}); return False
        if self.command == "POST" and self.headers.get_content_type() != "application/json":
            self._json(415, {"error": "application/json required"}); return False
        with RATE_LOCK:
            now = time.monotonic()
            while RATE and RATE[0] < now - 60:
                RATE.popleft()
            if len(RATE) >= 120:
                self._json(429, {"error": "too many requests; try again shortly"}); return False
            RATE.append(now)
        return True

    def _body(self) -> dict | None:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if n < 0 or n > 1_000_000:
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
            body = INDEX.read_text() if INDEX.is_file() else FALLBACK.decode()
            self.nonce = secrets.token_urlsafe(24)
            body = body.replace("<script>", f'<script nonce="{self.nonce}">').replace("<style>", f'<style nonce="{self.nonce}">')
            body = body.replace('<html', '<html data-token-required="' + ("true" if os.environ.get("HARNESS_UI_TOKEN") else "false") + '"', 1)
            return self._send(200, body.encode(), "text/html; charset=utf-8")
        if u.path in ("/manifest.json", "/manifest.webmanifest"):
            return self._send(200, json.dumps({"name": "Agent Harness", "short_name": "Harness", "start_url": "/", "display": "standalone", "background_color": "#111413", "theme_color": "#111413", "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"}]}).encode(), "application/manifest+json")
        if u.path == "/icon.svg":
            return self._send(200, b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 192"><rect width="192" height="192" rx="38" fill="#111413"/><path d="M50 45v102m92-102v102M50 96h92" stroke="#4fc3a1" stroke-width="20"/></svg>', "image/svg+xml")
        if u.path == "/sw.js":
            return self._send(200, b"self.addEventListener('install',()=>self.skipWaiting());self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));", "text/javascript")
        if not self._authorized():
            return self._json(401, {"error": "authentication required"})
        if u.path == "/api/events":
            return self._events()
        if u.path == "/api/playbooks":
            return self._json(200, {"playbooks": playbooks.catalog()})
        if u.path == "/api/teams":
            return self._json(200, {"teams": teams.catalog()})
        if u.path == "/api/turns":
            try:
                limit = int(parse_qs(u.query).get("limit", ["50"])[0])
            except ValueError:
                return self._json(400, {"error": "limit must be an integer"})
            return self._json(200, {"turns": orch.turn_history(limit)})
        if u.path.startswith("/api/receipt/"):
            rec = load_receipt(u.path.rsplit("/", 1)[-1])
            return self._json(200, safe_data(rec)) if rec else self._json(404, {"error": "unknown receipt"})
        if u.path == "/api/state":
            return self._json(200, state_view())
        if u.path == "/api/stats":
            q = parse_qs(u.query)
            try:
                minutes = int(q.get("minutes", ["60"])[0])
            except ValueError:
                return self._json(400, {"error": "minutes must be an integer"})
            return self._json(200, {**orch.stats_view(orch.read_messages(5000), minutes), **({"today": orch.today_stats()} if minutes >= 1440 else {})})
        if u.path.startswith("/api/turn/"):
            t = orch.turn_detail(u.path.rsplit("/", 1)[-1])
            return self._json(200, t) if t else self._json(404, {"error": "unknown turn"})
        return self._json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        if not self._mutation_ok():
            return
        u = urlparse(self.path)
        body = self._body()
        if body is None:
            return self._json(400, {"error": "body must be a JSON object"})
        if u.path in ("/api/playbooks", "/api/teams"):
            try:
                with orch._lock:
                    if u.path == "/api/playbooks":
                        if body.get("replace") and playbooks.slug(body.get("name")) == orch.load_cfg().get("playbook") and orch.REGISTRY.busy():
                            return self._json(409, {"error": "active playbook is in use"})
                        row = playbooks.upload(body.get("name"), body.get("content"), body.get("replace") is True)
                    else:
                        row = teams.save(body.get("name"), body.get("team"))
                return self._json(201, row)
            except FileExistsError:
                return self._json(409, {"error": "slug already exists"})
            except PermissionError as exc:
                return self._json(405, {"error": str(exc)})
            except ValueError as exc:
                return self._json(400, {"error": str(exc)})
        match = re.fullmatch(r"/api/turn/([^/]+)/stop", u.path)
        if match:
            try:
                orch.REGISTRY.terminate(match[1], stopped=True)
            except KeyError:
                return self._json(404, {"error": "unknown turn"})
            except orch.Busy:
                return self._json(409, {"error": "turn is not running"})
            return self._json(202, {"turn_id": match[1], "status": "stopping"})
        match = re.fullmatch(r"/api/delegate/([^/]+)/resume", u.path)
        if match:
            try:
                rid = orch.start_resume(match[1], body.get("prompt"))
            except KeyError:
                return self._json(404, {"error": "unknown receipt"})
            except ValueError as exc:
                return self._json(400, {"error": str(exc)})
            return self._json(202, {"id": rid, "status": "started"})
        if u.path == "/api/orchestrator":
            cfg, err = orch.update_cfg(body)
            if err:
                return self._json(400, {"error": err})
            o = {k: cfg.get(k) for k in ("vendor", "model", "effort", "name", "session_ref", "cwd", "turns", "playbook", "team")}
            o.update(busy=orch.REGISTRY.busy(), options=orch.options())
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
            if not isinstance(body.get("prompt"), str) or not body["prompt"].strip():
                return self._json(400, {"error": "prompt is required"})
            req = {k: body[k] for k in ("to", "prompt", "class", "model", "cwd", "schema", "wisdom", "timeout_s", "effort", "label", "playbook") if k in body}
            rid = orch.start_direct_delegation(req)
            return self._json(202, {"id": rid, "status": "started"})
        return self._json(404, {"error": "not found"})

    def do_DELETE(self):
        if not self._mutation_ok():
            return
        path = urlparse(self.path).path
        try:
            with orch._lock:
                if re.fullmatch(r"/api/playbooks/[^/]+", path):
                    playbooks.delete(path.rsplit("/", 1)[-1], orch.load_cfg().get("playbook", "wisdom"))
                elif re.fullmatch(r"/api/teams/[^/]+", path):
                    teams.delete(path.rsplit("/", 1)[-1])
                else:
                    return self._json(404, {"error": "not found"})
            return self._send(204, b"")
        except FileNotFoundError:
            return self._json(404, {"error": "unknown document"})
        except FileExistsError as exc:
            return self._json(409, {"error": str(exc)})
        except PermissionError as exc:
            return self._json(405, {"error": str(exc)})
        except ValueError as exc:
            return self._json(400, {"error": str(exc)})

    def _events(self):
        if not STREAM_SLOTS.acquire(blocking=False):
            return self._json(429, {"error": "too many event streams"})
        try:
            cursor = events.cursor()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            def send(kind, data, eid=None):
                frame = (f"id: {eid}\n" if eid is not None else "") + f"event: {kind}\ndata: {json.dumps(data)}\n\n"
                self.wfile.write(frame.encode()); self.wfile.flush()
            send("state", {"orchestrator": orch.load_cfg()}, cursor)
            last_stats = time.monotonic()
            deadline = last_stats + 55  # bounded streams reconnect; polling provides durable catch-up
            while time.monotonic() < deadline:
                rows = events.after(cursor, 1)
                for eid, kind, data in rows:
                    send(kind, data, eid)
                    cursor = eid
                if time.monotonic() - last_stats >= 15:
                    send("stats", orch.stats_view(orch.read_messages(5000)))
                    last_stats = time.monotonic()
                if not rows:
                    self.wfile.write(b": heartbeat\n\n"); self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        finally:
            STREAM_SLOTS.release()


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
