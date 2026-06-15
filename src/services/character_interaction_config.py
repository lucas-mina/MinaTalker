"""Fetch and parse character voice config from the Minamina data API.

Mirrors the Flutter client:
``GET {AVATAR_SERVER}/characters/{id}/interaction-config``
→ ``voiceConfig`` → TTS provider / voice id / model / options.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional
from urllib.parse import quote

import aiohttp

from src.config.schema import Config
from src.tts.factory import known_tts_types
from src.utils.logging import logger

_INTERACTION_CONFIG_TIMEOUT_SEC = 15.0


@dataclass
class CharacterInteractionVoice:
    """Parsed ``voiceConfig`` from interaction-config JSON."""

    voice_id: Optional[str] = None
    provider: Optional[str] = None  # minimax | inworld | elevenlabs
    model_id: Optional[str] = None
    option: Optional[dict[str, Any]] = field(default=None, repr=False)
    elevenlabs_stability: Optional[float] = None
    elevenlabs_similarity_boost: Optional[float] = None
    elevenlabs_speed: Optional[float] = None
    minimax_language_boost: Optional[str] = None

    def has_overrides(self) -> bool:
        return bool(
            self.voice_id
            or self.provider
            or self.model_id
            or self.option
            or self.elevenlabs_stability is not None
            or self.elevenlabs_similarity_boost is not None
            or self.elevenlabs_speed is not None
            or self.minimax_language_boost
        )


def _parse_double(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _voice_id_from_map(data: Mapping[str, Any]) -> Optional[str]:
    raw = data.get("voiceId", data.get("voice_id"))
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _model_id_from_map(data: Mapping[str, Any]) -> Optional[str]:
    raw = data.get("modelId", data.get("model_id", data.get("model")))
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _option_from_map(data: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    raw = data.get("option", data.get("options"))
    if not isinstance(raw, Mapping):
        return None
    return dict(raw)


def _string_option(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_voice_config_from_json(payload: Mapping[str, Any]) -> CharacterInteractionVoice:
    """Read ``voiceConfig`` from interaction-config JSON (same precedence as Flutter)."""
    vc = payload.get("voiceConfig")
    if not isinstance(vc, Mapping):
        return CharacterInteractionVoice()

    mini = vc.get("minimax")
    if isinstance(mini, Mapping):
        option = _option_from_map(mini)
        voice_id = _voice_id_from_map(mini)
        if voice_id:
            return CharacterInteractionVoice(
                voice_id=voice_id,
                provider="minimax",
                model_id=_model_id_from_map(mini),
                option=option,
                minimax_language_boost=_string_option(
                    option.get("language_boost") if option else None
                ),
            )

    iw = vc.get("inworld")
    if isinstance(iw, Mapping):
        voice_id = _voice_id_from_map(iw)
        if voice_id:
            return CharacterInteractionVoice(
                voice_id=voice_id,
                provider="inworld",
                model_id=_model_id_from_map(iw),
                option=_option_from_map(iw),
            )

    el = vc.get("elevenlabs", vc.get("elevenLabs"))
    if isinstance(el, Mapping):
        option = _option_from_map(el)
        voice_id = _voice_id_from_map(el)
        model_id = _model_id_from_map(el)
        stability = _parse_double(option.get("stability") if option else None)
        similarity = _parse_double(option.get("similarity") if option else None)
        speed = _parse_double(option.get("speed") if option else None)
        if (
            voice_id
            or model_id
            or option
            or stability is not None
            or similarity is not None
            or speed is not None
        ):
            return CharacterInteractionVoice(
                voice_id=voice_id,
                provider="elevenlabs",
                model_id=model_id,
                option=option,
                elevenlabs_stability=stability,
                elevenlabs_similarity_boost=similarity,
                elevenlabs_speed=speed,
            )

    return CharacterInteractionVoice()


def interaction_config_url(avatar_api_base: str, character_id: str) -> str:
    base = avatar_api_base.rstrip("/")
    cid = quote(character_id.strip(), safe="")
    return f"{base}/characters/{cid}/interaction-config"


async def fetch_character_interaction_voice(
    avatar_api_base: str,
    character_id: str,
    *,
    access_token: str | None = None,
) -> CharacterInteractionVoice | None:
    """``GET /characters/{id}/interaction-config`` with optional Bearer token."""
    cid = character_id.strip()
    if not cid:
        logger.warning("fetch_character_interaction_voice: empty character_id")
        return None

    url = interaction_config_url(avatar_api_base, cid)
    headers = {"Accept": "application/json"}
    token = (access_token or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    logger.info("Fetching interaction-config %s bearer=%s", url, bool(token))

    try:
        timeout = aiohttp.ClientTimeout(total=_INTERACTION_CONFIG_TIMEOUT_SEC)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as response:
                body = await response.text()
                if response.status != 200:
                    logger.warning(
                        "interaction-config HTTP %s for character_id=%s: %s",
                        response.status,
                        cid,
                        body[:500],
                    )
                    return None
                try:
                    decoded = await response.json(content_type=None)
                except Exception:
                    logger.warning(
                        "interaction-config invalid JSON for character_id=%s: %s",
                        cid,
                        body[:500],
                    )
                    return None
    except aiohttp.ClientError as exc:
        logger.warning(
            "interaction-config request failed character_id=%s url=%s: %s",
            cid,
            url,
            exc,
        )
        return None
    except Exception:
        logger.exception(
            "interaction-config unexpected error character_id=%s url=%s",
            cid,
            url,
        )
        return None

    if not isinstance(decoded, Mapping):
        logger.warning(
            "interaction-config response not an object for character_id=%s",
            cid,
        )
        return None

    voice = parse_voice_config_from_json(decoded)
    logger.info(
        "interaction-config character_id=%s provider=%s voice_id=%s model=%s",
        cid,
        voice.provider or "(unchanged)",
        voice.voice_id or "(unchanged)",
        voice.model_id or "(default)",
    )
    return voice


def apply_character_interaction_voice(
    session_config: Config,
    voice: CharacterInteractionVoice,
) -> bool:
    """Apply parsed interaction-config voice onto session TTS settings."""
    if not voice.has_overrides():
        return False

    known = known_tts_types()
    changed = False

    if voice.provider:
        provider = voice.provider.strip().lower()
        if provider in known:
            session_config.tts.type = provider
            changed = True
        else:
            logger.warning(
                "interaction-config unknown tts provider=%r; known=%s",
                provider,
                sorted(known),
            )

    if voice.voice_id:
        session_config.tts.ref_file = voice.voice_id
        changed = True

    if voice.model_id:
        session_config.tts.model = voice.model_id
        changed = True

    if voice.minimax_language_boost:
        session_config.tts.language_boost = voice.minimax_language_boost
        changed = True

    if voice.elevenlabs_stability is not None:
        session_config.tts.stability = voice.elevenlabs_stability
        changed = True

    if voice.elevenlabs_similarity_boost is not None:
        session_config.tts.similarity_boost = voice.elevenlabs_similarity_boost
        changed = True

    if voice.elevenlabs_speed is not None:
        session_config.tts.speed = voice.elevenlabs_speed
        changed = True

    return changed
