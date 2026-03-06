"""
ASR 引擎实现集中入口

对外只需要从这里 import 对应的引擎类即可，例如：
    from src.asr.engines import WhisperASR, FunASR
"""

from .whisper import WhisperASR
from .funasr import FunASR
from .sensevoice import SenseVoiceASR

__all__ = [
    "WhisperASR",
    "FunASR",
    "SenseVoiceASR",
]
