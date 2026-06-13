"""Read claims from Core/backend JWT access tokens (payload decode only)."""
from __future__ import annotations

import base64
import json

from src.utils.logging import logger

_USER_ID_CLAIMS = ("sub", "uid", "user_id", "userId", "id")


def decode_jwt_payload(token: str | None) -> dict | None:
    text = (token or "").strip()
    if not text:
        return None
    parts = text.split(".")
    if len(parts) < 2:
        logger.warning("JWT decode skipped: not enough segments")
        return None
    try:
        payload_b64 = parts[1]
        padding = "=" * (-len(payload_b64) % 4)
        raw = base64.urlsafe_b64decode(payload_b64 + padding)
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        logger.warning("JWT payload decode failed", exc_info=True)
        return None


def user_id_from_access_token(token: str | None) -> str | None:
    """Extract user id from common JWT claims (sub, uid, user_id, userId, id)."""
    payload = decode_jwt_payload(token)
    if not payload:
        return None
    for key in _USER_ID_CLAIMS:
        raw = payload.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            return text
    logger.warning("JWT payload missing user id claim (%s)", ", ".join(_USER_ID_CLAIMS))
    return None
