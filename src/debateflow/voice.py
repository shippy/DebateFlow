"""TTS wrapper — ElevenLabs (preferred) with OpenAI tts-1-hd fallback."""

from __future__ import annotations

import hashlib
import logging
import os
from itertools import combinations
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------

Provider = Literal["elevenlabs", "openai"]


def _elevenlabs_api_key() -> str | None:
    """Return ElevenLabs key if available."""
    return os.environ.get("DF_ELEVENLABS_API_KEY") or os.environ.get("ELEVENLABS_API_KEY")


def _openai_api_key() -> str | None:
    """Return OpenAI key if available."""
    return os.environ.get("OPENAI_API_KEY")


def get_provider() -> Provider:
    """Return the active TTS provider (ElevenLabs preferred, OpenAI fallback)."""
    if _elevenlabs_api_key():
        return "elevenlabs"
    if _openai_api_key():
        return "openai"
    raise ValueError(
        "No TTS API key found. Set DF_ELEVENLABS_API_KEY / ELEVENLABS_API_KEY "
        "or OPENAI_API_KEY in your environment."
    )


# ---------------------------------------------------------------------------
# ElevenLabs
# ---------------------------------------------------------------------------

def get_elevenlabs_client():
    """Return an ElevenLabs client."""
    from elevenlabs import ElevenLabs
    key = _elevenlabs_api_key()
    if not key:
        raise ValueError("No ElevenLabs API key found")
    return ElevenLabs(api_key=key)


ELEVENLABS_VOICE_POOL: list[dict[str, str]] = [
    {"voice_id": "JBFqnCBsd6RMkjVDRZzb", "name": "George"},
    {"voice_id": "TX3LPaxmHKxFdv7VOQHJ", "name": "Liam"},
    {"voice_id": "XB0fDUnXU5powFXDhCwa", "name": "Charlotte"},
    {"voice_id": "pFZP5JQG7iQjIQuC4Bku", "name": "Lily"},
    {"voice_id": "bIHbv24MWmeRgasZH58o", "name": "Will"},
    {"voice_id": "FGY2WhTYpPnrIDTdsKH5", "name": "Laura"},
]

# Keep backward-compat alias
DEFAULT_VOICE_POOL = ELEVENLABS_VOICE_POOL


def synthesize_turn_elevenlabs(text: str, voice_id: str, **kwargs) -> bytes:
    """Synthesize text to MP3 bytes via ElevenLabs.

    Optional kwargs are passed to the TTS convert call (e.g. stability, style).
    """
    client = get_elevenlabs_client()
    call_kwargs: dict = dict(
        voice_id=voice_id,
        text=text,
        model_id="eleven_turbo_v2_5",
        output_format="mp3_22050_32",
    )
    # Forward voice_settings-style overrides
    voice_settings = {}
    for k in ("stability", "similarity_boost", "style", "use_speaker_boost"):
        if k in kwargs:
            voice_settings[k] = kwargs[k]
    if voice_settings:
        call_kwargs["voice_settings"] = voice_settings

    audio_iter = client.text_to_speech.convert(**call_kwargs)
    return b"".join(chunk for chunk in audio_iter)


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

OPENAI_VOICE_POOL: list[dict[str, str]] = [
    {"voice_name": "alloy", "name": "Alloy"},
    {"voice_name": "echo", "name": "Echo"},
    {"voice_name": "fable", "name": "Fable"},
    {"voice_name": "onyx", "name": "Onyx"},
    {"voice_name": "nova", "name": "Nova"},
    {"voice_name": "shimmer", "name": "Shimmer"},
]


def synthesize_turn_openai(text: str, voice_name: str) -> bytes:
    """Synthesize text to MP3 bytes via OpenAI tts-1-hd."""
    from openai import OpenAI
    client = OpenAI(api_key=_openai_api_key())
    response = client.audio.speech.create(
        model="tts-1-hd",
        voice=voice_name,
        input=text,
        response_format="mp3",
    )
    return response.content


# ---------------------------------------------------------------------------
# Unified interface
# ---------------------------------------------------------------------------

def _all_distinct_pairs(pool: list[dict[str, str]]) -> list[tuple[dict[str, str], dict[str, str]]]:
    """Generate all ordered distinct pairs from the voice pool."""
    return list(combinations(pool, 2))


