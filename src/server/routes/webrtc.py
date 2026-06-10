# Linly-Talker-Stream (https://github.com/Kedreamix/Linly-Talker-Stream). Copyright [Linly-talker-stream@kedreamix]. Apache-2.0.
# Based on LiveTalking (C) 2024 LiveTalking@lipku https://github.com/lipku/LiveTalking (Apache-2.0).

"""WebRTC 相关路由"""
import json
import asyncio
from aiohttp import web, WSMsgType, WSCloseCode
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceServer, RTCConfiguration
from aiortc.rtcrtpsender import RTCRtpSender

from src.utils.webrtc import HumanPlayer
from src.avatars.factory import create_avatar
from src.utils.logging import logger
from src.server.state import state
from src.server.utils import randN
from src.config.loader import find_avatar_entry_by_catalog_id, load_avatar_entries
from src.llm.service import remove_session as remove_llm_session
from src.server.routes.chat import (
    core_llm_session_id_from_request_payload,
    process_human_message,
    webrtc_avatar_sessionid_from_chat_request,
)

# ------------------------------------------------------------------
# WS signaling protocol
# ------------------------------------------------------------------
# Client → Server messages:
#   { "type": "offer",     "sdp": "<sdp>", "avatar_id": <int|string|null> }  # string = YAML catalog id (e.g. UUID)
#   { "type": "candidate", "candidate": "<sdpMid>", "sdpMid": "<mid>", "sdpMLineIndex": <int> }
#   { "type": "is_speaking" }   # optional status query on existing WS
#   { "type": "ping" }
#   { "type": "bye" }
#
# Server → Client messages:
#   { "type": "answer",    "sdp": "<sdp>", "sessionid": <int> }
#   { "type": "candidate", "candidate": "<sdpMid>", "sdpMid": "<mid>", "sdpMLineIndex": <int> }
#   { "type": "speaking_state", "sessionid": <int>, "speaking": <bool> }
#   { "type": "pong" }
#   { "type": "error",     "error": "<message>" }
#   { "type": "bye" }
# ------------------------------------------------------------------

_WS_HEARTBEAT_INTERVAL = 25  # seconds between server-initiated pings
_WS_HEARTBEAT_TIMEOUT  = 15  # seconds to wait for pong before closing


def _extract_bearer_token(authorization_header: str | None) -> str | None:
    if not authorization_header:
        return None
    parts = authorization_header.strip().split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
        return parts[1].strip()
    return None


