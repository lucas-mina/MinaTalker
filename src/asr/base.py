"""
ASR 引擎基类
所有 ASR 引擎的统一抽象接口
"""

from __future__ import annotations

import os
import tempfile
import soundfile as sf
from io import BytesIO
from typing import Dict, Any
from abc import ABC, abstractmethod

from src.utils.logging import logger


class BaseASR(ABC):
    """
    所有 ASR 引擎的基类
    
    统一接口：
    - transcribe: 识别音频字节数据
    - set_language: 设置识别语言
    - get_info: 获取引擎信息
    """
    
    def __init__(self, config=None):
        """
        初始化 ASR 引擎
        
        Args:
            config: 配置对象（可选）
        """
        self.config = config
        self.language = "zh"  # 默认中文
        self._initialized = False
        
        logger.info(f'[ASR] 初始化 {self.__class__.__name__}')
    
    @abstractmethod
    def _load_model(self):
        """加载 ASR 模型（子类实现）"""
        pass
    
    @abstractmethod
    def _transcribe(self, audio_path: str) -> Dict[str, Any]:
        """
        识别音频文件（子类实现）
        
        Args:
            audio_path: 音频文件路径
            
        Returns:
            Dict 包含:
                - text: 识别的文本
                - language: 检测到的语言（可选）
                - confidence: 置信度（可选）
        """
        pass
    
    def transcribe(self, audio_bytes: bytes) -> Dict[str, Any]:
        """
        识别音频字节数据（统一入口）
        
        Args:
            audio_bytes: 音频文件的字节数据
            
        Returns:
            Dict 包含识别结果
        """
        # 延迟加载模型，避免启动时耗时/占用显存
        self.ensure_initialized()
        
        # 统一转成临时文件，方便不同引擎复用文件接口
        temp_audio_path = None
        try:
            temp_audio_path = self._save_temp_audio(audio_bytes)
            result = self._transcribe(temp_audio_path)
            
            logger.info(f'[ASR] 识别结果: {result.get("text", "")}')
            return result
            
        finally:
            # 清理临时文件
            if temp_audio_path and os.path.exists(temp_audio_path):
                try:
                    os.unlink(temp_audio_path)
                except Exception as e:
                    logger.warning(f'[ASR] 清理临时文件失败: {e}')

    def ensure_initialized(self):
        """Ensure ASR model is loaded exactly once."""
        if self._initialized:
            return
        self._load_model()
        self._initialized = True
    
    def _save_temp_audio(self, audio_bytes: bytes) -> str:
        """
        保存临时音频文件并转换为 wav 格式
        
        Args:
            audio_bytes: 音频字节数据
            
        Returns:
            临时文件路径
        """
        try:
            # 尝试读取音频并转换为 wav
            audio_stream = BytesIO(audio_bytes)
            data, samplerate = sf.read(audio_stream)
            
            # 创建临时 wav 文件
            temp_fd, temp_path = tempfile.mkstemp(suffix='.wav')
            os.close(temp_fd)
            
            sf.write(temp_path, data, samplerate)
            logger.debug(f'[ASR] 音频已保存: {temp_path}, 采样率: {samplerate}Hz')
            return temp_path
            
        except Exception as e:
            logger.warning(f'[ASR] 音频格式转换失败，保存原始格式: {e}')
            # 如果转换失败，直接保存原始字节
            temp_fd, temp_path = tempfile.mkstemp(suffix='.webm')
            os.close(temp_fd)
            
            with open(temp_path, 'wb') as f:
                f.write(audio_bytes)
            
            return temp_path
    
    def transcribe_text(self, audio_bytes: bytes) -> str:
        """
        简化接口：只返回识别的文本
        
        Args:
            audio_bytes: 音频文件的字节数据
            
        Returns:
            识别的文本字符串
        """
        result = self.transcribe(audio_bytes)
        return result.get("text", "")
    
    def set_language(self, language: str):
        """
        设置识别语言
        
        Args:
            language: 语言代码（如 'zh', 'en', 'auto'）
        """
        self.language = language
        logger.info(f'[ASR] 语言设置为: {language}')
    
    def get_info(self) -> Dict[str, Any]:
        """
        获取 ASR 引擎信息
        
        Returns:
            Dict 包含引擎信息
        """
        return {
            "engine": self.__class__.__name__,
            "language": self.language,
            "initialized": self._initialized
        }


__all__ = ["BaseASR"]
