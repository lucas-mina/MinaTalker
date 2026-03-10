"""路由模块"""
from .webrtc import offer, ws_signaling
from .chat import human, interrupt_talk, is_speaking, clear_history
from .audio import humanaudio, asr, asr_ws
from .video import set_audiotype, set_flower_mode, record, download_record
from .health import health_check
from .avatar import list_avatars
from .config import get_config

__all__ = [
    "offer",
    "ws_signaling",
    "human",
    "interrupt_talk",
    "is_speaking",
    "clear_history",
    "humanaudio",
    "asr",
    "asr_ws",
    "set_audiotype",
    "set_flower_mode",
    "record",
    "download_record",
    "health_check",
    "list_avatars",
    "get_config",
]
