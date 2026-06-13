"""Internal API LLM engine — WebSocket `/ws/chat` (streaming) or HTTP `/api/agent/chat` (legacy)."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator, Generator, Optional
from urllib import error, request
from urllib.parse import urlparse, urlunparse

import websockets
from websockets.exceptions import WebSocketException

from src.llm.base import BaseLLM
from src.llm.transient_network import is_transient_llm_network_error
from src.utils.logging import logger

_LLM_CONNECT_RETRIES = 3
_LLM_CONNECT_BACKOFF_SEC = (0.5, 1.5)


class InternalLLM(BaseLLM):
    """Core internal LLM: default WebSocket ``/ws/chat`` (Bearer + ``chat`` / ``chat.chunk`` / ``chat.done``)."""

    def __init__(
        self,
        config=None,
        parent=None,
        api_key: Optional[str] = None,
        base_url: str = "http://127.0.0.1:82",
        model: str = "grok-4-1",
        max_history: int = 10,
        character_id: Optional[str] = None,
    ):
        super().__init__(config, parent)
        self.api_key = api_key
        self.base_url = self._normalize_base_url(base_url)
        self.model = model
        self.max_history = max_history
        self.character_id = character_id
        self.conversation_history = []

        llm_cfg = getattr(config, "llm", None) if config else None
        self.transport = (getattr(llm_cfg, "internal_transport", None) or "websocket").strip().lower()
        self.ws_path = (getattr(llm_cfg, "internal_ws_path", None) or "/ws/chat").strip() or "/ws/chat"
        # Core thread id returned on chat.done — sent as session_id on subsequent turns
        self._remote_session_id: Optional[str] = None

        logger.info(
            "Internal LLM initialized: transport=%s model=%s base_url=%s ws_path=%s character_id=%s",
            self.transport,
            self.model,
            self.base_url,
            self.ws_path,
            self.character_id,
        )

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        clean = (base_url or "").strip().rstrip("/")
        if clean.endswith("/api-docs"):
            clean = clean[: -len("/api-docs")]
        return clean

    def add_to_history(self, role: str, content: str):
        self.conversation_history.append({"role": role, "content": content})
        if len(self.conversation_history) > self.max_history * 2:
            self.conversation_history = self.conversation_history[-self.max_history * 2 :]

    def clear_history(self):
        self.conversation_history = []
        self._remote_session_id = None
        logger.info("Internal LLM conversation history cleared")

    def _ws_uri(self) -> str:
        u = urlparse(self.base_url)
        scheme = "wss" if u.scheme == "https" else "ws"
        path = self.ws_path if self.ws_path.startswith("/") else f"/{self.ws_path}"
        return urlunparse((scheme, u.netloc, path, "", "", ""))

    @staticmethod
    def _event_name(obj: dict[str, Any]) -> str:
        ev = obj.get("event") or obj.get("type") or ""
        return str(ev).strip() if isinstance(ev, str) else ""

    @staticmethod
    def _extract_stream_text(obj: dict[str, Any]) -> str:
        """OpenAI-compatible chunk: choices[0].delta.content, or flat content/text."""
        ch = obj.get("choices")
        if isinstance(ch, list) and ch and isinstance(ch[0], dict):
            delta = ch[0].get("delta")
            if isinstance(delta, dict):
                c = delta.get("content")
                if isinstance(c, str):
                    return c
        for k in ("content", "text", "token"):
            v = obj.get(k)
            if isinstance(v, str) and v:
                return v
        nested = obj.get("data")
        if isinstance(nested, dict):
            return InternalLLM._extract_stream_text(nested)
        return ""

    def _build_outgoing_chat(
        self,
        user_message: str,
        lang: Optional[str] = None,
        client_session_id: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> dict[str, Any]:
        # Core expects envelope { "event": "...", "data": { ... } } (same shape as error responses).
        data: dict[str, Any] = {
            "character_id": self.character_id,
            "message": user_message,
            "model": self.model,
        }
        if timestamp and str(timestamp).strip():
            data["timestamp"] = str(timestamp).strip()
        if lang and str(lang).strip():
            data["lang"] = str(lang).strip()
        if client_session_id and str(client_session_id).strip():
            data["session_id"] = str(client_session_id).strip()
        elif self._remote_session_id:
            data["session_id"] = self._remote_session_id
        else:
            data["session_create"] = True
        logger.info(
            "Internal outgoing chat: session_id=%s session_create=%s",
            data.get("session_id"),
            bool(data.get("session_create")),
        )
        return {"event": "chat", "data": data}

    async def _ws_chat_chunks(
        self,
        user_message: str,
        lang: Optional[str] = None,
        client_session_id: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> AsyncIterator[str]:
        if not self.character_id or not str(self.character_id).strip():
            raise RuntimeError("internal LLM WebSocket requires llm.character_id (catalog id)")
        uri = self._ws_uri()
        headers: list[tuple[str, str]] = []
        if self.api_key:
            headers.append(("Authorization", f"Bearer {self.api_key}"))

        effective_sid = (
            (client_session_id and str(client_session_id).strip())
            or self._remote_session_id
            or "(new)"
        )
        logger.info(
            "Internal WS %s character_id=%s model=%s session_id=%s bearer=%s",
            uri,
            self.character_id,
            self.model,
            effective_sid,
            "yes" if self.api_key else "no",
        )

        outgoing = self._build_outgoing_chat(
            user_message,
            lang=lang,
            client_session_id=client_session_id,
            timestamp=timestamp,
        )
        host = urlparse(self.base_url).hostname or self.base_url
        for attempt in range(_LLM_CONNECT_RETRIES):
            sent = False
            try:
                async with websockets.connect(
                    uri,
                    additional_headers=headers,
                    max_size=None,
                    open_timeout=30,
                    ping_interval=20,
                    ping_timeout=60,
                ) as ws:
                    await ws.send(json.dumps(outgoing))
                    sent = True
                    async for raw in ws:
                        if isinstance(raw, bytes):
                            raw = raw.decode("utf-8", errors="replace")
                        if not raw or not str(raw).strip():
                            continue
                        try:
                            obj = json.loads(raw)
                        except json.JSONDecodeError:
                            logger.debug("Internal WS non-JSON frame: %s", raw[:200])
                            continue
                        if not isinstance(obj, dict):
                            continue

                        ev = self._event_name(obj)
                        low = ev.lower()

                        if "error" in low or ev == "error":
                            inner = obj.get("data") if isinstance(obj.get("data"), dict) else {}
                            msg = (
                                inner.get("message")
                                or obj.get("message")
                                or obj.get("detail")
                                or obj.get("error")
                                or str(obj)
                            )
                            raise RuntimeError(f"Internal WS error: {msg}")

                        if "chunk" in low or low.endswith(".chunk"):
                            piece = self._extract_stream_text(obj)
                            if not piece and isinstance(obj.get("data"), dict):
                                piece = self._extract_stream_text(obj["data"])
                            if piece:
                                yield piece
                            continue

                        if low == "chat.done" or low.endswith(".done") and "chat" in low:
                            done_inner = obj.get("data") if isinstance(obj.get("data"), dict) else {}
                            sid = done_inner.get("session_id") or obj.get("session_id")
                            if sid is not None and str(sid).strip():
                                self._remote_session_id = str(sid).strip()
                            logger.info("Internal WS chat.done session_id=%s", self._remote_session_id)
                            break

                        # token.update, build-prompt.result — ignore for chat stream
                        if low.startswith("token.") or "build-prompt" in low:
                            continue

                        # Some servers send bare delta objects without event
                        if not ev:
                            piece = self._extract_stream_text(obj)
                            if piece:
                                yield piece
                break
            except (WebSocketException, OSError) as exc:
                if sent or not is_transient_llm_network_error(exc):
                    raise RuntimeError(f"Internal WebSocket failed: {exc}") from exc
                if attempt >= _LLM_CONNECT_RETRIES - 1:
                    raise RuntimeError(f"Internal WebSocket failed: {exc}") from exc
                delay = _LLM_CONNECT_BACKOFF_SEC[
                    min(attempt, len(_LLM_CONNECT_BACKOFF_SEC) - 1)
                ]
                logger.warning(
                    "Internal WS DNS/connect failed (attempt %d/%d) host=%s uri=%s: %r; retrying in %.1fs",
                    attempt + 1,
                    _LLM_CONNECT_RETRIES,
                    host,
                    uri,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

    def _chat_once_http(
        self,
        messages: list[dict],
        lang: Optional[str] = None,
        client_session_id: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> str:
        payload = {"messages": messages, "model": self.model}
        if self.character_id:
            payload["character_id"] = self.character_id
        if timestamp and str(timestamp).strip():
            payload["timestamp"] = str(timestamp).strip()
        if lang and str(lang).strip():
            payload["lang"] = str(lang).strip()
        if client_session_id and str(client_session_id).strip():
            payload["session_id"] = str(client_session_id).strip()
        body = json.dumps(payload).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        logger.info(
            "Internal API POST %s/api/agent/chat model=%s character_id=%s messages=%d authorization=%s",
            self.base_url,
            self.model,
            self.character_id,
            len(messages),
            "Bearer" if self.api_key else "none",
        )

        req = request.Request(
            url=f"{self.base_url}/api/agent/chat",
            data=body,
            headers=headers,
            method="POST",
        )

        host = urlparse(self.base_url).hostname or self.base_url
        raw: str | None = None
        for attempt in range(_LLM_CONNECT_RETRIES):
            try:
                with request.urlopen(req, timeout=120) as resp:
                    raw = resp.read().decode("utf-8")
                break
            except error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"Internal API HTTP {exc.code}: {detail}") from exc
            except error.URLError as exc:
                if not is_transient_llm_network_error(exc) or attempt >= _LLM_CONNECT_RETRIES - 1:
                    raise RuntimeError(f"Internal API unreachable: {exc}") from exc
                delay = _LLM_CONNECT_BACKOFF_SEC[
                    min(attempt, len(_LLM_CONNECT_BACKOFF_SEC) - 1)
                ]
                logger.warning(
                    "Internal API DNS/connect failed (attempt %d/%d) host=%s: %r; retrying in %.1fs",
                    attempt + 1,
                    _LLM_CONNECT_RETRIES,
                    host,
                    exc,
                    delay,
                )
                time.sleep(delay)

        if raw is None:
            raise RuntimeError("Internal API unreachable after retries")

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Internal API non-JSON response: {raw[:200]}") from exc

        reply = parsed.get("reply") or parsed.get("response") or parsed.get("content")
        if not isinstance(reply, str) or not reply.strip():
            raise RuntimeError(f"Internal API missing reply field: {parsed}")

        return reply

    def _run_ws_stream_sync(
        self,
        user_message: str,
        lang: Optional[str] = None,
        client_session_id: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """Bridge async WS stream to sync generator (llm runs in thread pool; no running loop)."""

        async def collect() -> AsyncIterator[str]:
            async for chunk in self._ws_chat_chunks(
                user_message,
                lang=lang,
                client_session_id=client_session_id,
                timestamp=timestamp,
            ):
                yield chunk

        loop = asyncio.new_event_loop()
        ait = None
        try:
            asyncio.set_event_loop(loop)
            ait = collect().__aiter__()
            while True:
                try:
                    chunk = loop.run_until_complete(ait.__anext__())
                    yield chunk
                except StopAsyncIteration:
                    break
        finally:
            if ait is not None:
                try:
                    loop.run_until_complete(ait.aclose())
                except Exception:
                    pass
            loop.close()
            asyncio.set_event_loop(None)

    def chat_stream(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        lang: Optional[str] = None,
        session_id: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> Generator[str, None, None]:
        start_time = time.perf_counter()
        system_prompt = system_prompt or self.system_prompt

        self.add_to_history("user", message)

        if self.transport == "http":
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(self.conversation_history)
            logger.info("Internal HTTP sending %d messages", len(messages))
            reply = self._chat_once_http(
                messages, lang=lang, client_session_id=session_id, timestamp=timestamp
            )
            self.add_to_history("assistant", reply)
            logger.info("Internal HTTP response time: %.3fs", time.perf_counter() - start_time)
            yield reply
            return

        # WebSocket: core owns multi-turn context via session_id; we only send the latest user line.
        pieces: list[str] = []
        for chunk in self._run_ws_stream_sync(
            message, lang=lang, client_session_id=session_id, timestamp=timestamp
        ):
            pieces.append(chunk)
            yield chunk

        full = "".join(pieces)
        if not full.strip():
            raise RuntimeError("Internal WebSocket returned no assistant text (check chat.chunk format)")
        self.add_to_history("assistant", full)
        logger.info("Internal WS total time: %.3fs chars=%d", time.perf_counter() - start_time, len(full))
