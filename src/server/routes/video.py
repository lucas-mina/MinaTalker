"""视频相关路由"""
import os
import json
from aiohttp import web

from src.utils.logging import logger
from src.server.auth.session_access import check_session_access
from src.server.state import state
from src.config.loader import resolve_avatar_flower_audiotype, resolve_avatar_ex_model_id


def _extract_bearer_token(authorization_header: str | None) -> str | None:
    if not authorization_header:
        return None
    parts = authorization_header.strip().split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
        return parts[1].strip()
    return None


def _session_access_json_error(sessionid, access_token, action):
    err = check_session_access(int(sessionid or 0), access_token, action=action)
    if not err:
        return None
    return web.Response(
        content_type="application/json",
        text=json.dumps({"code": -1, "msg": err}),
        status=403,
    )


async def set_audiotype(request):
    """设置音频类型"""
    try:
        params = await request.json()
        sessionid = params.get('sessionid', 0)
        access_token = params.get("access_token") or _extract_bearer_token(request.headers.get("Authorization"))
        avatar_stream = state.avatar_streams.get(sessionid)
        if avatar_stream is not None:
            access_token = access_token or getattr(avatar_stream, "internal_access_token", None)
        denied = _session_access_json_error(sessionid, access_token, "set_audiotype")
        if denied:
            return denied
        if avatar_stream is None:
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": f"sessionid {sessionid} not found"}),
                status=404,
            )
        avatar_stream.set_custom_state(params['audiotype'], params['reinit'])

        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": 0, "msg": "ok"}
            ),
        )
    except Exception as e:
        logger.exception('exception:')
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": -1, "msg": str(e)}
            ),
        )


async def set_flower_mode(request):
    """
    Trigger the per-avatar "flower" custom video/audio state.
    
    Frontend sends:
      { "sessionid": number, "avatar_id": number|string }  # string = catalog id in avatar_config.yaml (e.g. UUID)
    
    We look up the corresponding *_ex model id from avatar_config.yaml
    (using the model_avatar_id_ex field) and, if supported, switch the
    running avatar's underlying video to that *_ex avatar (e.g.
    wav2lip_avatar1_ex). Optionally, we also look up a "flower"
    audiotype and call set_custom_state for any configured custom
    video/audio loops.
    """
    try:
        params = await request.json()
        sessionid = params.get("sessionid", 0)
        avatar_id = params.get("avatar_id")

        if not sessionid or sessionid not in state.avatar_streams:
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "invalid or unknown sessionid"}),
                status=400,
            )

        avatar_stream = state.avatar_streams[sessionid]
        access_token = params.get("access_token") or _extract_bearer_token(request.headers.get("Authorization"))
        access_token = access_token or getattr(avatar_stream, "internal_access_token", None)
        denied = _session_access_json_error(sessionid, access_token, "set_flower_mode")
        if denied:
            return denied

        if avatar_id is None or (isinstance(avatar_id, str) and not avatar_id.strip()):
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "avatar_id is required"}),
                status=400,
            )

        catalog_avatar_id = avatar_id

        if avatar_stream is None:
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "avatar stream not initialized"}),
                status=500,
            )

        # 1) Switch underlying avatar video to *_ex model if possible
        ex_avatar_id = resolve_avatar_ex_model_id(catalog_avatar_id)
        if ex_avatar_id and hasattr(avatar_stream, "switch_avatar"):
            logger.info(
                "[Flower] sessionid=%s avatar_id=%s switching avatar to %s",
                sessionid,
                catalog_avatar_id,
                ex_avatar_id,
            )
            try:
                avatar_stream.switch_avatar(ex_avatar_id)
            except Exception:
                logger.exception(
                    "[Flower] failed to switch avatar to %s for sessionid=%s",
                    ex_avatar_id,
                    sessionid,
                )

        # 2) Optionally trigger a custom video/audio state, if configured
        audiotype = resolve_avatar_flower_audiotype(catalog_avatar_id)
        if audiotype:
            logger.info(
                "[Flower] sessionid=%s avatar_id=%s audiotype=%s",
                sessionid,
                catalog_avatar_id,
                audiotype,
            )
            try:
                avatar_stream.set_custom_state(audiotype, reinit=True)
            except Exception:
                logger.exception(
                    "[Flower] failed to set_custom_state(%s) for sessionid=%s",
                    audiotype,
                    sessionid,
                )

        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": 0, "msg": "ok"}),
        )
    except Exception as e:
        logger.exception("[Flower] exception:")
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": -1, "msg": str(e)}),
            status=500,
        )


