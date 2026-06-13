"""音频相关路由"""
import json
from aiohttp import web
import asyncio
import re

from src.llm.env import resolve_llm_base_url_for_session
from src.llm.service import llm_response
from src.llm.transient_network import user_message_asr_http
from src.utils.logging import logger
from src.server.auth.session_access import check_session_access
from src.server.state import state

_ASR_PENDING_TEXT: dict[int, str] = {}
_ASR_SILENCE_STREAK: dict[int, int] = {}
_SENTENCE_END_RE = re.compile(r"[。！？!?….!]$")
_MIN_SILENCE_CHUNKS_TO_FLUSH = 2
_MIN_PENDING_TEXT_LEN_TO_FLUSH = 3


def _extract_bearer_token(authorization_header: str | None) -> str | None:
    if not authorization_header:
        return None
    parts = authorization_header.strip().split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
        return parts[1].strip()
    return None


def _append_asr_text(prev: str, chunk: str) -> str:
    """Append ASR chunk text with minimal spacing rules."""
    if not prev:
        return chunk
    if not chunk:
        return prev
    # Keep English words readable across chunk boundaries.
    if prev[-1].isalnum() and chunk[0].isalnum():
        return f"{prev} {chunk}"
    return f"{prev}{chunk}"


def _asr_llm_lang(client_lang) -> str | None:
    """Locale hint for internal LLM; omit when unknown/auto."""
    if not client_lang:
        return None
    s = str(client_lang).strip()
    if not s or s.lower() == "auto":
        return None
    return s


def _client_lang_to_whisper(client_lang: str) -> str:
    """Map client locale (e.g. zh-CN, en-US, auto) to ASR language code (zh, en, auto)."""
    if not client_lang:
        return "auto"
    lower = client_lang.strip().lower()
    if lower == "auto":
        return "auto"
    if lower.startswith("zh"):
        return "zh"
    if lower.startswith("en"):
        return "en"
    if lower.startswith("ja"):
        return "ja"
    if lower.startswith("ko"):
        return "ko"
    # pass through other ISO 639-1 style codes
    if len(lower) >= 2 and lower[:2].isalpha():
        return lower[:2]
    return "auto"


async def humanaudio(request):
    """处理音频文件上传"""
    try:
        form = await request.post()
        sessionid = int(form.get('sessionid', 0))
        access_token = form.get("access_token") or _extract_bearer_token(request.headers.get("Authorization"))
        avatar_stream = state.avatar_streams.get(sessionid)
        if avatar_stream is None:
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": f"sessionid {sessionid} not found"}),
                status=404,
            )
        access_token = access_token or getattr(avatar_stream, "internal_access_token", None)
        access_err = check_session_access(sessionid, access_token, action="humanaudio")
        if access_err:
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": access_err}),
                status=403,
            )
        fileobj = form["file"]
        filename = fileobj.filename
        filebytes = fileobj.file.read()
        avatar_stream.put_audio_file(filebytes)

        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": 0, "msg": "ok"}
            ),
        )
    except Exception as e:
        logger.exception('exception:')
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": -1, "msg": str(e)}
            ),
        )


