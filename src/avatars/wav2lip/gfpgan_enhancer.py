"""Optional GFPGAN face restoration for Wav2Lip mouth crops.

Lip-sync: blend GFPGAN lightly into a tight mouth band so Wav2Lip motion stays natural.
"""

from __future__ import annotations

import hashlib
import os
import threading
from collections import OrderedDict
from contextlib import nullcontext
from typing import Optional

import cv2
import numpy as np

from src.utils.logging import logger

# Serialize shared Wav2Lip + GFPGAN GPU work across concurrent sessions.
GPU_INFER_LOCK = threading.RLock()

_DEVICE = "cuda" if __import__("torch").cuda.is_available() else "cpu"

_SHARED_ENHANCER: Optional["GFPGANEnhancer"] = None
_SHARED_ENHANCER_KEY: tuple | None = None

GFPGAN_V14_URL = (
    "https://github.com/TencentARC/GFPGAN/releases/download/v1.3.4/GFPGANv1.4.pth"
)


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


class _CropCache:
    """Small LRU cache for identical Wav2Lip mouth crops."""

    __slots__ = ("_max", "_data")

    def __init__(self, max_entries: int = 64) -> None:
        self._max = max(0, int(max_entries))
        self._data: OrderedDict[str, np.ndarray] = OrderedDict()

    def get(self, key: str) -> np.ndarray | None:
        if self._max <= 0:
            return None
        hit = self._data.get(key)
        if hit is not None:
            self._data.move_to_end(key)
        return hit

    def put(self, key: str, value: np.ndarray) -> None:
        if self._max <= 0:
            return
        self._data[key] = value
        self._data.move_to_end(key)
        while len(self._data) > self._max:
            self._data.popitem(last=False)


