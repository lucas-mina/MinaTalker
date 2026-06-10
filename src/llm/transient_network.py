"""Classify transient DNS / TCP connect failures (e.g. Windows [Errno 11001] getaddrinfo failed)."""

from __future__ import annotations

import errno
import socket
from urllib.error import URLError

_OPENAI_CONNECT_TYPES: tuple[type, ...] = ()
try:
    from openai import APIConnectionError

    _OPENAI_CONNECT_TYPES = _OPENAI_CONNECT_TYPES + (APIConnectionError,)
except ImportError:
    pass
try:
    from openai import APITimeoutError

    _OPENAI_CONNECT_TYPES = _OPENAI_CONNECT_TYPES + (APITimeoutError,)
except ImportError:
    pass


# Shown to HTTP clients when the failure was transient (avoid raw errno / getaddrinfo in UI).
USER_MESSAGE_TRANSIENT_LLM = "Assistant is temporarily unavailable. Please try again."
USER_MESSAGE_TRANSIENT_LLM_ZH = "助手暂不可用，请稍后再试。"


def _exception_chain(exc: BaseException) -> list[BaseException]:
    out: list[BaseException] = []
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        out.append(cur)
        nxt = cur.__cause__ or cur.__context__
        cur = nxt if isinstance(nxt, BaseException) else None
    return out


def _transient_errno(en: int) -> bool:
    eai_again = getattr(errno, "EAI_AGAIN", None)
    if eai_again is not None and en == eai_again:
        return True
    for name in ("WSAHOST_NOT_FOUND", "WSATRY_AGAIN", "WSANO_DATA"):
        v = getattr(errno, name, None)
        if v is not None and en == v:
            return True
    if en in (11001, 11002):
        return True
    return False


def is_transient_llm_network_error(exc: BaseException) -> bool:
    """True for flaky DNS / transport before a stable HTTP response (safe to retry same request)."""
    if _OPENAI_CONNECT_TYPES and isinstance(exc, _OPENAI_CONNECT_TYPES):
        return True
    if isinstance(exc, (TimeoutError, ConnectionError, socket.timeout)):
        return True
    if isinstance(exc, URLError):
        r = exc.reason
        if isinstance(r, BaseException):
            return is_transient_llm_network_error(r)
        return False

    for part in _exception_chain(exc):
        if isinstance(part, URLError):
            r = part.reason
            if isinstance(r, BaseException) and is_transient_llm_network_error(r):
                return True
            continue
        if isinstance(part, OSError):
            if part.errno is not None and _transient_errno(part.errno):
                return True
            if isinstance(part, socket.gaierror):
                if part.errno is not None and _transient_errno(part.errno):
                    return True
                low = str(part).lower()
                if "getaddrinfo" in low and ("11001" in low or "11002" in low):
                    return True
    return False


def user_message_chat_http(exc: BaseException) -> str:
    """JSON ``msg`` for /human: generic text for transient LLM transport, else the error string."""
    if is_transient_llm_network_error(exc):
        return USER_MESSAGE_TRANSIENT_LLM
    return str(exc)


def user_message_asr_http(exc: BaseException) -> str:
    """JSON ``msg`` for ASR+LLM failures (Chinese wrapper)."""
    if is_transient_llm_network_error(exc):
        return f"语音识别失败：{USER_MESSAGE_TRANSIENT_LLM_ZH}"
    return f"语音识别失败: {exc}"
