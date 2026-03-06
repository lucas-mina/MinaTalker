"""
FunASR 引擎实现
阿里达摩院的 FunASR，专注中文识别
"""

from typing import Dict, Any

from src.utils.logging import logger
from src.asr.base import BaseASR


class FunASR(BaseASR):
    """
    FunASR 引擎（阿里达摩院）
    
    专注中文语音识别，速度快，准确度高
    """
    
    def __init__(self, config=None, model_name: str = "paraformer-zh", device: str = "auto"):
        """
        初始化 FunASR
        
        Args:
            config: 配置对象
            model_name: 模型名称（默认 paraformer-zh）
            device: 'auto' | 'cpu' | 'cuda'
        """
        super().__init__(config)
        
        self.model_name = model_name
        self.device = device
        self.model = None
        
        logger.info(f'[FunASR] 模型: {model_name}')
    
    def _load_model(self):
        """加载 FunASR 模型"""
        try:
            from funasr import AutoModel
            logger.info(f'[FunASR] 正在加载模型: {self.model_name}')
            self.model = AutoModel(model=self.model_name)
            logger.info('[FunASR] 模型加载成功')
            
        except ImportError:
            raise ImportError(
                "请安装 FunASR:\n"
                "  pip install funasr"
            )
        except Exception as e:
            logger.error(f'[FunASR] 模型加载失败: {e}')
            raise
    
    def _transcribe(self, audio_path: str) -> Dict[str, Any]:
        """
        使用 FunASR 识别音频
        
        Args:
            audio_path: 音频文件路径
            
        Returns:
            识别结果字典
        """
        result = self.model.generate(input=audio_path)
        
        if result and len(result) > 0:
            text = result[0].get("text", "")
            return {
                "text": text.strip(),
                "language": "zh"
            }
        
        return {
            "text": "",
            "language": "zh"
        }
    
    def get_info(self) -> Dict[str, Any]:
        """获取引擎信息"""
        info = super().get_info()
        info.update({
            "model_name": self.model_name
        })
        return info
