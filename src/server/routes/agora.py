"""Agora RTC routes: token, join, leave."""
from __future__ import annotations

import asyncio
import json

from aiohttp import web

from src.llm.service import remove_session as remove_llm_session
from src.server.agora_rtc.channel_id import agora_channel_for_client_id, agora_channel_for_room
from src.server.agora_rtc.codec import web_client_codec
from src.server.agora_rtc.player import AgoraHumanPlayer
from src.server.agora_rtc.publisher import AgoraRTCPublisher, _sdk_available
from src.server.agora_rtc.token_service import agora_token_required, build_rtc_token
from src.server.auth.jwt_claims import user_id_from_access_token
from src.server.auth.session_access import check_session_access, session_owner_user_id
from src.server.avatar_session import create_avatar_for_session
from src.server.routes.chat import core_llm_session_id_from_request_payload
from src.server.routes.webrtc import _extract_bearer_token
from src.server.state import state
from src.server.utils import randN
from src.utils.logging import logger

_agora_join_lock = asyncio.Lock()


def _agora_config():
    webrtc = getattr(state.config, "webrtc", None)
    return getattr(webrtc, "agora", None) if webrtc else None


def _channel_base(agora) -> str:
    return (getattr(agora, "default_channel", None) or "mina").strip() or "mina"


def _channel_for_session(sessionid: int, agora) -> str:
    return f"{_channel_base(agora)}_{sessionid}"


def _client_session_id_from_params(params: dict) -> str | None:
    sid = core_llm_session_id_from_request_payload(params)
    if sid:
        return sid
    raw = params.get("session_id")
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _find_sessionid_by_channel(channel: str) -> int | None:
    target = (channel or "").strip()
    if not target:
        return None
    for sid, (publisher, _player) in state.agora_sessions.items():
        if getattr(publisher, "_channel", None) == target:
            return sid
    return None


def _agora_session_meta(sessionid: int) -> dict:
    return state.agora_session_meta.get(sessionid) or {}


def _session_owner_user_id(sessionid: int) -> str | None:
    return session_owner_user_id(sessionid)

def _find_active_session_for_user_avatar(
    user_id: str | None,
    avatar_id: str | None,
) -> int | None:
    """Active publisher for this user+avatar (same user reconnect), not shared across users."""
    if not user_id or not avatar_id:
        return None
    user_norm = str(user_id).strip().lower()
    avatar_norm = str(avatar_id).strip().lower()
    if not user_norm or not avatar_norm:
        return None
    for sid, meta in state.agora_session_meta.items():
        if sid not in state.agora_sessions:
            continue
        owner = str(meta.get("user_id") or "").strip().lower()
        av = str(meta.get("avatar_id") or "").strip().lower()
        if owner == user_norm and av == avatar_norm:
            publisher, player = state.agora_sessions[sid]
            if _session_healthy(publisher, player):
                return sid
    return None


def _access_token_from_request(request, params: dict | None = None) -> str | None:
    params = params or {}
    token = (
        params.get("access_token")
        or _extract_bearer_token(request.headers.get("Authorization"))
        or request.query.get("access_token")
    )
    if token is None:
        return None
    text = str(token).strip()
    return text or None


def _user_id_from_params(params: dict, *, access_token: str | None = None) -> str | None:
    for key in ("user_id", "userid", "userId"):
        raw = params.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            return text
    from_jwt = user_id_from_access_token(
        access_token or params.get("access_token")
    )
    if from_jwt:
        return from_jwt
    return None


def _avatar_id_from_params(params: dict) -> str | None:
    raw = params.get("avatar_id")
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _channel_from_room_params(
    agora,
    *,
    user_id: str | None,
    avatar_id: str | None,
    client_session_id: str | None,
) -> str | None:
    base = _channel_base(agora)
    if user_id and avatar_id:
        return agora_channel_for_room(
            user_id=user_id,
            avatar_id=avatar_id,
            base=base,
        )
    if client_session_id:
        return agora_channel_for_client_id(client_session_id, base=base)
    return None


def _resolve_channel(*, sessionid: int, agora) -> str:
    """One Agora channel per server sessionid — never shared across users."""
    return _channel_for_session(sessionid, agora)


