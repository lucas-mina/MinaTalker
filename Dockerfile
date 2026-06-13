# syntax=docker/dockerfile:1
# MinaTalker — wav2lip + Agora RTC (Linux / NVIDIA GPU recommended)
#
# Fast rebuild tips:
#   set DOCKER_BUILDKIT=1
#   docker compose build          # deps layer cached when only src/config changed
#   docker compose up -d --build  # skip build if image exists
#
FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    MINATALKER_CONFIG=config/config_wav2lip.yaml

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3.10-venv \
    python3-pip \
    curl \
    ca-certificates \
    openssl \
    ffmpeg \
    libsndfile1 \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    git \
    && ln -sf /usr/bin/python3.10 /usr/local/bin/python3 \
    && ln -sf /usr/bin/python3.10 /usr/local/bin/python

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# --- Heavy deps layer: only bust when pyproject.toml / uv.lock change ---
COPY pyproject.toml ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv --python python3.10 \
    &&     uv sync --extra agora --no-install-project \
    && uv pip install elevenlabs

# --- App code: cheap rebuild when Python sources change ---
COPY src ./src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install -e src/avatars/wav2lip/

COPY config ./config
COPY web ./web
COPY scripts ./scripts
COPY docker/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh \
    && mkdir -p ssl_certs models agora_rtc_log data/records

EXPOSE 8010

ENTRYPOINT ["/entrypoint.sh"]
