from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import re
import threading
import time
from typing import AsyncIterator, Iterator, Optional
from urllib.parse import urlparse

import numpy as np
import requests
import websockets
from websockets.exceptions import WebSocketException

from src.tts.base import BaseTTS, State
from src.utils.logging import logger

_HTTP_STREAM_URL = "https://api.minimax.io/v1/t2a_v2"
_DEFAULT_API_BASE = "https://api.minimax.io"
_DEFAULT_MODEL = "speech-02-turbo"
_MAX_TEXT_CHARS = 10000
_BRACKET_TAG_RE = re.compile(r"\[[^\]]*\]")


def _tts_text_without_bracket_tags(raw: str) -> str:
    """Strip ElevenLabs-style [emotion] tags MiniMax would read literally."""
    text = _BRACKET_TAG_RE.sub(" ", raw.strip())
    return re.sub(r"\s+", " ", text).strip()


def _hex_to_bytes(hex_str: str) -> bytes:
    if len(hex_str) % 2:
        raise ValueError("minimax: odd-length audio hex")
    return bytes.fromhex(hex_str)


def _throw_if_task_failed(message: dict) -> None:
    event = message.get("event")
    if event == "task_failed":
        base_resp = message.get("base_resp") or {}
        raise RuntimeError(
            f"MiniMax TTS task_failed: {base_resp.get('status_msg', 'task_failed')}"
        )
    base_resp = message.get("base_resp")
    if isinstance(base_resp, dict):
        status_code = base_resp.get("status_code", 0)
        if status_code not in (0, None):
            raise RuntimeError(
                f"MiniMax TTS error: {base_resp.get('status_msg')} (code {status_code})"
            )


def _parse_ws_message(raw: str | bytes) -> dict:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    message = json.loads(raw)
    if not isinstance(message, dict):
        raise ValueError("minimax: expected JSON object from WebSocket")
    return message


class MiniMaxWsSession:
    """One MiniMax T2A WebSocket session per agent reply (minamina-app parity).

    Sequential task_continue per sentence. On read/synth failure the socket is
    torn down (invalidate) so the next synthesize opens a fresh connection.
    """

    def __init__(
        self,
        *,
        api_key: str,
        voice_id: str,
        model_id: str,
        sample_rate: int,
        speed: float,
        language_boost: str,
        ws_uri: str,
    ):
        self._api_key = api_key
        self._voice_id = voice_id
        self._model_id = model_id
        self._sample_rate = sample_rate
        self._speed = speed
        self._language_boost = language_boost
        self._ws_uri = ws_uri
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._closed = False
        self._invalidated = False
        self._task_started = False
        self._open_lock = asyncio.Lock()
        self._synth_lock = asyncio.Lock()

    @property
    def is_closed(self) -> bool:
        return self._closed

    async def open(self) -> None:
        if self._closed:
            raise RuntimeError("MiniMax TTS session closed")
        if self._invalidated:
            self._invalidated = False
            await self._tear_down_socket(send_task_finish=False)
        if self._ws is not None and self._task_started:
            return
        async with self._open_lock:
            if self._ws is not None and self._task_started:
                return
            await self._connect_and_start_task()

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        if self._closed:
            raise RuntimeError("MiniMax TTS session closed")
        payload_text = _tts_text_without_bracket_tags(text)
        if not payload_text:
            raise ValueError("minimax: empty text after tag strip")
        if len(payload_text) > _MAX_TEXT_CHARS:
            payload_text = payload_text[:_MAX_TEXT_CHARS]
            logger.warning("minimax: text truncated to %d chars", _MAX_TEXT_CHARS)

        async with self._synth_lock:
            await self.open()
            ws = self._ws
            if ws is None:
                raise RuntimeError("MiniMax TTS session not open")

            await ws.send(
                json.dumps({"event": "task_continue", "text": payload_text})
            )
            try:
                while not self._closed and self._ws is not None:
                    message = _parse_ws_message(await ws.recv())
                    _throw_if_task_failed(message)
                    data = message.get("data") or {}
                    audio_hex = data.get("audio")
                    if audio_hex:
                        yield _hex_to_bytes(audio_hex)
                    if message.get("is_final") is True:
                        break
            except Exception:
                await self.invalidate()
                raise

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._task_started = False
        await self._tear_down_socket(send_task_finish=True)

    async def invalidate(self) -> None:
        if self._closed:
            return
        self._invalidated = True
        self._task_started = False
        await self._tear_down_socket(send_task_finish=False)

    async def _tear_down_socket(self, *, send_task_finish: bool) -> None:
        ws = self._ws
        self._ws = None
        if ws is None:
            return
        if send_task_finish:
            try:
                await ws.send(json.dumps({"event": "task_finish"}))
            except WebSocketException:
                logger.warning("minimax: task_finish send failed during teardown")
        try:
            await ws.close()
        except WebSocketException:
            logger.warning("minimax: WebSocket close failed during teardown")

    async def _connect_and_start_task(self) -> None:
        try:
            ws = await websockets.connect(
                self._ws_uri,
                additional_headers={"Authorization": f"Bearer {self._api_key}"},
                ping_interval=None,
            )
            self._ws = ws

            message = _parse_ws_message(await ws.recv())
            if message.get("event") != "connected_success":
                _throw_if_task_failed(message)
                raise RuntimeError(
                    f"MiniMax TTS: expected connected_success, got {message.get('event')}"
                )

            task_start: dict = {
                "event": "task_start",
                "model": self._model_id,
                "voice_setting": {
                    "voice_id": self._voice_id,
                    "speed": self._speed,
                    "vol": 1,
                    "pitch": 0,
                    "english_normalization": False,
                },
                "audio_setting": {
                    "sample_rate": self._sample_rate,
                    "bitrate": 128000,
                    "format": "pcm",
                    "channel": 1,
                },
            }
            if self._language_boost and self._language_boost != "auto":
                task_start["language_boost"] = self._language_boost
            await ws.send(json.dumps(task_start))

            while True:
                message = _parse_ws_message(await ws.recv())
                _throw_if_task_failed(message)
                if message.get("event") == "task_started":
                    self._task_started = True
                    break
        except Exception:
            await self.invalidate()
            raise