async def record(request):
    """处理录制请求"""
    try:
        params = await request.json()
        logger.info(f'[录制API] 收到请求: {params}')

        sessionid = params.get('sessionid', 0)
        logger.info(f'[录制API] sessionid={sessionid}')
        
        if sessionid not in state.avatar_streams:
            logger.error(f'[录制API] 录制失败: sessionid {sessionid} 不存在')
            logger.error(f'[录制API] 当前可用的 sessionid: {list(state.avatar_streams.keys())}')
            return web.Response(
                content_type="application/json",
                text=json.dumps(
                    {"code": -1, "msg": f"sessionid {sessionid} not found"}
                ),
                status=404
            )

        avatar_stream = state.avatar_streams[sessionid]
        access_token = params.get("access_token") or _extract_bearer_token(request.headers.get("Authorization"))
        access_token = access_token or getattr(avatar_stream, "internal_access_token", None)
        denied = _session_access_json_error(sessionid, access_token, "record")
        if denied:
            return denied
        
        if avatar_stream is None:
            logger.error(f'[录制API] 录制失败: sessionid {sessionid} 的 avatar_stream 为 None')
            return web.Response(
                content_type="application/json",
                text=json.dumps(
                    {"code": -1, "msg": "avatar stream not initialized"}
                ),
                status=500
            )
        
        logger.info(f'[录制API] 找到 avatar_stream: {type(avatar_stream).__name__}')
        logger.info(f'[录制API] avatar_stream.recording 状态: {avatar_stream.recording}')
        logger.info(f'[录制API] avatar_stream 视频尺寸: width={avatar_stream.width}, height={avatar_stream.height}')
        
        if params['type'] == 'start_record':
            logger.info(f'[录制API] 开始录制 sessionid={sessionid}')
            avatar_stream.start_recording()
            logger.info(f'[录制API] start_recording 调用完成，当前 recording 状态: {avatar_stream.recording}')
            return web.Response(
                content_type="application/json",
                text=json.dumps(
                    {"code": 0, "msg": "ok"}
                ),
            )
        elif params['type'] == 'end_record':
            logger.info(f'[录制API] 停止录制 sessionid={sessionid}')
            avatar_stream.stop_recording()
            logger.info(f'[录制API] stop_recording 调用完成')
            
            response_data = {"code": 0, "msg": "ok"}
            if avatar_stream.current_record_file:
                filename = os.path.basename(avatar_stream.current_record_file)
                response_data['filename'] = filename
                response_data['filepath'] = avatar_stream.current_record_file
                logger.info(f'[录制API] 返回文件信息: {filename}')
            
            return web.Response(
                content_type="application/json",
                text=json.dumps(response_data),
            )
    except Exception as e:
        logger.exception('[录制API] 录制异常:')
        return web.Response(
            content_type="application/json",
            text=json.dumps(
                {"code": -1, "msg": str(e)}
            ),
            status=500
        )


async def download_record(request):
    """下载录制的视频文件"""
    try:
        filename = request.match_info.get('filename', '')
        if not filename:
            return web.Response(text='文件名不能为空', status=400)
        
        # 只允许下载 records 目录下的文件
        if '..' in filename or '/' in filename or '\\' in filename:
            return web.Response(text='非法文件名', status=400)
        
        filepath = f'data/records/{filename}'
        
        if not os.path.exists(filepath):
            logger.warning(f'[下载] 文件不存在: {filepath}')
            return web.Response(text='文件不存在', status=404)
        
        logger.info(f'[下载] 开始下载文件: {filepath}')
        
        return web.FileResponse(
            path=filepath,
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"'
            }
        )
    except Exception as e:
        logger.exception('[下载] 下载异常:')
        return web.Response(text=f'下载失败: {str(e)}', status=500)
