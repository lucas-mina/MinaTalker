"""Wav2Lip inference via ONNX Runtime + TensorRT Execution Provider."""

from __future__ import annotations

import os
from typing import Any

import torch

from src.utils.logging import logger


def default_onnx_path(*, batch_size: int, face_size: int, models_dir: str = "./models") -> str:
    return os.path.join(models_dir, f"wav2lip_b{batch_size}_s{face_size}.onnx")


class Wav2LipTensorRTModel:
    """ONNX Runtime session with TensorRT EP; callable like ``Wav2Lip`` for (mel, face)."""

    backend = "tensorrt"

    def __init__(self, session: Any, *, mel_name: str, face_name: str, output_name: str, device: str):
        self._session = session
        self._mel_name = mel_name
        self._face_name = face_name
        self._output_name = output_name
        self._device = device

    @classmethod
    def load(
        cls,
        onnx_path: str,
        *,
        trt_cache_path: str,
        trt_fp16: bool,
        device: str,
    ) -> "Wav2LipTensorRTModel":
        if device != "cuda":
            raise RuntimeError(
                "Wav2Lip tensorrt backend requires CUDA; "
                "set model.wav2lip.backend=pytorch for CPU/MPS."
            )
        if not os.path.isfile(onnx_path):
            raise FileNotFoundError(
                f"Wav2Lip ONNX not found: {onnx_path}. "
                "Export with: uv run python scripts/export_wav2lip_onnx.py "
                "--checkpoint ./models/wav2lip.pth --batch-size <model.batch_size>"
            )

        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise RuntimeError(
                "onnxruntime-gpu is required for model.wav2lip.backend=tensorrt. "
                "Install: uv sync --extra tensorrt"
            ) from exc

        trt_lib_dir = os.environ.get("TENSORRT_LIB_DIR")
        if trt_lib_dir:
            prev = os.environ.get("LD_LIBRARY_PATH", "")
            if trt_lib_dir not in prev.split(":"):
                os.environ["LD_LIBRARY_PATH"] = (
                    f"{trt_lib_dir}:{prev}" if prev else trt_lib_dir
                )

        available = ort.get_available_providers()
        if "TensorrtExecutionProvider" not in available:
            raise RuntimeError(
                "TensorrtExecutionProvider not available "
                f"(providers={available}). Install TensorRT + onnxruntime-gpu, "
                "or set model.wav2lip.backend=pytorch."
            )

        os.makedirs(trt_cache_path, exist_ok=True)
        trt_opts: dict[str, Any] = {
            "trt_engine_cache_enable": True,
            "trt_engine_cache_path": os.path.abspath(trt_cache_path),
            "trt_fp16_enable": bool(trt_fp16),
            "trt_max_workspace_size": 2 * 1024 * 1024 * 1024,
        }
        providers = [
            ("TensorrtExecutionProvider", trt_opts),
            "CUDAExecutionProvider",
        ]
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        logger.info(
            "Loading Wav2Lip TensorRT session onnx=%s cache=%s fp16=%s",
            onnx_path,
            trt_cache_path,
            trt_fp16,
        )
        session = ort.InferenceSession(
            onnx_path,
            sess_options=sess_options,
            providers=providers,
        )
        active = session.get_providers()
        logger.info("Wav2Lip ORT active providers: %s", active)
        if active[0] != "TensorrtExecutionProvider":
            logger.warning(
                "Wav2Lip ORT did not select TensorrtExecutionProvider first; got %s",
                active[0],
            )

        inputs = {i.name: i for i in session.get_inputs()}
        outputs = session.get_outputs()
        if len(inputs) < 2 or not outputs:
            raise RuntimeError(f"Unexpected Wav2Lip ONNX IO: inputs={list(inputs)} outputs={outputs}")

        mel_name = _pick_input_name(inputs, preferred=("mel", "audio_sequences"))
        face_name = _pick_input_name(inputs, preferred=("face", "face_sequences"), skip={mel_name})
        output_name = outputs[0].name

        return cls(
            session,
            mel_name=mel_name,
            face_name=face_name,
            output_name=output_name,
            device=device,
        )

    def __call__(self, mel_batch: torch.Tensor, img_batch: torch.Tensor) -> torch.Tensor:
        mel_np = mel_batch.detach().float().contiguous().cpu().numpy()
        img_np = img_batch.detach().float().contiguous().cpu().numpy()
        out = self._session.run(
            [self._output_name],
            {self._mel_name: mel_np, self._face_name: img_np},
        )[0]
        return torch.from_numpy(out).to(device=self._device, dtype=torch.float32)


def _pick_input_name(
    inputs: dict[str, Any],
    *,
    preferred: tuple[str, ...],
    skip: set[str] | None = None,
) -> str:
    skip = skip or set()
    names = [n for n in inputs if n not in skip]
    for key in preferred:
        for name in names:
            if key in name.lower():
                return name
    if not names:
        raise RuntimeError(f"No ONNX inputs left after skip={skip}")
    return names[0]
