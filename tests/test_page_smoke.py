"""Dependency-free browser smoke against independent fixtures; never starts a vendor."""
import shutil
import subprocess
import tempfile
import threading
import unittest
import time
import os
from pathlib import Path
from http.server import ThreadingHTTPServer
from .fixture_server import Fixture, make_handler


@unittest.skipUnless(shutil.which("chromium"), "Chromium is optional")
class PageSmoke(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is optional for CDP interactions')
    def test_workspace_refresh(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(Fixture('idle', True, False)))
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory(prefix='harness-workspace-browser-') as profile:
                proc = subprocess.Popen(['chromium', '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--user-data-dir='+profile, '--remote-debugging-port=0', 'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                try:
                    portfile = Path(profile) / 'DevToolsActivePort'
                    for _ in range(100):
                        if portfile.exists(): break
                        time.sleep(.05)
                    port = portfile.read_text().splitlines()[0]
                    result = subprocess.run(['node', str(Path(__file__).with_name('workspace_browser.mjs')), 'http://127.0.0.1:'+port, f'http://127.0.0.1:{server.server_port}/', os.environ.get('HARNESS_TEST_SCREENSHOTS', '')], capture_output=True, text=True, timeout=40)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                finally:
                    proc.terminate(); proc.wait(timeout=5)
        finally:
            server.shutdown(); server.server_close()

    @unittest.skipUnless(shutil.which('node'), 'Node is optional for CDP interactions')
    def test_sessions_and_worker_controls(self):
        srv = ThreadingHTTPServer(('127.0.0.1',0),make_handler(Fixture('live',False,False)))
        srv.daemon_threads=True
        threading.Thread(target=srv.serve_forever,daemon=True).start()
        try:
            for width,height in ((1440,900),(390,844)):
                with self.subTest(width=width), tempfile.TemporaryDirectory(prefix='harness-mobile-browser-') as profile:
                    proc=subprocess.Popen(['chromium','--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--user-data-dir='+profile,'--remote-debugging-port=0','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                    try:
                        portfile=Path(profile)/'DevToolsActivePort'
                        for _ in range(100):
                            if portfile.exists():break
                            time.sleep(.05)
                        port=portfile.read_text().splitlines()[0]
                        result=subprocess.run(['node',str(Path(__file__).with_name('mobile_browser.mjs')),'http://127.0.0.1:'+port,f'http://127.0.0.1:{srv.server_port}/',str(width),str(height)],capture_output=True,text=True,timeout=25)
                        self.assertEqual(result.returncode,0,result.stderr)
                    finally:
                        proc.terminate();proc.wait(timeout=5)
        finally:
            srv.shutdown();srv.server_close()

    def test_desktop_and_phone_render_live_controls(self):
        for width, height in ((1440, 900), (390, 844)):
            with self.subTest(width=width):
                server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Fixture("live", False, False)))
                server.daemon_threads = True
                thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
                try:
                    with tempfile.TemporaryDirectory(prefix="harness-page-") as profile:
                        result = subprocess.run(["chromium", "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                                                 "--user-data-dir=" + profile, f"--window-size={width},{height}", "--virtual-time-budget=2000",
                                                 "--dump-dom", f"http://127.0.0.1:{server.server_address[1]}/"], capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr[-1000:])
                    for rendered in ('id="stop-turn"', 'data-mid="m_', 'node worker', 'planned', 'Review docs/DESIGN.md'):
                        self.assertIn(rendered, result.stdout)
                    self.assertNotIn('id="feed-inner"></div>', result.stdout)
                finally:
                    server.shutdown(); server.server_close()


if __name__ == "__main__":
    unittest.main()
