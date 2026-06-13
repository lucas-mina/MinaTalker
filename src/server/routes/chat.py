"""聊天相关路由"""
import json
from aiohttp import web
import asyncio

from src.llm.env import resolve_llm_base_url_for_session
from src.llm.service import clear_session_history, llm_response
from src.llm.transient_network import user_message_chat_http
from src.utils.logging import logger
from src.server.auth.session_access import check_session_access
from src.server.state import state


def _json(data: dict) -> web.Response:
    return web.Response(content_type="application/json", text=json.dumps(data))


def _get_avatar_stream(sessionid):
    """Return the avatar stream for sessionid, or None if the session is gone."""
    return state.avatar_streams.get(sessionid)


def _optional_lang(params: dict) -> str | None:
    raw = params.get("lang")
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


def _optional_timestamp(params: dict) -> str | None:
    raw = params.get("timestamp")
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


def _coerce_int_avatar(v) -> int | None:
    """Parse WebRTC avatar ``sessionid`` (integer); ``None`` if not an int."""
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def core_llm_session_id_from_request_payload(data: dict) -> str | None:
    """
    Core/internal LLM thread id for ``session_id`` on the wire to Core.

    Accepts canonical ``session_id`` or client alias ``sessionid`` when it is
    **not** an integer (some clients use ``sessionid`` for the Core thread UUID).
    """
    r = data.get("session_id")
    if r is not None:
        s = str(r).strip()
        if s:
            return s
    alt = data.get("sessionid")
    if alt is None:
        return None
    if _coerce_int_avatar(alt) is not None:
        return None
    s = str(alt).strip()
    return s or None


def webrtc_avatar_sessionid_from_chat_request(server_sessionid: int | None, data: dict) -> int:
    """Numeric WebRTC room id: prefer server-bound session, else int ``sessionid`` in message."""
    if server_sessionid is not None:
        return int(server_sessionid)
    c = _coerce_int_avatar(data.get("sessionid"))
    return int(c) if c is not None else 0


def _optional_session_id(params: dict) -> str | None:
    return core_llm_session_id_from_request_payload(params)


def _extract_bearer_token(authorization_header: str | None) -> str | None:
    if not authorization_header:
        return None
    parts = authorization_header.strip().split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
        return parts[1].strip()
    return None


async def process_human_message(params: dict) -> dict:
    """Process a human chat/echo request and return JSON-serializable result."""
    has_core = bool(str(params.get("session_id") or "").strip())
    # Do not use ``.get("sessionid", 0)``: missing key must not become WebRTC room 0.
    if "sessionid" not in params:
        if has_core:
            sessionid = int(
                _coerce_int_avatar(params.get("webrtc_sessionid"))
                or _coerce_int_avatar(params.get("avatar_sessionid"))
                or 0
            )
        else:
            sessionid = 0
    else:
        raw_sid = params["sessionid"]
        av_int = _coerce_int_avatar(raw_sid)
        if av_int is not None:
            sessionid = av_int
        elif has_core and _coerce_int_avatar(raw_sid) is None:
            # ``sessionid`` held Core UUID; WebRTC room from explicit int keys or 0.
            sessionid = int(
                _coerce_int_avatar(params.get("webrtc_sessionid"))
                or _coerce_int_avatar(params.get("avatar_sessionid"))
                or 0
            )
        else:
            try:
                sessionid = int(raw_sid)
            except (TypeError, ValueError):
                sessionid = 0

    avatar_stream = _get_avatar_stream(sessionid)
    if avatar_stream is None:
        logger.warning(f'[CHAT] session {sessionid} not found (already closed?)')
        return {"code": -1, "msg": f"session {sessionid} not found"}

    access_token = params.get("access_token") or getattr(avatar_stream, "internal_access_token", None)
    if sessionid:
        access_err = check_session_access(sessionid, access_token, action="chat")
        if access_err:
            return {"code": -1, "msg": access_err}

    if params.get('interrupt'):
        avatar_stream.flush_talk()

    if access_token and str(access_token).strip():
        setattr(avatar_stream, "internal_access_token", str(access_token).strip())

    client_env = params.get("environment")
    if client_env is not None and str(client_env).strip():
        setattr(avatar_stream, "client_environment", str(client_env).strip())

    if params.get('type') == 'echo':
        text = params.get('text', '')
        rid = params.get("request_id")
        if rid:
            avatar_stream.voice_chat_turn_begin(str(rid))
        avatar_stream.put_msg_txt(text, {"request_id": str(rid)} if rid else {})
        if rid:
            avatar_stream.voice_chat_queue_closed()
        response_text = text
    elif params.get('type') == 'chat':
        # Log session-scoped LLM (WebRTC offer stamps llm.character_id on avatar_stream.config).
        global_llm = state.config.llm if state.config else None
        session_llm = getattr(getattr(avatar_stream, "config", None), "llm", None)
        logger.info(
            "[CHAT] LLM 配置 session=%s global=%s (effective routing uses session)",
            session_llm,
            global_llm,
        )
        core_sid = _optional_session_id(params)
        if core_sid:
            logger.info("[CHAT] Core LLM session_id=%s (avatar sessionid=%s)", core_sid, sessionid)
        fallback_base_url = (
            global_llm.base_url if global_llm else "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        resolved_base_url = resolve_llm_base_url_for_session(
            client_env, avatar_stream, fallback_base_url
        )
        response_text = await asyncio.get_event_loop().run_in_executor(
            None,
            llm_response,
            params.get('text', ''),
            avatar_stream,
            global_llm.provider if global_llm else "openai",
            global_llm.api_key if global_llm else None,
            resolved_base_url,
            global_llm.model if global_llm else "qwen-plus",
            access_token,
            global_llm.character_id if global_llm else None,
            _optional_lang(params),
            core_sid,
            params.get("request_id"),
            _optional_timestamp(params),
        )
    else:
        return {"code": -1, "msg": f"unknown type: {params.get('type')}"}

    return {"code": 0, "msg": "ok", "response": response_text}


