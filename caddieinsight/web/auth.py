"""Signed session tokens: stdlib HMAC, no dependency.

A token is ``user_id.expiry.signature`` where the signature is
HMAC-SHA256 over ``user_id.expiry`` with the app secret. Tampering with
either field breaks the signature; an expired token verifies but is
rejected on the clock.
"""

from __future__ import annotations

import hashlib
import hmac
import time

SESSION_COOKIE = "ci_session"
SESSION_DAYS = 30


def sign_session(secret: bytes, user_id: int, now: float | None = None) -> str:
    expiry = int((now or time.time()) + SESSION_DAYS * 86400)
    payload = f"{user_id}.{expiry}"
    signature = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def verify_session(
    secret: bytes, token: str, now: float | None = None
) -> int | None:
    """Return the user id for a valid, unexpired token, else ``None``."""
    try:
        user_part, expiry_part, signature = token.split(".")
        payload = f"{user_part}.{expiry_part}"
        expected = hmac.new(
            secret, payload.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        if int(expiry_part) < (now or time.time()):
            return None
        return int(user_part)
    except (ValueError, TypeError):
        return None
