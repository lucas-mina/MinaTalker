from __future__ import annotations

import base64
import json
import os
import time
from typing import Iterator

import numpy as np
import requests

from src.tts.base import BaseTTS, State
from src.utils.logging import logger

_STREAM_URL = "https://api.inworld.ai/tts/v1/voice:stream"
_DEFAULT_MODEL = "inworld-tts-2"


class InworldTTS(BaseTTS):
    """Inworld streaming TTS (REST voice:stream).

    Config fields used:
        tts.ref_file         – Inworld voice ID (required)
        tts.inworld_api_key  – Inworld API key (or inworld_api_key env)
        tts.model            – model id, default inworld-tts-2
    """

    def __init__(self, config, parent):
        super().__init__(config, parent)
        self.voice_id: str = (config.tts.ref_file or "").strip()
        api_key: str = (getattr(config.tts, "inworld_api_key", None) or "") or os.getenv("inworld_api_key", "")
        api_key = api_key.strip()
        if not api_key:
            raise ValueError(
                "Inworld API key is missing. Set tts.inworld_api_key (e.g. ${inworld_api_key}) or inworld_api_key env."
            )
        if not self.voice_id:
            raise ValueError("Inworld voice ID is missing. Set tts.ref_file to a valid voice ID.")
        self._api_key = api_key
        self._model_id: str = (getattr(config.tts, "model", None) or _DEFAULT_MODEL).strip() or _DEFAULT_MODEL
        self._delivery_mode: str = (getattr(config.tts, "delivery_mode", None) or "BALANCED").strip()

    def _stream_audio(self, text: str) -> Iterator[bytes]:
        payload = {
            "text": text,
            "voiceId": self.voice_id,
            "modelId": self._model_id,
            "audioConfig": {
                "audioEncoding": "PCM",
                "sampleRateHertz": self.sample_rate,
            },
            "deliveryMode": self._delivery_mode,
        }
        headers = {
            "Authorization": f"Basic {self._api_key}",
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
                    logger.error(
                        "inworld TTS HTTP %s: %s",
                        response.status_code,
                        body,
                    )
                    return
                for raw_line in response.iter_lines(decode_unicode=True):
                    if not raw_line or self.state != State.RUNNING:
                        continue
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        message = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("inworld: skip non-JSON stream line")
                        continue
                    if message.get("error"):
                        logger.error("inworld stream error: %s", message["error"])
                        continue
                    result = message.get("result") or {}
                    audio_b64 = result.get("audioContent")
                    if not audio_b64:
                        continue
                    chunk = base64.b64decode(audio_b64)
                    if not chunk:
                        continue
                    if first:
                        if chunk[:4] == b"RIFF":
                            logger.warning(
                                "inworld: audioEncoding=PCM but first chunk has WAV header; check API response"
                            )
                        logger.info(
                            "inworld time to first chunk: %.3fs voice_id=%s model=%s",
                            time.perf_counter() - start,
                            self.voice_id,
                            self._model_id,
                        )
                        first = False
                    yield chunk
        except Exception:
            logger.exception("inworld _stream_audio error")

    def txt_to_audio(self, msg: tuple[str, dict]):
        text, _textevent = msg
        logger.info("inworld producing audio voice_id=%s model=%s", self.voice_id, self._model_id)
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