async def human(request):
    """处理文本对话请求"""
    try:
        params = await request.json()
        params.setdefault("access_token", _extract_bearer_token(request.headers.get("Authorization")))
        # Client alias: non-numeric ``sessionid`` → Core ``session_id`` (LLM still uses ``session_id``).
        if not str(params.get("session_id") or "").strip():
            alias = core_llm_session_id_from_request_payload(params)
            if alias:
                params["session_id"] = alias
        result = await process_human_message(params)
        return _json(result)

    except Exception as e:
        logger.exception("human chat request failed:")
        return _json({"code": -1, "msg": user_message_chat_http(e)})


async def interrupt_talk(request):
    """中断当前对话"""
    try:
        params = await request.json()
        sessionid = params.get('sessionid', 0)
        access_token = params.get("access_token") or _extract_bearer_token(request.headers.get("Authorization"))

        access_err = check_session_access(int(sessionid or 0), access_token, action="interrupt")
        if access_err:
            return _json({"code": -1, "msg": access_err})

        avatar_stream = _get_avatar_stream(sessionid)
        if avatar_stream is None:
            logger.warning(f'[INTERRUPT] session {sessionid} not found')
            return _json({"code": -1, "msg": f"session {sessionid} not found"})

        avatar_stream.flush_talk()
        return _json({"code": 0, "msg": "ok"})

    except Exception as e:
        logger.exception('exception:')
        return _json({"code": -1, "msg": str(e)})


async def is_speaking(request):
    """查询是否正在说话"""
    try:
        params = await request.json()
        sessionid = params.get('sessionid', 0)
        access_token = params.get("access_token") or _extract_bearer_token(request.headers.get("Authorization"))

        access_err = check_session_access(int(sessionid or 0), access_token, action="is_speaking")
        if access_err:
            return _json({"code": -1, "msg": access_err})

        avatar_stream = _get_avatar_stream(sessionid)
        if avatar_stream is None:
            return _json({"code": -1, "msg": f"session {sessionid} not found"})

        return _json({"code": 0, "data": avatar_stream.is_speaking()})

    except Exception as e:
        logger.exception('exception:')
        return _json({"code": -1, "msg": str(e)})


async def clear_history(request):
    """清空对话历史"""
    try:
        params = await request.json()
        sessionid = params.get('sessionid', 0)
        access_token = params.get("access_token") or _extract_bearer_token(request.headers.get("Authorization"))

        access_err = check_session_access(int(sessionid or 0), access_token, action="clear_history")
        if access_err:
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": access_err}),
            )

        clear_session_history(sessionid)
        
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": 0, "msg": "对话历史已清空"}
            ),
        )
    except Exception as e:
        logger.exception('清空历史失败:')
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": -1, "msg": str(e)}
            ),
        )
