#!/usr/bin/env python3
"""Export Wav2Lip PyTorch checkpoint to fixed-batch ONNX for TensorRT EP."""

from __future__ import annotations

import argparse
import os
import sys

import torch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.avatars.wav2lip.avatar import WAV2LIP_FACE_SIZE, _load  # noqa: E402
from src.avatars.wav2lip.models import Wav2Lip  # noqa: E402
from src.avatars.wav2lip.trt_runner import default_onnx_path  # noqa: E402
from src.utils.logging import logger  # noqa: E402


def load_pytorch_checkpoint(path: str, device: torch.device) -> Wav2Lip:
    model = Wav2Lip()
    checkpoint = _load(path)
    state = checkpoint["state_dict"]
    cleaned = {k.replace("module.", ""): v for k, v in state.items()}
    model.load_state_dict(cleaned)
    model = model.to(device).eval().float()
    return model


def export_onnx(
    *,
    checkpoint: str,
    output: str,
    batch_size: int,
    face_size: int,
    opset: int,
) -> str:
    if not torch.cuda.is_available():
        logger.warning("CUDA not available; ONNX export on CPU may be slow")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model = load_pytorch_checkpoint(checkpoint, device)
    dummy_mel = torch.randn(batch_size, 1, 80, 16, device=device, dtype=torch.float32)
    dummy_face = torch.randn(batch_size, 6, face_size, face_size, device=device, dtype=torch.float32)

    os.makedirs(os.path.dirname(os.path.abspath(output)) or ".", exist_ok=True)
    with torch.no_grad():
        torch.onnx.export(
            model,
            (dummy_mel, dummy_face),
            output,
            input_names=["mel", "face"],
            output_names=["output"],
            dynamic_axes=None,
            opset_version=opset,
            do_constant_folding=True,
        )

    logger.info(
        "Exported Wav2Lip ONNX batch=%d face=%d -> %s",
        batch_size,
        face_size,
        output,
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Wav2Lip to ONNX for TensorRT")
    parser.add_argument("--checkpoint", default="./models/wav2lip.pth")
    parser.add_argument("--output", default="")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--face-size", type=int, default=WAV2LIP_FACE_SIZE)
    parser.add_argument("--opset", type=int, default=17)
    args = parser.parse_args()

    output = args.output or default_onnx_path(
        batch_size=args.batch_size,
        face_size=args.face_size,
    )
    export_onnx(
        checkpoint=args.checkpoint,
        output=output,
        batch_size=args.batch_size,
        face_size=args.face_size,
        opset=args.opset,
    )


if __name__ == "__main__":
    main()
