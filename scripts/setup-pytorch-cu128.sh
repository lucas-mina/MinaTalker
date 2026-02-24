#!/bin/bash
# Install PyTorch with CUDA 12.8 for RTX 5090 / Blackwell (sm_120).
# Run from project root after: uv sync (or after setup-env.sh).
# This replaces the default cu124 torch with cu128 wheels.

set -e
cd "$(dirname "$0")/.."
echo "Installing PyTorch with CUDA 12.8 for RTX 5090..."
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
echo "Done. Reinstall avatar if needed: uv pip install -e src/avatars/wav2lip"
