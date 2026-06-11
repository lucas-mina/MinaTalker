"""配置数据结构定义"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class AvatarEntry:
    """单个 Avatar 的配置条目"""
    id: int = 0
    key: str = ""
    name: str = ""
    age: int = 0
    bio: str = ""
    photo: str = ""
    level: str = ""
    location: str = ""
    tags: List[str] = field(default_factory=list)
    intimacy: int = 0
    next_reward: str = ""
    live: bool = False
    prompt_file: str = "prompt_mina.txt"
    model_avatar_id: str = ""
    model_avatar_id_ex: str = ""
    tts_provider: str = ""  # elevenlabs | inworld | minimax
    tts_voice_id: str = ""
    tts_model: str = ""
    language_boost: str = ""  # minimax only; e.g. Chinese,Yue | auto
    elevenlabs_voice_id: str = ""  # legacy; use tts_voice_id when tts_provider is set


@dataclass
class WebConfig:
    """前端 Web 配置"""
    port: int = 3000
    host: str = "0.0.0.0"


@dataclass
class AgoraConfig:
    """
    Agora RTC（可选）：启用后客户端可走 Agora SDK 拉流/推流，替代浏览器直连 aiortc。

    app_certificate 可选。不设时走 Agora Testing（仅 App ID，token=null）；
    设置时服务端签 RTC Token（Secured，生产推荐）。勿下发前端；可用 ${ENV} 读取。
    """
    enabled: bool = False
    app_id: str = ""
    app_certificate: Optional[str] = field(default=None, repr=False)
    token_expiration_seconds: int = 3600
    # 默认频道名（可与 sessionid / room 拼接）；具体策略由前后端约定
    default_channel: str = "mina"
    # 服务端 Avatar 推流固定 UID（观众订阅此 UID）
    publisher_uid: int = 10001


@dataclass
class WebRTCConfig:
    """
    WebRTC 相关：信令外可配 outbound 视频码率（aiortc 编码器）。

    aiortc 无标准 setParameters；浏览器 REMB 会写 encoder.target_bitrate，
    值夹在 MIN/MAX 之间。提高 default/min/max 可减轻前几帧糊、高分辨率顶不满码率。
    三项均为 0 时不改库内建常量。

    agora.enabled=true 时表示优先使用 Agora RTC；此时通常不再使用本服务的 /offer WebRTC 通路，
    出站码率微调（aiortc）也会跳过。
    """
    turn_config: Optional[Dict[str, Any]] = None
    outbound_video_default_bitrate_bps: int = 0
    outbound_video_min_bitrate_bps: int = 0
    outbound_video_max_bitrate_bps: int = 0
    agora: AgoraConfig = field(default_factory=AgoraConfig)


@dataclass
class AppConfig:
    """应用配置"""
    listenport: int = 8010
    listenhost: str = "0.0.0.0"  # 监听地址：0.0.0.0 允许外部访问，127.0.0.1 仅本地
    max_session: int = 1
    
    # SSL/HTTPS 配置
    ssl: bool = False  # 主开关：true 启用 HTTPS，false 使用 HTTP
    ssl_cert: Optional[str] = None  # SSL 证书文件路径（.pem 或 .crt）
    ssl_key: Optional[str] = None   # SSL 私钥文件路径（.key）
    
    # 前端配置（可选，支持嵌套字典或 WebConfig 对象）
    web: Optional[Dict[str, Any]] = field(default_factory=lambda: {"port": 3000, "host": "0.0.0.0"})


@dataclass
class ERNeRfConfig:
    """ERNeRF 专用配置"""
    # 数据与路径
    pose: str = "data/avatars/ernerf_obama/data_kf.json"
    au: str = "data/avatars/ernerf_obama/au.csv"

    workspace: str = "data/avatars/ernerf_obama/"
    ckpt: str = "data/avatars/ernerf_obama/ngp_kf.pth"
    torso_imgs: str = ""

    # 采样与训练相关
    data_range: List[int] = field(default_factory=lambda: [0, -1])
    seed: int = 0
    num_rays: int = 4096 * 16
    cuda_ray: bool = False
    max_steps: int = 16
    num_steps: int = 16
    upsample_steps: int = 0
    update_extra_interval: int = 16
    max_ray_batch: int = 4096

    # loss 相关
    warmup_step: int = 10000
    amb_aud_loss: int = 1
    amb_eye_loss: int = 1
    unc_loss: int = 1
    lambda_amb: float = 1e-4

    # 网络 / 渲染 backbone 选项
    fp16: bool = False
    bg_img: str = "white" #  white |  black
    fbg: bool = False
    exp_eye: bool = False
    fix_eye: float = -1.0
    smooth_eye: bool = False
    torso_shrink: float = 0.8

    # 数据集 / 空间相关
    color_space: str = "srgb"
    preload: int = 0
    bound: float = 1.0
    scale: float = 4.0
    offset: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    dt_gamma: float = 1.0 / 256.0
    min_near: float = 0.05
    density_thresh: float = 10.0
    density_thresh_torso: float = 0.01
    patch_size: int = 1

    # 嘴唇 / 躯干相关
    init_lips: bool = False
    finetune_lips: bool = False
    smooth_lips: bool = False
    torso: bool = False
    head_ckpt: str = ""

    # GUI 与相机
    gui: bool = False
    radius: float = 3.35
    fovy: float = 21.24
    max_spp: int = 1

    # 其它杂项（音频注意力等）
    att: int = 2
    aud: str = ""
    emb: bool = False

    ind_dim: int = 4
    ind_num: int = 10000
    ind_dim_torso: int = 8
    amb_dim: int = 2
    part: bool = False
    part2: bool = False
    train_camera: bool = False
    smooth_path: bool = False
    smooth_path_window: int = 7

    # ASR 相关
    asr: bool = False
    asr_wav: str = ""
    asr_play: bool = False
    asr_model: str = "cpierse/wav2vec2-large-xlsr-53-esperanto"
    asr_save_feats: bool = False

    # 全身模式相关
    fullbody: bool = False
    fullbody_img: str = "data/fullbody/img"
    fullbody_width: int = 580
    fullbody_height: int = 1080
    fullbody_offset_x: int = 0
    fullbody_offset_y: int = 0

    # -O 快捷选项：等价于 fp16 + cuda_ray + exp_eye
    O: bool = False


@dataclass
class TalkingGaussianConfig:
    """TalkingGaussian 专用配置"""
    # 模型路径
    source_path: str = "data/avatars/talkinggaussian_obama/Obama/source"
    model_path: str = "data/avatars/talkinggaussian_obama/Obama/model"
    bg_img: str = "white"
    sh_degree: int = 3

@dataclass
class ModelConfig:
    """模型配置"""
    type: str = "musetalk"  # wav2lip | musetalk | ultralight | ernerf | talkinggaussian
    avatar_id: str = "avator_1"
    batch_size: int = 16
    model_path: str = "./models"
    # 是否在启动时预加载所有 Avatar 及其 *_ex 变体（根据 avatar_config.yaml）
    preload_avatars: bool = False
    
    # 模型专属配置
    ernerf: ERNeRfConfig = field(default_factory=ERNeRfConfig)
    talkinggaussian: TalkingGaussianConfig = field(default_factory=TalkingGaussianConfig)


@dataclass
class TTSConfig:
    """TTS 配置"""
    type: str = "edgetts"  # edgetts | azuretts | fishtts | gpt-sovits | cosyvoice | tencent | doubao | indextts2 | xtts | elevenlabs | inworld | minimax
    ref_file: str = "zh-CN-YunxiaNeural"
    ref_text: Optional[str] = None
    tts_server: str = "http://127.0.0.1:9880"
    model: str = ""  # provider model id (e.g. inworld-tts-2, eleven_v3)
    delivery_mode: str = "BALANCED"  # inworld-tts-2: STABLE | BALANCED | CREATIVE
    # API key field — used by engines that require one (e.g. elevenlabs).
    # Supports ${ENV_VAR} substitution via the config loader.
    api_key: Optional[str] = None
    inworld_api_key: Optional[str] = None  # Inworld TTS only; supports ${inworld_api_key}
    minimax_api_key: Optional[str] = None  # MiniMax TTS only; supports ${MINIMAX_API_KEY}
    language_boost: str = "auto"  # MiniMax only; e.g. Chinese,Yue

    # ElevenLabs voice settings
    similarity_boost: float = 0.75
    style: float = 0.0
    use_speaker_boost: bool = True
    speed: float = 1.0


@dataclass
class VADConfig:
    """SileroVAD 语音活动检测配置"""
    enabled: bool = True          # False = skip VAD, always pass audio to ASR
    threshold: float = 0.5        # speech probability threshold (0.0–1.0)
    min_speech_ms: int = 250      # minimum speech duration in ms; shorter clips = silence
    min_silence_ms: int = 100     # minimum trailing silence to separate utterances
    speech_pad_ms: int = 30       # pad speech segments on both sides to avoid clipping


@dataclass
class ASRConfig:
    """ASR 语音识别配置"""
    mode: str = "server"  # browser | server | auto (优先浏览器，不支持时降级到服务器)
    type: str = "sensevoice"  # whisper | funasr | sensevoice (仅当 mode=server 时使用)
    model_size: str = "base"  # tiny | base | small | medium | large (仅 whisper 使用)
    model_name: str = "iic/SenseVoiceSmall"    # model name / local path for funasr/sensevoice engines
    language: str = "auto"   # zh | en | ja | ko | yue | auto (sensevoice: auto = 自动检测)
    device: str = "auto"   # auto | cpu | cuda
    vad: VADConfig = field(default_factory=VADConfig)
    # SenseVoice 增强选项 (仅 type=sensevoice 时生效)
    sensevoice_use_itn: bool = True       # 逆文本规范化 (数字、日期等)
    sensevoice_batch_size_s: Optional[int] = None   # 长音频按秒分批，None=默认
    sensevoice_merge_vad: Optional[bool] = None     # 合并 VAD 片段 (None=默认)
    sensevoice_merge_length_s: Optional[float] = None  # 合并最短时长(秒)，与 merge_vad 配合


@dataclass
class LLMConfig:
    """LLM 配置"""
    provider: str = "openai"  # openai-compatible provider alias: openai|dashscope|qwen|claude|ollama|vllm|internal
    api_key: str = ""
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: str = "qwen-plus"
    character_id: Optional[str] = None  # internal character routing id, e.g. "mayuki-type"
    # internal provider only:
    internal_transport: str = "websocket"  # websocket | http — core streaming vs legacy POST /api/agent/chat
    internal_ws_path: str = "/ws/chat"  # path on same host as base_url (origin)


@dataclass
class AudioConfig:
    """音频配置"""
    fps: int = 50
    sample_rate: int = 16000
    # 滑动窗口配置
    l: int = 10  # left length
    m: int = 8   # middle length
    r: int = 10  # right length


@dataclass
class VideoConfig:
    """视频配置"""
    width: int = 450
    height: int = 450
    fps: int = 25


@dataclass
class CustomVideoConfig:
    """自定义视频配置"""
    config_path: str = ""


@dataclass
class Config:
    """全局配置"""
    app: AppConfig = field(default_factory=AppConfig)
    webrtc: WebRTCConfig = field(default_factory=WebRTCConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    asr: ASRConfig = field(default_factory=ASRConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    video: VideoConfig = field(default_factory=VideoConfig)
    custom_video: CustomVideoConfig = field(default_factory=CustomVideoConfig)
    
    # 其他动态配置
    sessionid: int = 0
    customopt: List = field(default_factory=list)
    # resolved per-session prompt file (set at session creation time)
    prompt_file: Optional[str] = None
    
    @property
    def ernerf(self) -> ERNeRfConfig:
        """返回 model.ernerf"""
        return self.model.ernerf

    @property
    def talkinggaussian(self) -> TalkingGaussianConfig:
        """返回 model.talkinggaussian"""
        return self.model.talkinggaussian