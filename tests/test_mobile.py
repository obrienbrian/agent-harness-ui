"""Private phone boundary tests. Stub vendors; no live model calls."""
import http.client
import json
import os
import threading
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from . import test_ui as base
from harness_ui import server
from harness_ui import sessions
from harness import processes, workers


class PrivateAccess(unittest.TestCase):
    def test_https_identity_origin_and_local_access(self):
        origin = "https://test.example.ts.net"
        with patch.dict(os.environ, {"HARNESS_UI_ORIGIN": origin, "HARNESS_UI_TAILSCALE_USER": "owner@example.com"}):
            srv = server.make_server(port=0)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            def call(host, identity=None, origin_header=None, method="GET"):
                c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=3)
                h = {"Host": host, "Content-Type": "application/json"}
                if identity is not None: h["Tailscale-User-Login"] = identity
                if origin_header is not None: h["Origin"] = origin_header
                c.request(method, "/api/teams", body="{}" if method == "POST" else None, headers=h)
                r = c.getresponse(); r.read(); c.close(); return r.status
            try:
                self.assertEqual(call("test.example.ts.net", "owner@example.com"), 200)
                self.assertEqual(call("test.example.ts.net", "other@example.com"), 403)
                self.assertEqual(call("test.example.ts.net"), 403)
                self.assertEqual(call("test.example.ts.net.evil", "owner@example.com"), 403)
                self.assertEqual(call("test.example.ts.net", "owner@example.com", "https://evil.example", "POST"), 403)
                self.assertEqual(call("test.example.ts.net", "owner@example.com", "http://test.example.ts.net", "POST"), 403)
                self.assertEqual(call("test.example.ts.net", "owner@example.com", origin, "POST"), 400)
                self.assertEqual(call("127.0.0.1:" + str(srv.server_port)), 200)
            finally:
                srv.shutdown(); srv.server_close()


class SessionsAndWorkers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base.setUpModule()

    @classmethod
    def tearDownClass(cls):
        base.tearDownModule()
        base.SRV.server_close()

    def test_direct_worker_http_cancel_receipt(self):
        st,row=base.call('POST','/api/delegate',{'to':'claude','prompt':'SLOW cancellation proof','class':'readonly'})
        self.assertEqual(st,202)
        rid=row['id']
        deadline=time.monotonic()+4
        while time.monotonic()<deadline:
            if any(w['id']==rid and w.get('process') for w in workers.active()):break
            time.sleep(.02)
        else:self.fail('worker did not start')
        st,body=base.call('POST',f'/api/delegate/{rid}/cancel',{})
        self.assertEqual(st,202,body)
        deadline=time.monotonic()+4
        while time.monotonic()<deadline:
            st,rec=base.call('GET',f'/api/receipt/{rid}')
            if st==200:break
            time.sleep(.02)
        self.assertEqual(rec['root_code'],'HARNESS_WORKER_CANCELLED')
        self.assertEqual(base.call('POST',f'/api/delegate/{rid}/cancel',{})[0],409)

    def test_end_orchestrator_preserves_busy_turn_and_history(self):
        st,turn=base.call('POST','/api/say',{'text':'SLOW end session proof'})
        self.assertEqual(st,202)
        self.assertEqual(base.call('POST','/api/orchestrator/end',{})[0],409)
        base.call('POST',f"/api/turn/{turn['turn_id']}/stop",{})
        base.wait_turn(turn['turn_id'])
        self.assertEqual(base.call('POST','/api/orchestrator/end',{})[0],200)
        self.assertEqual(base.call('GET',f"/api/turn/{turn['turn_id']}")[0],200)

    def test_session_end_http_identity_and_service_guard(self):
        with tempfile.TemporaryDirectory(prefix='session-proof-') as d:
            binary=Path(d)/'claude'
            shutil.copy2(shutil.which('sleep'),binary)
            child=subprocess.Popen([str(binary),'30'])
            try:
                ident=processes.identity(child.pid)
                rows=sessions.discover([])
                row=next(r for r in rows if r['pid']==child.pid)
                self.assertTrue(row['can_end'])
                self.assertEqual(row['source'],'external')
                st,body=base.call('POST',f"/api/sessions/{row['id']}/end",{})
                self.assertEqual(st,202,body)
                child.wait(timeout=2)
                self.assertFalse(processes.same(ident))
                self.assertEqual(base.call('POST',f"/api/sessions/{row['id']}/end",{})[0],409)
                self.assertEqual(base.call('POST',f'/api/sessions/{child.pid}/end',{})[0],404)
            finally:
                if child.poll() is None:child.terminate();child.wait()

    def test_stale_session_and_service_cannot_signal(self):
        child=subprocess.Popen(['sleep','30'])
        try:
            ident=processes.identity(child.pid);sid='s_'+'a'*32
            sessions._known[sid]=({**ident,'start':'0'},{'can_end':True})
            self.assertEqual(base.call('POST',f'/api/sessions/{sid}/end',{})[0],409)
            self.assertIsNone(child.poll())
            sessions._known[sid]=(ident,{'can_end':False})
            self.assertEqual(base.call('POST',f'/api/sessions/{sid}/end',{})[0],403)
            self.assertIsNone(child.poll())
        finally:
            sessions._known.pop(sid,None)
            child.terminate();child.wait()