async def handle_offer(sdp: str, type_: str, avatar_id=None, access_token: str | None = None) -> tuple[dict, RTCPeerConnection]:
    """
    处理 WebRTC offer（SDP + type），创建会话、PC 和 answer。
    供 HTTP POST /offer 和 WebSocket 信令共用。
    返回: ({"sdp": str, "type": str, "sessionid": int}, RTCPeerConnection)
    """
    offer = RTCSessionDescription(sdp=sdp, type=type_)

    sessionid = randN(6)
    state.add_session(sessionid, None)
    logger.info('sessionid=%d, avatar_id=%s, session num=%d', sessionid, avatar_id, len(state.avatar_streams))

    # Resolve per-avatar config (prompt_file + model_avatar_id) from avatar_config.yaml
    from copy import deepcopy
    session_config = deepcopy(state.config)
    session_avatar_data = state.avatar  # default: preloaded global avatar

    if avatar_id is not None:
        try:
            entries = load_avatar_entries()
            matched = find_avatar_entry_by_catalog_id(entries, avatar_id)

            if matched:
                # 0. Internal LLM routing: use avatar catalog id as character_id when present
                catalog_char = matched.get("id")
                if catalog_char is not None and str(catalog_char).strip():
                    session_config.llm.character_id = str(catalog_char).strip()
                    logger.info(
                        "Using llm.character_id=%s from avatar_config (catalog id)",
                        session_config.llm.character_id,
                    )

                # 1. Stamp per-avatar prompt file
                prompt_file = matched.get("prompt_file")
                if prompt_file:
                    session_config.prompt_file = prompt_file
                    logger.info('Using prompt_file=%s for avatar_id=%s', prompt_file, avatar_id)

                # 2. Per-avatar TTS provider + voice (elevenlabs | inworld | minimax)
                provider = (matched.get("tts_provider") or "").strip().lower()
                voice_id = (matched.get("tts_voice_id") or matched.get("elevenlabs_voice_id") or "").strip()
                tts_model = (matched.get("tts_model") or "").strip()
                language_boost = (matched.get("language_boost") or "").strip()
                if not provider and voice_id:
                    provider = "elevenlabs"
                if voice_id and provider in ("elevenlabs", "inworld", "minimax"):
                    session_config.tts.type = provider
                    session_config.tts.ref_file = voice_id
                    if tts_model:
                        session_config.tts.model = tts_model
                    if language_boost:
                        session_config.tts.language_boost = language_boost
                    logger.info(
                        "Using tts provider=%s voice_id=%s model=%s language_boost=%s for avatar_id=%s",
                        provider,
                        voice_id,
                        tts_model or "(default)",
                        language_boost or session_config.tts.language_boost,
                        avatar_id,
                    )
                elif voice_id:
                    logger.warning(
                        "Unknown tts_provider=%r for avatar_id=%s (voice_id=%s)",
                        provider,
                        avatar_id,
                        voice_id,
                    )

                # 3. Load the per-avatar model assets (frames/coords/latents)
                model_avatar_id = matched.get("model_avatar_id")
                if model_avatar_id:
                    model_type = state.config.model.type
                    try:
                        if model_type == "wav2lip":
                            from src.avatars.wav2lip.avatar import load_avatar as _load_avatar
                        elif model_type == "musetalk":
                            from src.avatars.musetalk.avatar import load_avatar as _load_avatar
                        else:
                            _load_avatar = None

                        if _load_avatar:
                            logger.info(
                                'Loading avatar assets for model_avatar_id=%s (avatar_id=%s)',
                                model_avatar_id, avatar_id
                            )
                            session_avatar_data = await asyncio.get_event_loop().run_in_executor(
                                None, _load_avatar, model_avatar_id
                            )
                        else:
                            logger.warning(
                                'Per-avatar asset loading not supported for model type %s', model_type
                            )
                    except Exception:
                        logger.exception(
                            'Failed to load avatar assets for model_avatar_id=%s, using default.',
                            model_avatar_id
                        )
            else:
                logger.warning('No avatar entry found for avatar_id=%s', avatar_id)

        except Exception as e:
            logger.warning('Failed to resolve avatar config for avatar_id=%s: %s', avatar_id, e)

    # 创建 avatar stream（可能耗时，放线程池）
    avatar_stream = await asyncio.get_event_loop().run_in_executor(
        None, create_avatar, session_config, state.model, session_avatar_data, sessionid
    )
    if access_token:
        setattr(avatar_stream, "internal_access_token", access_token)
    state.add_session(sessionid, avatar_stream)
    
    ice_server = RTCIceServer(urls='stun:stun.miwifi.com:3478')
    pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=[ice_server]))
    state.add_peer_connection(pc)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logger.info("Connection state is %s" % pc.connectionState)
        if pc.connectionState == "failed":
            await pc.close()
            state.remove_peer_connection(pc)
            state.remove_session(sessionid)
            remove_llm_session(sessionid)
        if pc.connectionState == "closed":
            state.remove_peer_connection(pc)
            state.remove_session(sessionid)
            remove_llm_session(sessionid)

    player = HumanPlayer(state.avatar_streams[sessionid])
    pc.addTrack(player.audio)
    pc.addTrack(player.video)

    transceivers = pc.getTransceivers()
    if len(transceivers) >= 2:
        try:
            capabilities = RTCRtpSender.getCapabilities("video")
            if capabilities and capabilities.codecs:
                preferences = [c for c in capabilities.codecs if c and getattr(c, "name", None) == "H264"]
                preferences += [c for c in capabilities.codecs if c and getattr(c, "name", None) == "VP8"]
                preferences += [c for c in capabilities.codecs if c and getattr(c, "name", None) == "rtx"]
                if preferences:
                    transceivers[1].setCodecPreferences(preferences)
        except (ValueError, IndexError, AttributeError) as e:
            logger.warning("setCodecPreferences skipped: %s", e)

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return {
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type,
        "sessionid": sessionid,
    }, pc


async def offer(request):
    """处理 WebRTC offer 请求（HTTP POST）"""
    params = await request.json()
    access_token = (
        params.get("access_token")
        or _extract_bearer_token(request.headers.get("Authorization"))
        or request.query.get("access_token")
    )
    result, _pc = await handle_offer(
        params["sdp"],
        params["type"],
        params.get("avatar_id"),
        access_token,
    )
    return web.Response(
        content_type="application/json",
        text=json.dumps(result),
    )


