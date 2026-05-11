"""全局状态管理"""
from typing import Any, Awaitable, Callable, Dict, Optional, Set

from aiortc import RTCPeerConnection

from src.avatars.base import BaseAvatar
from src.utils.logging import logger

SignalingEmitter = Callable[[Dict[str, Any]], Awaitable[None]]


class ServerState:
    """服务器全局状态管理类"""
    
    def __init__(self):
        # 会话管理
        self.avatar_streams: Dict[int, BaseAvatar] = {}  # sessionid -> BaseAvatar
        
        # WebRTC 连接管理
        self.pcs: Set[RTCPeerConnection] = set()
        
        # 配置和模型
        self.config = None
        self.model = None
        self.avatar = None
        
        # 服务状态
        self.server_ready = False

        # WebSocket signaling: sessionid -> async fn(payload) for TTS utterance-end etc.
        self._signaling_emitters: Dict[int, SignalingEmitter] = {}

    def register_signaling_emitter(self, sessionid: int, emitter: Optional[SignalingEmitter]) -> None:
        """Register WS sender for a session (e.g. from ws_signaling). None unregisters."""
        if emitter is None:
            self._signaling_emitters.pop(sessionid, None)
        else:
            self._signaling_emitters[sessionid] = emitter

    async def emit_signaling(self, sessionid: int, payload: Dict[str, Any]) -> None:
        """Deliver a JSON payload to the client WebSocket for this session, if registered."""
        fn = self._signaling_emitters.get(sessionid)
        if fn is None:
            return
        try:
            await fn(payload)
        except Exception:
            logger.exception("emit_signaling failed sessionid=%s", sessionid)

    def add_session(self, sessionid: int, avatar_stream: BaseAvatar = None):
        """添加会话"""
        self.avatar_streams[sessionid] = avatar_stream
    
    def remove_session(self, sessionid: int):
        """移除会话"""
        if sessionid in self.avatar_streams:
            del self.avatar_streams[sessionid]
    
    def get_session(self, sessionid: int) -> BaseAvatar:
        """获取会话"""
        return self.avatar_streams.get(sessionid)
    
    def add_peer_connection(self, pc: RTCPeerConnection):
        """添加 WebRTC 连接"""
        self.pcs.add(pc)
    
    def remove_peer_connection(self, pc: RTCPeerConnection):
        """移除 WebRTC 连接"""
        self.pcs.discard(pc)


# 全局状态实例
state = ServerState()
