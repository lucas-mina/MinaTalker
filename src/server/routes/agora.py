"""Agora RTC routes: token, join, leave."""
from __future__ import annotations

import asyncio
import json

from aiohttp import web

from src.llm.service import remove_session as remove_llm_session
from src.server.agora.player import AgoraHumanPlayer
from src.server.agora.publisher import AgoraRTCPublisher, _sdk_available
from src.server.agora.token_service import agora_token_required, build_rtc_token
from src.server.avatar_session import create_avatar_for_session
from src.server.routes.webrtc import _extract_bearer_token
from src.server.state import state
from src.server.utils import randN
from src.utils.logging import logger


def _agora_config():
    webrtc = getattr(state.config, "webrtc", None)
    return getattr(webrtc, "agora", None) if webrtc else None


def _channel_for_session(sessionid: int, agora) -> str:
    base = (getattr(agora, "default_channel", None) or "mina").strip() or "mina"
    return f"{base}_{sessionid}"


async def get_agora_token(request):
    agora = _agora_config()
    if not agora or not getattr(agora, "enabled", False):
        return web.Response(status=404, text="Agora RTC is not enabled")

    channel = request.query.get("channel", "").strip()
    if not channel:
        return web.Response(status=400, text="channel is required")

    role = request.query.get("role", "audience").strip().lower()
    try:
        uid = int(request.query.get("uid", "0"))
    except ValueError:
        return web.Response(status=400, text="uid must be an integer")

    try:
        token = build_rtc_token(agora, channel_name=channel, uid=uid, role=role)
    except Exception as exc:
        logger.warning("Agora token build failed: %s", exc)
        return web.Response(status=500, text=str(exc))

    return web.Response(
        content_type="application/json",
        text=json.dumps({
            "token": token,
            "channel": channel,
            "uid": uid,
            "role": role,
            "token_required": agora_token_required(agora),
        }),
    )


async def agora_join(request):
    agora = _agora_config()
    if not agora or not getattr(agora, "enabled", False):
        return web.Response(status=404, text="Agora RTC is not enabled")

    try:
        params = await request.json()
    except json.JSONDecodeError:
        return web.Response(status=400, text="invalid json")

    access_token = (
        params.get("access_token")
        or _extract_bearer_token(request.headers.get("Authorization"))
        or request.query.get("access_token")
    )
    avatar_id = params.get("avatar_id")

    model_type = getattr(getattr(state.config, "model", None), "type", "")
    if model_type not in ("wav2lip", "musetalk", "ultralight"):
        return web.Response(
            status=400,
            text=f"Agora RTC publisher not supported for model type {model_type!r}",
        )

    sessionid = randN(6)
    channel = _channel_for_session(sessionid, agora)
    publisher_uid = int(getattr(agora, "publisher_uid", 10001) or 10001)

    try:
        avatar_stream, session_config = await create_avatar_for_session(
            sessionid,
            avatar_id,
            access_token,
        )
    except Exception as exc:
        logger.exception("Agora join: avatar session failed")
        state.remove_session(sessionid)
        return web.Response(status=500, text=str(exc))

    width = int(getattr(session_config.video, "width", 512) or 512)
    height = int(getattr(session_config.video, "height", 512) or 512)
    fps = int(getattr(session_config.video, "fps", 25) or 25)

    publisher = AgoraRTCPublisher(
        agora,
        channel_name=channel,
        publisher_uid=publisher_uid,
        width=width,
        height=height,
        fps=fps,
        sample_rate=int(getattr(session_config.audio, "sample_rate", 16000) or 16000),
    )

    try:
        publisher.start()
    except Exception as exc:
        logger.exception("Agora join: publisher start failed (sdk_available=%s)", _sdk_available())
        state.remove_session(sessionid)
        remove_llm_session(sessionid)
        return web.Response(status=503, text=str(exc))

    loop = asyncio.get_running_loop()
    player = AgoraHumanPlayer(avatar_stream, publisher)
    player.start(loop)
    state.add_agora_session(sessionid, publisher, player)

    audience_token = None
    try:
        audience_token = build_rtc_token(
            agora,
            channel_name=channel,
            uid=0,
            role="audience",
        )
    except Exception as exc:
        logger.warning("Agora join: audience token failed: %s", exc)
        player.stop()
        state.remove_agora_session(sessionid)
        state.remove_session(sessionid)
        remove_llm_session(sessionid)
        return web.Response(status=500, text=str(exc))

    logger.info(
        "Agora join ok sessionid=%s channel=%s publisher_uid=%s",
        sessionid,
        channel,
        publisher_uid,
    )

    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {
                "sessionid": sessionid,
                "channel": channel,
                "publisher_uid": publisher_uid,
                "app_id": (agora.app_id or "").strip(),
                "token": audience_token,
                "uid": 0,
                "token_required": agora_token_required(agora),
            }
        ),
    )


async def agora_leave(request):
    try:
        params = await request.json()
    except json.JSONDecodeError:
        return web.Response(status=400, text="invalid json")

    sessionid = params.get("sessionid")
    if sessionid is None:
        return web.Response(status=400, text="sessionid is required")

    try:
        sessionid = int(sessionid)
    except (TypeError, ValueError):
        return web.Response(status=400, text="sessionid must be an integer")

    state.remove_agora_session(sessionid)
    state.remove_session(sessionid)
    remove_llm_session(sessionid)
    logger.info("Agora leave sessionid=%s", sessionid)
    return web.Response(
        content_type="application/json",
        text=json.dumps({"code": 0, "msg": "ok", "sessionid": sessionid}),
    )
