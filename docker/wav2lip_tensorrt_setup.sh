#!/usr/bin/env bash
# Wav2Lip TensorRT prep: ONNX export + ORT provider check (when config backend=tensorrt).
set -euo pipefail

_wav2lip_tensorrt_prepare() {
  uv run python - <<'PY'
import os
import subprocess
import sys

import yaml

cfg_path = os.environ.get("MINATALKER_CONFIG", "config/config_wav2lip.yaml")
if not os.path.isfile(cfg_path):
    print(f"[entrypoint] WARNING: config not found for TRT setup: {cfg_path}", file=sys.stderr)
    sys.exit(0)

with open(cfg_path, encoding="utf-8") as f:
    cfg = yaml.safe_load(f) or {}

model = cfg.get("model") or {}
wav2lip = model.get("wav2lip") or {}
backend = str(wav2lip.get("backend") or "pytorch").strip().lower()
if backend != "tensorrt":
    print(f"[entrypoint] Wav2Lip backend={backend} (skip TensorRT setup)")
    sys.exit(0)

batch_size = int(model.get("batch_size") or 4)
onnx_path = (wav2lip.get("onnx_path") or "").strip()
if not onnx_path:
    onnx_path = f"./models/wav2lip_b{batch_size}_s256.onnx"

if os.path.isfile(onnx_path):
    print(f"[entrypoint] Wav2Lip ONNX ready: {onnx_path}")
else:
    ckpt = "models/wav2lip.pth"
    if not os.path.isfile(ckpt):
        print(
            f"[entrypoint] ERROR: backend=tensorrt but missing {onnx_path} and {ckpt}",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"[entrypoint] Exporting Wav2Lip ONNX batch={batch_size} -> {onnx_path}")
    subprocess.check_call(
        [
            sys.executable,
            "scripts/export_wav2lip_onnx.py",
            "--checkpoint",
            ckpt,
            "--batch-size",
            str(batch_size),
            "--output",
            onnx_path,
        ]
    )

try:
    import onnxruntime as ort
except ImportError as exc:
    print(f"[entrypoint] ERROR: TensorRT deps missing: {exc}", file=sys.stderr)
    sys.exit(1)

trt_lib_dir = os.environ.get(
    "TENSORRT_LIB_DIR",
    "/app/.venv/lib/python3.10/site-packages/tensorrt_libs",
)
nvinfer = os.path.join(trt_lib_dir, "libnvinfer.so.10")
if not os.path.isfile(nvinfer):
    print(
        f"[entrypoint] ERROR: {nvinfer} missing (ORT TensorRT EP needs TRT 10.x). "
        "Rebuild image with tensorrt-cu12-libs<11.",
        file=sys.stderr,
    )
    sys.exit(1)

providers = ort.get_available_providers()
print(f"[entrypoint] ONNX Runtime providers: {providers}")
if "TensorrtExecutionProvider" not in providers:
    print(
        "[entrypoint] ERROR: TensorrtExecutionProvider unavailable. "
        "Rebuild image with --extra tensorrt or set backend=pytorch.",
        file=sys.stderr,
    )
    sys.exit(1)

cache = wav2lip.get("trt_cache_path") or "./models/trt_cache"
trt_fp16 = bool(wav2lip.get("trt_fp16", False))
os.makedirs(cache, exist_ok=True)
if os.path.isdir(cache) and os.listdir(cache) and not trt_fp16:
    print(
        f"[entrypoint] WARNING: trt_fp16=false but {cache} is non-empty; "
        "delete it if engines were built with FP16",
        file=sys.stderr,
    )
print(f"[entrypoint] Wav2Lip TensorRT ready (cache={cache}, trt_fp16={trt_fp16})")
PY
}
