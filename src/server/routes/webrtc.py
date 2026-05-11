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
from src.config.loader import resolve_avatar_prompt_file, load_avatar_entries
from src.llm.service import remove_session as remove_llm_session
from src.server.routes.chat import process_human_message
from src.server.routes.audio import run_asr_on_audio, _pcm16_to_wav_bytes

# ------------------------------------------------------------------
# WS signaling protocol
# ------------------------------------------------------------------
# Client → Server messages:
#   { "type": "offer",     "sdp": "<sdp>", "avatar_id": <int|null> }
#   { "type": "candidate", "candidate": "<sdpMid>", "sdpMid": "<mid>", "sdpMLineIndex": <int> }
#   { "type": "is_speaking" }   # optional status query on existing WS
#   { "type": "ping" }
#   { "type": "bye" }
#
# Server → Client messages:
#   { "type": "answer",    "sdp": "<sdp>", "sessionid": <int> }
#   { "type": "candidate", "candidate": "<sdpMid>", "sdpMid": "<mid>", "sdpMLineIndex": <int> }
#   { "type": "speaking_state", "sessionid": <int>, "speaking": <bool>, "isEnd": <bool>,
#     "utteranceEnd"?: <bool>, "text"?: <str> }  # utteranceEnd=true: TTS last chunk (status end), not is_speaking()
#   { "type": "pong" }
#   { "type": "error",     "error": "<message>" }
#   { "type": "bye" }
# ------------------------------------------------------------------

_WS_HEARTBEAT_INTERVAL = 25  # seconds between server-initiated pings
_WS_HEARTBEAT_TIMEOUT  = 15  # seconds to wait for pong before closing


