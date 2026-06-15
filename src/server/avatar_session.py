"""Shared avatar session creation for WebRTC and Agora paths."""
from __future__ import annotations

import asyncio
from copy import deepcopy

from src.avatars.factory import create_avatar
from src.config.loader import find_avatar_entry_by_catalog_id, load_avatar_entries
from src.services.character_interaction_config import (
    apply_character_interaction_voice,
    fetch_character_interaction_voice,
)
from src.server.state import state
from src.utils.logging import logger


async def create_avatar_for_session(
    sessionid: int,
    avatar_id=None,
    access_token: str | None = None,
):
    """Resolve per-avatar config and create a BaseAvatar stream for sessionid."""
    session_config = deepcopy(state.config)
    session_avatar_data = state.avatar

    if avatar_id is not None:
        try:
            entries = load_avatar_entries()
            matched = find_avatar_entry_by_catalog_id(entries, avatar_id)

            if matched:
                catalog_char = matched.get("id")
                if catalog_char is not None and str(catalog_char).strip():
                    session_config.llm.character_id = str(catalog_char).strip()
                    logger.info(
                        "Using llm.character_id=%s from avatar_config (catalog id)",
                        session_config.llm.character_id,
                    )

                prompt_file = matched.get("prompt_file")
                if prompt_file:
                    session_config.prompt_file = prompt_file
                    logger.info("Using prompt_file=%s for avatar_id=%s", prompt_file, avatar_id)

                provider = (matched.get("tts_provider") or "").strip().lower()
                voice_id = (matched.get("tts_voice_id") or matched.get("elevenlabs_voice_id") or "").strip()
                tts_model = (matched.get("tts_model") or "").strip()
                language_boost = (matched.get("language_boost") or "").strip()
                if not provider and voice_id:
                    provider = "elevenlabs"
                if voice_id and provider in ("elevenlabs", "inworld", "minimax"):
                    session_config.tts.type = provider
                    session_config.tts.ref_file = voice_id
                    if tts_model:
                        session_config.tts.model = tts_model
                    if language_boost:
                        session_config.tts.language_boost = language_boost
                    logger.info(
                        "Using tts provider=%s voice_id=%s model=%s language_boost=%s for avatar_id=%s",
                        provider,
                        voice_id,
                        tts_model or "(default)",
                        language_boost or session_config.tts.language_boost,
                        avatar_id,
                    )
                elif voice_id:
                    logger.warning(
                        "Unknown tts_provider=%r for avatar_id=%s (voice_id=%s)",
                        provider,
                        avatar_id,
                        voice_id,
                    )

                model_avatar_id = matched.get("model_avatar_id")
                if model_avatar_id:
                    model_type = state.config.model.type
                    try:
                        if model_type == "wav2lip":
                            from src.avatars.wav2lip.avatar import load_avatar as _load_avatar
                        elif model_type == "musetalk":
                            from src.avatars.musetalk.avatar import load_avatar as _load_avatar
                        else:
                            _load_avatar = None

                        if _load_avatar:
                            logger.info(
                                "Loading avatar assets for model_avatar_id=%s (avatar_id=%s)",
                                model_avatar_id,
                                avatar_id,
                            )
                            session_avatar_data = await asyncio.get_event_loop().run_in_executor(
                                None, _load_avatar, model_avatar_id
                            )
                        else:
                            logger.warning(
                                "Per-avatar asset loading not supported for model type %s",
                                model_type,
                            )
                    except Exception:
                        logger.exception(
                            "Failed to load avatar assets for model_avatar_id=%s, using default.",
                            model_avatar_id,
                        )
            else:
                logger.warning("No avatar entry found for avatar_id=%s", avatar_id)

        except Exception as e:
            logger.warning("Failed to resolve avatar config for avatar_id=%s: %s", avatar_id, e)

    character_id = (session_config.llm.character_id or "").strip()
    avatar_api_base = (session_config.llm.base_url or "").strip()
    if character_id and avatar_api_base:
        try:
            voice = await fetch_character_interaction_voice(
                avatar_api_base,
                character_id,
                access_token=access_token,
            )
            if voice and apply_character_interaction_voice(session_config, voice):
                logger.info(
                    "Applied interaction-config voice for character_id=%s",
                    character_id,
                )
        except Exception:
            logger.exception(
                "Failed to apply interaction-config voice for character_id=%s",
                character_id,
            )
    elif character_id and not avatar_api_base:
        logger.warning(
            "llm.base_url empty; skip interaction-config for character_id=%s",
            character_id,
        )

    avatar_stream = await asyncio.get_event_loop().run_in_executor(
        None,
        create_avatar,
        session_config,
        state.model,
        session_avatar_data,
        sessionid,
    )
    if access_token:
        setattr(avatar_stream, "internal_access_token", access_token)
    state.add_session(sessionid, avatar_stream)
    return avatar_stream, session_config
