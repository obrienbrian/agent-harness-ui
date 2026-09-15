"""Encrypted Web Push with a durable outbox. No prompts or results leave the host."""
import base64
import datetime
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from harness import STATE_DIR, CONFIG_DIR
from harness.documents import atomic
from harness.receipts import now_iso


def unbase(value):
    if not isinstance(value, str) or len(value) > 256:
        raise ValueError('invalid push key')
    try:
        return base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
    except ValueError:
        raise ValueError('invalid push key') from None


def validate(subscription):
    if not isinstance(subscription, dict):
        raise ValueError('subscription required')
    endpoint = subscription.get('endpoint')
    if not isinstance(endpoint, str) or len(endpoint) > 4096:
        raise ValueError('invalid push endpoint')
    try:
        u = urlsplit(endpoint)
        host = u.hostname or ''
        trusted = host == 'fcm.googleapis.com' or host == 'updates.push.services.mozilla.com' or host.endswith('.push.apple.com')
        if u.scheme != 'https' or not trusted or u.port not in (None, 443) or u.username or u.password or u.fragment:
            raise ValueError('unsupported push service')
    except ValueError:
        raise ValueError('unsupported push service') from None
    keys = subscription.get('keys')
    if not isinstance(keys, dict):
        raise ValueError('push encryption keys required')
    public, auth = unbase(keys.get('p256dh')), unbase(keys.get('auth'))
    if len(public) != 65 or len(auth) != 16:
        raise ValueError('invalid push key length')
    from cryptography.hazmat.primitives.asymmetric import ec
    ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public)
    return {'endpoint': endpoint, 'keys': {k: keys[k] for k in ('p256dh', 'auth')}}