class GFPGANEnhancer:
    """GFPGAN on aligned Wav2Lip face crops; mouth band lightly blended for lip-sync."""

    __slots__ = (
        "enabled",
        "use_amp",
        "enhance_weight",
        "adaptive_weight",
        "mouth_only",
        "mouth_mix",
        "mouth_region_start",
        "mouth_blend_rows",
        "_restorer",
        "_crop_cache",
        "_stats",
    )

    def __init__(
        self,
        *,
        enabled: bool = False,
        model_path: str = "./models/GFPGANv1.4.pth",
        arch: str = "clean",
        channel_multiplier: int = 2,
        upscale: int = 1,
        use_amp: bool = False,
        enhance_weight: float = 0.25,
        adaptive_weight: bool = False,
        mouth_only: bool = True,
        mouth_mix: float = 0.35,
        mouth_region_start: float = 0.58,
        mouth_blend_rows: int = 12,
        frame_cache_size: int = 64,
        fp16: bool | None = None,
    ) -> None:
        self.enabled = bool(enabled)
        if fp16 is not None:
            self.use_amp = bool(fp16)
        else:
            self.use_amp = bool(use_amp)
        self.enhance_weight = float(np.clip(enhance_weight, 0.05, 1.0))
        self.adaptive_weight = bool(adaptive_weight)
        self.mouth_only = bool(mouth_only)
        self.mouth_mix = float(np.clip(mouth_mix, 0.0, 1.0))
        self.mouth_region_start = float(np.clip(mouth_region_start, 0.45, 0.75))
        self.mouth_blend_rows = max(0, int(mouth_blend_rows))
        self._restorer = None
        self._crop_cache = _CropCache(frame_cache_size)
        self._stats = {
            "total": 0,
            "enhanced": 0,
            "cache_hits": 0,
            "flat_rejected": 0,
        }

        if not self.enabled:
            return

        if _DEVICE != "cuda":
            logger.warning("GFPGAN requested but CUDA unavailable; face enhancement disabled")
            self.enabled = False
            return

        if not os.path.isfile(model_path):
            logger.error(
                "GFPGAN enabled but weights missing at %s — download from %s",
                model_path,
                GFPGAN_V14_URL,
            )
            self.enabled = False
            return

        try:
            _patch_torchvision_for_basicsr()
            from gfpgan import GFPGANer  # noqa: F401
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

        logger.info(
            "GFPGAN loaded: path=%s fp32=%s mouth_only=%s mouth_mix=%.2f "
            "enhance_weight=%.2f region_start=%.2f",
            model_path,
            not self.use_amp,
            self.mouth_only,
            self.mouth_mix,
            self.enhance_weight,
            self.mouth_region_start,
        )

    def _mouth_split_y(self, height: int) -> int:
        return max(1, min(height - 1, int(height * self.mouth_region_start)))

    def _mouth_roi(self, face_bgr: np.ndarray) -> np.ndarray:
        return face_bgr[self._mouth_split_y(face_bgr.shape[0]) :, :]

    def _compose_mouth_only(self, original: np.ndarray, enhanced: np.ndarray) -> np.ndarray:
        """Blend GFPGAN into mouth band; preserve Wav2Lip lip geometry via mouth_mix."""
        h, w = original.shape[:2]
        mouth_y = self._mouth_split_y(h)
        if enhanced.shape[0] != h or enhanced.shape[1] != w:
            enhanced = cv2.resize(enhanced, (w, h), interpolation=cv2.INTER_LINEAR)

        mix = self.mouth_mix
        if mix <= 0.0:
            return original.copy()

        out = original.copy()
        mouth_orig = original[mouth_y:].astype(np.float32)
        mouth_enh = enhanced[mouth_y:].astype(np.float32)
        out[mouth_y:] = np.clip(
            mouth_orig * (1.0 - mix) + mouth_enh * mix,
            0,
            255,
        ).astype(np.uint8)

        blend = min(self.mouth_blend_rows, mouth_y)
        if blend > 0:
            for i in range(blend):
                row = mouth_y - blend + i
                row_mix = mix * (i + 1) / blend
                out[row] = cv2.addWeighted(
                    original[row],
                    1.0 - row_mix,
                    enhanced[row],
                    row_mix,
                    0,
                )
        return out

    @staticmethod
    def _crop_hash(face_bgr: np.ndarray) -> str:
        return hashlib.md5(face_bgr.tobytes(), usedforsecurity=False).hexdigest()[:16]

    @staticmethod
    def _adaptive_enhancement_weight(face_bgr: np.ndarray) -> float:
        gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
        blur_score = min(float(cv2.Laplacian(gray, cv2.CV_64F).var()) / 500.0, 1.0)
        if blur_score > 0.8:
            return 0.3
        if blur_score < 0.3:
            return 0.7
        return 0.5

    def _resolve_enhance_weight(self, eval_roi: np.ndarray) -> float:
        if self.adaptive_weight:
            return self._adaptive_enhancement_weight(eval_roi)
        return self.enhance_weight

    def warm_up(self, size: int = 256) -> None:
        if not self.enabled or self._restorer is None:
            return
        dummy = np.zeros((size, size, 3), dtype=np.uint8)
        try:
            self.enhance(dummy)
            logger.info(
                "GFPGAN warm-up done (%dx%d, fp32=%s mouth_mix=%.2f)",
                size,
                size,
                not self.use_amp,
                self.mouth_mix,
            )
        except Exception:
            logger.exception("GFPGAN warm-up failed")

    def _enhance_aligned(self, face_bgr: np.ndarray) -> np.ndarray:
        import torch

        if self.mouth_only and self.mouth_mix <= 0.0:
            return face_bgr

        eval_roi = self._mouth_roi(face_bgr) if self.mouth_only else face_bgr
        in_std = float(eval_roi.std())
        weight = self._resolve_enhance_weight(eval_roi)

        amp_ctx = (
            torch.amp.autocast("cuda", enabled=True)
            if self.use_amp and _DEVICE == "cuda"
            else nullcontext()
        )

        with amp_ctx:
            _, restored_faces, _ = self._restorer.enhance(
                face_bgr,
                has_aligned=True,
                only_center_face=True,
                paste_back=False,
                weight=weight,
            )

        if not restored_faces:
            logger.warning("GFPGAN produced no restored face; using Wav2Lip crop")
            return face_bgr

        restored = restored_faces[0]
        out_roi = self._mouth_roi(restored) if self.mouth_only else restored
        out_std = float(out_roi.std())
        if out_std < 12.0 or (in_std > 20.0 and out_std < in_std * 0.35):
            self._stats["flat_rejected"] += 1
            logger.warning(
                "GFPGAN output looks flat (in_std=%.1f out_std=%.1f weight=%.2f); using Wav2Lip crop",
                in_std,
                out_std,
                weight,
            )
            return face_bgr

        self._stats["enhanced"] += 1
        if self.mouth_only:
            return self._compose_mouth_only(face_bgr, restored)
        return restored

    def enhance(self, face_bgr: np.ndarray, *, _lock: bool = True) -> np.ndarray:
        if not self.enabled or self._restorer is None:
            return face_bgr

        if face_bgr.ndim != 3 or face_bgr.shape[2] != 3:
            logger.warning("GFPGAN skip: expected HxWx3 BGR, got shape %s", face_bgr.shape)
            return face_bgr

        self._stats["total"] += 1
        cache_key = self._crop_hash(face_bgr)
        cached = self._crop_cache.get(cache_key)
        if cached is not None:
            self._stats["cache_hits"] += 1
            return cached.copy()

        try:
            if _lock:
                cm = GPU_INFER_LOCK
            else:
                cm = nullcontext()
            with cm:
                restored = self._enhance_aligned(face_bgr)
        except Exception:
            logger.exception("GFPGAN enhance failed")
            return face_bgr

        out_h, out_w = restored.shape[:2]
        in_h, in_w = face_bgr.shape[:2]
        if (out_h, out_w) != (in_h, in_w):
            restored = cv2.resize(restored, (in_w, in_h), interpolation=cv2.INTER_LINEAR)

        self._crop_cache.put(cache_key, restored.copy())
        return restored

    def enhance_batch(self, faces: list[np.ndarray]) -> list[np.ndarray]:
        if not self.enabled or self._restorer is None:
            return faces
        with GPU_INFER_LOCK:
            return [self.enhance(face, _lock=False) for face in faces]


