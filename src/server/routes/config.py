"""Public config for frontend (e.g. ASR mode)."""
import json
from aiohttp import web

from src.server.state import state


async def get_config(request):
    """Return public config the client needs (e.g. asr.mode to force server ASR)."""
    payload = {"asr": {"mode": "server", "type": "sensevoice", "vad": {"enabled": True}}}
    if state.config and hasattr(state.config, "asr") and state.config.asr:
        asr_cfg = state.config.asr
        payload["asr"]["mode"] = getattr(asr_cfg, "mode", "browser")
        payload["asr"]["type"] = getattr(asr_cfg, "type", "whisper")
        vad_cfg = getattr(asr_cfg, "vad", None)
        payload["asr"]["vad"] = {
            "enabled": getattr(vad_cfg, "enabled", False),
        }
    return web.Response(
        content_type="application/json",
        text=json.dumps(payload),
    )
