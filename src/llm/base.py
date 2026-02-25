"""LLM 基类模块"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Generator, Optional

from src.utils.logging import logger

if TYPE_CHECKING:
    from src.avatars.base import BaseAvatar


DEFAULT_SYSTEM_PROMPT = 'You are a helpful assistant.'
SENTENCE_DELIMITERS = ",.!;:，。！？：；"
MIN_SENTENCE_LENGTH = 10


def _is_noise(text: str, delimiters: str) -> bool:
    """Return True if text is purely punctuation/whitespace with no real word content."""
    stripped = text.strip()
    return bool(stripped) and all(c in delimiters + " " for c in stripped)


class TextStreamProcessor:
    """文本流处理器，负责分句和缓冲"""
    
    def __init__(self, delimiters: str = SENTENCE_DELIMITERS, min_length: int = MIN_SENTENCE_LENGTH):
        self.delimiters = delimiters
        self.min_length = min_length
        self.buffer = ""
    
    def process_chunk(self, text: str, callback) -> None:
        if not text:
            return
        
        # 以标点为分隔符，尽量保持语义完整再发给 TTS
        last_pos = 0
        for i, char in enumerate(text):
            if char in self.delimiters:
                sentence = self.buffer + text[last_pos:i + 1]
                last_pos = i + 1
                
                if len(sentence) >= self.min_length:
                    # Strip any leading noise prefix the buffer may have carried (e.g. "..")
                    sentence = sentence.lstrip(self.delimiters + " ") if _is_noise(self.buffer, self.delimiters) else sentence
                    if sentence:
                        callback(sentence)
                    self.buffer = ""
                else:
                    self.buffer = sentence
        
        self.buffer += text[last_pos:]
    
    def flush(self, callback) -> None:
        if self.buffer:
            # Drop fragments that are pure punctuation/whitespace noise (e.g. ".", "..")
            if not _is_noise(self.buffer, self.delimiters) and self.buffer.strip():
                callback(self.buffer)
            self.buffer = ""


class BaseLLM(ABC):
    """所有 LLM 引擎的基类"""
    
    def __init__(self, config, parent: Optional["BaseAvatar"] = None):
        self.config = config
        self.parent = parent
        self.system_prompt = self._load_system_prompt()
    
    def _load_system_prompt(self) -> str:
        from pathlib import Path

        config_dir = Path(__file__).parent.parent.parent / 'config'

        # Per-avatar prompt file takes priority when set on the session config
        configured = getattr(self.config, 'prompt_file', None) if self.config else None
        if configured:
            prompt_file = config_dir / configured
        else:
            prompt_file = config_dir / 'prompt.txt'

        try:
            text = prompt_file.read_text(encoding='utf-8').strip()
            logger.info(f"Loaded system prompt from: {prompt_file}")
            return text
        except FileNotFoundError:
            logger.warning(f"Prompt file not found: {prompt_file}, using default")
            return DEFAULT_SYSTEM_PROMPT
        except Exception as e:
            logger.error(f"Error loading prompt: {e}, using default")
            return DEFAULT_SYSTEM_PROMPT
    
    @abstractmethod
    def chat_stream(self, message: str, system_prompt: Optional[str] = None) -> Generator[str, None, None]:
        """流式调用 LLM，子类必须实现"""
        raise NotImplementedError("子类必须实现 chat_stream 方法")
    
    def generate_response(self, message: str, avatar_stream: Optional["BaseAvatar"] = None) -> str:
        """生成完整响应并推送到 avatar"""
        start_time = time.perf_counter()
        text_processor = TextStreamProcessor()
        full_response = ""
        
        target_avatar = avatar_stream or self.parent
        
        def send_to_avatar(text: str) -> None:
            if target_avatar:
                logger.info(f"Sending to avatar: {text}")
                target_avatar.put_msg_txt(text)
        
        try:
            # 记录首包延迟，方便定位 LLM 响应瓶颈
            first_chunk = True
            for chunk in self.chat_stream(message):
                if first_chunk:
                    first_chunk_time = time.perf_counter()
                    logger.info(f"Time to first chunk: {first_chunk_time - start_time:.3f}s")
                    first_chunk = False
                
                full_response += chunk
                
                if target_avatar:
                    text_processor.process_chunk(chunk, send_to_avatar)
            
            if target_avatar:
                text_processor.flush(send_to_avatar)
            
            total_time = time.perf_counter()
            logger.info(f"Total LLM response time: {total_time - start_time:.3f}s")
            
            return full_response
            
        except Exception as e:
            logger.error(f"Error in generate_response: {e}")
            raise