def _resolve_video_size(avatar_stream, session_config) -> tuple[int, int]:
    """Use config video.width/height; scale avatar frames on publish if assets differ."""
    width = int(getattr(session_config.video, "width", 512) or 512)
    height = int(getattr(session_config.video, "height", 512) or 512)
    frames = getattr(avatar_stream, "frame_list_cycle", None)
    if frames:
        try:
            frame_h, frame_w = frames[0].shape[:2]
            asset_w, asset_h = int(frame_w), int(frame_h)
            if asset_w != width or asset_h != height:
                logger.info(
                    "Agora publish %dx%d from config (avatar assets %dx%d, scaled on push)",
                    width,
                    height,
                    asset_w,
                    asset_h,
                )
            else:
                logger.info("Agora publish %dx%d (matches avatar assets)", width, height)
        except Exception:
            logger.exception("Failed to read avatar frame size; using config video size")
    else:
        logger.info("Agora publish %dx%d from config (no avatar frames yet)", width, height)
    return width, height


async def get_agora_channel(request):
    agora = _agora_config()
    if not agora or not getattr(agora, "enabled", False):
        return web.Response(status=404, text="Agora RTC is not enabled")

    params = {
        "user_id": request.query.get("user_id", "").strip() or None,
        "avatar_id": request.query.get("avatar_id", "").strip() or None,
        "session_id": request.query.get("session_id", "").strip() or None,
        "access_token": _access_token_from_request(request),
    }
    user_id = _user_id_from_params(params, access_token=params.get("access_token"))
    avatar_id = _avatar_id_from_params(params)
    client_session_id = _client_session_id_from_params(params)

    try:
        channel = _channel_from_room_params(
            agora,
            user_id=user_id,
            avatar_id=avatar_id,
            client_session_id=client_session_id,
        )
    except ValueError as exc:
        return web.Response(status=400, text=str(exc))

    existing_sid = _find_active_session_for_user_avatar(user_id, avatar_id)
    if existing_sid is None and channel:
        existing_sid = _find_sessionid_by_channel(channel)
    active_channel = None
    if existing_sid is not None:
        publisher, _player = state.agora_sessions.get(existing_sid, (None, None))
        active_channel = getattr(publisher, "_channel", None) if publisher else None

    return web.Response(
        content_type="application/json",
        text=json.dumps({
            "user_id": user_id,
            "avatar_id": avatar_id,
            "session_id": client_session_id,
            "channel": active_channel,
            "publisher_active": existing_sid is not None,
            "sessionid": existing_sid,
            "isolated_per_join": True,
        }),
    )


async def get_agora_token(request):
    agora = _agora_config()
    if not agora or not getattr(agora, "enabled", False):
        return web.Response(status=404, text="Agora RTC is not enabled")

    channel = request.query.get("channel", "").strip()
    access_token = _access_token_from_request(request)
    token_params = {
        "user_id": request.query.get("user_id", "").strip() or None,
        "avatar_id": request.query.get("avatar_id", "").strip() or None,
        "session_id": request.query.get("session_id", "").strip() or None,
        "access_token": access_token,
    }
    user_id = _user_id_from_params(token_params, access_token=access_token)
    avatar_id = _avatar_id_from_params(token_params)
    client_session_id = _client_session_id_from_params(token_params)
    if not channel:
        sid_raw = request.query.get("sessionid", "").strip()
        if sid_raw.isdigit():
            sid = int(sid_raw)
            if sid in state.agora_sessions:
                publisher, _player = state.agora_sessions[sid]
                channel = getattr(publisher, "_channel", None) or _channel_for_session(sid, agora)
        if not channel:
            sid = _find_active_session_for_user_avatar(user_id, avatar_id)
            if sid is not None:
                publisher, _player = state.agora_sessions[sid]
                channel = getattr(publisher, "_channel", None) or _channel_for_session(sid, agora)
        if not channel:
            try:
                channel = _channel_from_room_params(
                    agora,
                    user_id=user_id,
                    avatar_id=avatar_id,
                    client_session_id=client_session_id,
                )
            except ValueError as exc:
                return web.Response(status=400, text=str(exc))
    if not channel:
        return web.Response(
            status=400,
            text="channel, sessionid, or (avatar_id with Bearer access_token) is required",
        )

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
            "user_id": user_id,
            "avatar_id": avatar_id,
            "session_id": client_session_id or None,
            "uid": uid,
            "role": role,
            "token_required": agora_token_required(agora),
        }),
    )


def _publisher_alive(publisher) -> bool:
    if publisher is None:
        return False
    if hasattr(publisher, "is_alive"):
        return bool(publisher.is_alive)
    return bool(getattr(publisher, "_started", False) and not getattr(publisher, "_closed", True))


def _session_healthy(publisher, player) -> bool:
    if not _publisher_alive(publisher):
        return False
    thread = getattr(player, "_thread", None)
    if thread is not None and not thread.is_alive():
        logger.warning(
            "Agora session unhealthy: render thread dead channel=%s",
            getattr(publisher, "_channel", "?"),
        )
        return False
    return True


