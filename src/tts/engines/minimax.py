from __future__ import annotations

import json
import os
import time
from typing import Iterator

import numpy as np
import requests

from src.tts.base import BaseTTS, State
from src.utils.logging import logger

_STREAM_URL = "https://api.minimax.io/v1/t2a_v2"
_DEFAULT_MODEL = "speech-02-turbo"


class MiniMaxTTS(BaseTTS):
    """MiniMax streaming TTS (HTTP t2a_v2).

    Config fields used:
        tts.ref_file           – MiniMax voice ID (required)
        tts.minimax_api_key    – API key (or MINIMAX_API_KEY env)
        tts.model              – model id, default speech-02-turbo
        tts.speed              – speech speed multiplier
        tts.language_boost     – language hint, default auto (e.g. Chinese,Yue)
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

    def _parse_stream_line(self, raw_line: str) -> bytes | None:
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

    def _stream_audio(self, text: str) -> Iterator[bytes]:
        payload = {
            "model": self._model_id,
            "text": text,
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
                _STREAM_URL,
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
                    chunk = self._parse_stream_line(raw_line)
                    if not chunk:
                        continue
                    if first:
                        logger.info(
                            "minimax time to first chunk: %.3fs voice_id=%s model=%s",
                            time.perf_counter() - start,
                            self.voice_id,
                            self._model_id,
                        )
                        first = False
                    yield chunk
        except Exception:
            logger.exception("minimax _stream_audio error")

    def txt_to_audio(self, msg: tuple[str, dict]):
        text, _textevent = msg
        logger.info(
            "minimax producing audio voice_id=%s model=%s language_boost=%s",
            self.voice_id,
            self._model_id,
            self._language_boost,
        )
        self._stream_tts(self._stream_audio(text), msg)

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
