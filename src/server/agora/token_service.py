"""Agora RTC token generation (server-side only)."""
from __future__ import annotations

from src.config.schema import AgoraConfig
from src.server.agora.token import RtcTokenBuilder, Role_Publisher, Role_Subscriber
from src.utils.logging import logger


def _resolve_certificate(agora: AgoraConfig) -> str | None:
    cert = getattr(agora, "app_certificate", None)
    if cert is None:
        return None
    text = str(cert).strip()
    if not text or text.startswith("${"):
        return None
    return text


def agora_token_required(agora: AgoraConfig) -> bool:
    """True when App Certificate is set and RTC tokens must be generated."""
    return _resolve_certificate(agora) is not None


def build_rtc_token(
    agora: AgoraConfig,
    *,
    channel_name: str,
    uid: int,
    role: str = "audience",
) -> str | None:
    app_id = (getattr(agora, "app_id", None) or "").strip()
    if not app_id:
        raise ValueError("Agora app_id is not configured")

    app_certificate = _resolve_certificate(agora)
    if not app_certificate:
        logger.warning(
            "Agora app_certificate not set; joining without token. "
            "Use Agora Console Testing mode (App ID only). Do not use in production."
        )
        return None

    channel = (channel_name or "").strip()
    if not channel:
        raise ValueError("channel_name is required")

    expire = int(getattr(agora, "token_expiration_seconds", 3600) or 3600)
    rtc_role = Role_Publisher if str(role).lower() in ("publisher", "host", "broadcaster") else Role_Subscriber

    token = RtcTokenBuilder.build_token_with_uid(
        app_id,
        app_certificate,
        channel,
        int(uid),
        rtc_role,
        expire,
        expire,
    )
    if not token:
        raise RuntimeError("Failed to build Agora RTC token")
    return token
