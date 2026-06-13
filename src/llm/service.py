"""LLM 服务模块"""

from typing import Optional

from src.avatars.base import BaseAvatar
from src.llm.env import normalize_llm_base_url
from src.llm.factory import create_llm_engine
from src.llm.transient_network import is_transient_llm_network_error
from src.utils.logging import logger
import os

_session_llm_instances = {}


def llm_response(
    message: str,
    avatar_stream: BaseAvatar,
    provider: str = "openai",
    api_key: str = os.getenv("DASHSCOPE_API_KEY"),
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model: str = "qwen-plus",
    access_token: str | None = None,
    character_id: str | None = None,
    lang: str | None = None,
    session_id: str | None = None,
    voice_request_id: str | None = None,
    timestamp: str | None = None,
) -> str:
    """调用 LLM 并将响应流式推送到 avatar"""
    try:
        base_url = normalize_llm_base_url(base_url)
        config = getattr(avatar_stream, 'config', None)
        sessionid = getattr(avatar_stream, 'sessionid', 0)

        # Per-session llm.character_id (set at WebRTC offer from avatar_config id) wins over
        # the duplicate passed from state.config — chat/ASR only read global state today.
        session_llm = getattr(config, "llm", None) if config else None
        scid = getattr(session_llm, "character_id", None) if session_llm else None
        if scid is not None and str(scid).strip():
            resolved_character_id = str(scid).strip()
        elif character_id is not None and str(character_id).strip():
            resolved_character_id = str(character_id).strip()
        else:
            resolved_character_id = None
        
        # 为每个 session+provider 维护独立实例(保留对话历史)
        session_key = f"{sessionid}:{provider.lower()}"

        normalized_provider = (provider or "openai").lower()
        resolved_api_key = access_token if normalized_provider == "internal" and access_token else api_key

        if session_key not in _session_llm_instances:
            logger.info(f"Creating new LLM instance for session {sessionid} provider {provider}")
            _session_llm_instances[session_key] = create_llm_engine(
                llm_type=provider,
                config=config,
                parent=avatar_stream,
                api_key=resolved_api_key,
                base_url=base_url,
                model=model,
                max_history=10,  # 保留最近10轮对话
                character_id=resolved_character_id,
            )
        elif normalized_provider == "internal":
            llm = _session_llm_instances[session_key]
            current_character_id = getattr(llm, "character_id", None)
            current_base_url = getattr(llm, "base_url", None)
            if current_character_id != resolved_character_id:
                logger.info("Refreshing internal LLM for session %s (character_id changed)", sessionid)
                _session_llm_instances[session_key] = create_llm_engine(
                    llm_type=provider,
                    config=config,
                    parent=avatar_stream,
                    api_key=resolved_api_key,
                    base_url=base_url,
                    model=model,
                    max_history=10,
                    character_id=resolved_character_id,
                )
            elif current_base_url != base_url:
                logger.info(
                    "Refreshing internal LLM for session %s (base_url changed %s → %s)",
                    sessionid,
                    current_base_url,
                    base_url,
                )
                _session_llm_instances[session_key] = create_llm_engine(
                    llm_type=provider,
                    config=config,
                    parent=avatar_stream,
                    api_key=resolved_api_key,
                    base_url=base_url,
                    model=model,
                    max_history=10,
                    character_id=resolved_character_id,
                )
            elif resolved_api_key:
                # New JWT each chat; do not recreate (keeps InternalLLM._remote_session_id).
                llm.api_key = resolved_api_key

        llm = _session_llm_instances[session_key]
        if session_id and str(session_id).strip():
            logger.info("[LLM] session_id=%s session=%s provider=%s", str(session_id).strip(), sessionid, provider)

        last_exc: Exception | None = None
        for svc_attempt in range(2):
            try:
                return llm.generate_response(
                    message,
                    avatar_stream,
                    lang=lang,
                    session_id=session_id,
                    voice_request_id=voice_request_id,
                    timestamp=timestamp,
                )
            except Exception as e:
                last_exc = e
                if svc_attempt == 0 and is_transient_llm_network_error(e):
                    logger.warning(
                        "LLM generate_response failed (transient), service-level retry once: %r",
                        e,
                    )
                    continue
                logger.error("Error in llm_response: %s", e)
                raise
        assert last_exc is not None
        logger.error("Error in llm_response after service retry: %s", last_exc)
        raise last_exc

    except Exception as e:
        logger.error("Error in llm_response (outer): %s", e)
        raise


def clear_session_history(sessionid: int):
    """清空指定会话的对话历史"""
    matched = [k for k in _session_llm_instances.keys() if str(k).startswith(f"{sessionid}:")]
    for key in matched:
        _session_llm_instances[key].clear_history()
    if matched:
        logger.info(f"Cleared history for session {sessionid} ({len(matched)} providers)")


def remove_session(sessionid: int):
    """删除指定会话的 LLM 实例"""
    matched = [k for k in list(_session_llm_instances.keys()) if str(k).startswith(f"{sessionid}:")]
    for key in matched:
        del _session_llm_instances[key]
    if matched:
        logger.info(f"Removed LLM instances for session {sessionid} ({len(matched)} providers)")


__all__ = ["llm_response", "clear_session_history", "remove_session"]