class Push:
    def __init__(self, root=None, config=None, messages=None, sender=None):
        self.root = Path(root or STATE_DIR / 'push')
        self.config = Path(config or CONFIG_DIR / 'push')
        self.messages = Path(messages or STATE_DIR / 'ui-messages.jsonl')
        self.sender = sender or self.send
        self.stop = threading.Event()
        self.lock = threading.RLock()
        self.error = None
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.config.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.key = self.config / 'vapid.pem'
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        if not self.key.exists():
            private = ec.generate_private_key(ec.SECP256R1())
            atomic(self.key, private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        private = serialization.load_pem_private_key(self.key.read_bytes(), password=None)
        self.public_key = base64.urlsafe_b64encode(private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)).rstrip(b'=').decode()
        dbpath = self.root / 'outbox.sqlite3'
        fd = os.open(dbpath, os.O_CREAT | os.O_RDWR, 0o600); os.close(fd)
        self.db = sqlite3.connect(dbpath, check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS subscriptions (id TEXT PRIMARY KEY, value TEXT NOT NULL, created TEXT NOT NULL, last_status TEXT);
          CREATE TABLE IF NOT EXISTS outbox (id TEXT PRIMARY KEY, subscription TEXT NOT NULL, payload TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, next REAL NOT NULL, created REAL NOT NULL, status TEXT NOT NULL DEFAULT 'pending');
          CREATE TABLE IF NOT EXISTS cursor (id INTEGER PRIMARY KEY CHECK(id=1), offset INTEGER NOT NULL);
        ''')
        self.db.execute('INSERT OR IGNORE INTO cursor VALUES(1,?)', (self.messages.stat().st_size if self.messages.exists() else 0,))
        self.db.commit()

    def status(self):
        with self.lock:
            return {'available': True, 'public_key': self.public_key,
                    'subscriptions': self.db.execute('SELECT COUNT(*) FROM subscriptions').fetchone()[0],
                    'pending': self.db.execute("SELECT COUNT(*) FROM outbox WHERE status='pending'").fetchone()[0],
                    'failed': self.db.execute("SELECT COUNT(*) FROM outbox WHERE status='failed'").fetchone()[0],
                    'error': self.error}

    def subscribe(self, value):
        value = validate(value)
        sid = hashlib.sha256(value['endpoint'].encode()).hexdigest()
        with self.lock, self.db:
            count = self.db.execute('SELECT COUNT(*) FROM subscriptions').fetchone()[0]
            if count >= 16 and not self.db.execute('SELECT 1 FROM subscriptions WHERE id=?', (sid,)).fetchone():
                raise ValueError('device limit reached; disable alerts on an unused device')
            self.db.execute('INSERT INTO subscriptions VALUES(?,?,?,NULL) ON CONFLICT(id) DO UPDATE SET value=excluded.value', (sid, json.dumps(value), now_iso()))
        return {'id': sid, 'enabled': True}

    def unsubscribe(self, sid):
        if not isinstance(sid, str) or not re.fullmatch('[a-f0-9]{64}', sid):
            raise ValueError('invalid device id')
        with self.lock, self.db:
            self.db.execute('DELETE FROM subscriptions WHERE id=?', (sid,))
            self.db.execute('DELETE FROM outbox WHERE subscription=?', (sid,))

    def _queue(self, key, sid, kind, target=None):
        payload = {'title': 'Harness needs attention' if kind == 'attention' else 'Harness test notification' if kind == 'test' else 'Harness work finished',
                   'body': 'Open Harness to review the details.', 'tag': key, 'url': '/'}
        if target and isinstance(target, str) and target.startswith(('t_', 'dlg_')):
            payload['url'] = '/#' + ('turn=' if target.startswith('t_') else 'receipt=') + target
        self.db.execute('INSERT OR IGNORE INTO outbox(id,subscription,payload,next,created) VALUES(?,?,?,?,?)',
                        (key + ':' + sid, sid, json.dumps(payload), time.time(), time.time()))

    def test(self, sid):
        if not isinstance(sid, str) or not re.fullmatch('[a-f0-9]{64}', sid):
            raise ValueError('invalid device id')
        with self.lock, self.db:
            if not self.db.execute('SELECT 1 FROM subscriptions WHERE id=?', (sid,)).fetchone():
                raise KeyError(sid)
            self._queue('test-' + str(time.time_ns()), sid, 'test')

    def collect(self):
        if not self.messages.exists():
            return
        with self.lock, self.db:
            offset = self.db.execute('SELECT offset FROM cursor WHERE id=1').fetchone()[0]
            if self.messages.stat().st_size < offset:
                offset = 0
            subs = self.db.execute('SELECT id,created FROM subscriptions').fetchall()
            with self.messages.open('rb') as stream:
                stream.seek(offset)
                for _ in range(500):
                    line = stream.readline(1_000_001)
                    if not line or not line.endswith(b'\n'):
                        break  # don't acknowledge a partially appended message
                    offset = stream.tell()
                    try:
                        m = json.loads(line)
                        meta = m.get('meta') or {}
                        kind = meta.get('notification')
                        if not kind and m.get('kind') == 'receipt' and m.get('to') == 'user':
                            if meta.get('root_code') == 'HARNESS_WORKER_CANCELLED':
                                continue
                            kind = 'complete' if meta.get('root_code') == 'ok' else 'attention'
                        if kind:
                            for sid, created in subs:
                                if m.get('ts', '') >= created:
                                    self._queue(m['id'], sid, kind, meta.get('delegation_id') or meta.get('turn_id'))
                    except (ValueError, KeyError, TypeError):
                        continue
            self.db.execute('UPDATE cursor SET offset=? WHERE id=1', (offset,))

    def send(self, subscription, payload):
        import requests
        from pywebpush import webpush, WebPushException
        class NoRedirects(requests.Session):
            def request(self, *args, **kwargs):
                kwargs['allow_redirects'] = False
                return super().request(*args, **kwargs)
        with NoRedirects() as session:
            session.trust_env = False
            try:
                response = webpush(validate(subscription), data=payload, vapid_private_key=str(self.key),
                                   vapid_claims={'sub': os.environ.get('HARNESS_UI_PUSH_SUBJECT', 'mailto:operator@localhost')},
                                   ttl=86400, timeout=10, requests_session=session)
                return response.status_code
            except WebPushException as exc:
                return exc.response.status_code if exc.response is not None else 503

    def deliver(self):
        with self.lock:
            jobs = self.db.execute("SELECT id,subscription,payload,attempts,created FROM outbox WHERE status='pending' AND next<=? ORDER BY created LIMIT 16", (time.time(),)).fetchall()
        for key, sid, payload, attempts, created in jobs:
            if self.stop.is_set():
                break
            with self.lock:
                sub = self.db.execute('SELECT value FROM subscriptions WHERE id=?', (sid,)).fetchone()
            if not sub:
                continue
            try:
                code = self.sender(json.loads(sub[0]), payload)
            except Exception:
                code = 503  # never log an exception that may contain a capability URL
            with self.lock, self.db:
                if code in (404, 410):
                    self.unsubscribe(sid)
                    continue
                status = 'sent' if 200 <= code <= 202 else 'failed' if (400 <= code < 500 and code != 429) or 300 <= code < 400 or attempts >= 5 or time.time() - created > 86400 else 'pending'
                self.db.execute('UPDATE outbox SET status=?,attempts=?,next=? WHERE id=?',
                                (status, attempts + 1, time.time() + min(3600, 30 * 2 ** attempts), key))
                self.db.execute('UPDATE subscriptions SET last_status=? WHERE id=?', (str(code), sid))
        with self.lock, self.db:
            self.db.execute("DELETE FROM outbox WHERE status != 'pending' AND created < ?", (time.time() - 7 * 86400,))

    def run(self):
        while not self.stop.is_set():
            try:
                self.collect(); self.deliver(); self.error = None
            except Exception:
                self.error = 'notification processing failed; retrying'
            self.stop.wait(2)

    def close(self):
        self.stop.set()
        if getattr(self, 'thread', None):
            self.thread.join(timeout=12)
        with self.lock:
            self.db.close()

    def start(self):
        self.thread = threading.Thread(target=self.run, name='web-push', daemon=True)
        self.thread.start()