def _evict_agora_session(sessionid: int, *, reason: str) -> None:
    if sessionid not in state.agora_sessions and sessionid not in state.avatar_streams:
        return
    logger.warning("Agora evicting sessionid=%s (%s)", sessionid, reason)
    state.remove_agora_session(sessionid)
    state.remove_session(sessionid)
    remove_llm_session(sessionid)


def _refresh_publisher_for_audience(publisher, player) -> None:
    """Push an idle frame when the same user reconnects to an existing publisher."""
    if not _publisher_alive(publisher):
        logger.warning("Agora reuse skipped refresh: publisher not alive")
        return
    container = getattr(player, "_container", None)
    frames = getattr(container, "frame_list_cycle", None) if container else None
    if not frames:
        logger.warning("Agora reuse refresh: no idle avatar frames available")
        return
    try:
        publisher.push_idle_startup(frames)
        logger.info(
            "Agora reuse refreshed idle video for new audience channel=%s",
            getattr(publisher, "_channel", "?"),
        )
    except Exception:
        logger.exception("Agora reuse idle frame push failed")


def _build_join_payload(
    sessionid: int,
    agora,
    publisher,
    *,
    reused: bool = False,
    client_session_id: str | None = None,
    user_id: str | None = None,
    avatar_id: str | None = None,
) -> dict:
    channel = (getattr(publisher, "_channel", None) or "").strip() or _channel_for_session(sessionid, agora)
    publisher_uid = int(getattr(agora, "publisher_uid", 10001) or 10001)
    audience_token = build_rtc_token(
        agora,
        channel_name=channel,
        uid=0,
        role="audience",
    )
    payload = {
        "sessionid": sessionid,
        "channel": channel,
        "publisher_uid": publisher_uid,
        "video_width": int(getattr(publisher, "_width", 0) or 0),
        "video_height": int(getattr(publisher, "_height", 0) or 0),
        "video_codec": web_client_codec(
            getattr(publisher, "_client_video_codec", None)
            or getattr(publisher, "_video_codec", None)
            or getattr(agora, "video_codec", None),
            width=int(getattr(publisher, "_width", 0) or 0),
            height=int(getattr(publisher, "_height", 0) or 0),
        ),
        "app_id": (agora.app_id or "").strip(),
        "token": audience_token,
        "uid": 0,
        "token_required": agora_token_required(agora),
        "reused": reused,
    }
    if client_session_id:
        payload["session_id"] = client_session_id
    if user_id:
        payload["user_id"] = user_id
    if avatar_id:
        payload["avatar_id"] = avatar_id
    return payload


def _try_reuse_agora_session(
    agora,
    requested_sessionid: int | None = None,
    *,
    user_id: str | None = None,
) -> dict | None:
    """Reuse only when the client reconnects with its own active sessionid."""
    if requested_sessionid is None:
        return None
    if requested_sessionid not in state.agora_sessions:
        return None

    owner = _session_owner_user_id(requested_sessionid)
    if user_id and owner and user_id.strip().lower() != owner.strip().lower():
        logger.warning(
            "Agora join: user_id=%s denied reuse of sessionid=%s (owner=%s)",
            user_id,
            requested_sessionid,
            owner,
        )
        return None

    publisher, player = state.agora_sessions.get(requested_sessionid, (None, None))
    if not _session_healthy(publisher, player):
        logger.warning(
            "Agora join: stale sessionid=%s; removing and creating fresh session",
            requested_sessionid,
        )
        _evict_agora_session(requested_sessionid, reason="stale:reconnect")
        return None

    meta = _agora_session_meta(requested_sessionid)
    _refresh_publisher_for_audience(publisher, player)
    logger.info("Agora join reusing sessionid=%s (explicit reconnect)", requested_sessionid)
    return _build_join_payload(
        requested_sessionid,
        agora,
        publisher,
        reused=True,
        client_session_id=meta.get("client_session_id"),
        user_id=meta.get("user_id") or user_id,
        avatar_id=meta.get("avatar_id"),
    )


