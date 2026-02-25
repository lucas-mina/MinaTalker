"""聊天相关路由"""
import json
from aiohttp import web
import asyncio

from src.llm.service import llm_response
from src.utils.logging import logger
from src.server.state import state


def _json(data: dict) -> web.Response:
    return web.Response(content_type="application/json", text=json.dumps(data))


def _get_avatar_stream(sessionid):
    """Return the avatar stream for sessionid, or None if the session is gone."""
    return state.avatar_streams.get(sessionid)


async def human(request):
    """处理文本对话请求"""
    try:
        params = await request.json()
        sessionid = params.get('sessionid', 0)

        avatar_stream = _get_avatar_stream(sessionid)
        if avatar_stream is None:
            logger.warning(f'[CHAT] session {sessionid} not found (already closed?)')
            return _json({"code": -1, "msg": f"session {sessionid} not found"})

        if params.get('interrupt'):
            avatar_stream.flush_talk()

        if params['type'] == 'echo':
            avatar_stream.put_msg_txt(params['text'])
            response_text = params['text']
        elif params['type'] == 'chat':
            llm_config = state.config.llm if state.config else None
            logger.info(f'[CHAT] LLM 配置: {llm_config}')
            response_text = await asyncio.get_event_loop().run_in_executor(
                None,
                llm_response,
                params['text'],
                avatar_stream,
                llm_config.api_key if llm_config else None,
                llm_config.base_url if llm_config else "https://dashscope.aliyuncs.com/compatible-mode/v1",
                llm_config.model if llm_config else "qwen-plus"
            )
        else:
            return _json({"code": -1, "msg": f"unknown type: {params.get('type')}"})

        return _json({"code": 0, "msg": "ok", "response": response_text})

    except Exception as e:
        logger.exception('exception:')
        return _json({"code": -1, "msg": str(e)})


async def interrupt_talk(request):
    """中断当前对话"""
    try:
        params = await request.json()
        sessionid = params.get('sessionid', 0)

        avatar_stream = _get_avatar_stream(sessionid)
        if avatar_stream is None:
            logger.warning(f'[INTERRUPT] session {sessionid} not found')
            return _json({"code": -1, "msg": f"session {sessionid} not found"})

        avatar_stream.flush_talk()
        return _json({"code": 0, "msg": "ok"})

    except Exception as e:
        logger.exception('exception:')
        return _json({"code": -1, "msg": str(e)})


async def is_speaking(request):
    """查询是否正在说话"""
    try:
        params = await request.json()
        sessionid = params.get('sessionid', 0)

        avatar_stream = _get_avatar_stream(sessionid)
        if avatar_stream is None:
            return _json({"code": -1, "msg": f"session {sessionid} not found"})

        return _json({"code": 0, "data": avatar_stream.is_speaking()})

    except Exception as e:
        logger.exception('exception:')
        return _json({"code": -1, "msg": str(e)})


async def clear_history(request):
    """清空对话历史"""
    try:
        params = await request.json()
        sessionid = params.get('sessionid', 0)
        
        clear_session_history(sessionid)
        
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": 0, "msg": "对话历史已清空"}
            ),
        )
    except Exception as e:
        logger.exception('清空历史失败:')
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": -1, "msg": str(e)}
            ),
        )