async def asr(request):
    """ASR 语音识别接口：将音频转换为文本，然后调用 LLM 进行对话"""
    try:
        asr_cfg = state.config.asr if state.config else None
        asr_mode = str(getattr(asr_cfg, "mode", "browser")).lower()
        if asr_mode == "browser":
            logger.warning("[ASR] POST /asr rejected: asr.mode=browser (use client-side ASR)")
            return web.Response(
                content_type="application/json",
                text=json.dumps(
                    {"code": -1, "msg": "server ASR disabled (asr.mode=browser); use client speech recognition"}
                ),
                status=501,
            )

        form = await request.post()
        sessionid = int(form.get('sessionid', 0))
        access_token = form.get("access_token") or _extract_bearer_token(request.headers.get("Authorization"))
        avatar_stream = state.avatar_streams.get(sessionid)
        if avatar_stream is not None:
            access_token = access_token or getattr(avatar_stream, "internal_access_token", None)
        access_err = check_session_access(sessionid, access_token, action="asr")
        if access_err:
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": access_err}),
                status=403,
            )
        fileobj = form["file"]
        filebytes = fileobj.file.read()
        # Optional: client sends recognition language (e.g. zh-CN, en-US) so server uses it
        client_lang = form.get("language") or form.get("lang")
        if isinstance(client_lang, bytes):
            client_lang = client_lang.decode("utf-8", errors="replace")
        llm_lang = _asr_llm_lang(client_lang)

        # ASR/LLM 调用在同一流程中，失败时返回可读错误
        from src.asr import get_asr_engine
        
        try:
            asr_config = state.config.asr if state.config else None
            
            asr_engine = get_asr_engine(
                config=state.config,
                asr_type=asr_config.type if asr_config else "sensevoice",
                model_size=asr_config.model_size if asr_config else "base",
                device=asr_config.device if asr_config else "auto",
                model_name=asr_config.model_name if asr_config and asr_config.model_name else None,
                language=asr_config.language if asr_config else None,
            )
            
            configured_language = asr_config.language if asr_config else "zh"
            configured_type = asr_config.type if asr_config else "sensevoice"
            # For SenseVoice multilingual mode, honor server-side auto detection.
            # This avoids stale client UI language (e.g. zh-CN) forcing recognition.
            if configured_type == "sensevoice" and str(configured_language).lower() == "auto":
                language = "auto"
            elif client_lang and str(client_lang).strip():
                language = _client_lang_to_whisper(str(client_lang).strip())
            else:
                language = configured_language
            asr_engine.set_language(language)
            
            logger.info(f'[ASR] 开始识别音频，sessionid={sessionid}, language={language}')
            loop = asyncio.get_event_loop()

            # --- SileroVAD gate: skip ASR if no speech is detected ---
            vad_config = getattr(asr_config, 'vad', None)
            vad_enabled = getattr(vad_config, 'enabled', True)
            if vad_enabled:
                from src.asr.vad import get_vad_engine
                vad = get_vad_engine(device=asr_config.device if asr_config else "auto")
                threshold = getattr(vad_config, 'threshold', 0.5)
                min_speech_ms = getattr(vad_config, 'min_speech_ms', 250)
                min_silence_ms = getattr(vad_config, 'min_silence_ms', 100)
                speech_pad_ms = getattr(vad_config, 'speech_pad_ms', 30)
                has_speech = await loop.run_in_executor(
                    None, vad.has_speech, filebytes, threshold, min_speech_ms, min_silence_ms, speech_pad_ms
                )
                if not has_speech:
                    pending_text = _ASR_PENDING_TEXT.get(sessionid, "").strip()
                    if not pending_text:
                        _ASR_SILENCE_STREAK[sessionid] = 0
                        logger.info('[VAD] No speech detected — skipping ASR')
                        return web.Response(
                            content_type="application/json",
                            text=json.dumps({"code": 0, "silent": True, "msg": "no speech detected"}),
                        )

                    silence_streak = _ASR_SILENCE_STREAK.get(sessionid, 0) + 1
                    _ASR_SILENCE_STREAK[sessionid] = silence_streak
                    if silence_streak < _MIN_SILENCE_CHUNKS_TO_FLUSH:
                        return web.Response(
                            content_type="application/json",
                            text=json.dumps(
                                {
                                    "code": 0,
                                    "msg": "ok",
                                    "partial": True,
                                    "silent": True,
                                    "silence_streak": silence_streak,
                                    "text": pending_text,
                                }
                            ),
                        )

                    # Drop very short buffered noise instead of sending it to LLM.
                    if len(pending_text) < _MIN_PENDING_TEXT_LEN_TO_FLUSH:
                        logger.info('[ASR] Dropping short buffered text as noise: %r', pending_text)
                        _ASR_PENDING_TEXT[sessionid] = ""
                        _ASR_SILENCE_STREAK[sessionid] = 0
                        return web.Response(
                            content_type="application/json",
                            text=json.dumps({"code": 0, "silent": True, "msg": "noise filtered"}),
                        )

                    # End-of-utterance detected by sustained silence: flush buffered text to LLM.
                    logger.info('[ASR] Sustained silence detected, flushing buffered sentence')
                    llm_config = state.config.llm if state.config else None
                    avatar_stream = state.avatar_streams.get(sessionid)
                    if avatar_stream is None:
                        return web.Response(
                            content_type="application/json",
                            text=json.dumps(
                                {"code": -1, "msg": f"sessionid {sessionid} not found"}
                            ),
                            status=404
                        )

                    fallback_base_url = (
                        llm_config.base_url
                        if llm_config
                        else "https://dashscope.aliyuncs.com/compatible-mode/v1"
                    )
                    llm_text = await loop.run_in_executor(
                        None,
                        llm_response,
                        pending_text,
                        avatar_stream,
                        llm_config.provider if llm_config else "openai",
                        llm_config.api_key if llm_config else None,
                        resolve_llm_base_url_for_session(None, avatar_stream, fallback_base_url),
                        llm_config.model if llm_config else "qwen-plus",
                        access_token,
                        llm_config.character_id if llm_config else None,
                        llm_lang,
                        None,
                    )
                    _ASR_PENDING_TEXT[sessionid] = ""
                    _ASR_SILENCE_STREAK[sessionid] = 0
                    return web.Response(
                        content_type="application/json",
                        text=json.dumps(
                            {"code": 0, "msg": "ok", "text": pending_text, "response": llm_text, "final": True}
                        ),
                    )
                else:
                    _ASR_SILENCE_STREAK[sessionid] = 0
            # -------------------------------------------------------------

            result = await loop.run_in_executor(None, asr_engine.transcribe, filebytes)
            text = result.get("text", "").strip()
            
            if not text:
                return web.Response(
                    content_type="application/json",
                    text=json.dumps(
                        {"code": 0, "msg": "ok", "partial": True, "text": _ASR_PENDING_TEXT.get(sessionid, "").strip()}
                    ),
                )
            
            logger.info(f'[ASR] 识别结果: {text}')

            pending_text = _append_asr_text(_ASR_PENDING_TEXT.get(sessionid, ""), text).strip()
            _ASR_PENDING_TEXT[sessionid] = pending_text
            # If backend VAD is disabled, client-side VAD already segmented utterance.
            # Treat each chunk as final to avoid waiting for punctuation.
            should_finalize = (not vad_enabled) or bool(_SENTENCE_END_RE.search(pending_text))

            if not should_finalize:
                return web.Response(
                    content_type="application/json",
                    text=json.dumps(
                        {"code": 0, "msg": "ok", "partial": True, "text": pending_text}
                    ),
                )

            llm_config = state.config.llm if state.config else None
            logger.info(f'[ASR] LLM 配置: {llm_config}')
            avatar_stream = state.avatar_streams.get(sessionid)
            if avatar_stream is None:
                return web.Response(
                    content_type="application/json",
                    text=json.dumps(
                        {"code": -1, "msg": f"sessionid {sessionid} not found"}
                    ),
                    status=404
                )

            fallback_base_url = (
                llm_config.base_url
                if llm_config
                else "https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
            llm_text = await loop.run_in_executor(
                None,
                llm_response,
                pending_text,
                avatar_stream,
                llm_config.provider if llm_config else "openai",
                llm_config.api_key if llm_config else None,
                resolve_llm_base_url_for_session(None, avatar_stream, fallback_base_url),
                llm_config.model if llm_config else "qwen-plus",
                access_token,
                llm_config.character_id if llm_config else None,
                llm_lang,
                None,
            )
            logger.info(f'[ASR] LLM 回复: {llm_text}')
            _ASR_PENDING_TEXT[sessionid] = ""
            _ASR_SILENCE_STREAK[sessionid] = 0

            return web.Response(
                content_type="application/json",
                text=json.dumps(
                    {"code": 0, "msg": "ok", "text": pending_text, "response": llm_text, "final": True}
                ),
            )
            
        except Exception as e:
            logger.exception("[ASR] 语音识别失败:")
            return web.Response(
                content_type="application/json",
                text=json.dumps(
                    {"code": -1, "msg": user_message_asr_http(e)}
                ),
            )
            
    except Exception as e:
        logger.exception('[ASR] ASR 接口异常:')
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": -1, "msg": str(e)}
            ),
        )