async def agora_join(request):
    agora = _agora_config()
    if not agora or not getattr(agora, "enabled", False):
        return web.Response(status=404, text="Agora RTC is not enabled")

    try:
        params = await request.json()
    except json.JSONDecodeError:
        return web.Response(status=400, text="invalid json")

    access_token = _access_token_from_request(request, params)
    avatar_id = _avatar_id_from_params(params)
    user_id = _user_id_from_params(params, access_token=access_token)
    if user_id and not params.get("user_id"):
        logger.info("Agora join: user_id from access_token JWT")
    client_session_id = _client_session_id_from_params(params)

    requested_sessionid = params.get("sessionid")
    if requested_sessionid is not None:
        try:
            requested_sessionid = int(requested_sessionid)
        except (TypeError, ValueError):
            if client_session_id is None:
                client_session_id = str(requested_sessionid).strip() or None
            requested_sessionid = None

    reused_payload = _try_reuse_agora_session(
        agora,
        requested_sessionid,
        user_id=user_id,
    )
    if reused_payload is not None:
        return web.Response(
            content_type="application/json",
            text=json.dumps(reused_payload),
        )

    max_session = int(getattr(getattr(state.config, "app", None), "max_session", 1) or 1)
    if len(state.agora_sessions) >= max_session:
        active = list(state.agora_sessions.keys())
        logger.warning(
            "Agora join rejected: max_session=%d reached (active=%s) user_id=%s avatar_id=%s",
            max_session,
            active,
            user_id or "(none)",
            avatar_id or "(none)",
        )
        return web.Response(
            status=409,
            text=(
                f"All {max_session} avatar session slot(s) are in use. "
                "Raise app.max_session or wait for another user to disconnect."
            ),
        )

    async with _agora_join_lock:
        reused_payload = _try_reuse_agora_session(
            agora,
            requested_sessionid,
            user_id=user_id,
        )
        if reused_payload is not None:
            return web.Response(
                content_type="application/json",
                text=json.dumps(reused_payload),
            )

        if len(state.agora_sessions) >= max_session:
            return web.Response(
                status=409,
                text=(
                    f"All {max_session} avatar session slot(s) are in use. "
                    "Raise app.max_session or wait for another user to disconnect."
                ),
            )

        model_type = getattr(getattr(state.config, "model", None), "type", "")
        if model_type not in ("wav2lip", "musetalk", "ultralight"):
            return web.Response(
                status=400,
                text=f"Agora RTC publisher not supported for model type {model_type!r}",
            )

        sessionid = randN(6)
        channel = _resolve_channel(sessionid=sessionid, agora=agora)
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

        width, height = _resolve_video_size(avatar_stream, session_config)
        fps = int(getattr(session_config.video, "fps", 25) or 25)
        audio_fps = int(getattr(session_config.audio, "fps", 50) or 50)

        publisher = AgoraRTCPublisher(
            agora,
            channel_name=channel,
            publisher_uid=publisher_uid,
            width=width,
            height=height,
            fps=fps,
            sample_rate=int(getattr(session_config.audio, "sample_rate", 16000) or 16000),
            audio_fps=audio_fps,
        )

        try:
            publisher.start()
            frames = getattr(avatar_stream, "frame_list_cycle", None)
            if frames:
                try:
                    publisher.push_idle_startup(frames)
                    logger.info("Agora pushed paced idle startup on join channel=%s", channel)
                except Exception:
                    logger.exception("Agora idle frame push on join failed channel=%s", channel)
        except Exception as exc:
            logger.exception("Agora join: publisher start failed (sdk_available=%s)", _sdk_available())
            state.remove_session(sessionid)
            remove_llm_session(sessionid)
            return web.Response(status=503, text=str(exc))

        loop = asyncio.get_running_loop()
        player = AgoraHumanPlayer(avatar_stream, publisher)
        player.start(loop)
        state.add_agora_session(
            sessionid,
            publisher,
            player,
            user_id=user_id,
            avatar_id=avatar_id,
        )
        state.agora_session_meta[sessionid]["client_session_id"] = client_session_id

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
        _ = audience_token  # validated; payload rebuilt via _build_join_payload

        logger.info(
            "Agora join ok sessionid=%s channel=%s publisher_uid=%s user_id=%s avatar_id=%s session_id=%s",
            sessionid,
            channel,
            publisher_uid,
            user_id or "(none)",
            avatar_id or "(none)",
            client_session_id or "(none)",
        )

        return web.Response(
            content_type="application/json",
            text=json.dumps(
                _build_join_payload(
                    sessionid,
                    agora,
                    publisher,
                    reused=False,
                    client_session_id=client_session_id,
                    user_id=user_id,
                    avatar_id=avatar_id,
                )
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

    access_token = _access_token_from_request(request, params)
    access_err = check_session_access(sessionid, access_token, action="agora.leave")
    if access_err:
        return web.Response(status=403, text=access_err)

    async with _agora_join_lock:
        _evict_agora_session(sessionid, reason="client leave")
    logger.info("Agora leave sessionid=%s", sessionid)
    return web.Response(
        content_type="application/json",
        text=json.dumps({"code": 0, "msg": "ok", "sessionid": sessionid}),
    )


async def agora_test_page(request):
    """Redirect /agora-test.html → /public/agora-test.html (preserve query string)."""
    location = "/public/agora-test.html"
    if request.query_string:
        location = f"{location}?{request.query_string}"
    raise web.HTTPFound(location)