async def handle_offer(sdp: str, type_: str, avatar_id=None) -> tuple[dict, RTCPeerConnection]:
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
            avatar_id_int = int(avatar_id)
            entries = load_avatar_entries()
            matched = next((e for e in entries if e.get("id") == avatar_id_int), None)

            if matched:
                # 1. Stamp per-avatar prompt file
                prompt_file = matched.get("prompt_file")
                if prompt_file:
                    session_config.prompt_file = prompt_file
                    logger.info('Using prompt_file=%s for avatar_id=%s', prompt_file, avatar_id)

                # 2. Stamp per-avatar ElevenLabs voice ID (overrides global tts.ref_file)
                eleven_voice = (matched.get("elevenlabs_voice_id") or "").strip()
                if eleven_voice:
                    if getattr(session_config.tts, "type", "") == "elevenlabs":
                        session_config.tts.ref_file = eleven_voice
                        logger.info('Using elevenlabs_voice_id=%s for avatar_id=%s', eleven_voice, avatar_id)
                    else:
                        logger.info(
                            'elevenlabs_voice_id=%s found for avatar_id=%s but tts.type=%s — skipping override',
                            eleven_voice, avatar_id, getattr(session_config.tts, "type", "?")
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
    result, _pc = await handle_offer(
        params["sdp"],
        params["type"],
        params.get("avatar_id"),
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
    # ASR over same WebSocket (like chat)
    asr_config_received: bool = False
    asr_sessionid: int = 0
    asr_client_lang: str | None = None
    asr_sample_rate: int = 16000

    async def _flush_speaking_end_if_needed():
        """If client was last told speaking=true, emit speaking=false + isEnd before teardown or stream loss."""
        nonlocal last_speaking_state
        if ws.closed or sessionid is None or last_speaking_state is not True:
            return
        last_speaking_state = False
        await _send({
            "type": "speaking_state",
            "sessionid": sessionid,
            "speaking": False,
            "isEnd": True,
        })

    async def _cleanup(reason: str = ""):
        nonlocal pc, sessionid, speaking_task
        if reason:
            logger.info("ws_signaling: cleanup — %s (session=%s)", reason, sessionid)
        sid = sessionid
        if sid is not None:
            state.register_signaling_emitter(sid, None)
        await _flush_speaking_end_if_needed()
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
            # Session/PC torn down (e.g. ICE failed) but WS still open — avoid stuck "speaking" on client.
            await _flush_speaking_end_if_needed()
            return
        speaking = bool(avatar_stream.is_speaking())
        prev_sent = last_speaking_state
        if force or last_speaking_state is None or speaking != last_speaking_state:
            last_speaking_state = speaking
            is_end = prev_sent is True and speaking is False
            await _send({
                "type": "speaking_state",
                "sessionid": sessionid,
                "speaking": speaking,
                "isEnd": is_end,
            })

    async def _speaking_state_loop(bound_sessionid: int):
        try:
            while not ws.closed and sessionid == bound_sessionid:
                await _send_speaking_state()
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass

    async def _handle_offer(data: dict):
        nonlocal pc, sessionid, speaking_task, last_speaking_state

        sdp = data.get("sdp")
        if not sdp:
            await _send({"type": "error", "error": "missing sdp"})
            return

        if pc is not None:
            # Re-negotiate: tear down the previous session first
            await _cleanup("re-negotiate")

        result, new_pc = await handle_offer(sdp, "offer", data.get("avatar_id"))
        sessionid = result["sessionid"]
        pc = new_pc
        last_speaking_state = None

        async def _signaling_emit(payload: dict):
            nonlocal last_speaking_state
            await _send(payload)
            if payload.get("utteranceEnd"):
                last_speaking_state = False

        state.register_signaling_emitter(sessionid, _signaling_emit)

        await _send({"type": "answer", **result})
        await _send_speaking_state(force=True)
        if speaking_task is not None:
            speaking_task.cancel()
            try:
                await speaking_task
            except asyncio.CancelledError:
                pass
        speaking_task = asyncio.create_task(_speaking_state_loop(sessionid))
        logger.info("ws_signaling: offer handled, session=%s", sessionid)

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

                elif msg_type == "human":
                    # Handle chat/echo over the same WebSocket channel after signaling.
                    request_id = data.get("request_id")
                    try:
                        params = {
                            "sessionid": sessionid or data.get("sessionid", 0),
                            "text": data.get("text", ""),
                            "type": data.get("message_type", "chat"),
                            "interrupt": bool(data.get("interrupt", True)),
                        }
                        result = await process_human_message(params)
                        await _send({"type": "human_response", "request_id": request_id, **result})
                    except Exception as e:
                        logger.exception("ws_signaling: human failed: %s", e)
                        await _send({"type": "human_response", "request_id": request_id, "code": -1, "msg": str(e)})

                elif msg_type == "asr_config":
                    asr_config_received = True
                    asr_sessionid = int(data.get("sessionid", 0))
                    asr_client_lang = data.get("language") or data.get("lang") or "auto"
                    asr_sample_rate = int(data.get("sample_rate", 16000)) or 16000
                    await _send({"type": "asr_config_ok", "code": 0, "msg": "config ok"})

                else:
                    await _send({"type": "error", "error": f"unknown message type: {msg_type!r}"})

            elif msg.type == WSMsgType.BINARY:
                if not asr_config_received:
                    await _send({"type": "asr_result", "code": -1, "msg": "send asr_config first"})
                else:
                    pcm_bytes = msg.data
                    if not pcm_bytes:
                        await _send({"type": "asr_result", "code": 0, "msg": "ok", "partial": True, "text": ""})
                    else:
                        try:
                            wav_bytes = _pcm16_to_wav_bytes(pcm_bytes, sample_rate=asr_sample_rate)
                            result = await run_asr_on_audio(wav_bytes, asr_sessionid, asr_client_lang)
                            await _send({"type": "asr_result", **result})
                        except Exception as e:
                            logger.exception("ws_signaling: ASR failed: %s", e)
                            await _send({"type": "asr_result", "code": -1, "msg": str(e)})

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
