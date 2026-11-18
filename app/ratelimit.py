"""A small in-memory, per-visitor rate limiter (sliding window).

Good enough for a single-instance deployment; it resets when the server restarts.
"""
import threading
import time
from collections import defaultdict, deque

from flask import request

_hits = defaultdict(deque)
_lock = threading.Lock()


def client_ip():
    # Behind Cloud Run / a proxy, the visitor's address is the first entry of X-Forwarded-For.
    forwarded = request.headers.get('X-Forwarded-For', '')
    return forwarded.split(',')[0].strip() if forwarded else (request.remote_addr or 'unknown')


def allow(key, limit, window_s=600):
    """True if `key` has made fewer than `limit` calls in the last `window_s` seconds (and records this one)."""
    if limit <= 0:
        return True
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and now - q[0] > window_s:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        if len(_hits) > 10_000:                # don't grow forever under a flood of addresses
            for k in [k for k, v in _hits.items() if not v or now - v[-1] > window_s]:
                del _hits[k]
        return True