def get_voice_pool(provider: Provider | None = None) -> list[dict[str, str]]:
    """Return the voice pool for the given (or active) provider."""
    provider = provider or get_provider()
    if provider == "elevenlabs":
        return ELEVENLABS_VOICE_POOL
    return OPENAI_VOICE_POOL


def pick_voice_pair(
    debate_id: str, provider: Provider | None = None
) -> tuple[dict[str, str], dict[str, str]]:
    """Deterministic voice pair based on hash of debate_id.

    Returns (aff_voice, neg_voice) — always distinct voices.
    Uses the voice pool matching the active provider.
    """
    pool = get_voice_pool(provider)
    pairs = _all_distinct_pairs(pool)
    h = int(hashlib.sha256(debate_id.encode()).hexdigest(), 16)
    idx = h % len(pairs)
    return pairs[idx]


def synthesize_turn(text: str, voice_info: dict[str, str], **kwargs) -> bytes:
    """Synthesize a single turn, using ElevenLabs if available, else OpenAI.

    Args:
        text: The text to speak.
        voice_info: Dict from the voice pool — must contain either
                    ``voice_id`` (ElevenLabs) or ``voice_name`` (OpenAI).
        **kwargs: Extra settings forwarded to the ElevenLabs backend
                  (e.g. stability, style).
    """
    # Try ElevenLabs first
    if _elevenlabs_api_key() and "voice_id" in voice_info:
        try:
            return synthesize_turn_elevenlabs(text, voice_info["voice_id"], **kwargs)
        except Exception:
            logger.warning("ElevenLabs synthesis failed, falling back to OpenAI", exc_info=True)
            # Fall through to OpenAI if possible
            if not _openai_api_key():
                raise

    # OpenAI fallback
    if _openai_api_key():
        # Resolve voice name: explicit voice_name, or map ElevenLabs name → OpenAI
        vname = voice_info.get("voice_name")
        if not vname:
            # Fallback mapping: pick an OpenAI voice by index from the ElevenLabs pool
            el_names = [v["name"] for v in ELEVENLABS_VOICE_POOL]
            oa_names = [v["voice_name"] for v in OPENAI_VOICE_POOL]
            try:
                idx = el_names.index(voice_info.get("name", ""))
            except ValueError:
                idx = 0
            vname = oa_names[idx % len(oa_names)]
        return synthesize_turn_openai(text, vname)

    raise ValueError("No TTS provider available — set an API key.")


# ---------------------------------------------------------------------------
# Full-debate synthesis
# ---------------------------------------------------------------------------

def synthesize_debate(
    debate: dict,
    output_dir: str,
    **kwargs,
) -> dict[str, str]:
    """Synthesize all 4 turns of a debate to MP3 files.

    Args:
        debate: Raw debate dict (as loaded from JSON).
        output_dir: Base directory for audio output.
        **kwargs: Extra settings forwarded to ``synthesize_turn``
                  (e.g. stability, style).

    Returns:
        Mapping ``turn_1``..``turn_4`` → absolute MP3 file paths.
    """
    # Extract debate_id (handle both flat and nested metadata layouts)
    debate_id: str = debate.get("debate_id") or debate["metadata"]["debate_id"]
    turns: list[dict] = debate["turns"]

    if len(turns) != 4:
        raise ValueError(f"Expected 4 turns, got {len(turns)}")

    provider = get_provider()
    aff_voice, neg_voice = pick_voice_pair(debate_id, provider)

    debate_dir = Path(output_dir) / debate_id
    debate_dir.mkdir(parents=True, exist_ok=True)

    result: dict[str, str] = {}

    for i, turn in enumerate(turns, start=1):
        speaker = turn["speaker"].lower()
        voice = aff_voice if speaker == "aff" else neg_voice

        mp3_path = debate_dir / f"turn_{i}_{speaker}.mp3"

        if mp3_path.exists() and mp3_path.stat().st_size > 0:
            logger.info("Using cached audio: %s", mp3_path)
        else:
            logger.info("Synthesizing turn %d (%s) for debate %s", i, speaker, debate_id)
            audio_bytes = synthesize_turn(turn["text"], voice, **kwargs)
            mp3_path.write_bytes(audio_bytes)

        result[f"turn_{i}"] = str(mp3_path)

    return result
