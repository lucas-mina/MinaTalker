"""路由模块"""
from .webrtc import offer, ws_signaling
from .chat import human, interrupt_talk, is_speaking, clear_history
from .audio import humanaudio, asr
from .video import set_audiotype, set_flower_mode, record, download_record
from .health import health_check
from .avatar import list_avatars
from .config import get_config
from .agora import get_agora_token, get_agora_channel, agora_join, agora_leave, agora_test_page

__all__ = [
    "offer",
    "ws_signaling",
    "human",
    "interrupt_talk",
    "is_speaking",
    "clear_history",
    "humanaudio",
    "asr",
    "set_audiotype",
    "set_flower_mode",
    "record",
    "download_record",
    "health_check",
    "list_avatars",
    "get_config",
    "get_agora_token",
    "get_agora_channel",
    "agora_join",
    "agora_leave",
    "agora_test_page",
]
