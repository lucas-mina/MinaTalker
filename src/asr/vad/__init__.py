"""VAD (Voice Activity Detection) sub-package."""

from __future__ import annotations

from typing import Optional

from .silero_vad import SileroVAD

_vad_instance: Optional[SileroVAD] = None


def get_vad_engine(device: str = "auto", force_new: bool = False) -> SileroVAD:
    """
    Return the shared SileroVAD singleton, creating it on first call.

    Args:
        device: 'auto' | 'cpu' | 'cuda'
        force_new: If True, discard any existing instance and create a fresh one.

    Returns:
        SileroVAD instance (model is loaded lazily on first use).
    """
    global _vad_instance
    if _vad_instance is None or force_new:
        _vad_instance = SileroVAD(device=device)
    return _vad_instance


def release_vad_engine():
    """Release the VAD singleton (frees model memory)."""
    global _vad_instance
    if _vad_instance is not None:
        from src.utils.logging import logger
        logger.info("[VAD] Releasing SileroVAD engine")
        _vad_instance = None


__all__ = [
    "SileroVAD",
    "get_vad_engine",
    "release_vad_engine",
]
