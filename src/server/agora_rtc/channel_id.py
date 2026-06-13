"""Deterministic Agora channel names (legacy helpers).

Live join uses ``mina_{sessionid}`` — one isolated publisher channel per server session.
Do not hash only user+avatar or Core session_id; that caused unrelated users to share a room.
"""
from __future__ import annotations

import hashlib

from src.utils.logging import logger

AGORA_CHANNEL_MAX_LEN = 64
CHANNEL_HASH_HEX_LEN = 32


def _normalize_id(raw: str, *, field: str) -> str:
    text = str(raw or "").strip().lower()
    if not text:
        raise ValueError(f"{field} is empty")
    return text


def _channel_from_material(material: str, *, base: str) -> str:
    prefix = (base or "mina").strip() or "mina"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:CHANNEL_HASH_HEX_LEN]
    channel = f"{prefix}_{digest}"
    if len(channel) > AGORA_CHANNEL_MAX_LEN:
        logger.warning(
            "Agora channel name exceeds %d bytes (%d): %r",
            AGORA_CHANNEL_MAX_LEN,
            len(channel),
            channel,
        )
    return channel


def agora_channel_for_room(
    *,
    user_id: str,
    avatar_id: str,
    base: str = "mina",
) -> str:
    """Stable Agora channel for one user talking to one avatar.

    channel = ``{base}_`` + sha256(f"{user_id}:{avatar_id}".lower())[:32]
    """
    user = _normalize_id(user_id, field="user_id")
    avatar = _normalize_id(avatar_id, field="avatar_id")
    return _channel_from_material(f"{user}:{avatar}", base=base)


def agora_channel_for_client_id(client_id: str, *, base: str = "mina") -> str:
    """Legacy: hash Core LLM session_id only (prefer user_id + avatar_id)."""
    normalized = _normalize_id(client_id, field="session_id")
    logger.warning(
        "Agora channel derived from session_id only; pass user_id + avatar_id for room isolation"
    )
    return _channel_from_material(normalized, base=base)


def normalize_client_session_id(raw: str) -> str:
    return _normalize_id(raw, field="session_id")
