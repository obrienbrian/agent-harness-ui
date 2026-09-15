"""Dependency-free browser smoke against independent fixtures; never starts a vendor."""
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from .fixture_server import Fixture, make_handler


@unittest.skipUnless(shutil.which("chromium"), "Chromium is optional")
class PageSmoke(unittest.TestCase):
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
