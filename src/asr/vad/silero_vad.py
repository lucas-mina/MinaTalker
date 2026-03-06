"""
SileroVAD — Voice Activity Detection preprocessing layer.

Wraps the silero-vad model to detect whether audio contains real speech
before it is passed to Whisper (or any other ASR engine).

Usage:
    from src.asr.vad import get_vad_engine

    vad = get_vad_engine(device="auto")
    if vad.has_speech(audio_bytes):
        text = asr_engine.transcribe(audio_bytes)
"""

from __future__ import annotations

import io
from typing import List, Optional

import numpy as np
import torch
import soundfile as sf

from src.utils.logging import logger

_TARGET_SR = 16_000  # SileroVAD requires 8kHz or 16kHz; we use 16kHz


def _resolve_device(device: str) -> str:
    if device == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return device


class SileroVAD:
    """
    Lazy-loaded SileroVAD wrapper.

    The model is downloaded once from torch.hub on first use and then
    cached by torch.hub in ~/.cache/torch/hub/.
    """

    def __init__(self, device: str = "auto"):
        self.device = _resolve_device(device)
        self._model = None
        self._utils = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self):
        """Load the silero-vad model (called once, lazily)."""
        if self._model is not None:
            return
        logger.info(f"[VAD] Loading SileroVAD model on device={self.device}")
        try:
            # silero_vad PyPI package — preferred
            from silero_vad import load_silero_vad, get_speech_timestamps
            self._model = load_silero_vad()
            self._model.to(self.device)
            self._get_speech_ts = get_speech_timestamps
            logger.info("[VAD] SileroVAD loaded via silero-vad package")
        except ImportError:
            # Fallback: torch.hub (original repo)
            logger.warning(
                "[VAD] silero-vad package not found, falling back to torch.hub. "
                "Consider: pip install silero-vad"
            )
            model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                onnx=False,
            )
            self._model = model.to(self.device)
            (
                self._get_speech_ts,
                _,
                _,
                _,
                _,
            ) = utils
            logger.info("[VAD] SileroVAD loaded via torch.hub")

    def _audio_to_tensor(self, audio_bytes: bytes) -> Optional[torch.Tensor]:
        """
        Convert raw audio bytes (webm/opus/wav/mp3/…) to a 16 kHz mono float32 tensor.

        Decode order:
          1. PyAV  — handles WebM/Opus, MP4, MP3, and most container formats in-memory.
          2. soundfile — handles plain WAV, FLAC, OGG/Vorbis without an ffmpeg dependency.
        Returns None if all decoders fail.
        """
        data, sr = None, None

        # --- 1. Try PyAV (handles WebM/Opus natively, no temp file needed) ---
        try:
            import av as _av
            import numpy as _np

            with _av.open(io.BytesIO(audio_bytes)) as container:
                audio_stream = next(
                    (s for s in container.streams if s.type == "audio"), None
                )
                if audio_stream is None:
                    raise ValueError("No audio stream found")

                sr = audio_stream.codec_context.sample_rate
                chunks = []
                resampler = _av.AudioResampler(
                    format="fltp",           # float32 planar
                    layout="mono",
                    rate=_TARGET_SR,
                )
                for frame in container.decode(audio_stream):
                    for resampled in resampler.resample(frame):
                        arr = resampled.to_ndarray()  # shape: (1, N) float32
                        chunks.append(arr[0])

                # flush resampler
                for resampled in resampler.resample(None):
                    arr = resampled.to_ndarray()
                    chunks.append(arr[0])

                if chunks:
                    data = _np.concatenate(chunks).astype("float32")
                    sr = _TARGET_SR  # resampler already converted

        except Exception as exc:
            logger.debug(f"[VAD] PyAV decode failed ({exc}), trying soundfile")
            data, sr = None, None

        # --- 2. Fallback: soundfile (WAV, FLAC, OGG/Vorbis) ---
        if data is None:
            try:
                data, sr = sf.read(io.BytesIO(audio_bytes), dtype="float32", always_2d=False)
                if data.ndim > 1:
                    data = data.mean(axis=1)
            except Exception as exc:
                logger.warning(f"[VAD] Audio decode failed: {exc}")
                return None

        if data is None or len(data) == 0:
            return None

        # --- Resample to 16 kHz if soundfile path was taken and SR differs ---
        if sr != _TARGET_SR:
            try:
                import resampy
                data = resampy.resample(data, sr, _TARGET_SR)
            except ImportError:
                try:
                    from scipy.signal import resample_poly
                    from math import gcd
                    g = gcd(int(sr), _TARGET_SR)
                    data = resample_poly(data, _TARGET_SR // g, int(sr) // g)
                except ImportError:
                    target_len = int(len(data) * _TARGET_SR / sr)
                    data = np.interp(
                        np.linspace(0, len(data) - 1, target_len),
                        np.arange(len(data)),
                        data,
                    )

        return torch.from_numpy(data).float()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def has_speech(
        self,
        audio_bytes: bytes,
        threshold: float = 0.5,
        min_speech_duration_ms: int = 250,
        min_silence_duration_ms: int = 100,
        speech_pad_ms: int = 30,
    ) -> bool:
        """
        Return True if the audio contains at least one speech segment
        that meets the probability threshold and minimum duration.
        """
        self._load()

        wav = self._audio_to_tensor(audio_bytes)
        if wav is None or wav.numel() == 0:
            logger.warning("[VAD] Could not decode audio — treating as silence")
            return False

        # --- Diagnostics ---
        duration_ms = int(wav.numel() / _TARGET_SR * 1000)
        peak = float(wav.abs().max())
        rms = float(wav.pow(2).mean().sqrt())
        logger.info(
            f"[VAD] audio decoded: {wav.numel()} samples, "
            f"{duration_ms} ms, peak={peak:.4f}, rms={rms:.4f}"
        )
        if peak < 1e-4:
            logger.warning("[VAD] Audio is near-silent (peak < 1e-4) — check mic gain")

        wav = wav.to(self.device)

        # Run with lowered threshold for diagnostic scan so we can see what
        # probability the model actually assigns to the audio
        try:
            ts_diag = self._get_speech_ts(
                wav,
                self._model,
                sampling_rate=_TARGET_SR,
                threshold=0.1,   # very permissive — just to see raw scores
                min_speech_duration_ms=50,
            )
            logger.info(
                f"[VAD] diagnostic scan (thr=0.1, min=50ms): {len(ts_diag)} segments — "
                + (str(ts_diag[:3]) if ts_diag else "none")
            )
        except Exception:
            pass

        try:
            timestamps = self._get_speech_ts(
                wav,
                self._model,
                sampling_rate=_TARGET_SR,
                threshold=threshold,
                min_speech_duration_ms=min_speech_duration_ms,
                min_silence_duration_ms=min_silence_duration_ms,
                speech_pad_ms=speech_pad_ms,
            )
        except Exception as exc:
            logger.warning(f"[VAD] get_speech_timestamps failed: {exc} — passing audio through")
            return True  # fail-open: don't silently drop audio on VAD errors

        detected = len(timestamps) > 0
        logger.info(
            f"[VAD] has_speech={detected}, segments={len(timestamps)}, "
            f"threshold={threshold}, min_speech_ms={min_speech_duration_ms}"
        )
        return detected

    def get_speech_timestamps(
        self,
        audio_bytes: bytes,
        threshold: float = 0.5,
        min_speech_duration_ms: int = 250,
        min_silence_duration_ms: int = 100,
        speech_pad_ms: int = 30,
    ) -> List[dict]:
        """
        Return a list of speech segment dicts, each with 'start' and 'end'
        sample indices (at 16 kHz).

        Useful for future streaming / trimming use-cases.
        """
        self._load()

        wav = self._audio_to_tensor(audio_bytes)
        if wav is None or wav.numel() == 0:
            return []

        wav = wav.to(self.device)

        try:
            return self._get_speech_ts(
                wav,
                self._model,
                sampling_rate=_TARGET_SR,
                threshold=threshold,
                min_speech_duration_ms=min_speech_duration_ms,
                min_silence_duration_ms=min_silence_duration_ms,
                speech_pad_ms=speech_pad_ms,
            )
        except Exception as exc:
            logger.warning(f"[VAD] get_speech_timestamps failed: {exc}")
            return []
