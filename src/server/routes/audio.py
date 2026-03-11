"""音频相关路由"""
import json
import struct
from aiohttp import web
import asyncio
import re

from src.llm.service import llm_response
from src.utils.logging import logger
from src.server.state import state


def _pcm16_to_wav_bytes(pcm_bytes: bytes, sample_rate: int = 16000, channels: int = 1) -> bytes:
    """Wrap raw PCM 16-bit mono bytes in a minimal WAV header (44 bytes)."""
    data_size = len(pcm_bytes)
    byte_rate = sample_rate * channels * 2
    block_align = channels * 2
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        16,
        b"data",
        data_size,
    )
    return header + pcm_bytes

_ASR_PENDING_TEXT: dict[int, str] = {}
_ASR_SILENCE_STREAK: dict[int, int] = {}
_SENTENCE_END_RE = re.compile(r"[。！？!?….!]$")
_MIN_SILENCE_CHUNKS_TO_FLUSH = 2
_MIN_PENDING_TEXT_LEN_TO_FLUSH = 3


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


async def run_asr_on_audio(filebytes: bytes, sessionid: int, client_lang: str | None) -> dict:
    """
    Shared ASR logic: VAD + transcribe + optional LLM. Used by HTTP /asr and by /ws (ASR over same WebSocket as signaling/chat).
    Returns a dict suitable for JSON response: code, msg, optional text, response, partial, final, silent.
    """
    from src.asr import get_asr_engine

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
    if configured_type == "sensevoice" and str(configured_language).lower() == "auto":
        language = "auto"
    elif client_lang and str(client_lang).strip():
        language = _client_lang_to_whisper(str(client_lang).strip())
    else:
        language = configured_language
    asr_engine.set_language(language)

    vad_config = getattr(asr_config, "vad", None)
    vad_enabled = getattr(vad_config, "enabled", True)
    if vad_enabled:
        from src.asr.vad import get_vad_engine
        vad = get_vad_engine(device=asr_config.device if asr_config else "auto")
        threshold = getattr(vad_config, "threshold", 0.5)
        min_speech_ms = getattr(vad_config, "min_speech_ms", 250)
        min_silence_ms = getattr(vad_config, "min_silence_ms", 100)
        speech_pad_ms = getattr(vad_config, "speech_pad_ms", 30)
        loop = asyncio.get_event_loop()
        has_speech = await loop.run_in_executor(
            None, vad.has_speech, filebytes, threshold, min_speech_ms, min_silence_ms, speech_pad_ms
        )
        if not has_speech:
            pending_text = _ASR_PENDING_TEXT.get(sessionid, "").strip()
            if not pending_text:
                _ASR_SILENCE_STREAK[sessionid] = 0
                return {"code": 0, "silent": True, "msg": "no speech detected"}
            silence_streak = _ASR_SILENCE_STREAK.get(sessionid, 0) + 1
            _ASR_SILENCE_STREAK[sessionid] = silence_streak
            if silence_streak < _MIN_SILENCE_CHUNKS_TO_FLUSH:
                return {
                    "code": 0, "msg": "ok", "partial": True, "silent": True,
                    "silence_streak": silence_streak, "text": pending_text,
                }
            if len(pending_text) < _MIN_PENDING_TEXT_LEN_TO_FLUSH:
                _ASR_PENDING_TEXT[sessionid] = ""
                _ASR_SILENCE_STREAK[sessionid] = 0
                return {"code": 0, "silent": True, "msg": "noise filtered"}
            llm_config = state.config.llm if state.config else None
            avatar_stream = state.avatar_streams.get(sessionid)
            if avatar_stream is None:
                return {"code": -1, "msg": f"sessionid {sessionid} not found"}
            llm_text = await loop.run_in_executor(
                None,
                llm_response,
                pending_text,
                avatar_stream,
                llm_config.api_key if llm_config else None,
                llm_config.base_url if llm_config else "https://dashscope.aliyuncs.com/compatible-mode/v1",
                llm_config.model if llm_config else "qwen-plus",
            )
            _ASR_PENDING_TEXT[sessionid] = ""
            _ASR_SILENCE_STREAK[sessionid] = 0
            return {"code": 0, "msg": "ok", "text": pending_text, "response": llm_text, "final": True}
        _ASR_SILENCE_STREAK[sessionid] = 0

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, asr_engine.transcribe, filebytes)
    text = result.get("text", "").strip()
    if not text:
        return {
            "code": 0, "msg": "ok", "partial": True,
            "text": _ASR_PENDING_TEXT.get(sessionid, "").strip(),
        }
    pending_text = _append_asr_text(_ASR_PENDING_TEXT.get(sessionid, ""), text).strip()
    _ASR_PENDING_TEXT[sessionid] = pending_text
    should_finalize = (not vad_enabled) or bool(_SENTENCE_END_RE.search(pending_text))
    if not should_finalize:
        return {"code": 0, "msg": "ok", "partial": True, "text": pending_text}
    llm_config = state.config.llm if state.config else None
    avatar_stream = state.avatar_streams.get(sessionid)
    if avatar_stream is None:
        return {"code": -1, "msg": f"sessionid {sessionid} not found"}
    llm_text = await loop.run_in_executor(
        None,
        llm_response,
        pending_text,
        avatar_stream,
        llm_config.api_key if llm_config else None,
        llm_config.base_url if llm_config else "https://dashscope.aliyuncs.com/compatible-mode/v1",
        llm_config.model if llm_config else "qwen-plus",
    )
    _ASR_PENDING_TEXT[sessionid] = ""
    _ASR_SILENCE_STREAK[sessionid] = 0
    return {"code": 0, "msg": "ok", "text": pending_text, "response": llm_text, "final": True}


async def humanaudio(request):
    """处理音频文件上传"""
    try:
        form = await request.post()
        sessionid = int(form.get('sessionid', 0))
        fileobj = form["file"]
        filename = fileobj.filename
        filebytes = fileobj.file.read()
        state.avatar_streams[sessionid].put_audio_file(filebytes)

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
    """ASR 语音识别接口（HTTP）：将音频转换为文本，然后调用 LLM 进行对话"""
    try:
        form = await request.post()
        sessionid = int(form.get("sessionid", 0))
        fileobj = form["file"]
        filebytes = fileobj.file.read()
        client_lang = form.get("language") or form.get("lang")
        if isinstance(client_lang, bytes):
            client_lang = client_lang.decode("utf-8", errors="replace")

        logger.info(f"[ASR] 开始识别音频，sessionid={sessionid}, language={client_lang or 'default'}")
        try:
            result = await run_asr_on_audio(filebytes, sessionid, client_lang)
            status = 404 if result.get("code") == -1 and "not found" in result.get("msg", "") else 200
            return web.Response(
                content_type="application/json",
                text=json.dumps(result),
                status=status,
            )
        except Exception as e:
            logger.exception("[ASR] 语音识别失败:")
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": f"语音识别失败: {str(e)}"}),
            )
    except Exception as e:
        logger.exception("[ASR] ASR 接口异常:")
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": -1, "msg": str(e)}),
        )