async def ws_signaling(request):
    """
    Full WebSocket signaling endpoint.

    Lifecycle:
      1. Client connects → negotiation phase (expects 'offer').
      2. Server processes offer, replies with 'answer' + sessionid.
      3. Either side may trickle ICE candidates via 'candidate' messages.
      4. Server sends WS-level ping frames every _WS_HEARTBEAT_INTERVAL seconds;
         client must respond with pong (automatic in most browsers) or send
         { "type": "ping" } which the server acknowledges with { "type": "pong" }.
      5. Either side closes cleanly with { "type": "bye" } before WS close.
    """
    ws = web.WebSocketResponse(heartbeat=_WS_HEARTBEAT_INTERVAL, autoping=True)
    await ws.prepare(request)

    peer_addr = request.remote
    logger.info("ws_signaling: client connected from %s", peer_addr)

    # Per-connection mutable state
    pc: RTCPeerConnection | None = None
    sessionid: int | None = None
    speaking_task: asyncio.Task | None = None
    last_speaking_state: bool | None = None
    session_access_token: str | None = (
        _extract_bearer_token(request.headers.get("Authorization"))
        or request.query.get("access_token")
    )
    session_llm_session_id: str | None = core_llm_session_id_from_request_payload(
        {
            "session_id": request.query.get("session_id"),
            "sessionid": request.query.get("sessionid"),
        }
    )
    if session_llm_session_id:
        logger.info("ws_signaling: WS query Core session_id=%s", session_llm_session_id)

    async def _cleanup(reason: str = ""):
        nonlocal pc, sessionid, speaking_task
        if reason:
            logger.info("ws_signaling: cleanup — %s (session=%s)", reason, sessionid)
        if speaking_task is not None:
            speaking_task.cancel()
            try:
                await speaking_task
            except asyncio.CancelledError:
                pass
            speaking_task = None
        if sessionid is not None:
            state.remove_session(sessionid)
            remove_llm_session(sessionid)
            sessionid = None
        if pc is not None:
            await pc.close()
            state.remove_peer_connection(pc)
            pc = None

    async def _send(obj: dict):
        """Send a JSON text frame; swallow errors on a closing socket."""
        if not ws.closed:
            try:
                await ws.send_str(json.dumps(obj))
            except Exception:
                pass

    async def _send_speaking_state(force: bool = False):
        nonlocal last_speaking_state
        if sessionid is None:
            return
        avatar_stream = state.avatar_streams.get(sessionid)
        if avatar_stream is None:
            return
        speaking = bool(avatar_stream.is_speaking())
        if force or last_speaking_state is None or speaking != last_speaking_state:
            last_speaking_state = speaking
            await _send({
                "type": "speaking_state",
                "sessionid": sessionid,
                "speaking": speaking,
            })

    async def _speaking_state_loop(bound_sessionid: int):
        try:
            while not ws.closed and sessionid == bound_sessionid:
                await _send_speaking_state()
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass

    async def _handle_offer(data: dict):
        nonlocal pc, sessionid, speaking_task, last_speaking_state, session_access_token, session_llm_session_id

        sdp = data.get("sdp")
        if not sdp:
            await _send({"type": "error", "error": "missing sdp"})
            return

        if pc is not None:
            # Re-negotiate: tear down the previous session first
            await _cleanup("re-negotiate")

        message_access_token = data.get("access_token")
        if message_access_token:
            session_access_token = message_access_token
        offer_core_sid = core_llm_session_id_from_request_payload(data)
        if offer_core_sid:
            session_llm_session_id = offer_core_sid
            logger.info("ws_signaling: offer Core session_id=%s", session_llm_session_id)
        result, new_pc = await handle_offer(sdp, "offer", data.get("avatar_id"), session_access_token)
        sessionid = result["sessionid"]
        pc = new_pc
        last_speaking_state = None

        await _send({"type": "answer", **result})
        bound_sid = int(result["sessionid"])
        av_for_end = state.avatar_streams.get(bound_sid)
        if av_for_end is not None:
            loop = asyncio.get_running_loop()

            async def _send_chat_end(rid: str):
                await _send({"type": "chat.end", "request_id": rid, "sessionid": bound_sid})

            def _emit_chat_voice_end(request_id: str) -> None:
                fut = asyncio.run_coroutine_threadsafe(_send_chat_end(request_id), loop)

                def _log_send_err(f):
                    try:
                        f.result()
                    except Exception:
                        logger.exception(
                            "ws_signaling: chat.end failed sessionid=%s request_id=%s",
                            bound_sid,
                            request_id,
                        )

                fut.add_done_callback(_log_send_err)

            av_for_end.set_chat_voice_end_emitter(_emit_chat_voice_end)

        await _send_speaking_state(force=True)
        if speaking_task is not None:
            speaking_task.cancel()
            try:
                await speaking_task
            except asyncio.CancelledError:
                pass
        speaking_task = asyncio.create_task(_speaking_state_loop(sessionid))
        logger.info(
            "ws_signaling: offer handled, sessionid=%s session_id=%s",
            sessionid,
            session_llm_session_id or "(none)",
        )

    async def _handle_candidate(data: dict):
        """Feed a trickle ICE candidate into the peer connection."""
        if pc is None:
            logger.debug("ws_signaling: candidate received before PC ready, dropping")
            return
        candidate_str = data.get("candidate", "")
        sdp_mid = data.get("sdpMid", "")
        sdp_mline_index = data.get("sdpMLineIndex", 0)
        if not candidate_str:
            return
        try:
            from aiortc.sdp import candidate_from_sdp
            candidate = candidate_from_sdp(candidate_str.split("candidate:")[-1])
            candidate.sdpMid = sdp_mid
            candidate.sdpMLineIndex = sdp_mline_index
            await pc.addIceCandidate(candidate)
        except Exception as exc:
            logger.warning("ws_signaling: addIceCandidate failed: %s", exc)

    # ----------------------------------------------------------------
    # Main message loop
    # ----------------------------------------------------------------
    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except (json.JSONDecodeError, TypeError):
                    await _send({"type": "error", "error": "invalid json"})
                    continue

                msg_type = data.get("type")

                if msg_type == "offer":
                    try:
                        await _handle_offer(data)
                    except Exception as e:
                        logger.exception("ws_signaling: offer failed: %s", e)
                        await _send({"type": "error", "error": str(e) or "offer failed"})

                elif msg_type == "candidate":
                    await _handle_candidate(data)

                elif msg_type == "ping":
                    await _send({"type": "pong"})

                elif msg_type == "is_speaking":
                    await _send_speaking_state(force=True)

                elif msg_type == "bye":
                    logger.info("ws_signaling: received bye from %s (session=%s)", peer_addr, sessionid)
                    await _send({"type": "bye"})
                    break

                elif msg_type == "chat.request":
                    # Handle chat/echo over the same WebSocket channel after signaling.
                    request_id = data.get("request_id")
                    try:
                        if data.get("access_token"):
                            session_access_token = data.get("access_token")
                            _av_room = webrtc_avatar_sessionid_from_chat_request(sessionid, data)
                            av = state.avatar_streams.get(_av_room)
                            if av:
                                setattr(av, "internal_access_token", session_access_token)
                        params = {
                            "sessionid": webrtc_avatar_sessionid_from_chat_request(sessionid, data),
                            "text": data.get("text", ""),
                            "type": data.get("message_type", "chat"),
                            "interrupt": bool(data.get("interrupt", True)),
                            "access_token": data.get("access_token") or session_access_token,
                            "request_id": data.get("request_id"),
                        }
                        raw_lang = data.get("lang")
                        if raw_lang is not None and str(raw_lang).strip():
                            params["lang"] = str(raw_lang).strip()
                        msg_core_sid = core_llm_session_id_from_request_payload(data)
                        if msg_core_sid:
                            params["session_id"] = msg_core_sid
                        elif session_llm_session_id:
                            params["session_id"] = session_llm_session_id
                        if params.get("session_id"):
                            logger.info(
                                "ws_signaling: chat.request session_id=%s (webrtc sessionid=%s)",
                                params["session_id"],
                                params.get("sessionid"),
                            )
                        result = await process_human_message(params)
                        await _send({"type": "chat.response", "request_id": request_id, **result})
                    except Exception as e:
                        logger.exception("ws_signaling: human failed: %s", e)
                        await _send({"type": "chat.response", "request_id": request_id, "code": -1, "msg": str(e)})

                elif msg_type == "interrupt_talk":
                    target_session = webrtc_avatar_sessionid_from_chat_request(sessionid, data)
                    avatar_stream = state.avatar_streams.get(target_session)
                    if avatar_stream is None:
                        await _send({"type": "interrupt_response", "code": -1, "msg": f"session {target_session} not found"})
                    else:
                        avatar_stream.flush_talk()
                        await _send({"type": "interrupt_response", "code": 0, "msg": "ok"})

                else:
                    await _send({"type": "error", "error": f"unknown message type: {msg_type!r}"})

            elif msg.type == WSMsgType.PING:
                # aiohttp handles pong automatically with autoping=True; nothing to do.
                pass

            elif msg.type in (WSMsgType.CLOSE, WSMsgType.ERROR):
                break

    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.exception("ws_signaling: unhandled error (session=%s): %s", sessionid, exc)
    finally:
        await _cleanup("connection closed")
        if not ws.closed:
            await ws.close(code=WSCloseCode.OK)
        logger.info("ws_signaling: client disconnected from %s", peer_addr)

    return ws
