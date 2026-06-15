from __future__ import annotations

import time
from typing import Iterator

import numpy as np
from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs

from src.tts.base import BaseTTS, State
from src.utils.logging import logger

_OUTPUT_FORMAT = "pcm_16000"  # 16 kHz, 16-bit mono PCM — matches pipeline sample rate
_DEFAULT_MODEL_ID = "eleven_v3"


class ElevenLabsTTS(BaseTTS):
    """ElevenLabs streaming TTS engine (official SDK).

    Config fields used:
        tts.ref_file   – ElevenLabs voice ID (required)
        tts.api_key    – ElevenLabs API key (supports ${ENV_VAR} substitution)
        tts.model      – model id (optional; default eleven_v3)
        tts.stability / similarity_boost / speed – optional; set from interaction-config API

    Example config.yaml snippet:
        tts:
          type: elevenlabs
          ref_file: JBFqnCBsd6RMkjVDRZzb   # voice ID
          api_key: ${ELEVENLABS_API_KEY}
    """

    def __init__(self, config, parent):
        super().__init__(config, parent)
        self.voice_id: str = config.tts.ref_file
        api_key: str = getattr(config.tts, "api_key", "")
        if not api_key:
            raise ValueError(
                "ElevenLabs API key is missing. "
                "Set tts.api_key in config (e.g. ${ELEVENLABS_API_KEY})."
            )
        if not self.voice_id:
            raise ValueError(
                "ElevenLabs voice ID is missing. Set tts.ref_file to a valid voice ID."
            )
        self._client = ElevenLabs(api_key=api_key)
        model = (getattr(config.tts, "model", None) or _DEFAULT_MODEL_ID).strip()
        self._model_id = model or _DEFAULT_MODEL_ID

    def _voice_settings(self) -> VoiceSettings | None:
        """Only pass settings explicitly set (e.g. from interaction-config API)."""
        tts = self.config.tts
        kwargs: dict = {}
        stability = getattr(tts, "stability", None)
        if stability is not None:
            kwargs["stability"] = float(stability)
        similarity = getattr(tts, "similarity_boost", None)
        if similarity is not None:
            kwargs["similarity_boost"] = float(similarity)
        style = getattr(tts, "style", None)
        if style is not None:
            kwargs["style"] = float(style)
        use_speaker_boost = getattr(tts, "use_speaker_boost", None)
        if use_speaker_boost is not None:
            kwargs["use_speaker_boost"] = bool(use_speaker_boost)
        speed = getattr(tts, "speed", None)
        if speed is not None:
            kwargs["speed"] = float(speed)
        if not kwargs:
            return None
        return VoiceSettings(**kwargs)

    def _stream_audio(self, text: str) -> Iterator[bytes]:
        """Call ElevenLabs SDK streaming TTS and yield raw PCM chunks."""
        start = time.perf_counter()
        first = True
        try:
            stream_kwargs: dict = {
                "voice_id": self.voice_id,
                "text": text,
                "model_id": self._model_id,
                "output_format": _OUTPUT_FORMAT,
            }
            voice_settings = self._voice_settings()
            if voice_settings is not None:
                stream_kwargs["voice_settings"] = voice_settings
            audio_stream = self._client.text_to_speech.stream(**stream_kwargs)
            for chunk in audio_stream:
                if not chunk:
                    continue
                if first:
                    logger.info(f"elevenlabs time to first chunk: {time.perf_counter() - start:.3f}s")
                    first = False
                if self.state == State.RUNNING:
                    yield chunk
        except Exception:
            logger.exception("elevenlabs _stream_audio error")

    def txt_to_audio(self, msg: tuple[str, dict]):
        text, textevent = msg
        logger.info("elevenlabs producing audio with voice_id=%s", self.voice_id)
        self._stream_tts(self._stream_audio(text), msg)

    def _stream_tts(self, audio_stream: Iterator[bytes], msg: tuple[str, dict]):
        text, textevent = msg
        first = True
        last_stream = np.array([], dtype=np.float32)
        remainder = b""  # carry-over bytes that don't form a complete int16
        for chunk in audio_stream:
            if chunk is not None and len(chunk) > 0:
                chunk = remainder + chunk
                # Trim to a multiple of 2 bytes; hold the leftover for next iteration
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
