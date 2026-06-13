"""Avatar session access control by JWT owner (sessionid isolation)."""
from __future__ import annotations

from src.server.auth.jwt_claims import user_id_from_access_token
from src.server.state import state
from src.utils.logging import logger


def session_owner_user_id(sessionid: int) -> str | None:
    meta = state.agora_session_meta.get(sessionid) or {}
    raw = meta.get("user_id")
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def register_session_owner(
    sessionid: int,
    user_id: str | None,
    *,
    avatar_id: str | None = None,
) -> None:
    """Bind numeric avatar sessionid to the JWT user that created it."""
    if not user_id or not str(user_id).strip():
        logger.warning(
            "session %s has no owner user_id; other users may access it if they guess sessionid",
            sessionid,
        )
        return
    existing = dict(state.agora_session_meta.get(sessionid) or {})
    existing["user_id"] = str(user_id).strip()
    if avatar_id:
        existing["avatar_id"] = str(avatar_id).strip()
    state.agora_session_meta[sessionid] = existing


def deny_session_access_message(sessionid: int) -> str:
    return f"access denied for session {sessionid}"


def check_session_access(
    sessionid: int,
    access_token: str | None,
    *,
    action: str = "access",
) -> str | None:
    """
    Return an error message when access is denied, else None.

    When a session has an owner, the caller must present a JWT whose user id
    matches that owner. Unowned sessions (legacy dev without JWT at join) are
    left open.
    """
    if not sessionid:
        return None

    owner = session_owner_user_id(sessionid)
    if not owner:
        return None

    caller = user_id_from_access_token(access_token)
    if not caller:
        logger.warning(
            "session %s %s denied: owner=%s but no valid access_token",
            sessionid,
            action,
            owner,
        )
        return deny_session_access_message(sessionid)

    if caller.strip().lower() != owner.strip().lower():
        logger.warning(
            "session %s %s denied: caller=%s owner=%s",
            sessionid,
            action,
            caller,
            owner,
        )
        return deny_session_access_message(sessionid)

    return None
