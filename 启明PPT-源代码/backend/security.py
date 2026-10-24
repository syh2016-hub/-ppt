"""Passwords, opaque session tokens and in-memory login throttling."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Deque

PBKDF2_ITERATIONS = 310_000
_ALGORITHM = "pbkdf2_sha256"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("ascii"),
        PBKDF2_ITERATIONS,
    )
    return f"{_ALGORITHM}${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, expected = stored.split("$", 3)
        if algorithm != _ALGORITHM:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("ascii"),
            int(iterations),
        )
        return hmac.compare_digest(digest.hex(), expected)
    except (TypeError, ValueError):
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(40)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class LoginThrottle:
    """Sliding-window limiter that survives only for the life of the process."""

    def __init__(self, limit: int = 8, window_seconds: int = 600) -> None:
        self.limit = limit
        self.window = window_seconds
        self._events: dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _key(self, ip: str, username: str) -> str:
        return f"{ip}|{username.lower().strip()}"

    def allowed(self, ip: str, username: str) -> bool:
        key = self._key(ip, username)
        now = time.time()
        with self._lock:
            queue = self._events[key]
            while queue and now - queue[0] > self.window:
                queue.popleft()
            return len(queue) < self.limit

    def record_failure(self, ip: str, username: str) -> None:
        key = self._key(ip, username)
        with self._lock:
            self._events[key].append(time.time())

    def clear(self, ip: str, username: str) -> None:
        with self._lock:
            self._events.pop(self._key(ip, username), None)

    def retry_after(self, ip: str, username: str) -> int:
        key = self._key(ip, username)
        with self._lock:
            queue = self._events.get(key)
            if not queue:
                return 0
            return max(0, int(self.window - (time.time() - queue[0])))


login_throttle = LoginThrottle()


def valid_username(value: str) -> bool:
    import re

    return bool(re.fullmatch(r"[A-Za-z0-9_\u4e00-\u9fa5]{3,20}", value or ""))


def valid_password(value: str) -> bool:
    return isinstance(value, str) and 6 <= len(value) <= 72


def safe_compare_invite(value: str, expected: str) -> bool:
    return hmac.compare_digest((value or "").strip(), expected)


def client_ip(request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:80]
    return (request.remote_addr or "")[:80]
