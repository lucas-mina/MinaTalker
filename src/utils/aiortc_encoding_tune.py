"""Tune aiortc outbound video encoder bitrate constants (H264 / VP8)."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config.schema import WebRTCConfig

logger = logging.getLogger(__name__)


def apply_webrtc_outbound_video_bitrate(cfg: "WebRTCConfig | None") -> None:
    """
    Patch aiortc.codecs.h264 / vpx module-level MIN/DEFAULT/MAX_BITRATE when cfg sets any > 0.

    Browsers send REMB; aiortc applies it via encoder.target_bitrate (clamped to min..max).
    Raising defaults and floor helps sharp first frames and high-res talking heads.
    """
    if cfg is None:
        return
    d = int(cfg.outbound_video_default_bitrate_bps or 0)
    lo = int(cfg.outbound_video_min_bitrate_bps or 0)
    hi = int(cfg.outbound_video_max_bitrate_bps or 0)
    if d <= 0 and lo <= 0 and hi <= 0:
        return
    try:
        from aiortc.codecs import h264, vpx
    except ImportError:
        logger.warning("aiortc not installed; skip outbound video bitrate tuning")
        return

    def _patch(mod, name: str) -> None:
        if d > 0:
            mod.DEFAULT_BITRATE = d
        if lo > 0:
            mod.MIN_BITRATE = lo
        if hi > 0:
            mod.MAX_BITRATE = hi
        # Keep ordering sane for encoder setter: min <= default <= max
        if mod.MIN_BITRATE > mod.MAX_BITRATE:
            mod.MIN_BITRATE, mod.MAX_BITRATE = mod.MAX_BITRATE, mod.MIN_BITRATE
        mod.DEFAULT_BITRATE = max(
            mod.MIN_BITRATE, min(mod.DEFAULT_BITRATE, mod.MAX_BITRATE)
        )
        logger.info(
            "aiortc %s outbound bitrate: default=%s min=%s max=%s bps",
            name,
            mod.DEFAULT_BITRATE,
            mod.MIN_BITRATE,
            mod.MAX_BITRATE,
        )

    _patch(h264, "H264")
    _patch(vpx, "VP8")
