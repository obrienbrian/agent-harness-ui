"""Read-only discovery plus deliberate, identity-bound ending of external CLIs."""
import hashlib
import json
import os
from pathlib import Path
import threading
import time

from harness import processes
from harness.receipts import now_iso
from harness.documents import atomic, read_json
from harness import STATE_DIR

_lock = threading.RLock()
_known = {}
_ending = {}


def _key(identity):
    return 's_' + hashlib.sha256(json.dumps({k: identity[k] for k in ('pid', 'start', 'boot')}, sort_keys=True).encode()).hexdigest()[:32]


def discover(claude_rows, managed_pids=()):
    hints = {r.get('pid'): r for r in claude_rows if isinstance(r, dict)}
    out = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit() or int(path.name) in managed_pids:
            continue
        try:
            exe = Path(os.readlink(path / 'exe')).name
            if exe not in ('claude', 'codex'):
                continue
            ident = processes.identity(int(path.name))
            if not ident or ident['state'] == 'Z':
                continue
            if ident['session'] in managed_pids:
                continue
            args = (path / 'cmdline').read_bytes().split(b'\0')
            # Never offer process termination for shared daemons/MCP infrastructure.
            service = any(x in args[1:] for x in (b'app-server', b'daemon', b'mcp', b'mcp-server', b'remote-control'))
            cwd = os.readlink(path / 'cwd')
            hint = hints.get(ident['pid'], {})
            sid = _key(ident)
            row = {'id': sid, 'pid': ident['pid'], 'vendor': exe, 'source': 'external',
                   'name': hint.get('name') or (exe.title() + ' · ' + Path(cwd).name), 'cwd': cwd,
                   'kind': 'service' if service else hint.get('kind') or 'interactive',
                   'status': 'ending' if sid in _ending else hint.get('status') or 'running',
                   'can_end': not service, 'observed_at': now_iso()}
            out.append(row)
            with _lock:
                _known[sid] = (ident, row)
        except (OSError, ValueError):
            continue
    with _lock:
        active = {r['id'] for r in out}
        for sid in list(_known):
            if sid not in active:
                _known.pop(sid, None)
                _ending.pop(sid, None)
        for sid, started in list(_ending.items()):
            if time.monotonic() - started > 5 and sid in _known:
                for row in out:
                    if row['id'] == sid:
                        row['status'] = 'still running; end again or use terminal'
    return out


def end(sid):
    with _lock:
        known = _known.get(sid)
        if not known:
            raise KeyError(sid)
        ident, row = known
        if not row['can_end']:
            raise PermissionError('service processes are managed outside the session list')
        if not processes.send(ident):
            _known.pop(sid, None)
            raise KeyError(sid)
        _ending[sid] = time.monotonic()
        atomic(STATE_DIR / 'session-actions' / (sid + '.json'), json.dumps({'id': sid, 'vendor': row['vendor'], 'action': 'SIGTERM', 'at': now_iso()}).encode())
        return {'id': sid, 'status': 'ending'}