def build_gfpgan_enhancer(cfg) -> Optional[GFPGANEnhancer]:
    """Return a process-wide shared GFPGAN instance (one GPU copy for all sessions)."""
    global _SHARED_ENHANCER, _SHARED_ENHANCER_KEY
    wav2lip_cfg = getattr(cfg.model, "wav2lip", None)
    gfpgan_cfg = getattr(wav2lip_cfg, "gfpgan", None) if wav2lip_cfg is not None else None
    if gfpgan_cfg is None or not getattr(gfpgan_cfg, "enabled", False):
        return None

    use_amp = getattr(gfpgan_cfg, "use_amp", None)
    if use_amp is None:
        use_amp = bool(getattr(gfpgan_cfg, "fp16", False))

    key = (
        gfpgan_cfg.model_path,
        gfpgan_cfg.arch,
        gfpgan_cfg.channel_multiplier,
        gfpgan_cfg.upscale,
        bool(use_amp),
        float(getattr(gfpgan_cfg, "enhance_weight", 0.25)),
        bool(getattr(gfpgan_cfg, "adaptive_weight", False)),
        bool(getattr(gfpgan_cfg, "mouth_only", True)),
        float(getattr(gfpgan_cfg, "mouth_mix", 0.35)),
        float(getattr(gfpgan_cfg, "mouth_region_start", 0.58)),
        int(getattr(gfpgan_cfg, "mouth_blend_rows", 12)),
        int(getattr(gfpgan_cfg, "frame_cache_size", 64)),
    )
    with GPU_INFER_LOCK:
        if _SHARED_ENHANCER is None or _SHARED_ENHANCER_KEY != key:
            enhancer = GFPGANEnhancer(
                enabled=gfpgan_cfg.enabled,
                model_path=gfpgan_cfg.model_path,
                arch=gfpgan_cfg.arch,
                channel_multiplier=gfpgan_cfg.channel_multiplier,
                upscale=gfpgan_cfg.upscale,
                use_amp=bool(use_amp),
                enhance_weight=float(getattr(gfpgan_cfg, "enhance_weight", 0.25)),
                adaptive_weight=bool(getattr(gfpgan_cfg, "adaptive_weight", False)),
                mouth_only=bool(getattr(gfpgan_cfg, "mouth_only", True)),
                mouth_mix=float(getattr(gfpgan_cfg, "mouth_mix", 0.35)),
                mouth_region_start=float(getattr(gfpgan_cfg, "mouth_region_start", 0.58)),
                mouth_blend_rows=int(getattr(gfpgan_cfg, "mouth_blend_rows", 12)),
                frame_cache_size=int(getattr(gfpgan_cfg, "frame_cache_size", 64)),
            )
            if not enhancer.enabled:
                return None
            _SHARED_ENHANCER = enhancer
            _SHARED_ENHANCER_KEY = key
            logger.info(
                "GFPGAN shared instance ready (path=%s mouth_mix=%.2f enhance_weight=%.2f)",
                gfpgan_cfg.model_path,
                enhancer.mouth_mix,
                enhancer.enhance_weight,
            )
        return _SHARED_ENHANCER
