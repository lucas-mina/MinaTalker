"""
SenseVoice ASR engine (FunASR-based).

SenseVoiceSmall is a multilingual speech recognition model from
Alibaba DAMO Academy (iic/SenseVoiceSmall). It supports:
  - zh, en, ja, ko, yue (Cantonese)
  - Language auto-detection
  - Emotion and audio-event tags (stripped to plain text here)

The model can be loaded from a local path (e.g. ./models/iic/SenseVoiceSmall)
or from a ModelScope/HuggingFace hub ID (e.g. iic/SenseVoiceSmall).

Config example (config.yaml):
    asr:
      type: sensevoice
      model_name: "iic/SenseVoiceSmall"   # local path or hub ID
      language: auto                       # zh | en | ja | ko | yue | auto
      device: auto
      # Optional SenseVoice tuning:
      sensevoice_use_itn: true             # inverse text normalisation
      sensevoice_batch_size_s: 60         # batch long audio by seconds (optional)
      sensevoice_merge_vad: false         # merge VAD segments (optional)
      sensevoice_merge_length_s: 15       # min merge length in seconds (optional)
"""

import re
from typing import Dict, Any, Optional

import torch

from src.utils.logging import logger
from src.asr.base import BaseASR

# SenseVoice output contains special tags like <|zh|>, <|HAPPY|>, <|Speech|>, etc.
# We strip them to return clean transcript text.
_TAG_RE = re.compile(r"<\|[^|]*\|>")


def _strip_tags(text: str) -> str:
    return _TAG_RE.sub("", text).strip()


# SenseVoice language code mapping
_LANG_MAP = {
    "zh": "zh",
    "en": "en",
    "ja": "ja",
    "ko": "ko",
    "yue": "yue",
    "auto": "auto",
}


class SenseVoiceASR(BaseASR):
    """
    SenseVoice ASR engine via FunASR AutoModel.

    Loads SenseVoiceSmall either from a local directory or a
    ModelScope hub ID. Strips emotion/event tags from the output.
    Supports config-driven options: use_itn, batch_size_s, merge_vad, merge_length_s.
    """

    def __init__(
        self,
        config=None,
        model_name: str = "iic/SenseVoiceSmall",
        device: str = "auto",
        language: Optional[str] = None,
    ):
        """
        Args:
            config: global config object (optional)
            model_name: local model directory or ModelScope/HF model ID.
                        Defaults to "iic/SenseVoiceSmall" (hub download).
                        Pass a local path such as "./models/iic/SenseVoiceSmall"
                        to use a cached copy.
            device: 'auto' | 'cpu' | 'cuda'
            language: initial language (zh | en | ja | ko | yue | auto). If None, uses config or "zh".
        """
        super().__init__(config)
        self.model_name = model_name
        if device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
        self.model = None
        if language is not None:
            self.language = _LANG_MAP.get(language, language)
        elif config and getattr(config, "asr", None):
            cfg_lang = getattr(config.asr, "language", None)
            if cfg_lang:
                self.language = _LANG_MAP.get(cfg_lang, cfg_lang)
        logger.info(f"[SenseVoice] model_name={model_name}, device={self.device}, language={self.language}")

    # ------------------------------------------------------------------
    # BaseASR interface
    # ------------------------------------------------------------------

    def _load_model(self):
        """Load SenseVoiceSmall via FunASR AutoModel."""
        try:
            from funasr import AutoModel
        except ImportError:
            raise ImportError(
                "SenseVoice requires FunASR.\n"
                "  pip install funasr"
            )

        # Resolve the model path: prefer a local copy under models/ if it exists
        model_path = self._resolve_model_path(self.model_name)
        logger.info(f"[SenseVoice] Loading model from: {model_path}")
        try:
            common_kwargs = {
                "model": model_path,
                # Avoid update checks at startup and keep startup deterministic.
                "disable_update": True,
                # Use local/built-in implementation first to avoid remote import failures
                # like "No module named 'model'" when local checkpoints are present.
                "trust_remote_code": False,
                # Disable FunASR's built-in VAD/punc pipelines — we handle VAD
                # ourselves with SileroVAD and don't need punctuation restoration here.
                "vad_model": None,
                "punc_model": None,
                "device": self.device,
            }
            self.model = AutoModel(**common_kwargs)
            logger.info("[SenseVoice] Model loaded successfully")
        except Exception as exc:
            logger.error(f"[SenseVoice] Failed to load model: {exc}")
            raise

    @staticmethod
    def _resolve_model_path(model_name: str) -> str:
        """
        Resolve a model name to an absolute local path if a local copy exists
        under the project's models/ directory, otherwise return the name as-is
        (FunASR will attempt a hub download).

        e.g. "iic/SenseVoiceSmall"  →  "<project>/models/iic/SenseVoiceSmall"
             "/abs/path/to/model"   →  "/abs/path/to/model"   (unchanged)
        """
        from pathlib import Path
        from src.utils.paths import get_models_dir

        p = Path(model_name)
        if p.is_absolute() and p.exists():
            return str(p)

        candidate = get_models_dir() / model_name
        if candidate.exists():
            return str(candidate)

        return model_name  # fall through to hub download

    def _get_sensevoice_options(self) -> Dict[str, Any]:
        """Build generate() kwargs from config (SenseVoice-specific options)."""
        opts = {
            "use_itn": True,
            "ban_emo_unk": True,
        }
        if not self.config or not getattr(self.config, "asr", None):
            return opts
        asr = self.config.asr
        if getattr(asr, "sensevoice_use_itn", True) is not None:
            opts["use_itn"] = bool(getattr(asr, "sensevoice_use_itn", True))
        if getattr(asr, "sensevoice_batch_size_s", None) is not None:
            opts["batch_size_s"] = int(asr.sensevoice_batch_size_s)
        if getattr(asr, "sensevoice_merge_vad", None) is not None:
            opts["merge_vad"] = bool(asr.sensevoice_merge_vad)
        if getattr(asr, "sensevoice_merge_length_s", None) is not None:
            opts["merge_length_s"] = float(asr.sensevoice_merge_length_s)
        return opts

    def _transcribe(self, audio_path: str) -> Dict[str, Any]:
        """
        Run SenseVoice inference on a WAV file.

        Args:
            audio_path: path to the WAV file (written by BaseASR.transcribe)

        Returns:
            dict with keys: text, language
        """
        lang = _LANG_MAP.get(self.language, "auto")
        gen_kwargs = self._get_sensevoice_options()
        gen_kwargs["input"] = audio_path
        gen_kwargs["language"] = lang

        result = self.model.generate(**gen_kwargs)

        if result and len(result) > 0:
            raw_text = result[0].get("text", "")
            clean_text = _strip_tags(raw_text)
            detected_lang = result[0].get("language", lang)
            logger.debug(f"[SenseVoice] raw={raw_text!r}  clean={clean_text!r}")
            return {
                "text": clean_text,
                "language": detected_lang if detected_lang else lang,
            }

        return {"text": "", "language": lang}

    def get_info(self) -> Dict[str, Any]:
        info = super().get_info()
        info.update({
            "model_name": self.model_name,
            "device": self.device,
        })
        return info
