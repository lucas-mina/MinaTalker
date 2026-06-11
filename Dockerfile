# MinaTalker — wav2lip + Agora RTC (Linux / NVIDIA GPU recommended)
FROM nvidia/cuda:12.8.0-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    MINATALKER_CONFIG=config/config_wav2lip.yaml

RUN apt-get update && apt-get install -y --no-install-recommends \
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
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.10 /usr/local/bin/python3 \
    && ln -sf /usr/bin/python3.10 /usr/local/bin/python

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN uv venv --python python3.10 \
    && uv sync --extra agora \
    && uv pip install -e src/avatars/wav2lip/ \
    && uv pip install funasr modelscope elevenlabs

COPY config ./config
COPY web ./web
COPY docker/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh \
    && mkdir -p ssl_certs models agora_rtc_log data/records

# config_wav2lip.yaml: app.listenport
EXPOSE 8010

ENTRYPOINT ["/entrypoint.sh"]
