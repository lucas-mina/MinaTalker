"""Client environment → Core LLM base URL mapping."""

from __future__ import annotations

from typing import Any

from src.utils.logging import logger

_ENV_BASE_URLS = {
    "dev": "https://dev.minamina.ai",
    "prd": "https://prd.minamina.ai",
}


def normalize_llm_base_url(base_url: str) -> str:
    clean = (base_url or "").strip().rstrip("/")
    if clean.endswith("/api-docs"):
        clean = clean[: -len("/api-docs")]
    return clean


def resolve_llm_base_url(environment: str | None, fallback: str) -> str:
    """Map Flutter ``environment`` (``dev`` | ``prd``) to Core base URL."""
    fb = normalize_llm_base_url(fallback) or "https://prd.minamina.ai"
    if environment is None:
        return fb
    key = str(environment).strip().lower()
    if not key:
        return fb
    resolved = _ENV_BASE_URLS.get(key)
    if resolved is None:
        logger.warning("Unknown LLM environment %r; using config base_url %s", environment, fb)
        return fb
    logger.info("LLM base_url from environment=%s → %s", key, resolved)
    return resolved


def resolve_llm_base_url_for_session(
    environment: str | None,
    avatar_stream: Any | None,
    fallback: str,
) -> str:
    """Prefer request ``environment``, else last value stored on the avatar session."""
    env = environment
    if (env is None or not str(env).strip()) and avatar_stream is not None:
        env = getattr(avatar_stream, "client_environment", None)
    return resolve_llm_base_url(env, fallback)
