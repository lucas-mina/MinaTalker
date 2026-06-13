"""Agora video codec: config normalization, SDK mapping, bitrate tuning."""
from __future__ import annotations

from src.utils.logging import logger

DEFAULT_VIDEO_CODEC = "h264"
SUPPORTED_VIDEO_CODECS = frozenset({"av1", "h264", "vp8", "vp9", "h265"})

# Agora server SDK: AV1 encode falls back to H264 when short side < 360px.
AV1_MIN_SHORT_SIDE_PX = 360

# Relative to H.264 talking-head lip-sync at same resolution/fps.
_CODEC_BITRATE_SCALE: dict[str, float] = {
    "av1": 0.65,
    "h264": 1.0,
    "vp8": 1.15,
    "vp9": 0.75,
    "h265": 0.85,
}

# kbps per (width * height * fps); tuned from prior 576x1024@25 H264 ~6500 kbps.
_PIXEL_FPS_BITRATE_KBPS = 0.00044
_MIN_BITRATE_KBPS = 800
_MAX_BITRATE_KBPS = 8000

_SDK_CODEC_ATTR = {
    "av1": "VIDEO_CODEC_AV1",
    "h264": "VIDEO_CODEC_H264",
    "vp8": "VIDEO_CODEC_VP8",
    "vp9": "VIDEO_CODEC_VP9",
    "h265": "VIDEO_CODEC_H265",
}


def normalize_video_codec(value: str | None, *, default: str = DEFAULT_VIDEO_CODEC) -> str:
    name = (value or default).strip().lower()
    if name in SUPPORTED_VIDEO_CODECS:
        return name
    logger.warning("Unknown Agora video_codec %r; using %s", value, default)
    return default


def resolve_target_bitrate_kbps(
    width: int,
    height: int,
    fps: int,
    codec: str,
    override_kbps: int = 0,
) -> int:
    """Return SenderOptions.target_bitrate (kbps).

    Agora recommends 0 (STANDARD_BITRATE): SDK picks bitrate for Live Broadcast profile
    and adapts via CC. Use override_kbps > 0 only for explicit manual caps.
    """
    if int(override_kbps or 0) <= 0:
        return 0
    return int(override_kbps)


def estimate_video_bitrate_kbps(width: int, height: int, fps: int, codec: str) -> int:
    """Rough kbps estimate for logging only (not passed to SDK when target_bitrate=0)."""
    pixel_fps = max(1, int(width)) * max(1, int(height)) * max(1, int(fps))
    scale = _CODEC_BITRATE_SCALE.get(codec, 1.0)
    kbps = int(pixel_fps * _PIXEL_FPS_BITRATE_KBPS * scale)
    return max(_MIN_BITRATE_KBPS, min(kbps, _MAX_BITRATE_KBPS))


def resolve_sdk_video_codec_type(codec: str):
    """Map config codec name to agora.rtc.agora_base.VideoCodecType for SenderOptions."""
    from agora.rtc.agora_base import VideoCodecType

    normalized = normalize_video_codec(codec)
    if normalized == "h265":
        logger.warning(
            "Agora server SDK H265 encode not supported yet; SenderOptions uses H264"
        )
        normalized = "h264"
    attr = _SDK_CODEC_ATTR.get(normalized)
    if attr is None:
        logger.warning(
            "Agora SDK has no VideoCodecType mapping for codec=%r; using H264",
            normalized,
        )
        return VideoCodecType.VIDEO_CODEC_H264
    sdk_type = getattr(VideoCodecType, attr, None)
    if sdk_type is None:
        logger.warning(
            "Agora SDK missing VideoCodecType.%s for codec=%s; falling back to H264",
            attr,
            normalized,
        )
        return VideoCodecType.VIDEO_CODEC_H264
    return sdk_type


def effective_publish_codec(configured_codec: str | None, width: int, height: int) -> str:
    """Codec clients should expect on the wire (matches Agora SDK encode behavior)."""
    codec = normalize_video_codec(configured_codec)
    short_side = min(int(width), int(height))
    if codec == "av1" and short_side < AV1_MIN_SHORT_SIDE_PX:
        logger.warning(
            "Agora AV1 encode requires short side >= %dpx; %dx%d will be H264 on the wire",
            AV1_MIN_SHORT_SIDE_PX,
            width,
            height,
        )
        return "h264"
    if codec == "h265":
        logger.warning(
            "Agora server SDK does not support H265 encode yet; clients should decode H264"
        )
        return "h264"
    return codec


def web_client_codec(codec: str | None, *, width: int = 0, height: int = 0) -> str:
    if width > 0 and height > 0:
        return effective_publish_codec(codec, width, height)
    return normalize_video_codec(codec)
