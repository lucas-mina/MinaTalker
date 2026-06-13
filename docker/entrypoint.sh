#!/usr/bin/env bash
set -euo pipefail

CONFIG_FILE="${MINATALKER_CONFIG:-config/config_wav2lip.yaml}"
cd /app

# Agora native libs (Linux only)
if uv run python -c "import agora" 2>/dev/null; then
  AGORA_SDK="$(uv run python -c "import pathlib, agora; print(pathlib.Path(agora.__file__).resolve().parent / 'agora_sdk')")"
  if [[ -d "${AGORA_SDK}" ]]; then
    export LD_LIBRARY_PATH="${AGORA_SDK}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
    echo "[entrypoint] LD_LIBRARY_PATH includes Agora SDK: ${AGORA_SDK}"
  fi
fi

# Self-signed TLS for config app.ssl=true (paths match config_wav2lip.yaml)
SSL_CERT="ssl_certs/certificate.crt"
SSL_KEY="ssl_certs/private.key"
if [[ ! -f "${SSL_CERT}" || ! -f "${SSL_KEY}" ]]; then
  echo "[entrypoint] Generating self-signed TLS cert in ssl_certs/ ..."
  mkdir -p ssl_certs
  openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "${SSL_KEY}" \
    -out "${SSL_CERT}" \
    -days 365 \
    -subj "/CN=${SSL_CN:-localhost}"
fi

sync_models_from_host() {
  local host_dir="/models-host"
  local app_dir="/app/models"
  local stamp_file="${app_dir}/.sync_stamp"

  if [[ ! -f "${host_dir}/wav2lip.pth" ]]; then
    echo "[entrypoint] WARNING: ${host_dir}/wav2lip.pth missing. Set MINATALKER_PROJECT_DIR and ensure host ./models is mounted."
    return 1
  fi

  mkdir -p "${app_dir}"
  local host_stamp
  host_stamp="$(stat -c '%s-%Y' "${host_dir}/wav2lip.pth")"
  local force_sync="${SYNC_MODELS:-0}"

  if [[ "${force_sync}" == "1" ]] \
    || [[ ! -f "${app_dir}/wav2lip.pth" ]] \
    || [[ ! -f "${stamp_file}" ]] \
    || [[ "$(cat "${stamp_file}" 2>/dev/null || true)" != "${host_stamp}" ]]; then
    echo "[entrypoint] Syncing models ${host_dir} -> ${app_dir} (avoids Windows bind-mount I/O errors)..."
    cp -a "${host_dir}/." "${app_dir}/"
    echo "${host_stamp}" > "${stamp_file}"
    echo "[entrypoint] Model sync complete ($(stat -c%s "${app_dir}/wav2lip.pth") bytes)"
  else
    echo "[entrypoint] Models volume OK (wav2lip.pth $(stat -c%s "${app_dir}/wav2lip.pth") bytes)"
  fi
}

sync_models_from_host || true

if [[ ! -f "models/wav2lip.pth" ]]; then
  echo "[entrypoint] WARNING: models/wav2lip.pth still missing after sync"
fi

if [[ ! -d "data/avatars" ]] || [[ -z "$(ls -A data/avatars 2>/dev/null || true)" ]]; then
  echo "[entrypoint] WARNING: data/avatars empty or missing. Mount host repo ./data -> /app/data"
fi

echo "[entrypoint] models: $(ls -la models 2>/dev/null | head -5 || echo '(unreadable)')"
echo "[entrypoint] data/avatars: $(ls data/avatars 2>/dev/null | head -5 || echo '(empty)')"

echo "[entrypoint] Starting MinaTalker with ${CONFIG_FILE}"
exec uv run python -m src.server.app --config "${CONFIG_FILE}"
