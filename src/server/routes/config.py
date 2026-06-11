"""Public config for frontend (e.g. ASR mode)."""
import json
from aiohttp import web

from src.server.agora.token_service import agora_token_required
from src.server.state import state


async def get_config(request):
    """Return public config the client needs (e.g. asr.mode to force server ASR)."""
    payload = {
        "asr": {"mode": "server", "type": "sensevoice", "vad": {"enabled": True}},
        "webrtc": {
            "agora": {
                "enabled": False,
                "app_id": "",
                "default_channel": "mina",
                "publisher_uid": 10001,
                "token_required": False,
                "token_expiration_seconds": 3600,
            },
        },
    }
    if state.config and hasattr(state.config, "asr") and state.config.asr:
        asr_cfg = state.config.asr
        payload["asr"]["mode"] = getattr(asr_cfg, "mode", "browser")
        payload["asr"]["type"] = getattr(asr_cfg, "type", "whisper")
        vad_cfg = getattr(asr_cfg, "vad", None)
        payload["asr"]["vad"] = {
            "enabled": getattr(vad_cfg, "enabled", False),
        }
    if state.config and getattr(state.config, "webrtc", None):
        w = state.config.webrtc
        ag = getattr(w, "agora", None)
        if ag:
            payload["webrtc"]["agora"] = {
                "enabled": bool(getattr(ag, "enabled", False)),
                "app_id": getattr(ag, "app_id", "") or "",
                "default_channel": getattr(ag, "default_channel", "mina") or "mina",
                "publisher_uid": int(getattr(ag, "publisher_uid", 10001) or 10001),
                "token_required": agora_token_required(ag),
                "token_expiration_seconds": int(
                    getattr(ag, "token_expiration_seconds", 3600) or 3600
                ),
            }
    return web.Response(
        content_type="application/json",
        text=json.dumps(payload),
    )
