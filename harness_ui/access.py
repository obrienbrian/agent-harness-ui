"""Explicit private proxy trust. The HTTP listener remains loopback only."""
import hmac
import os
from urllib.parse import urlsplit


def remote_origin():
    value = os.environ.get("HARNESS_UI_ORIGIN", "").rstrip("/")
    if not value:
        return None
    u = urlsplit(value)
    if u.scheme != "https" or not u.hostname or u.username or u.password or u.path or u.query or u.fragment:
        raise ValueError("HARNESS_UI_ORIGIN must be one HTTPS origin")
    if not os.environ.get("HARNESS_UI_TAILSCALE_USER"):
        raise ValueError("HARNESS_UI_TAILSCALE_USER is required for private proxy access")
    return value


def is_remote(headers):
    origin = remote_origin()
    return bool(origin and headers.get("Host", "").lower() == urlsplit(origin).netloc.lower())


def host_ok(headers):
    host = headers.get("Host", "")
    try:
        u = urlsplit("http://" + host)
        if u.username or u.password or u.path or u.query or u.fragment or not u.hostname:
            return False
        u.port  # reject malformed ports
        return u.hostname.lower() in ("localhost", "127.0.0.1", "::1") or is_remote(headers)
    except ValueError:
        return False


def authorized(headers):
    if is_remote(headers):
        # Tailscale Serve strips client-supplied identity headers. Never bind the
        # backend to a LAN/tailnet address where callers could bypass that proxy.
        expected = os.environ.get("HARNESS_UI_TAILSCALE_USER", "")
        return bool(expected and hmac.compare_digest(headers.get("Tailscale-User-Login", "").encode(), expected.encode()))
    token = os.environ.get("HARNESS_UI_TOKEN", "")
    return not token or hmac.compare_digest(headers.get("Authorization", "").encode(), ("Bearer " + token).encode())


def origin_ok(headers):
    origin = headers.get("Origin")
    if is_remote(headers):
        return origin is None or origin == remote_origin()
    return origin is None or origin in ("http://" + headers.get("Host", ""), "https://" + headers.get("Host", ""))
