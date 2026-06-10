"""配置加载器"""
import os
import re
import yaml
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import fields

from .schema import (
    Config, AppConfig, ModelConfig, TTSConfig, ASRConfig, VADConfig, LLMConfig,
    AudioConfig, VideoConfig, CustomVideoConfig, ERNeRfConfig, TalkingGaussianConfig,
    WebRTCConfig, AgoraConfig,
)


def _merge_dicts(base: Dict, override: Dict) -> Dict:
    """
    深度合并两个字典
    
    Args:
        base: 基础字典
        override: 覆盖字典
    
    Returns:
        合并后的字典
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def load_yaml_config(config_file: Path) -> Dict:
    """加载 YAML 配置文件，支持环境变量插值"""
    if not config_file.exists():
        return {}
    
    with open(config_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 替换 ${VAR_NAME} 格式的环境变量，只替换存在的环境变量
    def replace_env_var(match):
        var_name = match.group(1)
        value = os.getenv(var_name)
        # 只有环境变量存在时才替换，否则保持原样
        return value if value is not None else match.group(0)
    
    content = re.sub(r'\$\{([^}]+)\}', replace_env_var, content)
    config_dict = yaml.safe_load(content) or {}
    
    return config_dict


def dict_to_config(config_dict: Dict) -> Config:
    """
    将字典转换为 Config 对象
    
    Args:
        config_dict: 配置字典
    
    Returns:
        Config 对象
    """
    app_config = AppConfig(**config_dict.get('app', {}))
    
    # 处理 model 配置
    model_dict = config_dict.get('model', {})
    
    # 如果顶层有 ernerf 配置，合并到 model.ernerf
    if 'ernerf' in config_dict:
        if 'ernerf' not in model_dict:
            model_dict['ernerf'] = {}
        # 顶层 ernerf 优先级更高
        model_dict['ernerf'] = _merge_dicts(model_dict.get('ernerf', {}), config_dict['ernerf'])
    
    # 如果顶层有 talkinggaussian 配置，合并到 model.talkinggaussian
    if 'talkinggaussian' in config_dict:
        if 'talkinggaussian' not in model_dict:
            model_dict['talkinggaussian'] = {}
        # 顶层 talkinggaussian 优先级更高
        model_dict['talkinggaussian'] = _merge_dicts(model_dict.get('talkinggaussian', {}), config_dict['talkinggaussian'])
    
    # 创建 ERNeRfConfig
    ernerf_config = ERNeRfConfig(**model_dict.get('ernerf', {}))
    
    # 创建 TalkingGaussianConfig
    talkinggaussian_config = TalkingGaussianConfig(**model_dict.get('talkinggaussian', {}))
    
    # 创建 ModelConfig
    model_dict_for_init = {k: v for k, v in model_dict.items() if k not in ['ernerf', 'talkinggaussian']}
    model_config = ModelConfig(**model_dict_for_init, ernerf=ernerf_config, talkinggaussian=talkinggaussian_config)
    
    tts_config = TTSConfig(**config_dict.get('tts', {}))
    # Handle nested vad dict so ASRConfig receives a VADConfig object, not a raw dict
    asr_dict = config_dict.get('asr', {})
    vad_dict = asr_dict.pop('vad', {}) if isinstance(asr_dict, dict) else {}
    vad_config = VADConfig(**vad_dict) if isinstance(vad_dict, dict) else VADConfig()
    asr_config = ASRConfig(**asr_dict, vad=vad_config)
    llm_config = LLMConfig(**config_dict.get('llm', {}))
    audio_config = AudioConfig(**config_dict.get('audio', {}))
    video_config = VideoConfig(**config_dict.get('video', {}))
    custom_video_config = CustomVideoConfig(**config_dict.get('custom_video', {}))

    webrtc_allowed = {f.name for f in fields(WebRTCConfig)}
    webrtc_raw = config_dict.get("webrtc") or {}
    if not isinstance(webrtc_raw, dict):
        webrtc_raw = {}
    agora_raw = webrtc_raw.get("agora") or {}
    if not isinstance(agora_raw, dict):
        agora_raw = {}
    agora_allowed = {f.name for f in fields(AgoraConfig)}
    agora_kwargs = {k: v for k, v in agora_raw.items() if k in agora_allowed}
    agora_config = AgoraConfig(**agora_kwargs)
    webrtc_kwargs = {
        k: v
        for k, v in webrtc_raw.items()
        if k in webrtc_allowed and k != "agora"
    }
    webrtc_config = WebRTCConfig(**webrtc_kwargs, agora=agora_config)

    return Config(
        app=app_config,
        webrtc=webrtc_config,
        model=model_config,
        tts=tts_config,
        asr=asr_config,
        llm=llm_config,
        audio=audio_config,
        video=video_config,
        custom_video=custom_video_config,
    )


def catalog_avatar_ids_match(stored: Any, requested: Any) -> bool:
    """
    True if avatar_config.yaml entry ``id`` matches a client-supplied avatar_id.

    Supports integer ids, UUID strings, other string ids, and JSON numeric strings
    (e.g. YAML id 1 vs client "1").
    """
    if stored is None or requested is None:
        return False
    if stored == requested:
        return True
    sa = str(stored).strip()
    sb = str(requested).strip()
    if sa == sb:
        return True
    try:
        return int(stored) == int(requested)
    except (TypeError, ValueError):
        return False


def find_avatar_entry_by_catalog_id(
    entries: list[Dict[str, Any]], avatar_id: Any
) -> Optional[Dict[str, Any]]:
    """Return the first avatar dict whose ``id`` matches ``avatar_id``, else None."""
    for entry in entries:
        if isinstance(entry, dict) and catalog_avatar_ids_match(entry.get("id"), avatar_id):
            return entry
    return None


def resolve_avatar_prompt_file(avatar_id: Any) -> Optional[str]:
    """
    Look up the prompt_file for a given avatar id from avatar_config.yaml.
    Returns the prompt_file string, or None if not found.
    """
    from ..utils.paths import get_config_dir
    avatar_config_path = get_config_dir() / "avatar_config.yaml"
    if not avatar_config_path.exists():
        return None
    avatar_data = load_yaml_config(avatar_config_path)
    for entry in avatar_data.get("avatars", []):
        if isinstance(entry, dict) and catalog_avatar_ids_match(entry.get("id"), avatar_id):
            return entry.get("prompt_file")
    return None


def resolve_avatar_flower_audiotype(avatar_id: Any) -> Optional[str]:
    """
    Look up the "flower" audiotype for a given avatar id from avatar_config.yaml.
    By convention we reuse the model_avatar_id_ex field as the audiotype key
    for custom video/audio loops (BaseAvatar.customopt).
    
    Returns:
        The audiotype string to pass into set_custom_state, or None if not found.
    """
    from ..utils.paths import get_config_dir
    avatar_config_path = get_config_dir() / "avatar_config.yaml"
    if not avatar_config_path.exists():
        return None
    avatar_data = load_yaml_config(avatar_config_path)
    for entry in avatar_data.get("avatars", []):
        if isinstance(entry, dict) and catalog_avatar_ids_match(entry.get("id"), avatar_id):
            # Use model_avatar_id_ex as the custom audiotype identifier
            return entry.get("model_avatar_id_ex")
    return None


def resolve_avatar_ex_model_id(avatar_id: Any) -> Optional[str]:
    """
    Look up the extended/ex avatar model id (model_avatar_id_ex)
    for a given avatar id from avatar_config.yaml.

    This is used to switch the running avatar's video to the *_ex
    variant (e.g. wav2lip_avatar1_ex) when triggering special modes
    such as "flower".
    """
    from ..utils.paths import get_config_dir
    avatar_config_path = get_config_dir() / "avatar_config.yaml"
    if not avatar_config_path.exists():
        return None
    avatar_data = load_yaml_config(avatar_config_path)
    for entry in avatar_data.get("avatars", []):
        if isinstance(entry, dict) and catalog_avatar_ids_match(entry.get("id"), avatar_id):
            return entry.get("model_avatar_id_ex")
    return None


def load_avatar_entries() -> list[Dict[str, Any]]:
    """
    Load avatar entries from avatar_config.yaml.

    Returns:
        A list of avatar dictionaries. If the file is missing or invalid,
        returns an empty list.
    """
    from ..utils.paths import get_config_dir

    avatar_config_path = get_config_dir() / "avatar_config.yaml"
    if not avatar_config_path.exists():
        return []

    avatar_data = load_yaml_config(avatar_config_path)
    avatars = avatar_data.get("avatars", [])
    # Ensure we always return a list of dicts
    if not isinstance(avatars, list):
        return []
    return [entry for entry in avatars if isinstance(entry, dict)]


def list_all_avatar_model_ids() -> list[str]:
    """
    Collect all model avatar ids (base + *_ex) from avatar_config.yaml.

    Returns:
        List of unique avatar model id strings such as
        ["wav2lip_avatar1", "wav2lip_avatar1_ex", ...].
    """
    entries = load_avatar_entries()
    ids = set()
    for entry in entries:
        base_id = entry.get("model_avatar_id")
        ex_id = entry.get("model_avatar_id_ex")
        if isinstance(base_id, str) and base_id:
            ids.add(base_id)
        if isinstance(ex_id, str) and ex_id:
            ids.add(ex_id)
    return list(ids)


def load_config(
    config_file: Optional[str] = None,
) -> Config:
    """
    加载配置
    
    Args:
        config_file: 指定配置文件路径
    
    Returns:
        Config: 最终配置对象
    """
    from ..utils.paths import get_project_root, get_config_dir
    
    # 1. 加载默认配置（起始为空，后续逐步合并）
    config_dict = {}
    
    # 2. 加载指定的配置文件（如果有传入 --config）
    if config_file:
        config_path = Path(config_file)
        if not config_path.is_absolute():
            config_path = get_project_root() / config_path
        
        if config_path.exists():
            file_config = load_yaml_config(config_path)
            config_dict = _merge_dicts(config_dict, file_config)
    
    # 3. 如果没有指定配置文件，加载默认 config.yaml
    if not config_file:
        default_config_file = get_config_dir() / "config.yaml"
        if default_config_file.exists():
            default_config = load_yaml_config(default_config_file)
            config_dict = _merge_dicts(config_dict, default_config)
    
    # 4. 转换为 Config 对象
    config = dict_to_config(config_dict)
    
    # 处理 -O 快捷选项
    if config.model.ernerf.O:
        config.model.ernerf.fp16 = True
        config.model.ernerf.cuda_ray = True
        config.model.ernerf.exp_eye = True
    
    return config
