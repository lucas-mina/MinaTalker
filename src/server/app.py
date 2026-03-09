# Linly-Talker-Stream (https://github.com/Kedreamix/Linly-Talker-Stream). Copyright [Linly-talker-stream@kedreamix]. Apache-2.0.
# Based on LiveTalking (C) 2024 LiveTalking@lipku https://github.com/lipku/LiveTalking (Apache-2.0).

"""主启动文件"""
import os
import sys

# Use UTF-8 for console on Windows so Chinese log messages do not raise UnicodeEncodeError
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
import argparse
import torch.multiprocessing as mp

from src.utils.logging import logger
from src.config.loader import load_config, list_all_avatar_model_ids
from src.avatars.factory import prepare_avatar_model
from src.asr import get_asr_engine
from src.server.state import state
from src.server.server import create_app, run_server


def main():
    """主启动函数"""
    # 设置 multiprocessing 启动方式
    try:
        mp.set_start_method('spawn')
    except RuntimeError:
        pass
    
    # 解析命令行参数
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--config', 
        type=str, 
        default="config/config.yaml",
        help="path to config file (e.g., config/config.yaml)"
    )
    args = parser.parse_args()
    
    # 加载配置
    state.config = load_config(config_file=args.config)
    logger.info(f"已加载配置: {state.config}")
    
    # 加载自定义视频配置
    state.config.customopt = []
    if state.config.custom_video.config_path:
        with open(state.config.custom_video.config_path, 'r') as file:
            state.config.customopt = json.load(file)
    
    # 可选：预加载所有 Avatar 及其 *_ex 变体到内存
    if getattr(state.config.model, "preload_avatars", False):
        try:
            avatar_ids = set(list_all_avatar_model_ids() or [])
            # 确保当前主 avatar 也包含在内
            if state.config.model.avatar_id:
                avatar_ids.add(state.config.model.avatar_id)
            logger.info("预加载 Avatar 资源，数量: %d", len(avatar_ids))
            model_type = state.config.model.type
            if model_type == "wav2lip":
                from src.avatars.wav2lip.avatar import preload_avatars as _preload
            elif model_type == "musetalk":
                from src.avatars.musetalk.avatar import preload_avatars as _preload
            else:
                _preload = None
            if _preload and avatar_ids:
                _preload(sorted(avatar_ids))
        except Exception:
            logger.exception("预加载 Avatar 资源失败，将继续正常启动。")
    
    # 加载模型
    logger.info(f"正在加载模型类型: {state.config.model.type}")
    state.model, state.avatar = prepare_avatar_model(state.config)
    logger.info("模型加载完成")

    # 预热 ASR，避免首个 /asr 请求在实时检测中触发模型加载卡顿
    asr_cfg = state.config.asr if state.config else None
    asr_mode = str(getattr(asr_cfg, "mode", "server")).lower()
    if asr_mode in ("server", "auto"):
        try:
            asr_engine = get_asr_engine(
                asr_type=getattr(asr_cfg, "type", "sensevoice"),
                model_size=getattr(asr_cfg, "model_size", "base"),
                device=getattr(asr_cfg, "device", "auto"),
                model_name=getattr(asr_cfg, "model_name", None),
            )
            logger.info("[ASR] 预热开始: type=%s, mode=%s", getattr(asr_cfg, "type", "sensevoice"), asr_mode)
            asr_engine.ensure_initialized()
            logger.info("[ASR] 预热完成")
        except Exception:
            logger.exception("[ASR] 预热失败，将在首次识别时重试加载。")
    
    # 创建并运行应用
    app = create_app()
    run_server(app, state.config)


if __name__ == '__main__':
    main()