class MiniMaxTTS(BaseTTS):
    """MiniMax streaming TTS — WebSocket (default) or HTTP t2a_v2.

    WebSocket mirrors minamina-app: one WS per reply, task_continue per sentence.
    Config:
        tts.ref_file            – MiniMax voice ID (required)
        tts.minimax_api_key     – API key (or MINIMAX_API_KEY env)
        tts.minimax_transport   – websocket | http (default websocket)
        tts.minimax_base_url    – API host, default https://api.minimax.io
        tts.model               – model id, default speech-02-turbo
        tts.speed               – speech speed multiplier
        tts.language_boost      – language hint, default auto (e.g. Chinese,Yue)
    """

    def __init__(self, config, parent):
        super().__init__(config, parent)
        self.voice_id: str = (config.tts.ref_file or "").strip()
        api_key: str = (
            (getattr(config.tts, "minimax_api_key", None) or "")
            or (getattr(config.tts, "api_key", None) or "")
            or os.getenv("MINIMAX_API_KEY", "")
        ).strip()
        if not api_key:
            raise ValueError(
                "MiniMax API key is missing. Set tts.minimax_api_key (e.g. ${MINIMAX_API_KEY}) or MINIMAX_API_KEY env."
            )
        if not self.voice_id:
            raise ValueError("MiniMax voice ID is missing. Set tts.ref_file to a valid voice ID.")
        self._api_key = api_key
        self._model_id: str = (getattr(config.tts, "model", None) or _DEFAULT_MODEL).strip() or _DEFAULT_MODEL
        self._speed: float = float(getattr(config.tts, "speed", 1.0) or 1.0)
        self._language_boost: str = (
            (getattr(config.tts, "language_boost", None) or "auto").strip() or "auto"
        )
        transport = (getattr(config.tts, "minimax_transport", None) or "websocket").strip().lower()
        self._use_websocket = transport != "http"
        api_base = (
            (getattr(config.tts, "minimax_base_url", None) or "")
            or os.getenv("MINIMAX_API_BASE", "")
            or _DEFAULT_API_BASE
        ).rstrip("/")
        self._http_stream_url = f"{api_base}/v1/t2a_v2"
        self._ws_uri = self._build_ws_uri(api_base)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._ws_session: Optional[MiniMaxWsSession] = None
        logger.info(
            "minimax transport=%s voice_id=%s model=%s",
            "websocket" if self._use_websocket else "http",
            self.voice_id,
            self._model_id,
        )

    def _build_ws_uri(self, api_base: str) -> str:
        parsed = urlparse(api_base if "://" in api_base else f"https://{api_base}")
        host = parsed.hostname or "api.minimax.io"
        port = parsed.port
        group_id = (os.getenv("MINIMAX_GROUP_ID") or "").strip()
        path = "/ws/v1/t2a_v2"
        if group_id:
            return f"wss://{host}{f':{port}' if port else ''}{path}?GroupId={group_id}"
        return f"wss://{host}{f':{port}' if port else ''}{path}"

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is not None:
            return self._loop
        loop = asyncio.new_event_loop()

        def _run_loop() -> None:
            asyncio.set_event_loop(loop)
            loop.run_forever()

        thread = threading.Thread(target=_run_loop, name="minimax-ws-async", daemon=True)
        thread.start()
        self._loop = loop
        self._loop_thread = thread
        return loop

    def _run_async(self, coro, *, timeout: float = 120.0):
        loop = self._ensure_loop()
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        try:
            return fut.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            logger.warning("minimax: async op timed out after %.1fs", timeout)
            raise

    def _close_ws_session(self) -> None:
        session = self._ws_session
        self._ws_session = None
        if session is None:
            return
        try:
            self._run_async(session.close(), timeout=5.0)
        except Exception:
            logger.exception("minimax: failed to close WebSocket session")

    def _get_ws_session(self) -> MiniMaxWsSession:
        if self._ws_session is None or self._ws_session.is_closed:
            self._ws_session = MiniMaxWsSession(
                api_key=self._api_key,
                voice_id=self.voice_id,
                model_id=self._model_id,
                sample_rate=self.sample_rate,
                speed=self._speed,
                language_boost=self._language_boost,
                ws_uri=self._ws_uri,
            )
        return self._ws_session

    def voice_turn_begin(self, _request_id: Optional[str] = None) -> None:
        """New agent reply — close any prior WebSocket session."""
        self._close_ws_session()

    def voice_turn_reset(self) -> None:
        self._close_ws_session()

    def flush_talk(self) -> None:
        self._close_ws_session()
        super().flush_talk()

    def _parse_http_stream_line(self, raw_line: str) -> bytes | None:
        line = raw_line.strip()
        if not line or line == "[DONE]":
            return None
        if line.startswith("data:"):
            line = line[5:].strip()
            if not line or line == "[DONE]":
                return None
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("minimax: skip non-JSON stream line")
            return None
        base_resp = message.get("base_resp") or {}
        status_code = base_resp.get("status_code", 0)
        if status_code != 0:
            logger.error(
                "minimax stream error status_code=%s status_msg=%s",
                status_code,
                base_resp.get("status_msg"),
            )
            return None
        data = message.get("data") or {}
        audio_hex = data.get("audio")
        if not audio_hex:
            return None
        try:
            return bytes.fromhex(audio_hex)
        except ValueError:
            logger.warning("minimax: invalid hex audio chunk")
            return None

    def _stream_audio_http(self, text: str) -> Iterator[bytes]:
        payload_text = _tts_text_without_bracket_tags(text)
        if not payload_text:
            logger.warning("minimax http: empty text after tag strip")
            return
        if len(payload_text) > _MAX_TEXT_CHARS:
            payload_text = payload_text[:_MAX_TEXT_CHARS]
            logger.warning("minimax: text truncated to %d chars", _MAX_TEXT_CHARS)

        payload = {
            "model": self._model_id,
            "text": payload_text,
            "stream": True,
            "stream_options": {"exclude_aggregated_audio": True},
            "language_boost": self._language_boost,
            "voice_setting": {
                "voice_id": self.voice_id,
                "speed": self._speed,
                "vol": 1,
                "pitch": 0,
            },
            "audio_setting": {
                "sample_rate": self.sample_rate,
                "format": "pcm",
                "channel": 1,
            },
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        start = time.perf_counter()
        first = True
        try:
            with requests.post(
                self._http_stream_url,
                json=payload,
                headers=headers,
                stream=True,
                timeout=120,
            ) as response:
                if response.status_code >= 400:
                    body = response.text[:500]
                    logger.error("minimax TTS HTTP %s: %s", response.status_code, body)
                    return
                for raw_line in response.iter_lines(decode_unicode=True):
                    if not raw_line or self.state != State.RUNNING:
                        continue
                    chunk = self._parse_http_stream_line(raw_line)
                    if not chunk:
                        continue
                    if first:
                        logger.info(
                            "minimax http time to first chunk: %.3fs voice_id=%s model=%s",
                            time.perf_counter() - start,
                            self.voice_id,
                            self._model_id,
                        )
                        first = False
                    yield chunk
        except Exception:
            logger.exception("minimax _stream_audio_http error")

    async def _stream_audio_ws(self, text: str) -> AsyncIterator[bytes]:
        session = self._get_ws_session()
        start = time.perf_counter()
        first = True
        async for chunk in session.synthesize(text):
            if self.state != State.RUNNING:
                break
            if first:
                logger.info(
                    "minimax ws time to first chunk: %.3fs voice_id=%s model=%s",
                    time.perf_counter() - start,
                    self.voice_id,
                    self._model_id,
                )
                first = False
            yield chunk

    def txt_to_audio(self, msg: tuple[str, dict]):
        text, _textevent = msg
        logger.info(
            "minimax producing audio transport=%s voice_id=%s model=%s language_boost=%s",
            "websocket" if self._use_websocket else "http",
            self.voice_id,
            self._model_id,
            self._language_boost,
        )
        if self._use_websocket:
            self._run_async(self._stream_tts_async(self._stream_audio_ws(text), msg))
        else:
            self._stream_tts(self._stream_audio_http(text), msg)

    async def _stream_tts_async(
        self, audio_stream: AsyncIterator[bytes], msg: tuple[str, dict]
    ) -> None:
        text, textevent = msg
        first = True
        last_stream = np.array([], dtype=np.float32)
        remainder = b""
        async for chunk in audio_stream:
            if chunk is None or len(chunk) == 0:
                continue
            chunk = remainder + chunk
            trim = len(chunk) & ~1
            remainder = chunk[trim:]
            chunk = chunk[:trim]
            if not chunk:
                continue
            stream = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32767.0
            stream = np.concatenate((last_stream, stream))
            streamlen = stream.shape[0]
            idx = 0
            while streamlen >= self.chunk:
                eventpoint: dict = {}
                if first:
                    eventpoint = {"status": "start", "text": text}
                    eventpoint.update(**textevent)
                    first = False
                self.parent.put_audio_frame(stream[idx : idx + self.chunk], eventpoint)
                streamlen -= self.chunk
                idx += self.chunk
            last_stream = stream[idx:]
        eventpoint = {"status": "end", "text": text}
        eventpoint.update(**textevent)
        self.parent.put_audio_frame(np.zeros(self.chunk, np.float32), eventpoint)

    def _stream_tts(self, audio_stream: Iterator[bytes], msg: tuple[str, dict]):
        text, textevent = msg
        first = True
        last_stream = np.array([], dtype=np.float32)
        remainder = b""
        for chunk in audio_stream:
            if chunk is None or len(chunk) == 0:
                continue
            chunk = remainder + chunk
            trim = len(chunk) & ~1
            remainder = chunk[trim:]
            chunk = chunk[:trim]
            if not chunk:
                continue
            stream = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32767.0
            stream = np.concatenate((last_stream, stream))
            streamlen = stream.shape[0]
            idx = 0
            while streamlen >= self.chunk:
                eventpoint: dict = {}
                if first:
                    eventpoint = {"status": "start", "text": text}
                    eventpoint.update(**textevent)
                    first = False
                self.parent.put_audio_frame(stream[idx : idx + self.chunk], eventpoint)
                streamlen -= self.chunk
                idx += self.chunk
            last_stream = stream[idx:]
        eventpoint = {"status": "end", "text": text}
        eventpoint.update(**textevent)
        self.parent.put_audio_frame(np.zeros(self.chunk, np.float32), eventpoint)
