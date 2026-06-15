"""Optional GFPGAN face restoration for Wav2Lip predicted mouth crops."""

from __future__ import annotations

import os
import threading
from typing import Optional

import cv2
import numpy as np

from src.utils.logging import logger

# Serialize shared Wav2Lip + GFPGAN GPU work across concurrent sessions.
GPU_INFER_LOCK = threading.RLock()

# Same device selection as avatar.py (import would be circular).
_DEVICE = "cuda" if __import__("torch").cuda.is_available() else "cpu"

_SHARED_ENHANCER: Optional["GFPGANEnhancer"] = None
_SHARED_ENHANCER_KEY: tuple | None = None


def _patch_torchvision_for_basicsr() -> None:
    """basicsr 1.4.x imports removed torchvision.transforms.functional_tensor."""
    import sys
    import types

    key = "torchvision.transforms.functional_tensor"
    if key in sys.modules:
        return
    import torchvision.transforms.functional as F

    shim = types.ModuleType(key)
    shim.rgb_to_grayscale = F.rgb_to_grayscale
    sys.modules[key] = shim


class GFPGANEnhancer:
    """Lazy-load GFPGAN and enhance aligned 256x256 Wav2Lip face crops."""

    __slots__ = ("enabled", "_restorer")

    def __init__(
        self,
        *,
        enabled: bool = False,
        model_path: str = "./models/GFPGANv1.4.pth",
        arch: str = "clean",
        channel_multiplier: int = 2,
        upscale: int = 1,
    ) -> None:
        self.enabled = bool(enabled)
        self._restorer = None

        if not self.enabled:
            return

        if _DEVICE != "cuda":
            logger.warning("GFPGAN requested but CUDA unavailable; face enhancement disabled")
            self.enabled = False
            return

        if not os.path.isfile(model_path):
            logger.error(
                "GFPGAN enabled but weights missing at %s — download GFPGANv1.4.pth",
                model_path,
            )
            self.enabled = False
            return

        try:
            _patch_torchvision_for_basicsr()
            from gfpgan import GFPGANer
        except ImportError:
            logger.error(
                "GFPGAN enabled but package not installed — "
                "run: uv pip install gfpgan basicsr facexlib"
            )
            self.enabled = False
            return

        try:
            self._restorer = GFPGANer(
                model_path=model_path,
                upscale=upscale,
                arch=arch,
                channel_multiplier=channel_multiplier,
                bg_upsampler=None,
            )
        except Exception:
            logger.exception("Failed to load GFPGAN from %s", model_path)
            self.enabled = False
            return

        logger.info("GFPGAN loaded: path=%s arch=%s upscale=%d", model_path, arch, upscale)

    def warm_up(self, size: int = 256) -> None:
        if not self.enabled or self._restorer is None:
            return
        dummy = np.zeros((size, size, 3), dtype=np.uint8)
        try:
            self.enhance(dummy)
            logger.info("GFPGAN warm-up done (%dx%d)", size, size)
        except Exception:
            logger.exception("GFPGAN warm-up failed")

    def enhance(self, face_bgr: np.ndarray, *, _lock: bool = True) -> np.ndarray:
        if not self.enabled or self._restorer is None:
            return face_bgr

        if face_bgr.ndim != 3 or face_bgr.shape[2] != 3:
            logger.warning("GFPGAN skip: expected HxWx3 BGR, got shape %s", face_bgr.shape)
            return face_bgr

        try:
            if _lock:
                cm = GPU_INFER_LOCK
            else:
                from contextlib import nullcontext
                cm = nullcontext()
            with cm:
                _, restored_faces, _ = self._restorer.enhance(
                    face_bgr,
                    has_aligned=True,
                    only_center_face=True,
                    paste_back=False,
                )
        except Exception:
            logger.exception("GFPGAN enhance failed")
            return face_bgr

        if not restored_faces:
            logger.warning("GFPGAN produced no restored face; using original crop")
            return face_bgr

        restored = restored_faces[0]
        out_h, out_w = restored.shape[:2]
        in_h, in_w = face_bgr.shape[:2]
        if (out_h, out_w) != (in_h, in_w):
            restored = cv2.resize(restored, (in_w, in_h), interpolation=cv2.INTER_LINEAR)

        return restored

    def enhance_batch(self, faces: list[np.ndarray]) -> list[np.ndarray]:
        """Enhance a Wav2Lip batch under one GPU lock (avoids per-frame lock overhead)."""
        if not self.enabled or self._restorer is None:
            return faces
        with GPU_INFER_LOCK:
            return [self.enhance(face, _lock=False) for face in faces]


def build_gfpgan_enhancer(cfg) -> Optional[GFPGANEnhancer]:
    """Return a process-wide shared GFPGAN instance (one GPU copy for all sessions)."""
    global _SHARED_ENHANCER, _SHARED_ENHANCER_KEY
    wav2lip_cfg = getattr(cfg, "wav2lip", None)
    gfpgan_cfg = getattr(wav2lip_cfg, "gfpgan", None) if wav2lip_cfg is not None else None
    if gfpgan_cfg is None or not getattr(gfpgan_cfg, "enabled", False):
        return None

    key = (
        gfpgan_cfg.model_path,
        gfpgan_cfg.arch,
        gfpgan_cfg.channel_multiplier,
        gfpgan_cfg.upscale,
    )
    with GPU_INFER_LOCK:
        if _SHARED_ENHANCER is None or _SHARED_ENHANCER_KEY != key:
            enhancer = GFPGANEnhancer(
                enabled=gfpgan_cfg.enabled,
                model_path=gfpgan_cfg.model_path,
                arch=gfpgan_cfg.arch,
                channel_multiplier=gfpgan_cfg.channel_multiplier,
                upscale=gfpgan_cfg.upscale,
            )
            if not enhancer.enabled:
                return None
            _SHARED_ENHANCER = enhancer
            _SHARED_ENHANCER_KEY = key
            logger.info("GFPGAN shared instance ready for all sessions")
        return _SHARED_ENHANCER
